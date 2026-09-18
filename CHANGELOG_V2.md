# Changelog — V2 UI/UX Redesign

## 0.2.0 — 2026-09-18

### Added
- Clinician-first Case Review hero experience:
  - Large retinal image viewer with zoom, pan, and fit controls.
  - Lesion overlay toggle and per-class filters.
  - Right-side AI Review panel with grade suggestion, probabilities, lesion summary, warnings, and review status.
  - Sticky bottom action bar: Accept, Adjust Grade, Needs Annotation, Escalate, Advanced Edit.
- Unified **Analyze** action that runs both global grading and lesion ROI inference in one step.
- V2 implementation plan at `docs/V2_IMPLEMENTATION_PLAN.md`.

### Changed
- Reduced product navigation to three views: **Worklist**, **Case Review**, **Models & Audit**.
- Combined grade review and lesion annotation into a single Case Review screen.
- CVAT preparation, pre-label push, and sync are now hidden behind **Advanced Edit**; the live
  CVAT round-trip remains available via the same backend endpoints.
- Visual redesign:
  - Removed all visible "KKU" text and logos.
  - Neutral premium clinical palette with `#A73B24` retained only as a subtle accent.
  - Generous whitespace, subtle borders, restrained shadows, improved typography.
- Updated `PREVIEW.html` for the new layout and disabled controls.
- Updated `README.md` and `docs/LOCAL_RUNBOOK.md` to describe the new workflow.
- Updated `docs/UI_THEME.md` to reflect the v2 palette.

### Fixed
- Backend test failure on Windows caused by `socket.connect` monkeypatch blocking asyncio
  `socketpair()` used by `TestClient`; `tests/conftest.py` now permits localhost-only socket
  plumbing.

## 0.2.1 — 2026-09-18

### Added
- Provider-neutral **REMOTE** inference mode (opt-in via `MODEL_RUNTIME=remote`).
  - `REMOTE_MODEL_URL` points the backend at an external Remote Model API.
  - `REMOTE_MODEL_TOKEN` is read from the environment only and sent as `Authorization: Bearer ...`;
    it is never returned by the API, persisted, or surfaced in the UI.
  - Backend proxies `/v1/predict/dr` and `/v1/predict/lesions`; preserves the existing
    `GlobalResult`/`LesionResult` Bridge v1 schema and the existing `/v1/models` metadata contract.
  - Inference latency and remote runtime status are surfaced in the Models & Audit metadata.
  - Clear timeout (504) and remote-error (502) responses; local-mode 503 path preserved.
- New tests with a mocked remote transport (`tests/test_remote.py`) covering success, timeout,
  non-2xx, malformed schema, token isolation, and metadata surfacing.

### Changed
- Action-bar hierarchy: primary review actions (Accept, Adjust Grade, Needs Annotation, Escalate) are now visually grouped; Advanced Edit/CVAT is separated and de-emphasized with a subtle style and external-link hint.
- Simplified clinical copy: "Model & provenance" → "Model details", "Preprocessing" → "Image preparation", and tightened lesion-help text.
- Improved empty-state guidance in the AI Review panel.
- Fixed a redundant disabled-condition in the Advanced Edit button template.
- Improved skip-link accessibility styling and focus visibility.

### Preserved
- Backend API contracts for `/v1/cases`, `/v1/infer/*`, `/v1/cases/{id}/review`, CVAT round-trip,
  persisted review state, and AI-vs-clinician overlay semantics unchanged.
- Local RETFound/PRISM and synthetic-mock providers remain the default and continue to work.
- Lesion colors remain independent from UI semantic colors.
- CVAT_TOKEN and REMOTE_MODEL_TOKEN remain environment-only; no secrets hardcoded or exposed.

## 0.3.0 — 2026-09-18

### Added
- Single-repo, multi-runtime-profile architecture selected via `APP_PROFILE`:
  - `review`     clinician workstation; UI, cases, review, CVAT, remote-proxy. Must not load weights.
  - `model_api`  GPU deployment of the Remote Model API contract.
  - `full`       both surfaces mounted together for public/synthetic demos.
- `dr_support.app.create_app()` top-level dispatcher with strict profile/runtime invariants.
- New `dr_support/services/model_api.py` implementing the Remote Model API contract:
  - `GET /health`, `GET /v1/models`, `POST /v1/predict/dr`, `POST /v1/predict/lesions`.
  - Bearer-token enforcement via `REMOTE_MODEL_TOKEN` (constant-time compare, never logged).
  - Bridges existing `RETFound` and `PRISM` provider classes — no model code is duplicated.
  - `/v1/predict/*` returns `503 ASSET_REQUIRED` until weights are configured on the GPU host.
- New `Dockerfile` and `docker-entrypoint.sh` for Hugging Face Docker Space deployment
  (Nvidia T4 small target; `APP_PROFILE=model_api`, `MODEL_RUNTIME=local`, `PORT=7860`).
