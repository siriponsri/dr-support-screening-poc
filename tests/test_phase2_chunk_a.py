"""Chunk A regression coverage for UWF review foundation behavior."""

import hashlib
import io

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from dr_support.api import create_app
from dr_support.images import BridgeImage
from dr_support.imaging import CoordinateMapping, DerivativeService, SourceDimensions
from dr_support.imaging.retinal_field import prepare_retinal_field


def test_named_grade_persists_and_disagreement_is_not_overwritten(tmp_path):
    path = tmp_path / "review.sqlite"
    client = TestClient(create_app(path, include_samples=False))
    base = "/v1/cases/SYNTH_001"

    first = client.get(base).json()
    saved = client.post(base + "/review", json={
        "revision": first["revision"],
        "action": "CORRECT_GRADE",
        "reviewer": "First clinician",
        "grade": 2,
    })
    assert saved.status_code == 200
    body = saved.json()
    assert body["grade_status"] == "CONFIRMED"
    assert body["reviewed_grade"] == 2
    assert body["reviewed_grade_label"] == "Moderate NPDR"
    assert body["grade_reviews"][-1]["grade_label"] == "Moderate NPDR"

    reopened = TestClient(create_app(path, include_samples=False)).get(base).json()
    assert reopened["grade_status"] == "CONFIRMED"
    assert reopened["reviewed_grade_label"] == "Moderate NPDR"

    disagreement = client.post(base + "/review", json={
        "revision": reopened["revision"],
        "action": "CORRECT_GRADE",
        "reviewer": "Second clinician",
        "grade": 1,
    })
    assert disagreement.status_code == 200
    body = disagreement.json()
    assert body["grade_status"] == "NEEDS_SECOND_REVIEW"
    assert body["state"] == "NEEDS_SECOND_REVIEW"
    assert body["reviewed_grade"] is None
    assert [entry["grade"] for entry in body["grade_reviews"]] == [2, 1]
    assert body["grade_adjudication"]["status"] == "UNRESOLVED"

    row = client.get("/v1/dataset/manifest").json()["images"][0]
    assert row["dr_grade_training_ready"] is False
    assert row["grade_eligibility_reason"] == "NEEDS_SECOND_REVIEW"

    resolved = client.post(base + "/review", json={
        "revision": body["revision"],
        "action": "ADJUDICATE_GRADE",
        "reviewer": "Adjudicating clinician",
        "grade": 2,
    })
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["grade_status"] == "CONFIRMED"
    assert body["reviewed_grade"] == 2
    assert body["grade_adjudication"]["status"] == "RESOLVED"
    assert [entry["grade"] for entry in body["grade_reviews"]] == [2, 1, 2]


def test_ungradable_cannot_clear_unresolved_grade_disagreement(tmp_path):
    client = TestClient(create_app(tmp_path / "review.sqlite", include_samples=False))
    base = "/v1/cases/SYNTH_001/review"

    first = client.post(base, json={
        "revision": 0,
        "action": "CORRECT_GRADE",
        "reviewer": "First clinician",
        "grade": 2,
    })
    second = client.post(base, json={
        "revision": first.json()["revision"],
        "action": "CORRECT_GRADE",
        "reviewer": "Second clinician",
        "grade": 1,
    })
    unresolved = second.json()
    assert unresolved["grade_status"] == "NEEDS_SECOND_REVIEW"
    assert unresolved["grade_adjudication"]["status"] == "UNRESOLVED"

    rejected = client.post(base, json={
        "revision": unresolved["revision"],
        "action": "MARK_UNGRADABLE",
        "reviewer": "Third clinician",
    })

    assert rejected.status_code == 409
    preserved = client.get("/v1/cases/SYNTH_001").json()
    assert preserved["grade_status"] == "NEEDS_SECOND_REVIEW"
    assert preserved["state"] == "NEEDS_SECOND_REVIEW"
    assert preserved["grade_adjudication"]["status"] == "UNRESOLVED"
    assert [entry["grade"] for entry in preserved["grade_reviews"]] == [2, 1]


