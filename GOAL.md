# Session GOAL — DR Support Screening POC

This document is the canonical handover for everything delivered in the
2026-09-18 work sessions against `siriponsri/dr-support-screening-poc`. It is
written so the next session — or the GPU deployment owner — can pick up
exactly where this one left off.

---

## 1. Summary

Seven commits landed across four sessions, taking the project from `v0.2.0` to
`v0.6.0` without breaking any existing test, contract, or UI surface:

| Commit    | Title                                                                                          | Version |
|-----------|------------------------------------------------------------------------------------------------|---------|
| `5e66b35` | `polish(ui): V2 clinician-first audit and polish pass`                                         | 0.2.1   |
| `0ebe017` | `feat(remote): provider-neutral REMOTE inference adapter with mocked tests`                    | 0.2.1   |
| `a9ccdfb` | `refactor: single-repo multi-runtime-profile architecture (review / model_api / full)`        | 0.3.0   |
| `463270e` | `docs: GOAL.md session summary (audit + polish, REMOTE adapter, profile architecture)`         | 0.3.0   |
| `eef51fd` | `harden(gpu): device resolver, GPU-ready providers, hardened Dockerfile, /health device fields` | 0.4.0 |
| `b6a2490` | `feat(modal): Modal deployment adapter for the model_api profile (T4 GPU, scale-to-zero)`       | 0.5.0 |
| `<M0.7>`  | `feat(lightning): Lightning AI Studio deployment adapter (scripts + runbook, no Docker / no LitServe rewrite)` | 0.6.0 |

Status: **PASS** — code is ready for HF GPU acceptance, Modal GPU
acceptance, AND Lightning AI Studio GPU acceptance. The Lightning adapter
is an additional deployment path; it does not modify the HF Docker Space
story or the Modal adapter.

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
├── scripts/         # M0.7: Lightning AI Studio setup + launch scripts
├── web/             # V2 clinician UI
├── tests/           # backend pytest + frontend jsdom
├── docs/            # PROFILES.md, REMOTE_MODEL_API.md, MODAL_DEPLOYMENT.md, LIGHTNING_DEPLOYMENT.md, ...
├── modal_app.py     # M0.6 Modal deployment adapter
├── Dockerfile       # M0.5 HF Docker Space image, default profile = model_api
├── docker-entrypoint.sh  # env-validator wrapper, execs dr_support.run
├── pyproject.toml   # 0.6.0
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
- `WORKERS > 1` → rejected by `docker-entrypoint.sh` and `scripts/start_lightning.sh`

Deployment paths (M0.5 / M0.6 / M0.7):

| Path | Artefact | Operator command |
|------|----------|------------------|
| Hugging Face Docker Space (v0.4.0) | `Dockerfile` + `docker-entrypoint.sh` | `docker build` / push to HF Space |
| Modal (v0.5.0) | `modal_app.py` reuses `Dockerfile` | `modal deploy modal_app.py` |
| Lightning AI Studio (v0.6.0) | `scripts/setup_lightning.sh` + `scripts/start_lightning.sh` | run inside the Studio; expose port 8000 via the Port plugin |

All three paths serve the same FastAPI surface with the same `/health`,
`/v1/models`, `/v1/predict/dr`, and `/v1/predict/lesions` contract.

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

## 6. Milestone D — GPU deployment hardening (`eef51fd`) — v0.4.0

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

## 7. Milestone E — Modal deployment adapter (`b6a2490`) — v0.5.0

Goal: add Modal as a second deployment target alongside the v0.4.0 HF Docker
Space, **without** changing the clinician UI, Bridge contracts, CVAT flow, or
model semantics. Modal serves the same `model_api` surface; the deployment
artefact is the existing v0.4.0 Dockerfile.

### 7.1 `modal_app.py` (new)

A thin Modal adapter that reuses the existing FastAPI surface:

- `modal.App(name="dr-support-screening-poc-model-api")`.
- `modal.Image.from_dockerfile("Dockerfile")` — single source of truth for the
  build artefact. The same image is the HF Docker Space image.
- `@modal.asgi_app()` exposing the existing FastAPI `model_api` produced by
  `dr_support.app.create_app()` with `APP_PROFILE=model_api`,
  `MODEL_RUNTIME=local`, `INFERENCE_DEVICE=cuda:0`.
