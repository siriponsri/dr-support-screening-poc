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


def _scan(client):
    assert client.post("/v1/admissions/scan").status_code == 200


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_manual_image_type_and_first_admission_time_both_survive_a_rescan(tmp_path, monkeypatch):
    client, folder = _workspace_client(tmp_path, monkeypatch)
    _write_image(folder / "fundus.png", fundus=True)
    _scan(client)
    image_id = _sha(folder / "fundus.png")
    case = client.app.state.store.get(image_id)
    case["admission"] = {**case["admission"], "retinal_modality": "UWF", "retinal_modality_state": "RESOLVED",
                         "retinal_modality_method": "MANUAL"}
    client.app.state.store.put(case)
    first = client.app.state.store.get(image_id)["admission"]
    _scan(client)
    again = client.app.state.store.get(image_id)["admission"]
    assert again["retinal_modality"] == "UWF" and again["retinal_modality_method"] == "MANUAL"
    assert again["created_at"] == first["created_at"]


def test_missing_then_returning_source_keeps_its_first_admission_time(tmp_path, monkeypatch):
    client, folder = _workspace_client(tmp_path, monkeypatch)
    path = folder / "fundus.png"
    _write_image(path, fundus=True)
    _scan(client)
    image_id = _sha(path)
    created = client.app.state.store.get(image_id)["admission"]["created_at"]
    parked = tmp_path / "parked.png"
    path.rename(parked)
    _scan(client)
    assert client.app.state.store.get(image_id)["admission"]["integrity_status"] == "SOURCE_MISSING"
    parked.rename(path)
    _scan(client)
    returned = client.app.state.store.get(image_id)["admission"]
    assert returned["integrity_status"] == "OK"
    assert returned["created_at"] == created


def test_source_change_still_names_the_latest_version_seen_at_that_name(tmp_path, monkeypatch):
    client, folder = _workspace_client(tmp_path, monkeypatch)
    path = folder / "fundus.png"
    _write_image(path, fundus=True, size=(400, 300))
    _scan(client)
    first = _sha(path)
    _write_image(path, fundus=True, size=(420, 310))
    _scan(client)
    second = _sha(path)
    _scan(client)  # An unchanged rescan must not reorder which version is the latest.
    assert first != second
    _write_image(path, fundus=True, size=(440, 320))
    _scan(client)
    third = client.app.state.store.get(_sha(path))["admission"]
    assert third["integrity_status"] == "SOURCE_CHANGED"
    assert third["integrity"]["previous_source_sha256"] == second
