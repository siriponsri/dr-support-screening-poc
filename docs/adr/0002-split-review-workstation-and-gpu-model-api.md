---
status: Accepted (retrospective)
date: 2026-09-23
---

# ADR-0002: Split the review workstation and the GPU Model API through runtime profiles

## Context and problem statement

Clinician workstations are ordinary Windows PCs. RETFound and PRISM-DR need a CUDA GPU and large, licence-restricted checkpoints. Loading weights on every workstation would spread model assets and make provenance hard to control.

## Considered options

- One code base with enforced profiles (`review`, `model_api`, `full`)
- Two separate repositories
- Model weights on every workstation

## Decision outcome

One repository; `dr_support/app.py` selects the surface through `APP_PROFILE`. `review` requires `MODEL_RUNTIME=remote` and calls a provider-neutral Model API (`/health`, `/v1/models`, `/v1/predict/dr`, `/v1/predict/lesions`) through `providers/remote.py`. `model_api` requires `MODEL_RUNTIME=local`, enforces CUDA, and runs with one worker. `full` is limited to demos. A misconfiguration is a startup error.

### Consequences

- Good: no weights on clinician machines; one audited place for checkpoints; the workstation remains usable when the Model API is down.
- Bad: inference needs a reachable GPU host on the hospital LAN; the remote contract becomes protected (`tests/test_remote.py`, `test_profiles.py`).

## More information

`dr_support/app.py`, `dr_support/services/model_api.py`, `scripts/model-server/`.