- `@modal.concurrent(max_inputs=1, target_inputs=1)` to preserve the
  v0.4.0 single-worker invariant. The api-level `RLock` is the actual
  correctness guard; the Modal concurrency knob is the public-facing
  promise.
- `gpu="T4"` by default; opt-in ladder `L4 → A10` via `MODAL_GPU` env. Any
  other value (e.g. `H100`, `A100`) is rejected — the adapter never
  silently changes hardware.
- No `min_containers`, no `scaledown_window`, no warm pool: scale-to-zero
  by default.
- `REMOTE_MODEL_TOKEN` delivered via `modal.Secret.from_name(
  "dr-support-remote-model-token", required_keys=[])`. The secret is
  optional; when absent, `_require_bearer` treats the endpoints as
  unauthenticated. When present, it enforces `Authorization: Bearer ...`
  with the constant-time comparison the v0.2.1 REMOTE adapter introduced.
- No duplication of dependency definitions: the Modal image is the v0.4.0
  Dockerfile; the Modal SDK is the only new dependency and it lives in the
  optional `[modal]` extra.
- Module is importable without `modal` installed; the `web` and `app`
  bindings become plain callables in that case so the contract tests still
  run on a CPU-only host.

### 7.2 Asset strategy — **baked into the Modal image at build time**

The same strategy used by the HF Docker Space. `setup_models --model all`
runs once during image build; SHA256-verified sources + weights live under
`/app/local-state/bridge` in the resulting image; cold-start latency is
dominated by uvicorn and model lazy-loading, not multi-GB network IO.

We deliberately do **not** ship a Volume-based strategy. A Volume would add
a second moving part (the `Volume.from_name(...)` mount and a
`weights.sha256` reconciliation step) without materially improving rebuild
time for immutable pinned revisions. The Modal image is the same artefact
that ships to the HF Space target — no second source of truth.

### 7.3 Hardware ladder

| GPU | VRAM | When to use |
|-----|------|-------------|
| `T4`  | 16 GB | Default. Sufficient for the released RETFound + PRISM checkpoints. |
| `L4`  | 24 GB | First fallback if PRISM activations exceed T4 headroom. |
| `A10` | 24 GB | Same memory class as L4 with a different CUDA capability. |

`H100` / `A100` are NOT in the ladder. The released checkpoints do not
need them and the price differential is not justified for a public POC.

### 7.4 Secrets

`REMOTE_MODEL_TOKEN` is delivered via a Modal `Secret` named
`dr-support-remote-model-token`. The secret is optional — when not
configured, `_require_bearer` accepts anonymous requests. When configured,
the token is sent only as `Authorization: Bearer ...` and never logged,
persisted, or echoed.

Other env values (`APP_PROFILE`, `MODEL_RUNTIME`, `INFERENCE_DEVICE`,
`HOST`, `PORT`, `WORKERS`) are baked into the image via
`os.environ.setdefault(...)` in `modal_app.build_asgi_app()`. The local
asset paths are wired by `dr_support.run.configure()` at container start.

### 7.5 Tests (`tests/test_modal_adapter.py`, 24 new tests)

- Static configuration: `DEFAULT_GPU == "T4"`, `ACCEPTED_GPUS == ("T4", "L4", "A10")`,
  secret name, app name, Dockerfile path (proves the image is the existing
  v0.4.0 artefact), concurrency invariants.
- `_resolve_gpu` honours `MODAL_GPU`, rejects `H100`/`A100`, strips whitespace.
- `build_asgi_app` pins `APP_PROFILE=model_api` + `MODEL_RUNTIME=local`,
  exposes the four `/health` / `/v1/models` / `/v1/predict/dr` /
  `/v1/predict/lesions` routes, does NOT mount the clinician UI routes
  (`/v1/cases`, `/v1/infer/*`, `/ui`).
- Strict-mode refusal: `build_asgi_app` raises `DeviceUnavailable` when
  `INFERENCE_DEVICE=cuda:0` is requested but no CUDA runtime is visible.
- Modal SDK integration (conditional on `modal` being installed):
  - `modal_app.app` is a `modal.App` named `dr-support-screening-poc-model-api`.
  - `modal_app.web` is a `modal.functions.Function`.
  - `web._spec_.gpus == "T4"`.
  - `web._spec_.secrets` references the bearer-token Secret.
  - `web._spec_.image` comes from `modal.Image.from_dockerfile`.
  - No warm-pool knobs (`scheduler_placement` is `None` or carries no
    `min_containers`).

