from pathlib import Path


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
