import os
from pathlib import Path
import re
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_start_cmd_is_the_single_owner_launcher():
    launcher = (ROOT / 'START.cmd').read_text(encoding='utf-8')
    common = (ROOT / 'scripts' / 'windows' / 'workstation-common.ps1').read_text(encoding='utf-8')
    worker = (ROOT / 'scripts' / 'windows' / 'start-workstation.ps1').read_text(encoding='utf-8')

    assert 'scripts\\windows\\start-workstation.ps1' in launcher
    assert '$env:APP_PROFILE = "review"' in common
    assert '$env:MODEL_RUNTIME = "remote"' in common
    assert '$env:HOST = "127.0.0.1"' in common
    assert '$env:PORT = "8000"' in common
    assert '$env:WORKERS = "1"' in common
    assert 'Get-Sha256Hex' in common
    assert 'Get-FileHash' not in common
    assert 'http://127.0.0.1:8000/app/' in worker
    assert 'Start-Process' in worker
    assert 'Ensure-FrontendBuild -AllowInstall' not in worker
    assert 'Ensure-FrontendBuild | Out-Null' in worker
    assert 'DR_DEMO_FOLDER' not in launcher
    assert 'IMG_01.jpg' not in launcher
    assert 'IMG_02.jpg' not in launcher
    assert 'IMG_03.jpg' not in launcher
    assert not (ROOT / 'START_DEMO.cmd').exists()
    assert (ROOT / 'OPEN_APP.cmd').exists()
    assert (ROOT / 'STOP.cmd').exists()
    assert (ROOT / 'SETUP.cmd').exists()


@pytest.mark.skipif(os.name != 'nt', reason='Windows launcher coverage')
def test_windows_powershell_can_compute_frontend_signature_without_get_file_hash():
    command = (
        ". 'scripts/windows/workstation-common.ps1'; "
        "$source = Get-FrontendSourceSignature; "
        "$dependency = Get-FrontendDependencySignature; "
        "if ($source -notmatch '^[0-9a-f]{64}$' -or $dependency -notmatch '^[0-9a-f]{64}$') { exit 1 }; "
        "Write-Output $source; Write-Output $dependency"
    )
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert all(re.fullmatch(r'[0-9a-f]{64}', line) for line in result.stdout.splitlines())
    assert len(result.stdout.splitlines()) == 2
