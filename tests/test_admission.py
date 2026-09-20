import hashlib

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from dr_support.api import create_app
from dr_support.services.admission import is_inference_eligible


def _write_image(path, *, fundus=False, size=(400, 300)):
    image = Image.new("RGB", size, "#777777")
    draw = ImageDraw.Draw(image)
    if fundus:
        image = Image.new("RGB", size, "#160604")
        draw = ImageDraw.Draw(image)
        draw.ellipse((24, 12, size[0] - 24, size[1] - 12), fill="#9b321d")
        draw.ellipse((size[0] // 2 - 22, size[1] // 2 - 22,
                      size[0] // 2 + 22, size[1] // 2 + 22), fill="#e7a45c")
        draw.line((size[0] // 2, size[1] // 2, 70, 82), fill="#31100a", width=7)
        draw.line((size[0] // 2, size[1] // 2, 320, 228), fill="#4f160c", width=5)
        draw.rectangle((150, 90, 176, 112), fill="#d96232")
    else:
        draw.rectangle((0, 0, size[0] // 2, size[1]), fill="#9a9a9a")
        draw.rectangle((size[0] // 2, 0, size[0], size[1]), fill="#6f6f6f")
    image.save(path, format="PNG")


def _workspace_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DR_SUPPORT_STATE", str(tmp_path / "fallback.sqlite"))
    monkeypatch.setenv("DR_SUPPORT_WORKSPACE_CATALOG", str(tmp_path / "catalog.sqlite"))
    app = create_app(include_samples=False)
    client = TestClient(app)
    input_folder = tmp_path / "input"
    output_folder = tmp_path / "output"
    input_folder.mkdir()
    output_folder.mkdir()
    response = client.post("/v1/workspaces", json={
        "name": "Admission fixtures",
        "input_folder": str(input_folder),
        "output_folder": str(output_folder),
        "database_path": str(tmp_path / "reviews.sqlite"),
    })
    assert response.status_code == 200
    return client, input_folder


def test_scan_handles_valid_ambiguous_invalid_and_quality_cases(tmp_path, monkeypatch):
    client, input_folder = _workspace_client(tmp_path, monkeypatch)
    _write_image(input_folder / "fundus.png", fundus=True)
    _write_image(input_folder / "ambiguous.png")
    _write_image(input_folder / "small.png", size=(32, 24))
    _write_image(input_folder / "wide.png", size=(1000, 100))
    (input_folder / "notes.txt").write_text("not an image", encoding="utf-8")
    (input_folder / "corrupt.jpg").write_bytes(b"not a jpeg")
    original = (input_folder / "fundus.png").read_bytes()

    response = client.post("/v1/admissions/scan")
    assert response.status_code == 200
    assert len(response.json()["records"]) == 6
    cases = {case["filename"]: case for case in client.get("/v1/cases").json()}

    assert cases["fundus.png"]["admission"]["modality_admission"] == "FUNDUS_ACCEPTED"
    assert cases["fundus.png"]["admission"]["quality_state"] == "NOT_EVALUATED"
    assert cases["ambiguous.png"]["admission"]["modality_admission"] == "NEEDS_REVIEW"
    assert cases["small.png"]["admission"]["quality_state"] == "NEEDS_REVIEW"
    assert cases["wide.png"]["admission"]["modality_admission"] == "NEEDS_REVIEW"
    assert cases["notes.txt"]["admission"]["modality_admission"] == "REJECTED_INVALID"
    assert cases["corrupt.jpg"]["admission"]["modality_admission"] == "REJECTED_INVALID"
    assert cases["fundus.png"]["admission_ui"]["label"] == "Ready for analysis"
    assert cases["ambiguous.png"]["admission_ui"]["label"] == "Needs review"
    assert cases["notes.txt"]["admission_ui"]["label"] == "Cannot analyze"
    assert (input_folder / "fundus.png").read_bytes() == original


def test_manual_admission_and_quality_overrides_are_auditable(tmp_path, monkeypatch):
    client, input_folder = _workspace_client(tmp_path, monkeypatch)
    _write_image(input_folder / "ambiguous.png")
    client.post("/v1/admissions/scan")
    item = next(case for case in client.get("/v1/cases").json() if case["filename"] == "ambiguous.png")
    accepted = client.post(f"/v1/cases/{item['image_id']}/admission", json={
        "revision": item["revision"],
        "reviewer": "Local clinician",
        "action": "ACCEPT_RETINAL",
        "note": "Manual retinal confirmation",
    })
    assert accepted.status_code == 200
    body = accepted.json()
    assert body["admission"]["modality_admission"] == "FUNDUS_ACCEPTED"
    assert body["admission"]["quality_state"] == "NOT_EVALUATED"
    assert body["admission"]["reviewed_by"] == "Local clinician"
    assert body["admission_history"][-1]["previous"]["modality_admission"] == "NEEDS_REVIEW"
    assert body["admission_history"][-1]["new"]["modality_admission"] == "FUNDUS_ACCEPTED"
    assert body["admission_history"][-1]["note"] == "Manual retinal confirmation"

    inadequate = client.post(f"/v1/cases/{item['image_id']}/admission", json={
        "revision": body["revision"],
        "reviewer": "Local clinician",
        "action": "QUALITY_INADEQUATE",
    })
    assert inadequate.status_code == 200
    body = inadequate.json()
    assert body["admission"]["modality_admission"] == "FUNDUS_ACCEPTED"
    assert body["admission"]["quality_state"] == "UNGRADABLE"
    assert body["admission_ui"]["label"] == "Image quality issue"


def test_inference_guard_blocks_all_noneligible_states_but_keeps_legacy_compatibility(tmp_path):
    client = TestClient(create_app(tmp_path / "state.sqlite", include_samples=False))
    image_id = "SYNTH_001"
    admission = client.get(f"/v1/cases/{image_id}").json()["admission"]
    assert is_inference_eligible(admission)
    assert client.post("/v1/infer/global", json={"image_id": image_id, "model_id": "mock-global"}).status_code == 200

    app = client.app
    for modality, quality in [
        ("NEEDS_REVIEW", "NOT_EVALUATED"),
        ("REJECTED_NON_FUNDUS", "NOT_EVALUATED"),
        ("REJECTED_INVALID", "NOT_EVALUATED"),
        ("FUNDUS_ACCEPTED", "UNGRADABLE"),
        ("FUNDUS_ACCEPTED", "NEEDS_REVIEW"),
    ]:
        app.state.admissions[image_id] = {**admission, "modality_admission": modality, "quality_state": quality}
        response = client.post("/v1/infer/global", json={"image_id": image_id, "model_id": "mock-global"})
        assert response.status_code == 409
        assert "needs review" in response.json()["detail"].lower()


def test_legacy_case_reopens_with_explicit_admission_defaults(tmp_path):
    path = tmp_path / "state.sqlite"
    first = TestClient(create_app(path, include_samples=False))
    body = first.get("/v1/cases/SYNTH_001").json()
    assert body["admission"]["quality_state"] == "NOT_EVALUATED"
    second = TestClient(create_app(path, include_samples=False))
    restored = second.get("/v1/cases/SYNTH_001").json()
    assert restored["admission"]["admission_method"] == "LEGACY_COMPAT"
    assert restored["admission_history"]
    assert hashlib.sha256(second.get("/v1/images/SYNTH_001").content).hexdigest() == body["image_sha256"]
