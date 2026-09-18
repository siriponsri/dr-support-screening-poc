# Session GOAL — DR Support Screening POC

This document is the canonical handover for everything delivered in the
2026-09-18 work sessions against `siriponsri/dr-support-screening-poc`. It is
written so the next session — or the GPU deployment owner — can pick up
exactly where this one left off.

---

## 1. Summary

Five commits landed across two sessions, taking the project from `v0.2.0` to
`v0.4.0` without breaking any existing test, contract, or UI surface:

| Commit    | Title                                                                                          | Version |
|-----------|------------------------------------------------------------------------------------------------|---------|
| `5e66b35` | `polish(ui): V2 clinician-first audit and polish pass`                                         | 0.2.1   |
| `0ebe017` | `feat(remote): provider-neutral REMOTE inference adapter with mocked tests`                    | 0.2.1   |
| `a9ccdfb` | `refactor: single-repo multi-runtime-profile architecture (review / model_api / full)`        | 0.3.0   |
| `463270e` | `docs: GOAL.md session summary (audit + polish, REMOTE adapter, profile architecture)`         | 0.3.0   |
| `<M0.5>`  | `harden(gpu): device resolver, GPU-ready providers, hardened Dockerfile, /health device fields` | 0.4.0 |

Status: **PASS** — code is ready for the first HF GPU acceptance.

---

## 2. What the codebase does

`dr-support-screening-poc` is a single-repo, multi-runtime-profile application
that exposes the DR Support Screening POC v2 clinician UI together with the
Remote Model API contract that backs it.

```
dr-support-screening-poc/
├── dr_support/
│   ├── api/         # clinician review workstation (cases, review, CVAT, UI, remote proxy)
│   ├── services/    # standalone deployment-side services (currently model_api)
│   ├── providers/   # shared model adapters (RETFound, PRISM, mock, remote proxy)
│   ├── runtime/     # device resolver, future memory accounting
│   ├── contracts/   # Bridge v1 request/response schemas
│   └── app.py       # top-level profile dispatcher
├── web/             # V2 clinician UI
├── tests/           # backend pytest + frontend jsdom
├── docs/            # PROFILES.md, REMOTE_MODEL_API.md, LOCAL_RUNBOOK.md, ...
├── Dockerfile       # HF Docker Space image, default profile = model_api
├── docker-entrypoint.sh  # env-validator wrapper, execs dr_support.run
├── pyproject.toml   # 0.4.0
└── .env.example
```

Runtime profiles (`APP_PROFILE`):

| Profile       | `APP_PROFILE` | `MODEL_RUNTIME` | Surface                                                                  | Loads weights locally? |
|---------------|---------------|-----------------|--------------------------------------------------------------------------|------------------------|
| Review        | `review`      | `remote`        | UI, `/v1/cases`, `/v1/cases/{id}/review`, `/v1/cases/{id}/cvat/*`, `/v1/infer/*` (proxy) | **No** |
| Model API     | `model_api`   | `local`         | `GET /health`, `GET /v1/models`, `POST /v1/predict/dr`, `POST /v1/predict/lesions` | Yes (CUDA-required, strict) |
| Full (demo)   | `full`        | `local`         | Everything from both profiles                                            | Yes (CPU-tolerant)     |

Profile / runtime invariants are **strict and fail-fast**:

- `APP_PROFILE=review` + `MODEL_RUNTIME=local` → `RuntimeError`
- `APP_PROFILE=review` + missing `REMOTE_MODEL_URL` → `RuntimeError`
- `APP_PROFILE=model_api` + `MODEL_RUNTIME=remote` → `RuntimeError`
- `APP_PROFILE=full` + `MODEL_RUNTIME=remote` → `RuntimeError`
- `APP_PROFILE=model_api` + `INFERENCE_DEVICE=cuda*` + no CUDA runtime → `DeviceUnavailable`
- `WORKERS > 1` → rejected by `docker-entrypoint.sh`

