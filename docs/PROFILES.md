# Runtime profiles

The codebase ships a single `dr_support.app.create_app()` factory that mounts
one of three runtime profiles. The active profile is selected with the
`APP_PROFILE` environment variable; `MODEL_RUNTIME` is enforced to a specific
value per profile so that a review workstation can never load local weights.

## Matrix

| Profile       | `APP_PROFILE` | `MODEL_RUNTIME` | Exposes                                                                 | Loads RETFound/PRISM weights locally? |
|---------------|---------------|-----------------|-------------------------------------------------------------------------|----------------------------------------|
| Review        | `review`      | `remote`        | `/ui`, `/v1/cases`, `/v1/cases/{id}/review`, `/v1/cases/{id}/cvat/*`, `/v1/infer/*` (proxy to remote), `GET /v1/models` | **No** — review workstations never load weights. |
| Model API     | `model_api`   | `local`         | `GET /health`, `GET /v1/models`, `POST /v1/predict/dr`, `POST /v1/predict/lesions` | Yes — required for the GPU deployment. |
| Full (demo)   | `full`        | `local`         | Everything from both profiles                                           | Yes — required for local demos.       |

Any other combination (e.g. `APP_PROFILE=review` with `MODEL_RUNTIME=local`)
is rejected at startup with a `RuntimeError`. `REMOTE_MODEL_URL` is optional
for the review profile: without it, remote models report
`REMOTE_NOT_CONFIGURED` and inference remains unavailable.

## Local development

The review profile is the default and works without any model weights. Point
it at a deployed model API:

```bash
export APP_PROFILE=review
export MODEL_RUNTIME=remote
export REMOTE_MODEL_URL=https://remote.example.invalid  # optional
export REMOTE_MODEL_TOKEN=...   # optional
python -m dr_support.run        # listens on 127.0.0.1:8000
```

The model_api profile can be exercised on a CPU host for contract testing:

```bash
export APP_PROFILE=model_api
export MODEL_RUNTIME=local
python -m dr_support.run        # listens on 127.0.0.1:8000
# GET /v1/models -> descriptors with status=ASSET_REQUIRED (no weights on disk)
# POST /v1/predict/dr -> 503 with "RETFound assets not configured"
```

## HF Docker Space deployment

The included `Dockerfile` builds a single image that supports all three
profiles. The default `APP_PROFILE=model_api` and `PORT=7860` match the HF
Docker Space conventions. The asset strategy is **download at image build
time** — `python -m dr_support.setup_models --model all` runs once during
`docker build`, the SHA256-verified sources and weights are baked into the
image, and the container entrypoint **does not re-download them** at run
time. Cold start is therefore dominated by uvicorn and model lazy-loading
rather than network IO.

```bash
docker build -t dr-support-poc:dev .
# GPU deployment of the model API:
docker run --rm --gpus all --shm-size=1g -p 7860:7860 \
    -e APP_PROFILE=model_api -e MODEL_RUNTIME=local \
    dr-support-poc:dev
# Clinician workstation proxying to that deployment:
docker run --rm -p 8000:8000 \
    -e APP_PROFILE=review -e MODEL_RUNTIME=remote \
    -e REMOTE_MODEL_URL=https://<hf-space>.hf.space \
    dr-support-poc:dev
```

The container entrypoint (`docker-entrypoint.sh`) only validates environment
variables (APP_PROFILE, MODEL_RUNTIME, presence of the pre-built assets for the
model_api / full profile, and `WORKERS=1` to avoid duplicate model loads). The actual startup is
delegated to `python -m dr_support.run`, which calls the profile dispatcher.

### GPU readiness

For `APP_PROFILE=model_api` (or `full`) the runtime resolver in
`dr_support.runtime.assert_cuda_ready` is invoked at container start. When
`INFERENCE_DEVICE=cuda:0` is requested but the host has no CUDA runtime
visible (e.g. the Space was provisioned without `t4-small`), startup fails
loudly with `DeviceUnavailable`. There is **no silent CPU fallback in
production mode** — set `INFERENCE_DEVICE=cpu` explicitly for local
development or contract tests, or set `DR_SUPPORT_RELAX_DEVICE=1` for
explicit test-only CPU relaxation.

The `/health` endpoint surfaces the resolved device in every response:

```json
{
  "status": "PASS_WITH_WARNINGS",
  "lane": "PUBLIC_SYNTHETIC_REMOTE_MODEL_API",
  "warnings": [],
  "providers": {"retfound-aptos5": "LOADED", "prism-dr-5fold": "LOADED"},
  "requested_device": "cuda:0",
  "effective_device": "cuda:0",
  "cuda_available": true,
  "cuda_device_count": 1,
  "cuda_device_name": "Tesla T4"
}
```

The same fields are echoed on each entry of `/v1/models`.

### Single-worker invariant

`WORKERS > 1` is rejected by the entrypoint. Two uvicorn workers would each
load the model weights into VRAM and exhaust a T4 16 GB within seconds; the
single-worker invariant keeps the deployment inside the hardware envelope.

## Contract invariants

The model_api surface implements the contract documented in
[`REMOTE_MODEL_API.md`](REMOTE_MODEL_API.md). The review profile's remote
proxy is the corresponding consumer; the contract tests in
`tests/test_remote.py` and `tests/test_profiles.py` lock the two ends
together without requiring GPU hardware.

## What this architecture explicitly does NOT do

- No training, fine-tuning, calibration, or scientific benchmarking.
- No weights committed to the repository.
- No bearer tokens in code, logs, or persistence.
- No raw image upload endpoint on the model API (image bytes travel inside
  the inference envelope).
- No clinical claims or autonomous referral.
