"""Owner-approved hospital key round-trip and presentation-only regression checks."""

import copy

import pytest
from fastapi.testclient import TestClient

from dr_support.api import create_app
from dr_support.images import BridgeImage, synthetic_image
from dr_support.services.admission import legacy_admission
from dr_support.services.patient_presentation import DISPLAY_INDICES, hospital_patient_label
from dr_support.store import Store


KEY = "HOSPITAL-" + "A1" * 12
OTHER = "HOSPITAL-" + "B2" * 12


def hospital_client(tmp_path):
    app = create_app(tmp_path / "identity.sqlite", include_samples=False)
    sample = synthetic_image()
    for name, sequence, key in [("prior", 1, KEY), ("current", 2, KEY), ("other", 1, OTHER)]:
        image = BridgeImage(name, sample.data, "HOSPITAL_AUTHORIZED", "fixture", filename=name + ".jpg", modality="CFP")
        app.state.images[name] = image
        record = legacy_admission(image)
        record.update(source_origin="HOSPITAL_AUTHORIZED", trusted_patient_key=key, trusted_laterality="LEFT",
                      trusted_capture_sequence=sequence, trusted_identity_method="AUTHORIZED_FILENAME_SEMANTICS")
        app.state.admissions[name] = record
    return app, TestClient(app)


def confirm(client, case, **overrides):
    return client.post("/v1/cases/" + case["image_id"] + "/confirm-image", json={
        "revision": case["revision"], "reviewer": "Synthetic operator", "patient_key": case["patient_key"],
        "laterality": case["laterality"], "retinal_modality": "CFP",
        "capture_sequence": case["visit_context"]["capture_sequence"], **overrides,
    })


def test_exact_trusted_key_keeps_provenance_pairing_and_history(tmp_path):
    app, client = hospital_client(tmp_path)
    prior = client.get("/v1/cases/prior").json()
    current = client.get("/v1/cases/current").json()
    assert len(KEY) == 33
    before = client.get("/v1/cases/current/comparison").json()
    assert before["eligible"] and before["comparison_state"] == "AUTO_PREVIOUS"
    response = confirm(client, current)
    assert response.status_code == 200
    saved = response.json()
    assert saved["patient_key"] == KEY == prior["patient_key"]
    assert saved["patient_resolution_method"] == current["patient_resolution_method"] == "AUTHORIZED_SOURCE"
    assert saved["laterality_resolution_method"] == "AUTHORIZED_SOURCE"
    assert saved["patient_display_label"] == current["patient_display_label"] == prior["patient_display_label"]
    assert saved["revision"] == current["revision"] + 1
    assert saved["resolution_history"][:-1] == current["resolution_history"]
    assert saved["events"][-1]["action"] == "CONFIRM_IMAGE"
    assert saved["events"][-1]["identity_assurance"] == "LOCAL_POC_SELF_DECLARED"
    assert DISPLAY_INDICES not in saved
    reloaded = client.get("/v1/cases/current").json()
    assert reloaded["resolution_history"] == saved["resolution_history"]
    assert reloaded["patient_key"] == KEY
    after = client.get("/v1/cases/current/comparison").json()
    assert after["eligible"] and after["visits"] == before["visits"]
    assert app.state.store.get("current")["patient_key"] == KEY


@pytest.mark.parametrize("replacement", [OTHER, KEY + "A", " " + KEY, "X" * 33, "full patient name"])
def test_tampered_or_invalid_manual_key_cannot_change_admission(tmp_path, replacement):
    app, client = hospital_client(tmp_path)
    current = client.get("/v1/cases/current").json()
    stored = copy.deepcopy(app.state.store.get("current"))
    admission = copy.deepcopy(app.state.admissions["current"])
    assert confirm(client, current, patient_key=replacement).status_code == 422
    assert app.state.store.get("current") == stored
    assert app.state.admissions["current"] == admission


def test_untrusted_long_key_is_not_grandfathered(tmp_path):
    app, client = hospital_client(tmp_path)
    current = client.get("/v1/cases/current").json()
    stored = app.state.store.get("current")
    stored["admission"]["trusted_identity_method"] = "NONE"
    stored["patient_resolution_method"] = "MANUAL"
    app.state.store.put(stored)
    assert confirm(client, current).status_code == 422


def test_manual_replacement_and_eye_only_keep_remain_explicit(tmp_path):
    _, client = hospital_client(tmp_path)
    current = client.get("/v1/cases/current").json()
    response = client.post("/v1/cases/current/resolver", json={
        "revision": current["revision"], "reviewer": "Synthetic operator", "patient_action": "KEEP",
        "laterality_action": "SET", "laterality": "RIGHT",
    })
    assert response.status_code == 200
    assert client.get("/v1/cases/current").json()["patient_key"] == KEY
    current = response.json()
    changed = confirm(client, current, patient_key="demo007").json()
    assert changed["patient_key"] == "DEMO007" and changed["patient_resolution_method"] == "MANUAL"
    assert changed["patient_display_label"] != current["patient_display_label"]
    assert client.get("/v1/cases/current").json()["patient_key"] == "DEMO007"
    unlinked = confirm(client, changed, patient_key=None).json()
    assert unlinked["patient_key"] is None and unlinked["patient_display_label"] is None


def test_labels_survive_restart_additions_and_retired_identity_without_clinical_writes(tmp_path):
    path = tmp_path / "labels.sqlite"
    store = Store(path)
    def assign(image_id, key):
        case = store.get(image_id)
        case["patient_key"] = key
        store.put(case)
        return hospital_patient_label(store, case, source_origin="HOSPITAL_AUTHORIZED")
    first, label = assign("z", KEY)
    second, different = assign("y", OTHER)
    assert label == "Patient 1" and different == "Patient 2"
    assert first["revision"] == 0 and first["events"] == []
    store = Store(path)
    assert assign("a", KEY)[1] == label
    assert assign("z", "MANUAL003")[1] == "Patient 3"
    assert assign("b", KEY)[1] == label
    assert assign("c", "MANUAL004")[1] == "Patient 4"
    assert assign("y", OTHER)[1] == different
