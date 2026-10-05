from pathlib import Path


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
