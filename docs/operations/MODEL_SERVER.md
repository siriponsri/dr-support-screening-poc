<!-- canonical-topic: model-api -->

# Model Server

The Model API is the hospital-side inference service. It supports the existing provider-neutral contract only; it does not add MRI, OCT, PACS, DICOMweb, calibration, or explainability models.

## One-time online setup

```bash
cd /opt/dr-support-screening-poc
./scripts/model-server/setup.sh
```

The setup script:

1. Requires Python 3.11 or 3.12 and creates `.venv`.
2. Installs the project plus model and DICOM extras.
3. Clones RETFound and PRISM-DR at the pinned detached revisions.
4. Downloads the approved RETFound checkpoint and PRISM weight archive.
5. Verifies source cleanliness, revision pins, archive SHA-256, and all checkpoint file hashes.
6. Runs one synthetic RETFound and PRISM inference on the configured device.
7. Prints `READY` only when verification and smoke inference succeed.

The setup path may use the internet. It writes assets under `local-state/bridge` by default; this directory is runtime state and must not be committed. Override `RETFOUND_SOURCE`, `RETFOUND_WEIGHTS`, `PRISM_SOURCE`, or `PRISM_WEIGHTS` only with paths containing the same verified assets.

## Pinned provenance

- RETFound source revision: `ae9a9ecf37857cf47b8aa9f87cd6f710d75db287`.
- RETFound checkpoint SHA-256: `a96b9dbcb78eff373912fb0a48d316dc35ffb0715bb2a1b9128b096d780edbbf`.
- PRISM-DR source revision: `79637440a535e4f8118e939d3787121f82180125`.
- PRISM archive SHA-256: `966a38bade7ed9049d5bc4b91a3adebb8f4c92afba64386abf6ab13a537c3b49`.
- Individual PRISM file hashes: `dr_support/providers/prism_assets.json`.

The RETFound source is [rmaphoh/RETFound](https://github.com/rmaphoh/RETFound)
and is licensed CC BY-NC 4.0. The PRISM-DR source is
[zubeyrozeren/PRISM-DR](https://github.com/zubeyrozeren/PRISM-DR); its code is
MIT and its released weights are described upstream for academic use. PRISM-DR
also uses Ultralytics components under AGPL-3.0. These research-use terms do
not establish commercial or clinical deployment clearance.

## Normal startup

```bash
./scripts/model-server/start.sh
```

Startup sets `APP_PROFILE=model_api`, `MODEL_RUNTIME=local`, `INFERENCE_DEVICE=cuda:0`, `HOST=0.0.0.0`, `PORT=7860`, `WORKERS=1`, and `MODEL_REQUIRE_VERIFIED_ASSETS=1` unless the operator overrides the documented non-secret host/device values. It first runs:

```bash
.venv/bin/python -m dr_support.setup_models --model all --verify
```

That command never downloads or mutates assets. If verification fails, startup stops with an actionable error. Model weights are loaded lazily on the first inference, but the source and checkpoint integrity gate is performed before the service becomes ready.

## Health and model metadata

```bash
./scripts/model-server/healthcheck.sh
curl --fail http://127.0.0.1:7860/health
curl --fail http://127.0.0.1:7860/v1/models
```

`/health` reports `status`, device information, and `assets_verified`. A verified service reports `status: PASS` and `assets_verified: true`. `/v1/models` reports the stable model IDs `retfound-aptos5` and `prism-dr-5fold`, task, revision, modality, device, status, warnings, and preprocessing.

## Inference contract

- `POST /v1/predict/dr` runs RETFound for a CFP fundus image.
- `POST /v1/predict/lesions` runs PRISM-DR for a CFP fundus image.
- Source image SHA-256 and provenance are preserved in the response.
- PRISM rectangles are returned in original-image pixel coordinates.
- Empty lesion output is valid evidence and is not proof of no lesions.
- The review workstation calls its existing `/v1/infer/*` routes; it does not load local weights.

## CUDA and offline acceptance

Production model API startup expects CUDA. A missing GPU or unavailable CUDA runtime is a readiness failure, not a silent CPU fallback. After setup, disable internet access and verify `/health`, `/v1/models`, one grade request, and one lesion request. CVAT Online is optional and not part of the offline path.
