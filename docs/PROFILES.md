# Runtime profiles

The codebase ships a single `dr_support.app.create_app()` factory that mounts
one of three runtime profiles. The active profile is selected with the
`APP_PROFILE` environment variable; `MODEL_RUNTIME` is enforced to a specific
value per profile so that misconfiguration fails fast at startup.

## Matrix

| Profile       | `APP_PROFILE` | `MODEL_RUNTIME` | Exposes                                                                 | Loads RETFound/PRISM weights locally? |
|---------------|---------------|-----------------|-------------------------------------------------------------------------|----------------------------------------|
| Review        | `review`      | `remote`        | `/ui`, `/v1/cases`, `/v1/cases/{id}/review`, `/v1/cases/{id}/cvat/*`, `/v1/infer/*` (proxy to remote), `GET /v1/models` | **No** — review workstations never load weights. |
| Model API     | `model_api`   | `local`         | `GET /health`, `GET /v1/models`, `POST /v1/predict/dr`, `POST /v1/predict/lesions` | Yes — required for the GPU deployment. |
| Full (demo)   | `full`        | `local`         | Everything from both profiles                                           | Yes — required for local demos.       |

Any other combination (e.g. `APP_PROFILE=review` with `MODEL_RUNTIME=local`)
is rejected at startup with a `RuntimeError`.

## Local development

The review profile is the default and works without any model weights. Point
it at a deployed model API:

```bash
export APP_PROFILE=review
export MODEL_RUNTIME=remote
export REMOTE_MODEL_URL=https://remote.example.invalid
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
Docker Space conventions. Build once, run per profile:

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

The container's entrypoint runs `python -m dr_support.setup_models --model all`
when `model_api` or `full` is selected, so weights are fetched and verified
on first start. The CPU-only review profile never reaches that step.

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
