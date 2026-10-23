"""Pure PowerShell/fake-process Docker startup controls; no Docker is executed."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/windows/release-docker.ps1"


def run_fake(tmp_path, scenario):
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is unavailable")
    fake_desktop = tmp_path / "Docker Desktop.exe"
    fake_desktop.write_text("synthetic placeholder; never executed", encoding="utf-8")
    escaped_script = str(SCRIPT).replace("'", "''")
    escaped_desktop = str(fake_desktop).replace("'", "''")
    program = f"""
$ErrorActionPreference='Stop'
. '{escaped_script}'
$env:DOCKER_HOST=$null
$env:DOCKER_CONTEXT=$null
$script:Tick=0
$script:ProbeCalls=@()
$script:Launches=@()
$script:EngineIndex=0
$script:Scenario='{scenario}'
function Get-ReleaseDockerElapsedMilliseconds {{ param($Watch) return $script:Tick }}
function Start-Sleep {{ param($Milliseconds) $script:Tick += $Milliseconds }}
function Get-ReleaseDockerDesktopPath {{
    if ($script:Scenario -eq 'missing_desktop') {{ return 'Z:\\synthetic-missing\\Docker Desktop.exe' }}
    return '{escaped_desktop}'
}}
function Test-ReleaseDockerDesktopRunning {{ return $script:Scenario -eq 'already_starting' }}
function Start-Process {{
    param($FilePath,$WindowStyle,[switch]$PassThru,$ErrorAction)
    $script:Launches += [pscustomobject]@{{Path=$FilePath; WindowStyle=$WindowStyle}}
    if ($script:Scenario -eq 'start_denied') {{ throw 'synthetic_secret_must_not_leak' }}
    return [pscustomobject]@{{Id=42}}
}}
function Invoke-ReleaseDockerProbe {{
    param($Docker,$Operation,$Endpoint,$TimeoutMilliseconds)
    $script:ProbeCalls += [pscustomobject]@{{Operation=$Operation; Timeout=$TimeoutMilliseconds; Endpoint=$Endpoint}}
    $script:Tick += [Math]::Min(100,$TimeoutMilliseconds)
    if ($Operation -eq 'Context') {{
        if ($script:Scenario -eq 'remote_context') {{
            return [pscustomobject]@{{Succeeded=$true; Output='ssh://synthetic_secret_must_not_leak@unapproved'; TimedOut=$false}}
        }}
        if ($script:Scenario -eq 'context_failure') {{
            return [pscustomobject]@{{Succeeded=$false; Output='synthetic_secret_must_not_leak'; TimedOut=$false}}
        }}
        return [pscustomobject]@{{Succeeded=$true; Output='npipe:////./pipe/dockerDesktopLinuxEngine'; TimedOut=$false}}
    }}
    $script:EngineIndex += 1
    if ($script:Scenario -eq 'windows_engine') {{
        return [pscustomobject]@{{Succeeded=$true; Output='windows'; TimedOut=$false}}
    }}
    $ready = $script:Scenario -eq 'ready' -or (($script:Scenario -in @('start','already_starting')) -and $script:EngineIndex -gt 1)
    return [pscustomobject]@{{Succeeded=$ready; Output=$(if ($ready) {{'linux'}} else {{'synthetic_secret_must_not_leak'}}); TimedOut=$false}}
}}
if ($script:Scenario -eq 'remote_environment') {{ $env:DOCKER_HOST='tcp://synthetic_secret_must_not_leak@unapproved:2375' }}
$arguments=@{{Docker='synthetic-docker.exe'; TimeoutSeconds=1; PollMilliseconds=50}}
if ($script:Scenario -eq 'external') {{ $arguments.ManagedLocal=$false }}
if ($script:Scenario -eq 'missing_client') {{ $arguments.Docker='' }}
$status=Ensure-ReleaseDockerEngine @arguments
[pscustomobject]@{{Status=$status; Probes=@($script:ProbeCalls); Launches=@($script:Launches); Elapsed=$script:Tick}} | ConvertTo-Json -Depth 8 -Compress
"""
    path = tmp_path / "fake-docker-control.ps1"
    path.write_text(program, encoding="utf-8")
    result = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-File", str(path)],
                            capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stderr
    assert "synthetic_secret_must_not_leak" not in result.stdout
    return json.loads(result.stdout)


def test_ready_engine_does_not_launch_desktop(tmp_path):
    result = run_fake(tmp_path, "ready")
    assert result["Status"]["Ready"] is True
    assert result["Status"]["Started"] is False
    assert result["Launches"] == []
    assert [item["Operation"] for item in result["Probes"]] == ["Context", "Engine"]


def test_installed_desktop_starts_hidden_once_and_waits_until_ready(tmp_path):
    result = run_fake(tmp_path, "start")
    assert result["Status"]["Ready"] is True
    assert result["Status"]["Started"] is True
    assert len(result["Launches"]) == 1
    assert result["Launches"][0]["WindowStyle"] == "Hidden"
    assert result["Launches"][0]["Path"] == str(tmp_path / "Docker Desktop.exe")
    assert len([p for p in result["Probes"] if p["Operation"] == "Engine"]) == 2


def test_existing_desktop_startup_does_not_launch_duplicate(tmp_path):
    result = run_fake(tmp_path, "already_starting")
    assert result["Status"]["Ready"] is True
    assert result["Status"]["Started"] is False
    assert result["Launches"] == []


@pytest.mark.parametrize("scenario,status", [
    ("missing_client", "CLIENT_MISSING"), ("missing_desktop", "DESKTOP_NOT_INSTALLED"),
    ("start_denied", "DESKTOP_START_DENIED"), ("timeout", "STARTUP_TIMEOUT"),
    ("remote_context", "LOCAL_ENDPOINT_REQUIRED"), ("remote_environment", "LOCAL_ENDPOINT_REQUIRED"),
    ("context_failure", "LOCAL_ENDPOINT_REQUIRED"), ("windows_engine", "LINUX_ENGINE_REQUIRED"),
])
def test_failures_are_bounded_actionable_and_secret_safe(tmp_path, scenario, status):
    result = run_fake(tmp_path, scenario)
    assert result["Status"]["Ready"] is False
    assert result["Status"]["Status"] == status
    assert result["Status"]["Detail"]
    assert result["Elapsed"] <= 1000
    assert all(0 < probe["Timeout"] <= 1000 for probe in result["Probes"])
    assert len(result["Launches"]) <= 1
    if scenario.startswith("remote") or scenario == "context_failure":
        assert not any(probe["Operation"] == "Engine" for probe in result["Probes"])
        assert result["Launches"] == []


def test_external_postgres_never_probes_or_launches_docker(tmp_path):
    result = run_fake(tmp_path, "external")
    assert result["Status"]["Status"] == "NOT_REQUIRED"
    assert result["Status"]["Required"] is False
    assert result["Launches"] == result["Probes"] == []


def test_helper_parses_without_running_any_function():
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell parser is unavailable")
    escaped = str(SCRIPT).replace("'", "''")
    result = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command",
                             f"$null=[scriptblock]::Create([IO.File]::ReadAllText('{escaped}')); exit 0"],
                            capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(os.name != "nt", reason="Windows native fake executable boundary")
def test_native_probe_drains_output_hides_stderr_and_bounds_owned_child(tmp_path):
    powershell = shutil.which("powershell")
    if powershell is None:
        pytest.skip("Windows PowerShell compiler is unavailable")
    script = str(SCRIPT).replace("'", "''")
    executable = str(tmp_path / "SyntheticDockerProbe.exe").replace("'", "''")
    source = """
