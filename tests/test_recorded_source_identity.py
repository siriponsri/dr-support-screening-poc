"""Recorded source identity amendment, Part A: write-once projection at case creation."""
import hashlib

import pytest

from dr_support.services.source_identity import (
    RECORDED_KEYS,
    admitted_source_hash,
    record_source_identity_on_creation,
)
from dr_support.store import apply_case_defaults, new_case
from test_admission import _workspace_client, _write_image
from test_prism_preview_binding import prepare, rig  # noqa: F401

DIGEST = "1" * 64


def admission(**changes):
    record = {"image_id": DIGEST, "source_sha256": DIGEST, "integrity_status": "OK",
              "integrity": {"status": "OK", "changed_sources": []},
              "source_metadata": {"source_sha256": DIGEST, "integrity_status": "OK"}}
    record.update(changes)
    return record


def stored(client, image_id):
    return client.app.state.store.get(image_id)


def scan_one(tmp_path, monkeypatch):
    client, folder = _workspace_client(tmp_path, monkeypatch)
    _write_image(folder / "fundus.png", fundus=True)
    assert client.post("/v1/admissions/scan").status_code == 200
    image_id = hashlib.sha256((folder / "fundus.png").read_bytes()).hexdigest()
    return client, image_id


def test_new_admission_records_the_admission_hash_once(tmp_path, monkeypatch):
    client, image_id = scan_one(tmp_path, monkeypatch)
    case = stored(client, image_id)
    assert case["admission"]["source_sha256"] == image_id
    assert case["source_sha256"] == case["image_sha256"] == image_id


def test_existing_case_without_projection_is_never_filled_by_rescan(tmp_path, monkeypatch):
    client, image_id = scan_one(tmp_path, monkeypatch)
    case = stored(client, image_id)
    for key in RECORDED_KEYS:
        del case[key]
    client.app.state.store.put(case)  # A case admitted before the amendment.
    assert client.post("/v1/admissions/scan").status_code == 200
    case = stored(client, image_id)
    assert case["admission"] is not None
    assert all(key not in case for key in RECORDED_KEYS)


def test_manual_admission_review_never_changes_the_projection(tmp_path, monkeypatch):
    client, image_id = scan_one(tmp_path, monkeypatch)
    revision = client.get(f"/v1/cases/{image_id}").json()["revision"]
    response = client.post(f"/v1/cases/{image_id}/admission", json={
        "revision": revision, "reviewer": "TEST_ONLY", "action": "QUALITY_INADEQUATE"})
    assert response.status_code == 200
    case = stored(client, image_id)
    assert case["admission"]["quality_state"] == "UNGRADABLE"
    assert case["source_sha256"] == case["image_sha256"] == image_id


def test_creation_projection_writes_both_keys_from_the_admission_record():
    case = new_case(DIGEST)
    assert record_source_identity_on_creation(case, admission()) is True
    assert case["source_sha256"] == case["image_sha256"] == DIGEST


@pytest.mark.parametrize("record", [
    admission(source_sha256=None),
    admission(source_sha256="2" * 64, source_metadata=None),
    admission(source_sha256="F" * 64, image_id="F" * 64),
    admission(integrity_status="SOURCE_MISSING"),
    admission(integrity={"status": "SOURCE_CHANGED", "changed_sources": []}),
    admission(integrity={"status": "OK", "changed_sources": [{"filename": "x"}]}),
    admission(source_metadata={"source_sha256": "2" * 64}),
    admission(source_metadata={"source_sha256": DIGEST, "integrity_status": "SOURCE_MISSING"}),
])
def test_unsound_admission_records_write_nothing(record):
    case = new_case(DIGEST)
    assert record_source_identity_on_creation(case, record) is False
    assert all(key not in case for key in RECORDED_KEYS)


@pytest.mark.parametrize("existing", [
    {"revision": 1},
    {"admission": admission()},
    {"admission_history": [{"action": "AUTOMATIC_ADMISSION"}]},
    {"source_sha256": "2" * 64},
    {"image_sha256": DIGEST},
])
def test_only_a_case_being_created_and_never_an_existing_value(existing):
    case = {**new_case(DIGEST), **existing}
    before = dict(case)
    assert record_source_identity_on_creation(case, admission()) is False
    assert case == before


def test_duplicate_content_is_sound_and_metadata_may_be_absent():
    record = admission(integrity_status="DUPLICATE_CONTENT", source_metadata=None,
                       integrity={"status": "DUPLICATE_CONTENT", "changed_sources": []})
    assert admitted_source_hash({"image_id": DIGEST}, record) == DIGEST


def test_defaults_never_manufacture_a_recorded_identity():
    assert all(key not in new_case(DIGEST) for key in RECORDED_KEYS)
    assert all(key not in apply_case_defaults({"image_id": DIGEST}) for key in RECORDED_KEYS)


def test_created_projection_satisfies_the_preview_attestation_gate(rig):  # noqa: F811
    for key in RECORDED_KEYS:
        del rig.store.case[key]
    refused = rig.client.post("/v1/cases/fixture/prism-input-preview", json={"revision": 0})
    assert refused.status_code == 503 and "Recorded source attestation" in refused.json()["detail"]
    created = new_case(rig.image.sha256)
    assert record_source_identity_on_creation(created, rig.app.state.admissions["fixture"])
    rig.store.case.update({key: created[key] for key in RECORDED_KEYS})
    assert prepare(rig)["source_sha256"] == rig.image.sha256