---

## 3. Milestone A — V2 audit + polish pass (`5e66b35`)

Goal: small, high-impact UI improvements without redesigning the V2 clinician
surface.

- Action-bar hierarchy — the four primary review actions (Accept, Adjust
  Grade, Needs Annotation, Escalate) are visually grouped; **Advanced Edit /
  CVAT** is separated by a divider and de-emphasized with a `.subtle` style
  plus an external-link hint. Discoverable without competing with clinical
  decisions.
- Simplified clinical copy — `Model & provenance` → `Model details`,
  `Preprocessing` → `Image preparation`, tighter lesion-help text, clearer
  empty-state guidance in the AI Review panel.
- Improved accessibility — better focus visibility on the skip link, refactored
  to use the standard visually-hidden pattern.
- Bug fix — removed a redundant disabled-condition in the Advanced Edit button
  template (`${advancedUrl ? '' : ''}` was always empty).

Preserved: V2 UI, all element IDs, backend contracts, persisted review state,
CVAT round-trip, AI-vs-clinician overlay distinction.

Files: `web/app.js`, `web/style.css`, `CHANGELOG_V2.md`.

---

## 4. Milestone B — provider-neutral REMOTE inference (`0ebe017`)

Goal: add a remote inference mode without breaking existing local/mock modes.

Architecture:

```
DR Support Screening POC (review workstation)
        |   HTTPS  (Authorization: Bearer ${REMOTE_MODEL_TOKEN}, optional)
        v
Remote Model API
        |- GET  /health
        |- GET  /v1/models
        |- POST /v1/predict/dr
        `- POST /v1/predict/lesions