public class SyntheticDockerProbe {
    public static int Main(string[] args) {
        if (System.Environment.GetEnvironmentVariable("SYNTHETIC_PROBE_HANG") == "1") {
            System.Threading.Thread.Sleep(30000);
        }
        System.Console.Error.WriteLine("synthetic_secret_must_not_leak");
        System.Console.WriteLine(System.Array.IndexOf(args, "context") >= 0
            ? "npipe:////./pipe/dockerDesktopLinuxEngine" : "linux");
        return 0;
    }
}
"""
    program = f"""
$ErrorActionPreference='Stop'
. '{script}'
Add-Type -TypeDefinition @'
{source}
'@ -OutputAssembly '{executable}' -OutputType ConsoleApplication
$context=Invoke-ReleaseDockerProbe -Docker '{executable}' -Operation Context -TimeoutMilliseconds 2000
$engine=Invoke-ReleaseDockerProbe -Docker '{executable}' -Operation Engine -Endpoint 'npipe:////./pipe/dockerDesktopLinuxEngine' -TimeoutMilliseconds 2000
$env:SYNTHETIC_PROBE_HANG='1'
$watch=[Diagnostics.Stopwatch]::StartNew()
$timeout=Invoke-ReleaseDockerProbe -Docker '{executable}' -Operation Context -TimeoutMilliseconds 100
$elapsed=$watch.ElapsedMilliseconds
[pscustomobject]@{{Context=$context; Engine=$engine; Timeout=$timeout; Elapsed=$elapsed}} | ConvertTo-Json -Depth 5 -Compress
"""
    path = tmp_path / "native-fake-probe.ps1"
    path.write_text(program, encoding="utf-8")
    result = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-File", str(path)],
                            capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stderr
    assert "synthetic_secret_must_not_leak" not in result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["Context"]["Succeeded"] is True
    assert data["Context"]["Output"] == "npipe:////./pipe/dockerDesktopLinuxEngine"
    assert data["Engine"]["Output"] == "linux"
    assert data["Timeout"]["TimedOut"] is True
    assert data["Timeout"]["Succeeded"] is False
    assert data["Elapsed"] < 2000