def test_legacy_escalate_cannot_clear_unresolved_grade_disagreement(tmp_path):
    client = TestClient(create_app(tmp_path / "review.sqlite", include_samples=False))
    base = "/v1/cases/SYNTH_001/review"

    first = client.post(base, json={
        "revision": 0,
        "action": "CORRECT_GRADE",
        "reviewer": "First clinician",
        "grade": 2,
    })
    second = client.post(base, json={
        "revision": first.json()["revision"],
        "action": "CORRECT_GRADE",
        "reviewer": "Second clinician",
        "grade": 1,
    })
    unresolved = second.json()

    rejected = client.post(base, json={
        "revision": unresolved["revision"],
        "action": "ESCALATE",
        "reviewer": "Third clinician",
    })

    assert rejected.status_code == 409
    assert rejected.json()["detail"] == (
        "Resolve the outstanding grade disagreement before escalating the case"
    )
    preserved = client.get("/v1/cases/SYNTH_001").json()
    assert preserved["revision"] == unresolved["revision"]
    assert preserved["grade_status"] == "NEEDS_SECOND_REVIEW"
    assert preserved["state"] == "NEEDS_SECOND_REVIEW"
    assert preserved["grade_adjudication"]["status"] == "UNRESOLVED"
    assert [entry["grade"] for entry in preserved["grade_reviews"]] == [2, 1]


def test_legacy_mark_incorrect_cannot_clear_unresolved_grade_disagreement(tmp_path):
    client = TestClient(create_app(tmp_path / "review.sqlite", include_samples=False))
    base = "/v1/cases/SYNTH_001"

    inference = client.post("/v1/infer/global", json={
        "image_id": "SYNTH_001",
        "modality": "CFP",
        "model_id": "mock-global",
    })
    assert inference.status_code == 200
    ai_case = client.get(base).json()
    assert ai_case["global"]["grade"] == 2

    first = client.post(base + "/review", json={
        "revision": ai_case["revision"],
        "action": "CORRECT_GRADE",
        "reviewer": "First clinician",
        "grade": 2,
    })
    second = client.post(base + "/review", json={
        "revision": first.json()["revision"],
        "action": "CORRECT_GRADE",
        "reviewer": "Second clinician",
        "grade": 1,
    })
    unresolved = second.json()
    assert unresolved["grade_status"] == "NEEDS_SECOND_REVIEW"
    assert [entry["grade"] for entry in unresolved["grade_reviews"]] == [2, 1]

    rejected = client.post(base + "/review", json={
        "revision": unresolved["revision"],
        "action": "MARK_INCORRECT",
        "reviewer": "Third clinician",
    })

    assert rejected.status_code == 409
    assert rejected.json()["detail"] == (
        "Resolve the outstanding grade disagreement before marking the AI suggestion incorrect"
    )
    preserved = client.get(base).json()
    assert preserved["revision"] == unresolved["revision"]
    assert preserved["grade_status"] == "NEEDS_SECOND_REVIEW"
    assert preserved["state"] == "NEEDS_SECOND_REVIEW"
    assert preserved["global"]["grade"] == 2
    assert preserved["grade_adjudication"]["status"] == "UNRESOLVED"
    assert [entry["grade"] for entry in preserved["grade_reviews"]] == [2, 1]

    resolved = client.post(base + "/review", json={
        "revision": preserved["revision"],
        "action": "ADJUDICATE_GRADE",
        "reviewer": "Adjudicating clinician",
        "grade": 2,
    })
    assert resolved.status_code == 200
    assert resolved.json()["grade_status"] == "CONFIRMED"


def test_historical_unknown_review_remains_readable_without_a_grade(tmp_path):
    client = TestClient(create_app(tmp_path / "legacy.sqlite", include_samples=False))
    case = client.app.state.store.get("SYNTH_001")
    case["state"] = "REVIEWED"
    case["clinician_review"] = {
        "reviewer": "Legacy clinician",
        "final_grade": None,
        "review_action": "ESCALATE",
        "remark": "Historical unresolved review",
        "timestamp": "2025-01-01T00:00:00Z",
        "revision": 2,
    }
    case.pop("grade_status", None)
    client.app.state.store.put(case)

    reopened = client.get("/v1/cases/SYNTH_001").json()
    assert reopened["grade_status"] == "UNKNOWN"
    assert reopened["reviewed_grade"] is None
    assert reopened["grade_reviews"][0]["grade"] is None
    assert reopened["clinician_review"]["reviewer"] == "Legacy clinician"


