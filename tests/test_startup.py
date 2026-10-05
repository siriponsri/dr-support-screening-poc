import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_release_launchers_are_the_single_workstation_path():
    launchers = {
        "FIRST_RUN.bat": "release-first-run.ps1",
        "START_DR_SCREENING.bat": "release-start.ps1",
        "STOP_DR_SCREENING.bat": "release-stop.ps1",
        "CHECK_SYSTEM.bat": "release-check-system.ps1",
    }
    for name, script in launchers.items():
        launcher = ROOT / name
        assert launcher.exists()
        assert script in launcher.read_text(encoding="utf-8")

    common = (ROOT / "scripts/windows/release-common.ps1").read_text(encoding="utf-8")
    start = (ROOT / "scripts/windows/release-start.ps1").read_text(encoding="utf-8")
    stop = (ROOT / "scripts/windows/release-stop.ps1").read_text(encoding="utf-8")
    assert '$env:APP_PROFILE = "review"' in common
    assert '$env:MODEL_RUNTIME = "remote"' in common
    assert '$env:HOST = "127.0.0.1"' in common
    assert '$env:PORT = "8000"' in common
    assert '$env:WORKERS = "1"' in common
    assert "Test-ReleaseFrontend" in start
    assert "npm" not in start.lower()
    assert "127.0.0.1:8000/app/" in start
    assert "Test-ReleasePostgres" in common
    assert "DR_SUPPORT_DATABASE_URL" in common
    assert "SELECT 1" in common
    assert "Test-ReleasePostgres" in start
    assert "Test-ReleasePostgres" in (ROOT / "scripts/windows/release-first-run.ps1").read_text(encoding="utf-8")
    assert "Test-ReleasePostgres" in (ROOT / "scripts/windows/release-check-system.ps1").read_text(encoding="utf-8")
    assert "Stop-Process" in stop

    retired = ("SETUP.cmd", "START.cmd", "OPEN_APP.cmd", "STOP.cmd")
    assert all(not (ROOT / name).exists() for name in retired)
    retired_helpers = (
        "bootstrap.ps1",
        "start-workstation.ps1",
        "open-workstation.ps1",
        "stop-workstation.ps1",
        "workstation-common.ps1",
    )
    assert all(not (ROOT / "scripts/windows" / name).exists() for name in retired_helpers)


def test_system_check_marks_managed_unhealthy_process_not_ready():
    powershell = shutil.which("powershell")
    if not powershell:
        pytest.skip("Windows PowerShell is unavailable")
    probe = ROOT / "local-state" / "release" / "test-process-readiness.ps1"
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text(
        ". (Join-Path $PSScriptRoot '..\\..\\scripts\\windows\\release-common.ps1')\n"
        "function Test-ReleaseManagedProcess([int] $ProcessId) { return $true }\n"
        "function Test-ReleaseHealth { return $false }\n"
        "$status = Get-ReleaseProcessStatus ([pscustomobject]@{ pid = 123 })\n"
        "if ($status.State -ne 'UNHEALTHY' -or $status.Ready) { exit 1 }\n"
        "function Test-ReleaseManagedProcess([int] $ProcessId) { return $false }\n"
        "$stopped = Get-ReleaseProcessStatus ([pscustomobject]@{ pid = 123 })\n"
        "if ($stopped.State -ne 'STOPPED' -or -not $stopped.Ready) { exit 2 }\n",
        encoding="utf-8",
    )
    try:
        result = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(probe)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr or result.stdout
    finally:
        probe.unlink(missing_ok=True)