- 19 new tests in `tests/test_profiles.py` covering profile dispatch, invariants,
  bearer enforcement, envelope validation, and an end-to-end review → model_api proxy smoke.

### Changed
- `dr_support/contracts.py` → `dr_support/contracts/` package (no public API change).
- `dr_support/api.py` → `dr_support/api/` package (no public API change; `from dr_support.api import create_app` still works).
- `pyproject.toml` bumped to `0.3.0` and now ships a `dr-support-run` console script.
- `.env.example` reorganised into profile/runtime sections; new `APP_PROFILE`, `HOST`, `PORT`, `WORKERS` knobs.
- `dr_support.run` now composes the right uvicorn command per profile and can be invoked as a module.

### Preserved
- V2 clinician UI unchanged.
- `/v1/cases`, `/v1/infer/*`, `/v1/cases/{id}/review`, `/v1/cases/{id}/cvat/{send,sync}` contracts unchanged.
- Persisted review state and CVAT round-trip semantics unchanged.
- AI-vs-clinician overlay distinction and lesion overlay colors unchanged.
- The remote provider adapter (M0 of the prior milestone) is unchanged and remains the
  consumer of the new `model_api` surface.
- Real GPU model code paths (`RETFound`, `PRISM`) are unchanged; they continue to load
  weights only when configured and are reused by both the review and model_api surfaces.

## 0.4.0 — 2026-09-18 (M0.5 GPU deployment hardening)

### Added
- New `dr_support/runtime/device.py` — single source of truth for
  `INFERENCE_DEVICE`. Lazily probes `torch.cuda`, exposes a cached
  `DeviceSnapshot`, and refuses to silently fall back to CPU in production.
- Provider constructors accept `allow_cpu_fallback`. The production
  `model_api` factory wires providers with `allow_cpu_fallback=False`; tests
  pass `True`.
- `RETFound` and `PRISM` metadata now report `requested_device`,
  `effective_device`, and `cuda_available`. A warning is added when the
  requested GPU device is unavailable so operators see the mismatch.
- `/health` response on the `model_api` (and review) service surfaces
  `requested_device`, `effective_device`, `cuda_available`,
  `cuda_device_count`, and `cuda_device_name`. Returns `FAIL` when a CUDA
  device is requested but no CUDA runtime is visible.
- `/v1/models` entries echo the same device fields.
- 22 new tests in `tests/test_device.py` covering resolver behaviour,
  provider metadata, factory strict-mode refusal, and `/health` / `/v1/models`
  surfacing.

### Changed
- `RETFound.infer` now moves the input tensor to the resolved device and uses
  `torch.inference_mode()`. The provider also disables autograd on every
  parameter at load time. The checkpoint still loads via `map_location='cpu'`
  to avoid host-CPU bottlenecks during weight IO.
- `PRISM.load` moves the ROI YOLO cropper, every fold's ultralytics YOLO, and
  every SAHI `AutoDetectionModel` to the resolved device.
- `PRISM.infer` passes `device=str(device)` to the ROI YOLO and the SE-fold
  YOLO calls instead of the hard-coded `device='cpu'`. A `finally` clause
  invokes `torch.cuda.empty_cache()` on the resolved device to release any
  intermediate CUDA tensors held by the autograd engine.
- Dockerfile hard-pinned to a single-stage `nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04`
  base with Python 3.12 installed via the deadsnakes PPA. The image bakes the
  project source, the `[models,test]` extras, and the verified model assets
  (`setup_models --model all`) at build time. No GPU-only commands run during
  build.
- `docker-entrypoint.sh` is now wired via the Dockerfile's `ENTRYPOINT`
  directive. It only validates environment variables (APP_PROFILE,
  MODEL_RUNTIME, REMOTE_MODEL_URL for the review profile, presence of the
  pre-built assets for the model_api / full profile, `WORKERS=1`) before
  execing `python -m dr_support.run`. The duplicate `setup_models` call was
  removed.
- `.env.example` adds `INFERENCE_DEVICE` and the test-only
  `DR_SUPPORT_RELAX_DEVICE` knob.
- Bumped project version to `0.4.0`.

### Preserved
- Bridge v1 `GlobalResult`/`LesionResult` schema unchanged.
- `/v1/cases`, `/v1/infer/*`, `/v1/cases/{id}/review`, CVAT round-trip and
  persisted review state unchanged.
- Profile / runtime invariants from v0.3.0 (`review` + `MODEL_RUNTIME=local`
  still rejected, `model_api/full` + `MODEL_RUNTIME=remote` still rejected).
- Checkpoint SHA256 verification, preprocessing, class order, thresholds,
  ensemble logic, and label mapping in PRISM unchanged.
- Thresholds and ensemble outputs of PRISM not modified to fit memory.
- V2 clinician UI untouched.
- Public/synthetic POC only; no scientific claims.

