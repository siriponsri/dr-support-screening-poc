import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_no_code_launchers_have_expected_roles():
    assert (ROOT / "FIRST_RUN.bat").read_text(encoding="utf-8").find("release-first-run.ps1") >= 0
    assert (ROOT / "START_DR_SCREENING.bat").read_text(encoding="utf-8").find("release-start.ps1") >= 0
    assert (ROOT / "STOP_DR_SCREENING.bat").read_text(encoding="utf-8").find("release-stop.ps1") >= 0
    assert (ROOT / "CHECK_SYSTEM.bat").read_text(encoding="utf-8").find("release-check-system.ps1") >= 0
    start = (ROOT / "scripts/windows/release-start.ps1").read_text(encoding="utf-8")
    assert "npm" not in start.lower()
    assert "Test-ReleaseFrontend" in start
    assert "127.0.0.1:8000/app/" in start


def test_release_builder_and_model_identity_are_contract_only():
    builder = (ROOT / "scripts/release/build_release.py").read_text(encoding="utf-8")
    assert "workstation_allowlist" in builder
    assert "model_api_allowlist" in builder
    assert '"scripts/model-server"' not in builder
    assert "weights_included" in builder
    identity = json.loads((ROOT / "scripts/release/model_artifacts.json").read_text(encoding="utf-8"))
    assert identity == {
        "model_id": "uspec-uwf-grading",
        "artifact": "grading_state.pt",
        "expected_bytes": 1213535294,
        "expected_sha256": "8f07eb11859f638faee368a56c7c532ca946fee320f92f030a0cf25c63b769ac",
        "status": "IDENTITY_ONLY_NOT_ACQUIRED",
        "policy": "Do not download, include, load, or infer with this artifact in the release package.",
    }


def test_model_api_helpers_remain_disabled():
    start = (ROOT / "scripts/release/model-api-start.sh").read_text(encoding="utf-8")
    health = (ROOT / "scripts/release/model-api-health.sh").read_text(encoding="utf-8")
    check = (ROOT / "scripts/release/model-api-check.sh").read_text(encoding="utf-8")
    verify = (ROOT / "scripts/release/model-api-verify.sh").read_text(encoding="utf-8")
    assert "BLOCKED" in start
    assert "NOT_RUN" in health
    assert "P3.1" in start
    assert "NOT_RUN" in check
    assert "NOT_RUN" in verify


def test_builder_rejects_missing_prebuilt_frontend(tmp_path, monkeypatch):
    import scripts.release.build_release as builder

    monkeypatch.setattr(builder, "ROOT", tmp_path)
    try:
        builder.package("workstation", "test", tmp_path / "out", "abc")
    except SystemExit as exc:
        assert "frontend/dist" in str(exc)
    else:
        raise AssertionError("missing prebuilt frontend must block workstation packaging")


def test_gitignore_excludes_release_runtime():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "local-state/release/" in text
    assert "*.pt" in text
    assert ".env" in text
