# Retinal Review Workbench

Retinal Review Workbench is a clinician-controlled retinal screening review and dataset workspace. It is a public/synthetic research and clinical-support proof of concept, not an autonomous diagnostic or regulated medical device.

## Safety and scope

The workstation admits hospital-staged retinal images, records pseudonymous patient/eye context, shows optional RETFound and PRISM-DR model evidence, and keeps the clinician's review authoritative. Model scores are not calibrated clinical probabilities. An empty lesion result does not prove that lesions are absent. Original admitted images remain immutable.

The normal review workstation and the Linux GPU Model API are separate deployment roles. The workstation does not require model weights or a GPU.

## Quick start on Windows

From a clean clone with approved internet access:

```text
SETUP.cmd
START.cmd
```

The browser opens at `http://127.0.0.1:8000/app/`. Use `OPEN_APP.cmd` to open or start it later and `STOP.cmd` to stop only the repository-managed process. Daily starts reuse dependencies and rebuild the frontend only when its tracked source or lockfile state changes.

For the controlled Linux GPU deployment, use [the Model API operations guide](docs/operations/MODEL_SERVER.md) and `scripts/model-server/`. Do not install Node/npm on that host.

## Core workflow

Worklist -> Confirm Image -> Review -> Confirm final DR grade or send for senior review -> Edit Annotations only when needed -> Confirm Annotation -> Datasets.

## Documentation

Start at the [documentation portal](docs/README.md). It is organized for clinicians, hospital operators, developers, reference work, architecture decisions, and presentations.

## Repository map

```text
dr_support/       FastAPI workstation and Model API
frontend/         React/Vite clinician UI
scripts/          Windows lifecycle, docs, and Linux Model API tooling
deployment/       Controlled Model API service configuration
tests/            Backend, API, browser, and smoke tests
docs/             Canonical source documents and generated PDFs/presentations
web/              Legacy compatibility UI
local-state/      Ignored runtime state only
```

## Validation

```powershell
uv run pytest -q
uv run ruff check dr_support tests
cd frontend; npm.cmd test; npm.cmd run typecheck; npm.cmd run build; cd ..
python scripts/docs/check_docs.py
npm.cmd test
```

## Privacy and license

Use only approved synthetic/public fixtures in tests, screenshots, examples, and public documentation. Do not commit PHI, secrets, credentials, model weights, runtime databases, or `local-state/` artifacts. See [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY_NOTICES.md).
