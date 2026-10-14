# Split Model API containers (engineering source handoff)

This directory defines three independent Model API containers; it does not
include weights, source checkouts, secrets, patient data, or database data.
All three services request one NVIDIA GPU and bind to loopback on their
respective ports: RETFound 7864, USPEC 7861, PRISM 7862. Keep research assets
outside image layers and mount them read-only. PRISM UWF remains experimental;
no rim mask is activated by this deployment.

## Host requirements

- Linux Docker Engine with Compose v2 and NVIDIA Container Toolkit configured.
- T4-class CUDA host; the source-tagged PyTorch 2.11.0 / CUDA 12.8 image passed a
  T4 CUDA smoke in the current Studio, but these application images still need
  build and route-level GPU verification.
- Private, exact assets already acquired and authorized for the intended
  non-commercial research/demo use. This documentation does not grant rights.
- A private `REMOTE_MODEL_TOKEN`; do not put it in this repository.

## Validate definition

From repository root, pass the exact already-authorized asset paths and a
private token in the shell environment, without writing a `.env` to Git:

```bash
export RETFOUND_SOURCE=/private/RETFound-source/RETFound
export RETFOUND_WEIGHTS=/private/RETFound-checkpoints/retfound-aptos.pth
export USPEC_MODEL_DIR=/private/uspec
export PRISM_SOURCE=/private/PRISM-DR
export PRISM_WEIGHTS=/private/prism-weights
export REMOTE_MODEL_TOKEN='...'
export DR_SCREENING_IMAGE_TAG="$(git rev-parse --short HEAD)"
docker compose -f deployment/model-api/compose.yml config --quiet
docker compose -f deployment/model-api/compose.yml build
```

Check build context and layers before running. Compose binds API ports to
`127.0.0.1` only. Configure the review app with its existing endpoint/auth
contract; do not expose these ports publicly. `docker compose ... up -d` starts
models and loads them lazily on first inference. `docker compose ... ps` and
`curl http://127.0.0.1:<port>/health` are liveness checks; `/v1/models` readiness
must additionally be checked after a real inference. Stop with
`docker compose -f deployment/model-api/compose.yml down` (without `-v`) to
preserve any attached data. No application/DB stack is defined here, and no
browser workflow is certified by this file.

This is a private engineering source/build handoff, not a clinical or production release. Current Studio performed individual T4 route-level synthetic inference for USPEC, PRISM and RETFound in isolated containers. It did not qualify simultaneous model residency, review/browser E2E, remote reachability, image reload on a target host, or a trusted-FOV PREPARED rim-removal path. See the external delivery run receipts for exact scope.

## Single-runtime validation and operations

The Compose file accepts host-port overrides `RETFOUND_PORT`, `USPEC_PORT`, and
`PRISM_PORT` for coexistence with existing local services. Source repositories
are mounted read-only; Git's safe-directory exception is scoped to the exact
mounted upstream source path inside the two source-verifying containers.
RETFound and USPEC pin `timm==1.0.22`, matching recorded model runtime. USPEC additionally requires `opencv-python-headless==4.11.0.86` for its locked native FOV preprocessing. Private paths must point directly at the verified source repository and checkpoint directory; they are not copied into image layers.

For a bounded container smoke, it is valid to start only one service with
`docker compose ... up -d retfound` (similarly for `uspec` or `prism`). Verify
health, exact `/v1/models` descriptor, authorized SYNTHETIC route inference,
wrong-modality rejection, and post-inference health before describing that
service as container-qualified. This single-service smoke does not prove
three-container compose, multi-runtime GPU residency, review-API/browser E2E,
restart persistence, or private workstation reachability.