def test_ungradable_and_second_review_are_separate_grade_states(tmp_path):
    client = TestClient(create_app(tmp_path / "review.sqlite", include_samples=False))
    base = "/v1/cases/SYNTH_001"

    second = client.post(base + "/review", json={
        "revision": 0,
        "action": "REQUEST_SECOND_REVIEW",
        "reviewer": "First clinician",
    })
    assert second.status_code == 200
    assert second.json()["grade_status"] == "NEEDS_SECOND_REVIEW"
    assert second.json()["reviewed_grade"] is None

    client = TestClient(create_app(tmp_path / "ungradable.sqlite", include_samples=False))
    ungradable = client.post(base + "/review", json={
        "revision": 0,
        "action": "MARK_UNGRADABLE",
        "reviewer": "First clinician",
    })
    assert ungradable.status_code == 200
    body = ungradable.json()
    assert body["grade_status"] == "UNGRADABLE"
    assert body["clinician_review"]["final_grade"] is None
    assert body["reviewed_grade"] is None
    assert body["reviewed_grade_label"] is None


def test_workspace_origin_is_truthful_and_model_boundary_stays_manual(tmp_path):
    image = Image.new("RGB", (320, 240), (80, 35, 25))
    output = io.BytesIO()
    image.save(output, format="PNG")
    input_folder = tmp_path / "input"
    output_folder = tmp_path / "output"
    input_folder.mkdir()
    output_folder.mkdir()
    (input_folder / "workspace.png").write_bytes(output.getvalue())

    client = TestClient(create_app(tmp_path / "fallback.sqlite", include_samples=False))
    created = client.post("/v1/workspaces", json={
        "name": "Chunk A workspace",
        "input_folder": str(input_folder),
        "output_folder": str(output_folder),
        "database_path": str(tmp_path / "workspace.sqlite"),
    })
    assert created.status_code == 200
    client.post("/v1/admissions/scan")
    case = next(item for item in client.get("/v1/cases").json() if item["filename"] == "workspace.png")
    assert case["source_origin"] == "WORKSPACE"
    confirmed = client.post(f"/v1/cases/{case['image_id']}/confirm-image", json={
        "revision": case["revision"],
        "reviewer": "Workspace clinician",
        "laterality": "UNKNOWN",
        "retinal_modality": "CFP",
    })
    assert confirmed.status_code == 200
    assert confirmed.json()["source_origin"] == "WORKSPACE"
    inference = client.post("/v1/infer/global", json={
        "image_id": case["image_id"],
        "modality": "CFP",
        "model_id": "retfound-aptos5",
    })
    assert inference.status_code == 409
    assert "manual review only" in inference.json()["detail"]


def test_analysis_representation_and_spatial_mismatch_fail_closed(tmp_path):
    source = Image.new("RGB", (320, 240), (80, 35, 25))
    output = io.BytesIO()
    source.save(output, format="TIFF")
    data = output.getvalue()
    image = BridgeImage(
        hashlib.sha256(data).hexdigest(), data, "PUBLIC", "fixture",
        modality="CFP", filename="fixture.tiff", media_type="image/tiff",
    )
    derivative = DerivativeService().prepare_analysis(image)
    audit = derivative.audit_record()
    assert audit["representation_version"] == "uwf-analysis-representation-v1"
    assert audit["original_coordinate_space"] == "original_image_pixels"
    assert audit["spatial_mapping_version"] == "analysis-to-original-v1"
    assert audit["source_origin"] == "PUBLIC"

    client = TestClient(create_app(tmp_path / "review.sqlite", include_samples=False))
    assert client.post("/v1/infer/lesion-roi", json={
        "image_id": "SYNTH_001", "model_id": "mock-lesion",
    }).status_code == 200
    case = client.app.state.store.get("SYNTH_001")
    case["analysis_derivative"] = {"source_sha256": "0" * 64}
    client.app.state.store.put(case)
    detail = client.get("/v1/cases/SYNTH_001").json()
    assert detail["spatial_ai_display"]["status"] == "BLOCKED"
    assert detail["lesion"] is None
    assert detail["explainability"]["status"] == "UNAVAILABLE"

    case = client.app.state.store.get("SYNTH_001")
    case["analysis_derivative"] = None
    case["lesion"]["provenance"]["source_type"] = "PUBLIC"
    client.app.state.store.put(case)
    detail = client.get("/v1/cases/SYNTH_001").json()
    assert detail["spatial_ai_display"]["reason"] == "SOURCE_ORIGIN_MISMATCH"
    assert detail["lesion"] is None


