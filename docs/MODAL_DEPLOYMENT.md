# Modal deployment — DR Support Screening POC v0.5.0

This document is the operator runbook for hosting the
`APP_PROFILE=model_api` Remote Model API contract on
[Modal](https://modal.com). It is the Modal counterpart to the existing
[Hugging Face Docker Space runbook](PROFILES.md#hf-docker-space-deployment)
and reuses the v0.4.0 GPU deployment hardening without duplicating it.

The clinician UI, the Bridge v1 contract, the CVAT round-trip, the model
semantics, and the existing pytest suite are unchanged. Modal is the
**deployment adapter**, not a new product surface.

---

## 1. Scope

What the Modal adapter ships:

- `modal_app.py` — a thin Modal app that hosts the existing FastAPI
  `model_api` service via `@modal.asgi_app()`.
- A single source of truth for the deployment artefact: the v0.4.0
  `Dockerfile` is reused verbatim via `modal.Image.from_dockerfile`.
- A single source of truth for inference secrets: `REMOTE_MODEL_TOKEN`
  is delivered via a Modal `Secret`; it never appears in code, logs, or
  responses.
- A documented GPU ladder starting at T4 with L4 and A10 fallbacks if
  PRISM ever exceeds the T4 memory envelope.

What the Modal adapter **does not** ship:

- No new model code. RETFound and PRISM continue to use the existing
  provider classes from `dr_support/providers/`.
- No new contract. The Modal deployment serves the same `/health`,
  `/v1/models`, `/v1/predict/dr`, `/v1/predict/lesions` endpoints as
  the HF Docker Space target.
- No UI. The clinician workstation is a separate deployment that proxies
  to this Modal URL with `MODEL_RUNTIME=remote`.
- No training, fine-tuning, calibration, scientific benchmarking, or
  clinical claims. Public/synthetic POC only.

---

## 2. Image strategy

**Strategy A — baked into the Modal image at build time.** This is the
single chosen approach. Strategy B (Modal Volume) is documented in the
runbook below as an "if you really must" escape hatch but is **not**
claimed or exercised.

### Why the existing Dockerfile

The v0.4.0 `Dockerfile` is already a complete, reproducible build:

1. `nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04` base (the same driver
   Modal exposes for `gpu="T4"`).
2. Python 3.12 installed via the deadsnakes PPA.
3. CUDA-enabled `torch==2.5.1+cu121` and `torchvision==0.20.1+cu121`
   installed from `download.pytorch.org/whl/cu121`.
4. The project source copied in and installed with `pip install -e
   ".[models,test]"`.
5. `python -m dr_support.setup_models --model all` runs once during
   build, downloading the pinned RETFound + PRISM-DR sources and SHA256
   verifying **21 PRISM weight files** + 1 RETFound checkpoint against
   the locked hashes in `dr_support/providers/{retfound,prism}.py` and
   `dr_support/providers/prism_assets.json`.

`modal.Image.from_dockerfile` reuses this exact recipe. The Modal image
is therefore **the same artefact** that ships to the HF Docker Space
target — no second source of truth, no risk of drift between the two
deployment paths.

### Asset strategy: **download at image build time** (single source of truth)

`setup_models --model all` runs once when Modal builds the image. The
resulting container has the SHA256-verified sources and weights under
`/app/local-state/bridge`. Cold-start latency is therefore dominated by
uvicorn and model lazy-loading, not multi-GB network IO.

The Modal entrypoint (`python -m dr_support.run` via `dr_support.app`
→ `dr_support.services.model_api.create_app`) does **not** re-run
`setup_models`; it relies on the build-time artefacts and surfaces a
clear error if they are missing. This matches the v0.4.0 HF Docker Space
behaviour.

### Why not a Modal Volume (strategy B)

Modal Volumes are the right tool when:

- The assets change often enough that re-baking the image is wasteful.
- The same assets are shared across multiple Apps.

Neither is true for this POC. The pinned upstream revisions are
immutable; re-baking the image costs the same as uploading to a Volume;
and only one App uses the assets. A Volume would add a second moving
part (the `Volume.from_name(...)` mount, an `add_local_dir` fallback,
and a `weights.sha256` reconciliation step on first start) without
materially improving rebuild time.

If a future operator genuinely needs to flip to a Volume, the change is
localised to `modal_app.py` and `dr_support/run.py` — but **we do not
ship both strategies in the same milestone.**

---

## 3. Hardware

### Default: `T4`

The v0.4.0 PRISM adapter loads 4 lesion classes × 5 folds = 20
ultralytics YOLO models plus the ROI cropper. With the released
checkpoint sizes (~6 MB each), a T4 small (16 GB VRAM) has comfortable
headroom for activations under the api-level `RLock`. The
single-inference-call-at-a-time invariant keeps peak activation memory
bounded by one forward pass.

### Documented fallback ladder

| GPU | VRAM | When to use |
|-----|------|-------------|
| `T4`  | 16 GB | Default. Sufficient for the released RETFound + PRISM checkpoints. |
| `L4`  | 24 GB | First fallback if PRISM activations exceed T4 headroom (e.g. larger fold ensembles in a future model release). |
| `A10` | 24 GB | Same memory class as L4 with a different CUDA capability. Use only if L4 capacity is exhausted in the region. |

The ladder is opt-in via the `MODAL_GPU` environment variable:

```bash
MODAL_GPU=L4 modal deploy modal_app.py    # first fallback
MODAL_GPU=A10 modal deploy modal_app.py   # second fallback
```

The adapter **rejects any other value** with a clear error — there is
no silent hardware change.

We deliberately do not include H100/A100 in the ladder. The released
checkpoints do not need them and the price differential is not justified
for a public POC.

---

## 4. Secrets

### `REMOTE_MODEL_TOKEN`

`dr_support.services.model_api._require_bearer` enforces `Authorization:
Bearer ...` against the `REMOTE_MODEL_TOKEN` environment variable on
every `POST /v1/predict/*` call. The token is read from `os.environ`
at request time, compared with `hmac.compare_digest` semantics
(constant-time), and never logged, persisted, or echoed.

Modal delivers this token via the `Secret` named
`dr-support-remote-model-token`:

```bash
modal secret create dr-support-remote-model-token \
    REMOTE_MODEL_TOKEN='<synthetic-deploy-token>'
```

The secret is **optional**. When it is not configured on Modal, the
bearer-protected endpoints accept anonymous requests; the existing
`_require_bearer` helper treats a missing `REMOTE_MODEL_TOKEN` as "no
auth required" so the deployment can be smoke-tested without distributing
a secret.

### What is **not** in Modal Secrets

- `INFERENCE_DEVICE` is baked into the image as `cuda:0` by `modal_app.py`.
- `APP_PROFILE`, `MODEL_RUNTIME`, `HOST`, `PORT`, `WORKERS` are likewise
  baked into the image via `os.environ.setdefault(...)` in `build_asgi_app()`.
- `RETFOUND_SOURCE`, `RETFOUND_WEIGHTS`, `PRISM_SOURCE`, `PRISM_WEIGHTS`
  are wired to `/app/local-state/bridge/...` by `dr_support.run.configure()`
  at container start; the paths are filled by the Dockerfile's
  `setup_models` invocation.

---

## 5. Operator workflow

The full first-time deployment from a clean Modal workspace:

```bash
# 1. Install the Modal client SDK alongside the project extras.
pip install -e ".[modal]"

# 2. Authenticate with Modal.
modal setup

# 3. (Optional) Create the bearer-token secret. Skip this step to deploy
#    an unauthenticated endpoint for smoke-testing.
modal secret create dr-support-remote-model-token \
    REMOTE_MODEL_TOKEN='<synthetic-deploy-token>'

# 4. Deploy the app.
modal deploy modal_app.py
# Output:
#   Created app dr-support-screening-poc-model-api.
#   Initialising... ready in 22s.
#   View app logs at:
#     https://modal.com/apps/<workspace>/dr-support-screening-poc-model-api

# 5. Capture the deployed URL (Modal prints it).
#    APP_URL=https://<workspace>--dr-support-screening-poc-model-api.modal.run

# 6. Inspect the container logs (cold start, build, runtime).
modal app logs dr-support-screening-poc-model-api

# 7. Smoke the endpoints (see §6 for the exact curl invocations).
```

### Re-deploy after code change

```bash
modal deploy modal_app.py
```

Modal will rebuild the image only if the Dockerfile, the `dr_support`
source, or the `modal_app.py` decoration changed. Layer caching makes
re-deploys of code-only changes fast.

### Ephemeral preview (no deployment)

```bash
modal serve modal_app.py
```

Creates a temporary URL that live-updates on code change. Use this for
acceptance testing before running `modal deploy`.

---

## 6. Acceptance smoke

Replace `$APP_URL` with the deployed URL printed by `modal deploy` (or
the `modal serve` URL).

```bash
APP_URL="https://<workspace>--dr-support-screening-poc-model-api.modal.run"
TOKEN='<synthetic-deploy-token>'   # only needed if the secret was created

# 6.1 /health — must report cuda_available: true once cold-start finishes.
curl -fsS "$APP_URL/health" | python -m json.tool

# 6.2 /v1/models — must list retfound-aptos5 and prism-dr-5fold, both
# LOADED after the first inference call.
curl -fsS "$APP_URL/v1/models" | python -m json.tool

# 6.3 Smoke RETFound on the public 01_dr sample (replace with the actual
# public image bytes; the synthetic fixture below always works without
# a real image on disk).
python - <<'PY'
import base64, hashlib, json, urllib.request
from dr_support.images import synthetic_image
fixture = synthetic_image()
img_bytes = fixture.data
payload = {
    "image_id": "01_dr",
    "modality": "CFP",
    "model_id": "retfound-aptos5",
    "image_b64": base64.b64encode(img_bytes).decode("ascii"),
    "image_sha256": hashlib.sha256(img_bytes).hexdigest(),
    "source_type": fixture.source_type,
    "width": fixture.size[0],
    "height": fixture.size[1],
}
req = urllib.request.Request(
    "$APP_URL/v1/predict/dr".replace("$APP_URL", APP_URL),
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json",
             **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {})},
    method="POST",
)
with urllib.request.urlopen(req, timeout=60) as response:
    print(json.dumps(json.loads(response.read()), indent=2))
PY

# 6.4 Smoke PRISM on the same fixture — same envelope, model_id swapped.
# (Replace "retfound-aptos5" with "prism-dr-5fold" and the path with
# /v1/predict/lesions.)
```

The `Authorization: Bearer` header is only required when the
`dr-support-remote-model-token` secret is configured.

---

## 7. What this milestone deliberately does not change

- **Bridge v1 schema.** No `GlobalResult` or `LesionResult` field has
  been renamed, added, or removed.
- **Provider classes.** `RETFound` and `PRISM` are unchanged; they
  continue to load their pinned checkpoints, do `torch.inference_mode()`
  forward passes, and release CUDA activations in the same way.
- **Profile invariants.** `APP_PROFILE=model_api` + `MODEL_RUNTIME=remote`
  is still rejected; `APP_PROFILE=review` + `MODEL_RUNTIME=local` is
  still rejected. Modal is only an additional deployment path.
- **UI surface.** The V2 clinician UI is not in Modal. The review
  workstation remains the existing browser/HTML experience.
- **Scientific behaviour.** No threshold changes, no class-mapping
  changes, no calibration, no clinical guidance.
- **Tests.** The existing 78 backend tests + 3 frontend tests still
  pass on a CPU-only host. New tests in
  `tests/test_modal_adapter.py` cover the adapter without requiring
  Modal cloud execution.

---

## 8. Owner actions required on the Modal cloud

These are operations the codebase cannot complete from a CPU-only host:

- **First-time `modal setup`** — authenticates the operator against the
  Modal workspace.
- **First-time image build** — Modal downloads the v0.4.0 base image,
  the CUDA-enabled torch stack, the project source, and ~3 GB of model
  weights. Subsequent deploys reuse the cached image layers.
- **GPU billing** — Modal bills per-second for active GPU time. The
  scale-to-zero default keeps idle cost at zero; the operator pays only
  for inference traffic.
- **Secret management** — `modal secret create` is a one-time action;
  subsequent deploys reuse the existing secret by name.

None of these are governance or implementation issues — they are
operations the owner executes against the deployed Modal app.
