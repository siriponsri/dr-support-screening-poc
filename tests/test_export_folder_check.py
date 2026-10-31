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


def set_manifest_note(folder, value):
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    manifest["note"] = value
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


@pytest.mark.parametrize("leak", ["/etc", "/ผู้ป่วย/image.png", "/患者/image.png", "path:/home/u/a.png",
                                  "file:///home/u/a.png", "~/a.png", "//server/share/a.png", "(/data/a.png)"])
def test_audit_counterexample_paths_fail(exported, leak):  # docs/audit/20261031-local-web-real-api/CHECKER_PROBES.json
    set_manifest_note(exported, leak)
    assert check(exported)["checks"]["no_absolute_paths"] is False


@pytest.mark.parametrize("value", [r"images\sub\a.png", "https://example.org/a/b", "s3://bucket/key",
                                   "2026-10-31T17:00:00+00:00", "grade 2/4", "HE/EX"])
def test_ordinary_values_are_not_paths(exported, value):
    set_manifest_note(exported, value)
    assert check(exported)["checks"]["no_absolute_paths"] is True


def test_a_surplus_csv_cell_fails_even_with_a_matching_hash(exported):
    import hashlib
    path = exported / "images.csv"
    lines = path.read_text(encoding="utf-8").split("\n")
    lines[1] = lines[1] + ",C:/sample/image.png"
    path.write_text("\n".join(lines), encoding="utf-8", newline="")
    manifest = json.loads((exported / "manifest.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest["file_sha256"]["images.csv"] = manifest["images_csv_sha256"] = digest
    (exported / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    report = check(exported)
    assert report["checks"]["file_hashes"] is True
    assert report["checks"]["row_widths"] is False and report["checks"]["no_absolute_paths"] is False
    assert report["status"] == "FAIL"


def test_a_missing_csv_cell_fails(exported):
    path = exported / "images.csv"
    lines = path.read_text(encoding="utf-8").split("\n")
    lines[1] = lines[1].rsplit(",", 1)[0]
    path.write_text("\n".join(lines), encoding="utf-8", newline="")
    assert check(exported)["checks"]["row_widths"] is False


def test_an_unreadable_folder_fails_without_printing_its_path(tmp_path, monkeypatch, capsys):
    from pathlib import Path

    def deny(self):
        raise PermissionError(13, "denied", str(self))
    monkeypatch.setattr(Path, "iterdir", deny)
    folder = tmp_path / "dataset-export-x"
    folder.mkdir()
    assert main([str(folder)]) == 1
    printed = capsys.readouterr().out
    assert '"readable": false' in printed and str(tmp_path) not in printed


@pytest.mark.parametrize("leak", [r"\Users\User\img.jpg", "C:file.jpg", "see /home/someone/a.png"])
def test_rooted_and_drive_relative_windows_paths_fail(exported, leak):  # Review 2026-10-31 counterexamples
    set_manifest_note(exported, leak)
    assert check(exported)["checks"]["no_absolute_paths"] is False


def test_plain_lesion_text_with_a_slash_is_not_a_path(exported):
    set_manifest_note(exported, "MA /HE")
    assert check(exported)["checks"]["no_absolute_paths"] is True


def rewrite(path, change):
    import csv
    import io
    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8"), newline="")))
    change(rows)
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\r\n").writerows(rows)
    path.write_text(buffer.getvalue(), encoding="utf-8", newline="")


def test_a_training_ready_finding_on_a_test_only_image_fails(exported):
    def test_only(rows):
        rows[1][rows[0].index("label_class")] = "TEST_ONLY"

    def ready(rows):
        rows[1][rows[0].index("include_in_training")] = "True"
    rewrite(exported / "images.csv", test_only)
    rewrite(exported / "annotations.csv", ready)
    report = check(exported)
    assert report["checks"]["ready_annotations_on_ready_images"] is False and report["status"] == "FAIL"


def test_another_boolean_spelling_cannot_hide_a_training_ready_row(exported):
    def spell(rows):
        rows[1][rows[0].index("include_in_training")] = "true"
    rewrite(exported / "images.csv", spell)
    assert check(exported)["checks"]["boolean_cells"] is False


def test_the_lesion_ready_annotation_count_must_match(exported):
    manifest = json.loads((exported / "manifest.json").read_text(encoding="utf-8"))
    manifest["lesion_ready_annotation_count"] = manifest["lesion_ready_annotation_count"] + 1
    (exported / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert check(exported)["checks"]["ready_counts_match"] is False