def test_double_mask_candidates_measure_actual_paths_and_geometry():
    """Record the available shared path and its actual double-mask probe.

    The checked-in field-building step used by the shared UWF derivative is
    ``prepare_retinal_field``; it is the available implementation corresponding
    to the research ``border_component_v1`` step.  A separate adapter-v4
    implementation is not present in this checkout, so this test does not
    claim equivalence with adapter v4.  The available double-mask probe
    reruns the shipped derivative path on its own output, which makes any
    second-pass geometry change observable.
    """
    source = Image.new("RGB", (512, 384), (7, 7, 7))
    draw = ImageDraw.Draw(source)
    draw.ellipse((32, 24, 480, 360), fill=(170, 60, 35))
    draw.ellipse((230, 140, 280, 180), fill=(240, 240, 220))
    source_data = io.BytesIO()
    source.save(source_data, format="PNG", optimize=False, compress_level=9)
    source_bytes = source_data.getvalue()
    source_dimensions = SourceDimensions(
        width=source.width,
        height=source.height,
        bit_depth=8,
        channels=3,
    )
    source_image = BridgeImage(
        hashlib.sha256(source_bytes).hexdigest(),
        source_bytes,
        "SYNTHETIC",
        "Approved synthetic UWF double-mask fixture",
        modality="UWF",
        filename="double-mask-fixture.png",
        media_type="image/png",
        source_origin="SYNTHETIC",
    )

    def measure_stage(label, input_sha256, data):
        with Image.open(io.BytesIO(data)) as decoded:
            decoded.load()
            image = decoded.convert("RGB")
        dimensions = SourceDimensions(
            width=image.width,
            height=image.height,
            bit_depth=8,
            channels=len(image.getbands()),
        )
        visible_mask_bytes = bytes(
            255 if pixel != (0, 0, 0) else 0
            for pixel in image.getdata()
        )
        visible_mask = Image.frombytes("L", image.size, visible_mask_bytes)
        return {
            "label": label,
            "input_sha256": input_sha256,
            "output_sha256": hashlib.sha256(data).hexdigest(),
            "dimensions": dimensions.model_dump(mode="json"),
            "geometry": {
                "visible_mask_bbox": visible_mask.getbbox(),
                "visible_fraction": visible_mask_bytes.count(255) / (
                    image.width * image.height
                ),
                "visible_mask_sha256": hashlib.sha256(visible_mask_bytes).hexdigest(),
                "coordinate_mapping": CoordinateMapping.for_dimensions(
                    source_dimensions,
                    dimensions,
                ).model_dump(mode="json"),
            },
        }

    service = DerivativeService()
    shared = service.prepare_analysis(source_image, source_modality="UWF")
    shared_image = BridgeImage(
        hashlib.sha256(shared.data).hexdigest(),
        shared.data,
        "SYNTHETIC",
        "Shared masked-analysis derivative",
        modality="UWF",
        filename="double-mask-fixture-analysis.png",
        media_type="image/png",
        source_origin="SYNTHETIC",
    )
    double_mask = service.prepare_analysis(shared_image, source_modality="UWF")
    source_field = prepare_retinal_field(source)

    evidence = {
        "original": {
            "label": "original",
            "input_sha256": source_image.sha256,
            "output_sha256": source_image.sha256,
            "dimensions": source_dimensions.model_dump(mode="json"),
            "mask_sha256": source_field.mask_sha256,
            "valid_retina_fraction": source_field.valid_fraction,
            "geometry": {
                "mask_bbox": source_field.mask.getbbox(),
                "coordinate_mapping": CoordinateMapping.for_dimensions(
                    source_dimensions,
                    source_dimensions,
                ).model_dump(mode="json"),
            },
        },
        "shared_analysis": measure_stage(
            "shared_analysis", source_image.sha256, shared.data,
        ),
        "double_mask_probe": measure_stage(
            "double_mask_probe", shared_image.sha256, double_mask.data,
        ),
    }
    evidence["shared_analysis"]["lineage_sha256"] = shared.lineage.derivative_sha256
    evidence["shared_analysis"]["mask_sha256"] = shared.valid_retina_mask_sha256
    evidence["shared_analysis"]["valid_retina_fraction"] = shared.valid_retina_fraction
    evidence["double_mask_probe"]["lineage_sha256"] = double_mask.lineage.derivative_sha256
    evidence["double_mask_probe"]["mask_sha256"] = double_mask.valid_retina_mask_sha256
    evidence["double_mask_probe"]["valid_retina_fraction"] = double_mask.valid_retina_fraction

    assert evidence["shared_analysis"]["input_sha256"] == evidence["original"]["output_sha256"]
    assert (
        evidence["double_mask_probe"]["input_sha256"]
        == evidence["shared_analysis"]["output_sha256"]
    )
    assert (
        evidence["shared_analysis"]["output_sha256"]
        == evidence["shared_analysis"]["lineage_sha256"]
    )
    assert (
        evidence["double_mask_probe"]["output_sha256"]
        == evidence["double_mask_probe"]["lineage_sha256"]
    )
    assert evidence["original"]["mask_sha256"] == evidence["shared_analysis"]["mask_sha256"]

    # On this deterministic fixture, a second actual pass shrinks the measured
    # field.  Record the difference instead of claiming adapter-v4 equivalence.
    assert (
        evidence["shared_analysis"]["output_sha256"]
        != evidence["double_mask_probe"]["output_sha256"]
    )
    assert (
        evidence["shared_analysis"]["mask_sha256"]
        != evidence["double_mask_probe"]["mask_sha256"]
    )
    assert (
        evidence["shared_analysis"]["valid_retina_fraction"]
        > evidence["double_mask_probe"]["valid_retina_fraction"]
    )
    assert evidence["shared_analysis"]["dimensions"] == evidence["double_mask_probe"]["dimensions"]
    assert evidence["shared_analysis"]["geometry"] != evidence["double_mask_probe"]["geometry"]
    assert (
        evidence["shared_analysis"]["geometry"]["coordinate_mapping"]
        == evidence["double_mask_probe"]["geometry"]["coordinate_mapping"]
    )
    assert (
        evidence["shared_analysis"]["geometry"]["visible_mask_sha256"]
        != evidence["double_mask_probe"]["geometry"]["visible_mask_sha256"]
    )


def test_spatial_ai_requires_matching_lineage_and_coordinate_mapping(tmp_path):
    client = TestClient(create_app(tmp_path / "review.sqlite", include_samples=False))
    assert client.post("/v1/infer/lesion-roi", json={
        "image_id": "SYNTH_001", "model_id": "mock-lesion",
    }).status_code == 200
    case = client.app.state.store.get("SYNTH_001")
    image = client.app.state.images["SYNTH_001"]
    audit = DerivativeService().prepare_analysis(image).audit_record()
    case["analysis_derivative"] = audit
    case["lesion"]["provenance"]["image_sha256"] = audit["analysis_sha256"]
    client.app.state.store.put(case)

    detail = client.get("/v1/cases/SYNTH_001").json()
    assert detail["spatial_ai_display"]["status"] == "AVAILABLE"

    case["analysis_derivative"]["coordinate_mapping"]["scale_x"] *= 2
    client.app.state.store.put(case)
    detail = client.get("/v1/cases/SYNTH_001").json()
    assert detail["spatial_ai_display"]["reason"] == "DIMENSION_MISMATCH"
    assert detail["lesion"] is None
