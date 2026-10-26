"""AC-09 export folder check on a synthetic workspace export; no hospital data or network."""
import json

import pytest

from scripts.qa.check_export_folder import check, main
from test_dataset import _human_annotations, _workspace_client


@pytest.fixture
def exported(tmp_path):
    app, client, output_folder = _workspace_client(tmp_path)
    assert client.post("/v1/infer/global", json={"image_id": "SYNTH_001", "model_id": "mock-global"}).status_code == 200
    assert client.post("/v1/infer/lesion-roi", json={"image_id": "SYNTH_001", "model_id": "mock-lesion"}).status_code == 200
    case = client.get("/v1/cases/SYNTH_001").json()
    saved = client.put("/v1/cases/SYNTH_001/annotations", json=_human_annotations(case["revision"]))
    reviewed = client.post("/v1/cases/SYNTH_001/review", json={
        "revision": saved.json()["revision"], "action": "CORRECT_GRADE", "reviewer": "Dataset clinician", "grade": 3})
    assert reviewed.status_code == 200
    export = client.post("/v1/dataset/export")
    assert export.status_code == 200
    return output_folder / export.json()["directory_name"]


def test_a_synthetic_export_passes_every_check(exported, capsys):
    report = check(exported)
    assert report["status"] == "PASS", report
    assert report["counts"]["images"] == 1 and report["counts"]["annotations"] == 5
    assert main([str(exported)]) == 0
    printed = capsys.readouterr().out
    assert "SYNTH_001" not in printed and "Dataset clinician" not in printed  # Counts and check names only.


def test_a_changed_csv_fails_the_hash_check(exported):
    path = exported / "images.csv"
    path.write_bytes(path.read_bytes() + b"\n")
    report = check(exported)
    assert report["status"] == "FAIL" and report["checks"]["file_hashes"] is False


@pytest.mark.parametrize("leak", ["C:\\Users\\someone\\input\\a.png", "/home/someone/input/a.png",
                                  "\\\\fileserver\\share\\a.png"])
def test_an_absolute_local_path_fails(exported, leak):
    manifest = json.loads((exported / "manifest.json").read_text(encoding="utf-8"))
    manifest["note"] = leak
    (exported / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert check(exported)["checks"]["no_absolute_paths"] is False


def test_a_training_ready_test_only_row_fails(exported):
    path = exported / "images.csv"
    text = path.read_text(encoding="utf-8").replace(",CLINICIAN,", ",TEST_ONLY,", 1)
    path.write_text(text, encoding="utf-8", newline="")
    report = check(exported)
    assert report["checks"]["test_only_not_training_ready"] is False and report["status"] == "FAIL"


def test_an_extra_or_missing_file_fails(exported):
    (exported / "notes.txt").write_text("x", encoding="utf-8")
    assert check(exported) == {"status": "FAIL", "checks": {"exact_files": False}, "counts": {}}
    (exported / "notes.txt").unlink()
    (exported / "annotations.csv").unlink()
    assert check(exported)["status"] == "FAIL"


def test_the_check_never_writes(exported):
    before = {path.name: (path.stat().st_mtime_ns, path.read_bytes()) for path in exported.iterdir()}
    check(exported)
    assert {path.name: (path.stat().st_mtime_ns, path.read_bytes()) for path in exported.iterdir()} == before