These tests do not require Modal cloud execution. The only side-effect is
the static module-level decorator wiring; the function body is invoked
through `TestClient` against the FastAPI surface that `build_asgi_app`
returns.

---

## 8. Milestone F — Lightning AI Studio deployment adapter (`<M0.7>`) — v0.6.0 — **this session**

Goal: add Lightning AI Studio as the third deployment target alongside the
v0.4.0 HF Docker Space and the v0.5.0 Modal adapter, **without** changing
the clinician UI, Bridge contracts, CVAT flow, or model semantics.
Lightning serves the same `model_api` surface; the deployment artefacts are
two thin Linux shell scripts and one operator runbook. **No Docker, no
LitServe rewrite, no new FastAPI app, no second dependency tree.**

### 8.1 Architecture

```
Local clinician workstation (Windows)
        |   HTTPS  (Authorization: Bearer ${REMOTE_MODEL_TOKEN}, optional)
        v
Lightning AI Studio (GPU T4)
        |   public URL exposed by Studio "Port" plugin on port 8000
        v
existing FastAPI model_api
        |
        +-- RETFound (dr_support/providers/retfound.py)
        +-- PRISM-DR  (dr_support/providers/prism.py)
        |
        v
GPU
```

The Lightning **Port** plugin (right-side panel of the Studio UI) exposes
the local uvicorn listener on port `8000` to a public URL. The clinician
workstation points `REMOTE_MODEL_URL` at that URL. Auth, schema, and
device semantics are unchanged from the v0.4.0 / v0.5.0 contract.

### 8.2 `scripts/setup_lightning.sh` (new)

Idempotent one-time Studio-side setup. The script:

1. Creates (or reuses) a Python virtualenv under `.venv/`.
2. Upgrades `pip`, `wheel`, `setuptools`.
3. Installs the project in editable mode with the `[models,test]` extras.
4. Runs `python -m dr_support.setup_models --model all` to acquire the
   pinned RETFound + PRISM-DR sources and SHA256-verify every weight file
   under `local-state/bridge/`.

Subsequent runs are cheap no-ops because `setup_models` is idempotent and
the Studio's persistent disk keeps the downloaded checkpoints. The script
**does not duplicate** `setup_models` logic — it delegates directly to
`python -m dr_support.setup_models --model all`. It does **not** clone
RETFound / PRISM-DR directly, does **not** call `gdown.download`
directly, does **not** compute SHA256s directly, and does **not** commit
checkpoints to git.

### 8.3 `scripts/start_lightning.sh` (new)

Linux launch script. The script:

1. Pins `APP_PROFILE=model_api`, `MODEL_RUNTIME=local`,
   `INFERENCE_DEVICE=cuda:0`, `HOST=0.0.0.0`, `PORT=8000`,
   `WORKERS=1` via `export ...="${VAR:-default}"`.
2. Pre-flight `torch.cuda.is_available()` probe — if CUDA is not visible,
   the script exits with code 2 and a clear message instead of silently
   starting the server on CPU.
3. Refuses `WORKERS != 1` before uvicorn boots (duplicate workers would
   each load the model into VRAM and exhaust the T4 within seconds).
4. Execs `python -m dr_support.run`, which boots the FastAPI `model_api`
   on `0.0.0.0:8000` via the existing dispatcher.

`set -euo pipefail` is enabled throughout. The script never dereferences
or echoes `REMOTE_MODEL_TOKEN`; bearer auth is handled by the existing
`dr_support.services.model_api._require_bearer` helper inside FastAPI.

### 8.4 `docs/LIGHTNING_DEPLOYMENT.md` (new)

Operator runbook with the full first-time acceptance sequence:

- **A.** create / open a Lightning Studio
- **B.** select GPU / T4
- **C.** clone the GitHub repo into the persistent home directory
- **D.** install dependencies via `bash scripts/setup_lightning.sh`
- **E.** confirm the asset cache under `local-state/bridge/`
- **F.** set `REMOTE_MODEL_TOKEN` in the Studio's environment-variables
  panel (a fresh, random value; never a real production token)
