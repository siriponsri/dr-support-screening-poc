# Model Server — Draft for S8 Rewrite

## Goal

One-time online setup, repeatable offline operation.

## Target operator commands

```bash
./scripts/model-server/setup.sh
./scripts/model-server/start.sh
./scripts/model-server/healthcheck.sh
```

S8 must rewrite these commands to match the implementation.

## Setup responsibilities

- verify Python/runtime prerequisites;
- install model + DICOM dependencies;
- verify CUDA/device when configured;
- invoke the repository's existing model-asset setup mechanism;
- preserve pinned source revisions and checkpoint SHA256 values;
- load both RETFound and PRISM once;
- run smoke inference;
- report `READY` only when all required checks pass.

## Startup responsibilities

Normal startup must not download assets. Missing or mismatched weights must fail clearly with an instruction to rerun approved setup while online.

Expected environment intent:

```text
APP_PROFILE=model_api
MODEL_RUNTIME=local
INFERENCE_DEVICE=cuda:0
WORKERS=1
HOST=0.0.0.0   # only when protected by hospital LAN/firewall policy
PORT=8000
REMOTE_MODEL_TOKEN=<optional configured secret>
```

Verify all names/defaults against final code.

## API checks

At minimum verify:
- `GET /health`
- `GET /v1/models`
- one DR prediction
- one lesion prediction
- exact request image SHA validation
- no raw DICOM PHI in requests/logs.
