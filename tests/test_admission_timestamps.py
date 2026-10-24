"""Admission timestamps survive rescans and restarts (owner-approved fix, 2026-10-24)."""
import hashlib

from dr_support.services.admission import preserve_admission_timestamps
from test_admission import _workspace_client, _write_image


def test_unchanged_rescan_keeps_both_timestamps():
    saved = {"image_id": "a", "quality_state": "NOT_EVALUATED", "created_at": "t0", "updated_at": "t1"}
    record = {**saved, "created_at": "t9", "updated_at": "t9"}
    assert preserve_admission_timestamps(saved, record) == saved


def test_changed_content_keeps_first_admission_time_and_moves_updated_at():
    saved = {"image_id": "a", "integrity_status": "OK", "created_at": "t0", "updated_at": "t1"}
    record = {"image_id": "a", "integrity_status": "SOURCE_CHANGED", "created_at": "t9", "updated_at": "t9"}
    result = preserve_admission_timestamps(saved, record)
    assert result == {**record, "created_at": "t0", "updated_at": "t9"}


def test_new_source_keeps_its_own_timestamps():
    record = {"image_id": "a", "created_at": "t9", "updated_at": "t9"}
    assert preserve_admission_timestamps(None, record) is record


def test_rescan_through_the_app_keeps_created_at_and_revision(tmp_path, monkeypatch):
    client, folder = _workspace_client(tmp_path, monkeypatch)
    _write_image(folder / "fundus.png", fundus=True)
    assert client.post("/v1/admissions/scan").status_code == 200
    image_id = hashlib.sha256((folder / "fundus.png").read_bytes()).hexdigest()
    first = client.app.state.store.get(image_id)
    assert client.post("/v1/admissions/scan").status_code == 200
    again = client.app.state.store.get(image_id)
    assert again["admission"] == first["admission"]
    assert again["revision"] == first["revision"]
    assert again.get("admission_history") == first.get("admission_history")