- **G.** run `bash scripts/start_lightning.sh`
- **H.** expose port 8000 via the Studio **Port** plugin
- **I.** smoke `GET /health`
- **J.** smoke `GET /v1/models`
- **K.** smoke `POST /v1/predict/dr` (RETFound on one synthetic image)
- **L.** smoke `POST /v1/predict/lesions` (PRISM on the same image)
- **M.** connect the local review workstation via `REMOTE_MODEL_URL`
- **N.** stop the GPU when finished

Plus consolidated PASS criteria, a troubleshooting matrix, the
cardless / cost-aware operational policy (no benchmark / batch runs;
stop the Studio after acceptance; never claim a specific free-GPU-hours
budget), the hardware ladder (T4 default; L4 / A10 only if T4 OOM is
actually observed), the auth contract, the persistent-asset strategy, and
the Windows-owner helper showing exactly what to copy from the Studio
URL into the local `.env`.

The runbook deliberately stays silent on a specific Lightning free-GPU-
hours budget — Lightning credit availability varies by account, and the
acceptance flow is designed to spend the minimum possible GPU time.

### 8.5 Asset strategy — **persistent on the Studio home directory**

`scripts/setup_lightning.sh` downloads the pinned RETFound + PRISM-DR
sources and weights into `local-state/bridge/` once and verifies every
checkpoint against the SHA256s in
`dr_support/providers/{retfound,prism}.py` and
`dr_support/providers/prism_assets.json`. Subsequent runs of the setup
script are no-ops because `setup_models` is idempotent and the Studio's
persistent disk survives restarts.

Single predictable path — no second cache layout:

| Env var           | Path                                     |
|-------------------|------------------------------------------|
| `RETFOUND_SOURCE` | `local-state/bridge/sources/RETFound`    |
| `RETFOUND_WEIGHTS`| `local-state/bridge/retfound-aptos.pth`  |
| `PRISM_SOURCE`    | `local-state/bridge/sources/PRISM-DR`    |
| `PRISM_WEIGHTS`   | `local-state/bridge/prism`               |

`scripts/start_lightning.sh` does not set these; the existing
`dr_support.run.configure()` helper wires them from the project root
when `python -m dr_support.run` boots.

### 8.6 Tests (`tests/test_lightning_adapter.py`, 41 new tests)

- **Launch script environment defaults** (10 tests): the bash script
  pins `APP_PROFILE=model_api`, `MODEL_RUNTIME=local`,
  `INFERENCE_DEVICE=cuda:0`, `HOST=0.0.0.0`, `PORT=8000`, `WORKERS=1`,
  uses `set -euo pipefail`, execs `python -m dr_support.run`, refuses
  to silently fall back to CPU, and refuses `WORKERS > 1`.
- **CUDA pre-flight fail-fast** (1 test): mirrors the v0.4.0 strict-mode
  refusal so the Lightning adapter cannot bypass the no-CPU-fallback
  invariant.
- **Setup script idempotency + asset reuse** (8 tests): the setup script
  exists, delegates to `python -m dr_support.setup_models --model all`,
  does NOT duplicate setup logic (no raw `git clone`, no raw
  `gdown.download`, no raw SHA256), installs the project with
  `pip install -e ".[models,test]"`, targets the single
  `local-state/bridge/` cache path, never commits checkpoints, and does
  NOT require Docker.
- **Runbook coverage** (7 tests): the runbook exists, documents all A–N
  steps, documents the consolidated PASS criteria, warns about stopping
  the GPU, does NOT claim a specific free-GPU-hours budget, keeps the
  existing HF / Modal paths intact, and explains the public-port
  mechanism via the Studio Port plugin.
- **Contract unchanged** (5 tests): the four `model_api` routes are still
  present (`/health`, `/v1/models`, `/v1/predict/dr`,
  `/v1/predict/lesions`), the bearer contract still gates the predict
  endpoints, the `/health` device snapshot is intact, and the
  `503 RETFound/PRISM-DR assets not configured` paths still fire when no
  weights are present.
- **No CPU fallback in model_api** (2 tests): the dispatcher still
  refuses to start when `INFERENCE_DEVICE=cuda:0` is requested without a
  CUDA runtime (mirroring `tests/test_device.py`), and `/health` still
  returns `status=FAIL` with `cuda_available=false` in the same
  configuration.
