"""CPU-only USPEC artifact, preprocessing, and Model API contract tests."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from dr_support.contracts import InferenceRequest
from dr_support.images import BridgeImage, synthetic_image
from dr_support.models.uspec_artifact import (
    CAPABILITY_ID,
    MODEL_ID,
    MODEL_VERSION,
    PREPROCESSING,
    RESEARCH_MODEL_ID,
    REPRESENTATION,
    TRANSFORM,
    ArtifactContract,
    verify_source_files,
    verify_stream,
    verified_artifact,
)
from dr_support.providers.uspec import USPEC


def _artifact_bundle(directory: Path, checkpoint: bytes = b"safe tensor fixture"):
    from dr_support.models.uspec_artifact import _MANIFEST_FIELDS

    directory.mkdir(parents=True, exist_ok=True)
    checkpoint_sha256 = hashlib.sha256(checkpoint).hexdigest()
    files_sha256 = {
        "grading_state.pt": checkpoint_sha256,
        "retina_grading_v4.py": "1" * 64,
        "uspec_adapter.py": "2" * 64,
        "offline_grading.py": "3" * 64,
        "requirements-local.txt": "4" * 64,
    }
    manifest = {**_MANIFEST_FIELDS, "files_sha256": files_sha256}
    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    (directory / "manifest.json").write_bytes(manifest_bytes)
    (directory / "grading_state.pt").write_bytes(checkpoint)
    contract = ArtifactContract(
        size=len(checkpoint),
        sha256=checkpoint_sha256,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        files_sha256=tuple(files_sha256.items()),
    )
    return contract


def _payload(model_id: str, modality: str, *, source_type: str = "SYNTHETIC") -> dict:
    raw = synthetic_image().data
    with Image.open(io.BytesIO(raw)) as decoded:
        width, height = decoded.size
    return {
        "image_id": "SYNTHETIC_USPEC",
        "modality": modality,
        "model_id": model_id,
        "image_b64": base64.b64encode(raw).decode("ascii"),
        "image_sha256": hashlib.sha256(raw).hexdigest(),
        "source_type": source_type,
        "width": width,
        "height": height,
    }


def _phase3_payload(*, source_sha256: str | None = None) -> dict:
    payload = _payload(MODEL_ID, "UWF")
    digest = payload["image_sha256"]
    source_origin = payload.pop("source_type")
    return {
        **payload,
        "invocation_id": "uspec-invocation-1234",
        "capability_id": CAPABILITY_ID,
        "task": "global",
        "model_version": MODEL_VERSION,
        "source_sha256": source_sha256 or digest,
        "source_origin": source_origin,
        "analysis_sha256": digest,
        "representation_version": REPRESENTATION,
        "transform_id": TRANSFORM,
        "request_case_revision": 0,
    }


def _model_api(monkeypatch, *, provider_set="uspec"):
    from dr_support.services.model_api import create_app

    monkeypatch.setenv("APP_PROFILE", "model_api")
    monkeypatch.setenv("MODEL_RUNTIME", "local")
    monkeypatch.setenv("MODEL_API_PROVIDER_SET", provider_set)
    monkeypatch.delenv("MODEL_REQUIRE_VERIFIED_ASSETS", raising=False)
    monkeypatch.delenv("USPEC_MODEL_DIR", raising=False)
    monkeypatch.delenv("USPEC_ENABLE_CANDIDATE_LOAD", raising=False)
    return create_app(device_strict=False)


def test_checkpoint_identity_matches_and_rejects_mismatch(tmp_path):
    contract = _artifact_bundle(tmp_path / "bundle")
    with verified_artifact(tmp_path / "bundle", contract) as (stream, observed):
        assert verify_stream(stream, contract)["sha256"] == contract.sha256
        assert observed["manifest_sha256"] == contract.manifest_sha256

    wrong = replace(contract, sha256="f" * 64)
    with pytest.raises(ValueError, match="identity mismatch"):
        with verified_artifact(tmp_path / "bundle", wrong):
            pass


def test_checkpoint_bytes_mismatch_is_rejected(tmp_path):
    contract = _artifact_bundle(tmp_path / "bundle")
    (tmp_path / "bundle" / "grading_state.pt").write_bytes(b"changed")
    with pytest.raises(ValueError, match="size mismatch|SHA-256 mismatch"):
        with verified_artifact(tmp_path / "bundle", contract):
            pass


def test_source_file_hash_verification_matches_and_rejects_mismatch(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    source = b"hash-reviewed source"
    (root / "retina_grading_v4.py").write_bytes(source)
    expected = hashlib.sha256(source).hexdigest()
    assert verify_source_files(root, {"retina_grading_v4.py": expected}) == {
        "retina_grading_v4.py": expected
    }
    with pytest.raises(ValueError, match="source SHA-256 mismatch"):
        verify_source_files(root, {"retina_grading_v4.py": "0" * 64})


def test_uspec_only_asset_verification_does_not_require_legacy_assets(monkeypatch):
    import dr_support.model_assets as assets

    monkeypatch.setenv("USPEC_MODEL_DIR", "/external/uspec-artifacts")
    monkeypatch.setattr(assets, "verify_source", lambda *args: pytest.fail("legacy source checked"))
    monkeypatch.setattr(assets, "verify_weight", lambda *args: pytest.fail("legacy weights checked"))
    monkeypatch.setattr(
        assets,
        "verify_uspec_directory",
        lambda directory: {"sha256": "a" * 64, "sha256_status": "VERIFIED_FROM_BYTES"},
    )

    result = assets.verify_assets("uspec")
    assert set(result["models"]) == {MODEL_ID}


def test_uspec_descriptor_is_uwf_only_and_artifact_absence_is_safe(monkeypatch):
    app = _model_api(monkeypatch)
    client = TestClient(app)
    health = client.get("/health").json()
    descriptors = {item["model_id"]: item for item in client.get("/v1/models").json()}

    assert health["providers"] == {MODEL_ID: "ASSET_REQUIRED"}
    assert set(descriptors) == {MODEL_ID}
    descriptor = descriptors[MODEL_ID]
    assert descriptor["task"] == "global"
    assert descriptor["capability_id"] == CAPABILITY_ID
    assert descriptor["research_model_id"] == RESEARCH_MODEL_ID
    assert descriptor["research_model_id"] != descriptor["capability_id"]
    assert descriptor["modalities"] == ["UWF"]
    assert descriptor["class_order"] == [0, 1, 2, 3, 4]
    assert descriptor["input_representation"] == REPRESENTATION
    assert descriptor["preprocessing"] == PREPROCESSING
    assert descriptor["release_status"] == "RESEARCH_ONLY"
    assert descriptor["runtime_qualification"] == "ENGINEERING_QUALIFIED"
    assert descriptor["rights_status"] == "UNVERIFIED"
    assert descriptor["clinical_validation_status"] == "NOT_ESTABLISHED"
    assert descriptor["production_authorization"] == "NOT_AUTHORIZED"

    response = client.post("/v1/predict/dr", json=_payload(MODEL_ID, "UWF"))
    assert response.status_code == 503


def test_uspec_artifact_directory_without_manifest_or_checkpoint_is_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("USPEC_MODEL_DIR", str(tmp_path))
    assert USPEC(allow_cpu_fallback=True).metadata()["status"] == "ASSET_REQUIRED"


def test_legacy_host_keeps_cfp_providers_and_uwf_never_uses_retfound(monkeypatch):
    app = _model_api(monkeypatch, provider_set="legacy")
    client = TestClient(app)
    assert set(app.state.providers) == {"retfound-aptos5", "prism-dr-5fold"}
    response = client.post("/v1/predict/dr", json=_payload("retfound-aptos5", "UWF"))
    assert response.status_code == 200
    assert response.json()["state"] == "UNSUPPORTED"
    assert response.json()["model_id"] == "retfound-aptos5"


@pytest.mark.parametrize("source_type", ["PUBLIC", "SYNTHETIC"])
def test_public_and_synthetic_v1_contracts_preserve_source_sha(monkeypatch, source_type):
    app = _model_api(monkeypatch)
    payload = _payload(MODEL_ID, "CFP", source_type=source_type)
    response = TestClient(app).post("/v1/predict/dr", json=payload)
    assert response.status_code == 200
    result = response.json()
    assert result["state"] == "UNSUPPORTED"
    assert result["provenance"]["source_type"] == source_type
    assert result["provenance"]["image_sha256"] == payload["image_sha256"]


@pytest.mark.parametrize("source_type", ["PUBLIC", "SYNTHETIC"])
def test_fake_cpu_inference_accepts_only_permitted_origins(source_type):
    torch = pytest.importorskip("torch")

    class FakeEncoder:
        def __call__(self, pixel_values):
            return SimpleNamespace(
                last_hidden_state=torch.zeros((pixel_values.shape[0], 1, 1024), device=pixel_values.device)
            )

    class FakeModel:
        encoder = FakeEncoder()

        @staticmethod
        def aggregate(features):
            assert features.shape == (1, 49, 1024)
            return torch.tensor([[-2.0, -1.0, 0.0, 1.0, 2.0]], device=features.device)

    image = replace(synthetic_image(), source_type=source_type, modality="UWF")
    provider = USPEC(allow_cpu_fallback=True)
    provider.model = FakeModel()
    provider.device = "cpu"
    result = provider.infer(
        InferenceRequest(image_id=image.image_id, modality="UWF", model_id=MODEL_ID),
        image,
    )

    assert result.grade == 4
    assert result.provenance.source_type == source_type
    assert result.provenance.image_sha256 == image.sha256
    assert result.provenance.preprocessing.startswith(PREPROCESSING)


def test_provider_converts_original_grayscale_input_to_rgb():
    torch = pytest.importorskip("torch")
    output = io.BytesIO()
    grayscale = Image.new("L", (640, 480), 20)
    grayscale.save(output, format="PNG")
    raw = output.getvalue()
    image = BridgeImage(
        image_id=hashlib.sha256(raw).hexdigest(),
        data=raw,
        source_type="SYNTHETIC",
        source="synthetic-grayscale",
        modality="UWF",
        filename="synthetic-grayscale.png",
        media_type="image/png",
        source_origin="SYNTHETIC",
    )

    class FakeEncoder:
        def __call__(self, pixel_values):
            assert pixel_values.shape[1:] == (3, 224, 224)
            return SimpleNamespace(
                last_hidden_state=torch.zeros(
                    (pixel_values.shape[0], 1, 1024), device=pixel_values.device
                )
            )

    class FakeModel:
        encoder = FakeEncoder()

        @staticmethod
        def aggregate(features):
            return torch.zeros((1, 5), device=features.device)

    provider = USPEC(allow_cpu_fallback=True)
    provider.model = FakeModel()
    provider.device = "cpu"
    result = provider.infer(
        InferenceRequest(image_id=image.image_id, modality="UWF", model_id=MODEL_ID),
        image,
    )

    assert result.state == "AI_SUGGESTION"
    assert result.provenance.image_sha256 == image.sha256


@pytest.mark.parametrize("source_type", ["WORKSPACE", "UNKNOWN"])
def test_provider_blocks_workspace_and_unknown_origins(source_type):
    image = replace(synthetic_image(), source_type=source_type, modality="UWF")
    provider = USPEC(allow_cpu_fallback=True)
    request = InferenceRequest(image_id=image.image_id, modality="UWF", model_id=MODEL_ID)

    with pytest.raises(ValueError, match="source origin is blocked"):
        provider.infer(request, image)


@pytest.mark.parametrize("origin", ["WORKSPACE", "UNKNOWN"])
def test_phase3_blocks_workspace_and_unknown_origins(monkeypatch, origin):
    app = _model_api(monkeypatch)
    payload = _phase3_payload()
    payload["source_origin"] = origin
    response = TestClient(app).post("/v2/predict/dr", json=payload)
    assert response.status_code == 409


def test_phase3_uspec_requires_original_source_rgb_context(monkeypatch):
    app = _model_api(monkeypatch)
    provider = app.state.providers[MODEL_ID]
    provider._status = "NOT_LOADED"
    received = []

    def infer(request, image):
        received.append(image.data)
        return provider._result(image, request.modality, [0.2] * 5, mask_status="FOV_ONLY")

    provider.infer = infer
    payload = _phase3_payload()
    response = TestClient(app).post("/v2/predict/dr", json=payload)

    assert response.status_code == 200
    result = response.json()
    original = base64.b64decode(payload["image_b64"])
    assert received == [original]
    assert result["input"]["source_sha256"] == payload["image_sha256"]
    assert result["input"]["analysis_sha256"] == payload["image_sha256"]
    assert result["result"]["provenance"]["image_sha256"] == payload["image_sha256"]


@pytest.mark.parametrize(
    "updates",
    [
        {"source_sha256": "a" * 64},
        {"representation_version": "phase2-uwf-v1"},
        {"transform_id": "analysis-uwf-v1"},
        {"mask_version": "analysis-uwf-retinal-mask-v1"},
        {"modality": "CFP"},
    ],
)
def test_phase3_rejects_analysis_derivative_or_inappropriate_uspec_context(monkeypatch, updates):
    app = _model_api(monkeypatch)
    payload = _phase3_payload()
    payload.update(updates)
    response = TestClient(app).post("/v2/predict/dr", json=payload)
    assert response.status_code == 422


def test_phase3_rejects_non_uspec_capability_id(monkeypatch):
    app = _model_api(monkeypatch)
    payload = _phase3_payload()
    payload["capability_id"] = "dr_grade"

    response = TestClient(app).post("/v2/predict/dr", json=payload)

    assert response.status_code == 422


def test_uspec_result_preserves_provenance_and_does_not_claim_calibration():
    image = replace(synthetic_image(), modality="UWF")
    provider = USPEC(allow_cpu_fallback=True)
    result = provider._result(
        image,
        "UWF",
        [0.05, 0.15, 0.2, 0.4, 0.2],
        mask_status="FOV_ONLY",
    )

    assert result.model_id == MODEL_ID
    assert result.grade == 3
    assert result.provenance.image_sha256 == image.sha256
    assert result.provenance.source_type == "SYNTHETIC"
    assert result.provenance.checkpoint_sha256["grading_state.pt"]
    assert result.provenance.preprocessing == f"{PREPROCESSING}; mask_status=FOV_ONLY"
    assert any("not calibrated clinical probabilities" in item for item in result.warnings)


def test_native_preprocessing_produces_49_rgb_patches_and_mask_provenance():
    pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from dr_support.imaging.uspec_preprocessing import prepare_patches

    image = synthetic_image()
    with Image.open(io.BytesIO(image.data)) as decoded:
        patches, audit = prepare_patches(decoded)

    assert len(patches) == 49
    assert all(patch.mode == "RGB" and patch.size == (224, 224) for patch in patches)
    assert audit["preprocessing"] == PREPROCESSING
    assert audit["mask_status"] in {"FOV_ONLY", "UNMASKED_FALLBACK"}

    grayscale = Image.new("L", (320, 240), 80)
    grayscale_patches, _ = prepare_patches(grayscale)
    assert all(patch.mode == "RGB" for patch in grayscale_patches)


def test_model_api_import_does_not_import_torch_or_load_checkpoints():
    script = (
        "import builtins; "
        "original = builtins.__import__; "
        "builtins.__import__ = lambda name, *a, **k: "
        "(_ for _ in ()).throw(AssertionError('torch imported')) "
        "if name == 'torch' or name.startswith('torch.') else original(name, *a, **k); "
        "importer = __import__; "
        "importer('dr_support.providers.uspec'); "
        "importer('dr_support.services.model_api')"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_safe_loader_uses_weights_only_and_never_falls_back(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")
    from dr_support.models.uspec_mil import load_verified_model

    contract = _artifact_bundle(tmp_path / "bundle")
    observed_kwargs = []

    def safe_load(stream, **kwargs):
        observed_kwargs.append(kwargs)
        return {"weight": torch.ones((2, 1)), "bias": torch.zeros(2)}

    monkeypatch.setattr(torch, "load", safe_load)
    model, observed = load_verified_model(
        tmp_path / "bundle",
        device="cpu",
        contract=contract,
        factory=lambda: torch.nn.Linear(1, 2),
    )

    assert model.training is False
    assert observed["sha256"] == contract.sha256
    assert len(observed_kwargs) == 1
    assert observed_kwargs[0]["weights_only"] is True
    assert observed_kwargs[0]["map_location"] == "cpu"


def test_safe_loader_rejects_quantized_state_before_model_load(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")
    from dr_support.models.uspec_mil import load_verified_model

    contract = _artifact_bundle(tmp_path / "bundle")
    state = {
        "weight": torch.quantize_per_tensor(torch.ones((2, 1)), 0.1, 0, torch.qint8),
        "bias": torch.zeros(2),
    }
    monkeypatch.setattr(torch, "load", lambda *args, **kwargs: state)
    load_state_dict_called = False

    class LinearWithoutLoading(torch.nn.Linear):
        def load_state_dict(self, *args, **kwargs):
            nonlocal load_state_dict_called
            load_state_dict_called = True
            return super().load_state_dict(*args, **kwargs)

    with pytest.raises(ValueError, match="reviewed dense state dictionary"):
        load_verified_model(
            tmp_path / "bundle",
            device="cpu",
            contract=contract,
            factory=lambda: LinearWithoutLoading(1, 2),
        )

    assert not load_state_dict_called


def test_strict_uspec_runtime_rejects_cpu_device(monkeypatch, tmp_path):
    from dr_support.runtime import DeviceUnavailable

    monkeypatch.setenv("USPEC_MODEL_DIR", str(tmp_path))
    monkeypatch.setenv("USPEC_ENABLE_CANDIDATE_LOAD", "1")
    monkeypatch.setenv("INFERENCE_DEVICE", "cpu")
    provider = USPEC(allow_cpu_fallback=False)

    with pytest.raises(DeviceUnavailable, match="requires CUDA"):
        provider.load()