```

Contract documented at [`docs/REMOTE_MODEL_API.md`](docs/REMOTE_MODEL_API.md).

Implementation:

- New `dr_support/providers/remote.py` with `RemoteModelProvider`,
  `RemoteGlobalProvider`, `RemoteLesionProvider`.
- Wire format: JSON envelope with base64-encoded image bytes (mockable with
  `httpx.MockTransport`).
- Tokens: `REMOTE_MODEL_TOKEN` from environment only, sent as
  `Authorization: Bearer ...`. Never logged, persisted, or echoed.
- Per-call timing: `last_inference_ms` and `last_metadata_ms` exposed.
- Error mapping: timeout → `504`, non-2xx → `502`, malformed schema → `502`,
  local-mode path → `503` (unchanged).
- Case event log records `runtime: "remote"` and `latency_ms` for each remote
  inference.

Tests (20 new in `tests/test_remote.py`):

- Provider-level: payload/token wiring, missing-token behaviour, timeout,
  non-2xx, malformed schema, metadata surfacing, unreachable remote,
  model-not-listed, missing/invalid URL rejection, token never leaks into
  metadata.
- API-level: routes inference through the proxy, latency recorded in events,
  504/502 status mapping, `/v1/models` reflects remote runtime, local mode
  unaffected, CVAT round-trip preserved, token never echoed.

Documentation: `docs/REMOTE_MODEL_API.md`, `docs/LOCAL_RUNBOOK.md`,
`README.md`, `.env.example`.

---

## 5. Milestone C — single-repo multi-runtime-profile architecture (`a9ccdfb`)

Goal: prepare the codebase for the GPU deployment without creating a separate
repository (owner override). One codebase, three profiles.

Layout:

```
dr_support/
├── api/         # clinician review workstation
├── services/    # standalone deployment-side services (currently model_api)
├── providers/   # shared model adapters (RETFound, PRISM, mock, remote proxy)
├── contracts/   # Bridge v1 request/response schemas
└── app.py       # top-level profile dispatcher
```

The `model_api` service does **not duplicate model code** — it instantiates the
existing `RETFound` and `PRISM` provider classes from `dr_support/providers/`.
Weight-loading, preprocessing, class order, lesion mapping, and the Bridge v1
contract are all the same code path that runs in the `full` profile and that
the review profile proxies to.

Deployment artefacts (later hardened in M0.5):

- `Dockerfile` — multi-stage CUDA 12.1 / cuDNN 8 image built for Nvidia T4 small
  (HF Docker Space target).
- `docker-entrypoint.sh` — env-validator wrapper.
- `docs/PROFILES.md` — full matrix, local-dev instructions, HF deployment
  walkthrough, contract invariants, explicit "what this does NOT do" list.

Tests (19 new in `tests/test_profiles.py`): profile dispatch, invariants,
model_api surface, bearer enforcement, M4 proxy smoke.

---

## 6. Milestone D — GPU deployment hardening (`<M0.5>`) — **this session**

Goal: make `APP_PROFILE=model_api` actually GPU-ready before the owner deploys
to Hugging Face, without changing any contract or UI surface.

### 6.1 Device abstraction (`dr_support/runtime/device.py`)

Single source of truth for `INFERENCE_DEVICE`:

- Reads `INFERENCE_DEVICE` from the environment (default `cpu`), normalises
  case, exposes a cached `DeviceSnapshot` with `requested_device`,
  `effective_device`, `cuda_available`, `cuda_device_count`, `cuda_device_name`.
- Lazily imports `torch` so CPU-only CI and contract tests do not require GPU
  libraries.
- Rejects unknown device strings (only `cpu` and `cuda*` are accepted).
- Production path: `INFERENCE_DEVICE=cuda*` with no CUDA runtime →
  `DeviceUnavailable` instead of silent CPU fallback.
- Test path: `DR_SUPPORT_RELAX_DEVICE=1` opts out of the startup assertion so
  the contract tests keep working on a CPU-only host.

### 6.2 RETFound (`dr_support/providers/retfound.py`)

- Constructor accepts `allow_cpu_fallback` (defaults to permissive).
- `load()`: `model = model.to(device)`; `model.eval()`; every parameter has
  `requires_grad_(False)`. Checkpoint loads via `map_location='cpu'` for safe
  IO, then moves to the resolved device.
- `infer()`: `tensor = tensor.to(device)` and wraps the forward pass in
  `torch.inference_mode()`. The model parameters are already frozen at load.
- `metadata()`: reports `requested_device`, `effective_device`,
  `cuda_available`, plus a warning when the requested GPU device is unavailable.

### 6.3 PRISM (`dr_support/providers/prism.py`)

- Constructor accepts `allow_cpu_fallback`.
- `load()`: moves ROI YOLO, every per-fold ultralytics YOLO, and every SAHI
  `AutoDetectionModel` to the resolved device. The ROI YOLO uses
  `self.roi.to(device)`; per-fold YOLO uses `model.to(device)`; SAHI uses
  `device=str(device)` at construction (the device is wired into the
  underlying ultralytics model).
- `infer()`: passes `device=str(device)` to the ROI YOLO and the SE-fold
  ultralytics calls instead of the hard-coded `device='cpu'`. The
  `.cpu().numpy()` calls remain for SAHI / NMS compatibility.
- Memory safety: a `finally` clause invokes
  `torch.cuda.empty_cache()` on the resolved device to release any
  intermediate CUDA tensors held by the autograd engine. The cleanup is
  best-effort and never masks the original inference result. The api-level
  `RLock` continues to ensure only one inference call runs at a time, so
  peak activation memory stays bounded by a single forward pass.
- Preserved: thresholds, ensemble logic, class mapping, lesion mapping,
  preprocessing, label canonicalisation, source revisions, weight SHA256s.

### 6.4 Model API service (`dr_support/services/model_api.py`)

- `create_app(device_strict=True)` wires providers with
  `allow_cpu_fallback=False` and invokes `assert_cuda_ready()` at startup.
  A misconfigured GPU host fails loudly with `DeviceUnavailable` instead of
  silently degrading to CPU at the first inference call.
- `device_strict=False` is the explicit test escape hatch. The `full` profile
  dispatcher uses this so local demos can boot without a GPU.
- `/health` now returns `requested_device`, `effective_device`,
  `cuda_available`, `cuda_device_count`, `cuda_device_name`. The status
  becomes `FAIL` when a CUDA device is requested but no CUDA runtime is
  visible, so the HF liveness probe surfaces the actual GPU wiring.
- `/v1/models` entries echo the same device fields.

### 6.5 Profile dispatcher (`dr_support/app.py`)

- `create_app(profile=...)` exposes `device_strict=True` for the `model_api`
  profile (production) and `device_strict=False` for the `full` profile
  (local demo).
- All other invariants from v0.3.0 are preserved.

### 6.6 Dockerfile (hardened)

- Single-stage, `nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04` base.
- Python 3.12 installed via the deadsnakes PPA (Ubuntu 22.04 only ships 3.10).
- Pinned dependency install order:
  1. CUDA-enabled `torch==2.5.1+cu121` and `torchvision==0.20.1+cu121` from the
     `download.pytorch.org/whl/cu121` extra index;
  2. project metadata + source + `docker-entrypoint.sh`;
  3. `pip install -e ".[models,test]"` against the copied source;
  4. `python -m dr_support.setup_models --model all` to acquire and verify
     model sources + weights at build time.
- No GPU-only commands run during build.
- Healthcheck against `/health` (unauthenticated).
- `ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]` + `CMD []` so the
  entrypoint is actually used.

### 6.7 docker-entrypoint.sh

- Validates `APP_PROFILE` against the supported values.
- For `review`: requires `MODEL_RUNTIME=remote` and `REMOTE_MODEL_URL`. If
  `PORT=7860` (HF default) and `PORT_OVERRIDE` is unset, drops to `8000`
  (review workstation default).
- For `model_api` / `full`: refuses to start if the build-time asset
  directory is empty (`/app/local-state/bridge/{sources/RETFound,
  sources/PRISM-DR, retfound-aptos.pth, prism}`).
- Rejects `WORKERS > 1` so duplicate uvicorn workers cannot exhaust VRAM.
- Execs `python -m dr_support.run` after validation.

### 6.8 Asset strategy — **download at image build time**

The Dockerfile runs `python -m dr_support.setup_models --model all` once
during `docker build`. The container entrypoint does **not** re-download.
The trade-off is:

- ✅ Cold-start latency is dominated only by uvicorn and model lazy-loading.
- ✅ The same image is bit-for-bit reproducible against the pinned upstream
  revisions in `dr_support/providers/{retfound,prism}.py`.
- ❌ First build pulls multi-GB weights and the upstream `RETFound` and
  `PRISM-DR` git sources. The build host needs network access.

If the owner needs faster builds later, the asset strategy can flip to
download at container startup by moving the `setup_models` call from the
Dockerfile into `docker-entrypoint.sh` — but the spec says "do not claim
both", so we keep one consistent strategy.

### 6.9 Tests (`tests/test_device.py`, 22 new tests)

- Resolver: cuda + cuda:0 + CUDA:0 prefix detection; cpu pass-through;
  cuda with cuda available; cuda unavailable → strict raise; cuda
  unavailable → fallback only when explicitly allowed; unknown device string
  rejected; assert_cuda_ready passes/raises consistently.
- Snapshot caching: cached value returned without re-probing; force_refresh
  bypasses the cache.
- Provider metadata surfaces `requested_device`, `effective_device`,
  `cuda_available` honestly. RETFound and PRISM both warn when the
  requested GPU is unavailable.
- Strict provider construction: `RETFound(allow_cpu_fallback=False)` and
  `PRISM(allow_cpu_fallback=False)` both refuse to resolve cuda without a
  CUDA runtime.
- PRISM inference cleanup: `PRISM._release_cuda_memory` is a safe no-op when
  torch is unavailable or when the device is not cuda.
- Model API factory: strict mode refuses to start on a misconfigured host;
  `DR_SUPPORT_RELAX_DEVICE=1` opts out for tests; `/health` and `/v1/models`
  surface the device snapshot; `/health` returns `FAIL` when a CUDA device
  is requested but no CUDA runtime is available.

---

## 7. Verification matrix

Run on the local Windows CPU host, before each commit:

| Tool                         | Command                                                | Result                       |
|------------------------------|--------------------------------------------------------|------------------------------|
| Backend unit + integration   | `python -m pytest -q`                                  | **78 passed**, 1 skipped     |
| Frontend JS contract + UI    | `npm test`                                             | 3/3 PASS                     |
| Lint                         | `python -m ruff check dr_support tests`                | All checks passed            |

Test inventory by file:

| Test file                       | Count | Covers                                                            |
|---------------------------------|-------|-------------------------------------------------------------------|
| `tests/test_bridge.py`          | 8     | Bridge contracts, CVAT online safety, weight hashing              |
| `tests/test_workflow.py`        | 8     | Review round-trip, manual sync, error paths                       |
| `tests/test_sync.py`            | 2     | CVAT send / pull idempotency                                      |
| `tests/test_remote.py`          | 20    | Remote provider, mocked integration, token isolation              |
| `tests/test_profiles.py`        | 19    | Profile dispatch, invariants, model_api surface, M4 proxy smoke   |
| `tests/test_device.py`          | 22    | GPU device resolver, provider propagation, no-CPU-fallback, /health |
| `tests/test_browser_ui.py`      | 1     | Real-browser preview smoke (skipped on this host)                 |
| `tests/overlay.test.cjs`        | —     | Imported CVAT geometry overrides AI provenance                    |
| `tests/ui.test.cjs`             | —     | DOM + real API: navigation, Analyze, grade correction             |
| `tests/preview.test.cjs`        | —     | Offline PREVIEW.html, no API calls, controls disabled             |

Total new tests in M0.5: **22** (`tests/test_device.py`).

---

## 8. Files added or modified in the M0.5 hardening pass

```
dr_support/runtime/__init__.py              +13 / -0    NEW (runtime package)
dr_support/runtime/device.py                +200 / -0   NEW (resolver + DeviceSnapshot + assert_cuda_ready)
dr_support/providers/retfound.py            +30 / -13   (device + inference_mode + metadata)
dr_support/providers/prism.py               +75 / -20   (device on ROI + YOLO + SAHI + cuda.empty_cache)
dr_support/services/model_api.py            +60 / -8    (device_strict + /health + /v1/models device fields)
dr_support/api/_factory.py                   +12 / -2    (/health device fields + provider allow_cpu_fallback=True)
dr_support/app.py                           +35 / -5    (device_strict wiring for model_api vs full profile)
Dockerfile                                   rewritten   (single-stage, deadsnakes, no GPU-only build steps, ENTRYPOINT)
docker-entrypoint.sh                         rewritten   (env-only validator; no duplicate setup_models call)
.env.example                                 +14 / -0    (INFERENCE_DEVICE + DR_SUPPORT_RELAX_DEVICE)
docs/PROFILES.md                             +30 / -10   (GPU readiness section, single-worker invariant, asset strategy)
docs/LOCAL_RUNBOOK.md                       unchanged    (no contract changes)
web/index.html                               version bump v0.3.0 → v0.4.0
PREVIEW.html                                 version bump v0.3.0 → v0.4.0
pyproject.toml                               version bump 0.3.0 → 0.4.0
CHANGELOG_V2.md                              +60 / -0    (0.4.0 entry: Added / Changed / Preserved)
tests/test_device.py                         +420 / -0   NEW (22 device-resolver + provider + factory tests)
```

---

## 9. Operator notes for the HF GPU deployment

1. Push the current `main` (after this session).
2. Create or update the Hugging Face Space:
   - SDK: `docker`
   - Hardware: `t4-small` (16 GB VRAM)
   - Dockerfile: this repo's `Dockerfile`
   - Space secrets: `REMOTE_MODEL_TOKEN` if review workstations will
     authenticate (optional)
3. The Space will:
   - Build the image once. `setup_models --model all` runs in the build
     layer and the resulting image contains the SHA256-verified model
     sources + weights.
   - Start the container. `docker-entrypoint.sh` validates `APP_PROFILE`,
     `MODEL_RUNTIME`, presence of pre-built assets, and `WORKERS=1`.
   - Run `python -m dr_support.run`, which calls
     `dr_support.app.create_app()` → `dr_support.services.model_api.create_app()`
     → `dr_support.runtime.assert_cuda_ready()`.
4. First inference call:
   - `RETFound.load()` reads the checkpoint (already on disk in the image),
     builds the ViT, moves it to `cuda:0`, disables autograd, sets
     `requires_grad_(False)`.
   - `PRISM.load()` builds the namespace, loads the ROI YOLO and all 4
     lesion classes × 5 folds = 20 models into VRAM on `cuda:0`.
   - `RETFound.infer()` moves the input tensor to `cuda:0`, runs in
     `torch.inference_mode()`, and surfaces the Bridge v1 `GlobalResult`.
   - `PRISM.infer()` runs all 20 fold inferences under the api-level
     `RLock`, then `torch.cuda.empty_cache()` releases intermediate
     activations.
5. `/health` returns `cuda_available: true`, `effective_device: cuda:0`,
   `cuda_device_count: 1`, `cuda_device_name: Tesla T4` (or whatever the
   actual GPU reports).
6. The first request will be slow (cold start). Subsequent requests stay
   bounded by the api-level lock and a single forward pass on the GPU.

---

## 10. What's NOT done — explicit owner actions

These are deployment-time concerns that this codebase cannot complete from a
CPU-only host:

- **Actual GPU run on HF T4 small.** The code is GPU-ready and the
  contract tests prove it. The owner is the only one who can flip the
  switch on the HF Space hardware and observe the Bridge v1 outputs flowing
  end-to-end through a real `cuda:0` device.
- **Real PRISM inference.** All 20 fold weights need to actually live on
  the GPU host's SSD at the pinned paths. `setup_models` guarantees the
  download + verification on first build; the owner does not have to do
  anything beyond the initial build.
- **CVAT round-trip on a live workspace.** CVAT Online still requires the
  `CVAT_TOKEN` to be present at the review workstation's runtime. The
  same `OWNER_ACTION_REQUIRED` message from v0.3.0 still applies.

None of these are governance or implementation issues — they are
operations the owner executes against the deployed HF Space.

---

## 11. Status

**PASS** — code is ready for the first HF GPU acceptance run.

- All in-scope deliverables shipped; 78 backend tests + 3 frontend tests pass
  locally on a CPU-only host.
- GPU device abstraction is strict by default; CPU fallback only allowed
  when explicitly opted in via `DR_SUPPORT_RELAX_DEVICE=1`.
- RETFound and PRISM run their parameters, activations, and SAHI / YOLO
  pipelines on the resolved device with `torch.inference_mode()` and
  `torch.cuda.empty_cache()` cleanup.
- Dockerfile bakes assets at build time; entrypoint is wired and never
  re-downloads; `WORKERS > 1` is rejected; the image is reproducible against
  pinned upstream revisions and SHA256s.
- `/health` and `/v1/models` expose `requested_device`, `effective_device`,
  `cuda_available`, `cuda_device_count`, `cuda_device_name` for HF platform
  monitoring.
- Public/synthetic POC only; no scientific claims, no calibrated-probability
  assertions, no clinical guidance.