- **No secret leakage** (8 tests): the launch script, the setup script,
  and the runbook contain no `sk-` / `ghp_` / `xoxb-` / `hf_` / `AKIA`
  style secret prefixes; the launch script never even references
  `REMOTE_MODEL_TOKEN` (bearer auth is handled inside FastAPI); the
  setup script never dereferences or echoes the token; the runbook uses
  only the `<synthetic-deploy-token>` placeholder.

These tests do not require the Lightning cloud; the bash scripts are
read as text rather than executed, so the test suite stays CPU-only and
Windows-friendly.

---

## 9. Verification matrix

Run on the local Windows CPU host, before each commit:

| Tool                         | Command                                                       | Result                       |
|------------------------------|---------------------------------------------------------------|------------------------------|
| Backend unit + integration   | `python -m pytest -q`                                         | **143 passed**, 1 skipped    |
| Frontend JS contract + UI    | `npm test`                                                    | 3/3 PASS                     |
| Lint                         | `python -m ruff check dr_support tests scripts modal_app.py`  | All checks passed            |

Test inventory by file:

| Test file                       | Count | Covers                                                            |
|---------------------------------|-------|-------------------------------------------------------------------|
| `tests/test_bridge.py`          | 8     | Bridge contracts, CVAT online safety, weight hashing              |
| `tests/test_workflow.py`        | 8     | Review round-trip, manual sync, error paths                       |
| `tests/test_sync.py`            | 2     | CVAT send / pull idempotency                                      |
| `tests/test_remote.py`          | 20    | Remote provider, mocked integration, token isolation              |
| `tests/test_profiles.py`        | 19    | Profile dispatch, invariants, model_api surface, M4 proxy smoke   |
| `tests/test_device.py`          | 22    | GPU device resolver, provider propagation, no-CPU-fallback, /health |
| `tests/test_modal_adapter.py`   | 24    | Modal adapter config, GPU ladder, ASGI surface, SDK integration   |
| `tests/test_lightning_adapter.py` | 41  | Lightning launch script, setup script, runbook coverage, contract unchanged, no-CPU-fallback, no secret leakage |
| `tests/test_browser_ui.py`      | 1     | Real-browser preview smoke (skipped on this host)                 |
| `tests/overlay.test.cjs`        | —     | Imported CVAT geometry overrides AI provenance                    |
| `tests/ui.test.cjs`             | —     | DOM + real API: navigation, Analyze, grade correction             |
| `tests/preview.test.cjs`        | —     | Offline PREVIEW.html, no API calls, controls disabled             |

Total new tests in M0.7: **41** (`tests/test_lightning_adapter.py`).

---

## 10. Files added or modified in the M0.7 Lightning adapter pass

```
scripts/setup_lightning.sh                       +60 / -0   NEW (idempotent Studio setup; delegates to setup_models)
scripts/start_lightning.sh                       +70 / -0   NEW (Linux launch script; pre-flight CUDA probe; execs dr_support.run)
docs/LIGHTNING_DEPLOYMENT.md                     +340 / -0  NEW (A–N operator runbook; PASS criteria; troubleshooting)
tests/test_lightning_adapter.py                  +430 / -0  NEW (41 tests; launch defaults, contract stability, no-secret-leakage)
.env.example                                     +20 / -0   (Lightning section; points at scripts + runbook)
CHANGELOG_V2.md                                  +60 / -0   (0.6.0 entry: Added / Changed / Preserved)
pyproject.toml                                   +1 / -1    (version bump 0.5.0 → 0.6.0)
GOAL.md                                          overwritten (M0.7 summary + exact status)
```

No existing file under `dr_support/`, `web/`, `Dockerfile`,
`docker-entrypoint.sh`, `modal_app.py`, or `docs/MODAL_DEPLOYMENT.md` was
modified.

---

## 11. Operator notes for the Lightning deployment

