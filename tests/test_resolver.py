"""S2A2 patient/eye resolver coverage."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from dr_support.api import create_app
from dr_support.providers.remote import RemoteGlobalProvider
from dr_support.services.resolver import (
    OCREvidence,
    ResolverService,
    parse_filename,
    reconcile,
)


@pytest.mark.parametrize(
    ("filename", "patient", "eye"),
    [
        ("PAT0001_L1.jpg", "PAT0001", "LEFT"),
        ("PAT0001_R1.jpg", "PAT0001", "RIGHT"),
        ("PAT0001_LEFT_01.png", "PAT0001", "LEFT"),
        ("PAT0001_RIGHT_01.PNG", "PAT0001", "RIGHT"),
        ("PAT0001-L.jpg", "PAT0001", "LEFT"),
        ("FI3010_L1_APR.jpg", "FI3010", "LEFT"),
        ("BK9881_R1_APR.jpg", "BK9881", "RIGHT"),
    ],
)
def test_explicit_filename_patterns(filename, patient, eye):
    parsed = parse_filename(filename)
    assert parsed.patient_candidate == patient
    assert parsed.laterality == eye
    assert parsed.parser_status == "MATCHED"


def test_filename_capture_sequence_is_evidence_not_chronology():
    parsed = parse_filename("FC8804_L1.jpg")
    assert parsed.capture_sequence == 1
    assert parse_filename("FC8804_L2.jpg").capture_sequence == 2
    assert parse_filename("FC8804_LEFT.jpg").capture_sequence is None
    assert parse_filename("FC8804 L1.jpg").laterality == "LEFT"
    assert parse_filename("FC8804 L1.jpg").capture_sequence == 1
    assert parse_filename("FC8804_OS2.jpg").laterality == "LEFT"
    assert parse_filename("FC8804 OD2.jpg").laterality == "RIGHT"


def test_filename_with_conflicting_trailing_eye_token_stays_ambiguous():
    for filename in ("FC8804 L1 R2.jpg", "FC8804 L1 L2 R3.jpg"):
        parsed = parse_filename(filename)
        assert parsed.patient_candidate == "FC8804"
        assert parsed.laterality == "UNKNOWN"
        assert parsed.capture_sequence is None
        assert parsed.parser_status == "AMBIGUOUS"
        assert parsed.pattern == "PATIENT_EYE_CONFLICTING_SUFFIX"


def test_filename_parser_keeps_unknown_and_ambiguous_names_conservative():
    assert parse_filename("PAT0001.jpg").patient_candidate == "PAT0001"
    assert parse_filename("PAT0001.jpg").laterality == "UNKNOWN"
    ambiguous = parse_filename("PAT0001_X1.jpg")
    assert ambiguous.patient_candidate == "PAT0001"
    assert ambiguous.parser_status == "AMBIGUOUS"
    unknown = parse_filename("unknown_001.jpg")
    assert unknown.patient_candidate is None
    assert unknown.parser_status == "NO_MATCH"


def test_multiple_captures_share_one_patient_key_without_becoming_one_image():
    left_one = reconcile(parse_filename("DEMO001_L1.jpg"))
    left_two = reconcile(parse_filename("DEMO001_L2.jpg"))
    right_one = reconcile(parse_filename("DEMO001_R1.jpg"))
    assert [left_one["patient_key"], left_two["patient_key"], right_one["patient_key"]] == [
        "DEMO001",
        "DEMO001",
        "DEMO001",
    ]
    assert left_one["laterality"] == left_two["laterality"] == "LEFT"
    assert right_one["laterality"] == "RIGHT"


def test_reconciliation_matrix_is_independent_and_conservative():
    resolved = reconcile(parse_filename("PAT0001_L1.jpg"))
    assert resolved["resolver_state"] == "RESOLVED"
    assert resolved["patient_key"] == "PAT0001"
    assert resolved["laterality"] == "LEFT"

    agrees = reconcile(
        parse_filename("PAT0001_L1.jpg"),
        OCREvidence("USABLE_CANDIDATE", "PAT0001", "LEFT", "medium"),
    )
    assert agrees["resolver_state"] == "RESOLVED"

    patient_conflict = reconcile(
        parse_filename("PAT0001_L1.jpg"),
        OCREvidence("USABLE_CANDIDATE", "PAT0002", "LEFT", "medium"),
    )
    assert patient_conflict["patient_resolution_state"] == "CONFLICT"
    assert patient_conflict["resolver_state"] == "CONFLICT"

    eye_conflict = reconcile(
        parse_filename("PAT0001_L1.jpg"),
        OCREvidence("USABLE_CANDIDATE", "PAT0001", "RIGHT", "medium"),
    )
    assert eye_conflict["patient_key"] == "PAT0001"
    assert eye_conflict["laterality_resolution_state"] == "CONFLICT"
    assert eye_conflict["resolver_state"] == "CONFLICT"

    ocr_candidate = reconcile(
        parse_filename("unknown_001.jpg"),
        OCREvidence("USABLE_CANDIDATE", "PAT0003", "RIGHT", "low"),
    )
    assert ocr_candidate["patient_resolution_state"] == "NEEDS_CONFIRMATION"
    assert ocr_candidate["laterality_resolution_state"] == "NEEDS_CONFIRMATION"

    no_text = reconcile(parse_filename("unknown_001.jpg"), OCREvidence("NO_TEXT_DETECTED"))
    assert no_text["resolver_state"] == "UNLINKED"
    assert no_text["patient_key"] is None

    no_eye = reconcile(parse_filename("PAT0001.jpg"))
    assert no_eye["patient_resolution_state"] == "RESOLVED"
    assert no_eye["laterality"] == "UNKNOWN"


def test_ocr_is_optional_filename_first_and_never_returns_raw_text():
    class FakeOCR:
        def __init__(self):
            self.calls = 0

        def extract(self, image, *, filename):
            self.calls += 1
            return OCREvidence("USABLE_CANDIDATE", "PAT0005", "LEFT", "medium")

    adapter = FakeOCR()
    service = ResolverService(adapter)
    complete = service.resolve(object(), "PAT0001_L1.jpg")
    assert complete["patient_key"] == "PAT0001"
    assert adapter.calls == 0

    fallback = service.resolve(object(), "unknown_001.jpg")
    assert fallback["patient_candidate"] == "PAT0005"
    assert fallback["patient_resolution_state"] == "NEEDS_CONFIRMATION"
    assert "raw_text" not in fallback["resolver_evidence"]["ocr"]
    assert adapter.calls == 1


def _demo_image(path, color):
    image = Image.new("RGB", (240, 180), color)
    image.save(path, format="JPEG")


def test_demo_images_group_by_pseudonymous_patient_and_eye(tmp_path, monkeypatch):
    for name, color in [
        ("img13_L1.jpg", (190, 70, 30)),
        ("img15_L2.jpg", (191, 71, 31)),
        ("img14_R1.jpg", (192, 72, 32)),
        ("img16_R2.jpg", (193, 73, 33)),
        ("unknown_001.jpg", (100, 100, 100)),
    ]:
        _demo_image(tmp_path / name, color)
    monkeypatch.setenv("DR_DEMO_FOLDER", str(tmp_path))
    client = TestClient(create_app(tmp_path / "state.sqlite", include_samples=False))

    cases = {case["filename"]: case for case in client.get("/v1/cases").json()}
    assert cases["img13_L1.jpg"]["patient_key"] == "IMG13"
    assert cases["img15_L2.jpg"]["patient_key"] == "IMG15"
    assert cases["img14_R1.jpg"]["laterality"] == "RIGHT"
    assert cases["unknown_001.jpg"]["patient_resolution_state"] == "UNLINKED"


def test_manual_resolution_is_independent_auditable_and_persistent(tmp_path):
    path = tmp_path / "state.sqlite"
    client = TestClient(create_app(path, include_samples=False))
    base = "/v1/cases/SYNTH_001"
    initial = client.get(base).json()
    assert initial["patient_resolution_state"] == "UNLINKED"

    saved = client.post(
        base + "/resolver",
        json={
            "revision": initial["revision"],
            "reviewer": "Local clinician",
            "patient_action": "SET",
            "patient_key": "P000042",
            "laterality_action": "SET",
            "laterality": "LEFT",
            "note": "Synthetic grouping confirmation",
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["patient_key"] == "P000042"
    assert body["laterality"] == "LEFT"
    event = body["resolution_history"][-1]
    assert event["action"] == "MANUAL_RESOLUTION"
    assert event["previous"]["patient_key"] is None
    assert event["new"]["patient_key"] == "P000042"
    assert event["automatic_evidence"] is not None

    restored = TestClient(create_app(path, include_samples=False)).get(base).json()
    assert restored["patient_key"] == "P000042"
    assert restored["laterality"] == "LEFT"
    assert restored["resolution_history"][-1]["reviewer"] == "Local clinician"

    unlinked = client.post(
        base + "/resolver",
        json={
            "revision": restored["revision"],
            "reviewer": "Local clinician",
            "patient_action": "LEAVE_UNLINKED",
        },
    )
    assert unlinked.status_code == 200
    assert unlinked.json()["patient_key"] is None
    assert unlinked.json()["laterality"] == "LEFT"


def test_stale_automatic_resolution_refreshes_once_and_survives_restart(tmp_path):
    image_path = tmp_path / "HN5071 L1.jpg"
    _demo_image(image_path, (120, 80, 40))
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("DR_DEMO_FOLDER", str(tmp_path))
    try:
        path = tmp_path / "refresh.sqlite"
        app = create_app(path, include_samples=False)
        client = TestClient(app)
        image_id = next(case["image_id"] for case in client.get("/v1/cases").json()
                         if case["filename"] == image_path.name)
        legacy = app.state.store.get(image_id)
        legacy["patient_key"] = None
        legacy["patient_resolution_state"] = "UNLINKED"
        legacy["patient_resolution_method"] = "NONE"
        legacy["patient_candidate"] = None
        legacy["laterality"] = "UNKNOWN"
        legacy["laterality_resolution_state"] = "UNLINKED"
        legacy["laterality_resolution_method"] = "NONE"
        legacy["laterality_candidate"] = None
        legacy["resolver_state"] = "UNLINKED"
        legacy["resolver_evidence"] = {"version": "filename-resolver-v1", "filename": {}}
        legacy["resolution_history"] = []
        app.state.store.put(legacy)

        refreshed = client.get(f"/v1/cases/{image_id}").json()
        assert refreshed["patient_key"] == "HN5071"
        assert refreshed["laterality"] == "LEFT"
        assert refreshed["resolver_evidence"]["filename"]["capture_sequence"] == 1
        assert [event["action"] for event in refreshed["resolution_history"]] == [
            "AUTOMATIC_RESOLUTION_REFRESH",
        ]
        revision = refreshed["revision"]

        repeated = client.get(f"/v1/cases/{image_id}").json()
        assert repeated["revision"] == revision
        assert repeated["resolution_history"] == refreshed["resolution_history"]

        restored = TestClient(create_app(path, include_samples=False)).get(f"/v1/cases/{image_id}").json()
        assert restored["patient_key"] == "HN5071"
        assert restored["laterality"] == "LEFT"
        assert restored["resolution_history"] == refreshed["resolution_history"]
    finally:
        monkeypatch.undo()


def test_confirm_image_in_any_history_protects_identity_from_refresh():
    case = {
        "patient_key": "MANUAL01",
        "patient_resolution_state": "RESOLVED",
        "patient_resolution_method": "MANUAL",
        "patient_candidate": "MANUAL01",
        "laterality": "RIGHT",
        "laterality_resolution_state": "RESOLVED",
        "laterality_resolution_method": "MANUAL",
        "laterality_candidate": "RIGHT",
        "resolver_state": "RESOLVED",
        "resolver_evidence": {"version": "filename-resolver-v1"},
        "admission_history": [{"action": "CONFIRM_IMAGE"}],
        "resolution_history": [],
        "events": [],
    }
    decision = ResolverService().resolve(object(), "HN5071 L1.jpg")
    from dr_support.services.resolver import apply_automatic_resolution

    assert apply_automatic_resolution(case, decision, timestamp="2026-10-03T00:00:00Z") is True
    assert case["patient_key"] == "MANUAL01"
    assert case["laterality"] == "RIGHT"


def test_partial_manual_resolution_refreshes_only_unprotected_identity_and_audits_evidence():
    case = {
        "patient_key": "MANUAL01",
        "patient_resolution_state": "RESOLVED",
        "patient_resolution_method": "MANUAL",
        "patient_reason_code": "MANUAL_ASSIGNED",
        "patient_candidate": "MANUAL01",
        "patient_confidence_or_strength": "HIGH",
        "laterality": "UNKNOWN",
        "laterality_resolution_state": "UNLINKED",
        "laterality_resolution_method": "NONE",
        "laterality_reason_code": "NO_LATERALITY_EVIDENCE",
        "laterality_candidate": None,
        "resolver_state": "RESOLVED",
        "resolver_evidence": {"version": "filename-resolver-v1", "filename": {}},
        "resolution_history": [],
        "events": [],
    }
    decision = ResolverService().resolve(object(), "HN5071 L1.jpg")
    from dr_support.services.resolver import apply_automatic_resolution

    assert apply_automatic_resolution(case, decision, timestamp="2026-10-03T00:00:00Z") is True
    assert case["patient_key"] == "MANUAL01"
    assert case["patient_resolution_method"] == "MANUAL"
    assert case["laterality"] == "LEFT"
    event = case["resolution_history"][-1]
    assert event["previous_evidence"]["version"] == "filename-resolver-v1"
    assert event["new_evidence"]["filename"]["pattern"] == "PATIENT_EYE_CAPTURE"
    assert event["new_evidence"]["filename"]["parser_status"] == "MATCHED"
    assert event["new_evidence"]["filename"]["capture_sequence"] == 1
    assert event["new_evidence"]["patient_method"] == "MANUAL"
    assert "raw_text" not in event["new_evidence"]


def test_explicit_unknown_eye_is_a_valid_manual_decision(tmp_path):
    client = TestClient(create_app(tmp_path / "state.sqlite", include_samples=False))
    base = "/v1/cases/SYNTH_001"
    initial = client.get(base).json()
    saved = client.post(
        base + "/resolver",
        json={
            "revision": initial["revision"],
            "reviewer": "Local clinician",
            "patient_action": "SET",
            "patient_key": "P000042",
            "laterality_action": "SET",
            "laterality": "UNKNOWN",
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["patient_key"] == "P000042"
    assert body["laterality"] == "UNKNOWN"
    assert body["laterality_resolution_state"] == "RESOLVED"
    assert body["resolver_ui"]["laterality"]["action_required"] is False


def test_remote_inference_payload_has_no_identity_fields():
    provider = RemoteGlobalProvider(base_url="http://127.0.0.1:9")
    request = SimpleNamespace(image_id="image-1", modality="CFP", model_id="retfound-aptos5")
    image = SimpleNamespace(
        data=b"synthetic-image-bytes",
        sha256="a" * 64,
        source_type="PUBLIC",
        size=(640, 480),
    )
    payload = provider._payload(request, image)
    assert set(payload) == {
        "image_id",
        "modality",
        "model_id",
        "image_b64",
        "image_sha256",
        "source_type",
        "width",
        "height",
    }
    assert not any("patient" in key or "ocr" in key or "laterality" in key for key in payload)