```bash
# 1. In the Lightning Studio terminal:
cd ~
git clone https://github.com/siriponsri/dr-support-screening-poc.git
cd dr-support-screening-poc

# 2. One-time idempotent setup (venv + project + model assets).
bash scripts/setup_lightning.sh

# 3. Set the bearer-token secret in the Studio's environment-variables
#    panel BEFORE launching:
#      REMOTE_MODEL_TOKEN=<fresh synthetic-deploy-token>
#    Generate with:  python -c "import secrets; print(secrets.token_urlsafe(32))"

# 4. Launch the model_api profile on 0.0.0.0:8000.
bash scripts/start_lightning.sh

# 5. In the Studio UI: open the "Port" plugin (right-side panel) and
#    expose port 8000. The plugin prints a public URL of the form
#    https://<id>.lightning.ai.

# 6. Smoke the four contract endpoints (see docs/LIGHTNING_DEPLOYMENT.md
#    §7 for the exact curl invocations).

# 7. Stop the Studio when finished so Lightning credits are not consumed.
```

GPU fallback (only when T4 OOM is actually observed):

```bash
# Re-create the Studio with an L4 or A10 machine type.
# The script does NOT auto-escalate hardware — the operator reports
# PASS_WITH_WARNINGS / OWNER_HARDWARE_ACTION_REQUIRED and escalates
# manually.
```

The launch script **never** silently changes hardware. There is no
environment variable for GPU selection; the GPU is selected at Studio
creation time, and changing it means a new Studio.

---

## 12. What's NOT done — explicit owner actions

These are deployment-time concerns that this codebase cannot complete from a
CPU-only host:

- **First Lightning Studio creation.** The owner signs in to
  [lightning.ai](https://lightning.ai), creates a Studio, and selects a
  GPU (T4 default) machine type.
- **First GPU acceptance run.** The owner executes steps A–N of
  `docs/LIGHTNING_DEPLOYMENT.md` against the live Studio, including the
  first `/health` + RETFound + PRISM smoke, then stops the Studio.
- **Lightning credit management.** GPU usage consumes Lightning credits;
  the owner monitors credit availability and stops the Studio when not
  in use.
- **`REMOTE_MODEL_TOKEN` rotation.** Rotating the token is a Studio
  env-panel action; the local `.env` must be updated to match.
- **First-time `modal setup`.** Still required if the owner also wants
  to keep the v0.5.0 Modal target.
- **First-time HF GPU acceptance run.** The v0.4.0 code is still GPU-ready
  and the contract tests prove it. The HF Space owner flips the switch
  on the HF Space hardware and observes the Bridge v1 outputs flowing
  end-to-end through a real `cuda:0` device.
- **Live PRISM inference (any deployment).** All 20 fold weights need to
  actually live on the GPU host's SSD at the pinned paths. `setup_models`
  guarantees the download + verification on first build; the owner does
  not have to do anything beyond the initial build.
- **CVAT round-trip on a live workspace.** CVAT Online still requires the
  `CVAT_TOKEN` to be present at the review workstation's runtime. The
  same `OWNER_ACTION_REQUIRED` message from v0.3.0 still applies.

None of these are governance or implementation issues — they are
operations the owner executes against the deployed HF Space, Modal app,
or Lightning Studio.

---

## 13. Status

**PASS** — code is ready for HF GPU acceptance, Modal GPU acceptance, AND
Lightning AI Studio GPU acceptance.

- All in-scope deliverables shipped; 143 backend tests + 3 frontend
  tests pass locally on a CPU-only host.
- The Lightning adapter is an additional deployment path; it does not
  modify the HF Docker Space story, the Modal adapter, or any contract /
  UI surface.
- `scripts/start_lightning.sh` pins the same production env as
  `Dockerfile` / `docker-entrypoint.sh` / `modal_app.py`; refuses
  `WORKERS > 1`; refuses to silently fall back to CPU via a pre-flight
  `torch.cuda.is_available()` probe; execs `python -m dr_support.run`.
- `scripts/setup_lightning.sh` is idempotent and delegates to the
  existing `python -m dr_support.setup_models --model all` — no
  duplicated download / hash logic.
- Asset cache lives under the single, predictable
  `local-state/bridge/` path; the Lightning persistent disk keeps it
  across Studio restarts.
- `REMOTE_MODEL_TOKEN` delivered via the Studio's environment-variables
  panel; never hardcoded, logged, or echoed by either script.
- Hardware is selected at Studio creation time; the launch script
  never silently changes GPU class.
- V2 clinician UI untouched; the Lightning deployment never hosts the
  UI.
- Public/synthetic POC only; no scientific claims, no
  calibrated-probability assertions, no clinical guidance.
