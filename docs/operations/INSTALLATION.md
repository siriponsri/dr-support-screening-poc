<!-- canonical-topic: workstation-lifecycle -->

# Installation

This guide installs the review workstation and the separate hospital Model API from a clean checkout. The repository slug and Python import namespace remain `dr_support`; the product display name is Retinal Review Workbench.

## Prerequisites

- Windows 10/11 for the clinician workstation, with approved internet access for first setup.
- No machine-wide Administrator access is required for the supported workstation path.
- Linux with an NVIDIA CUDA-capable GPU for the separate Model API deployment.

## Windows clinician workstation

The supported no-code release path is deliberately short:

```text
extract release -> FIRST_RUN.bat -> START_DR_SCREENING.bat -> browser opens
```

`FIRST_RUN.bat` provisions project-managed Python 3.12 and locked workstation dependencies from an extracted release. It reuses the prebuilt frontend and does not install or run npm. Use `CHECK_SYSTEM.bat` for a read-only diagnostic.

## No-code release path

For a packaged workstation, use `README_START_HERE.md` and the root
`FIRST_RUN.bat`, `START_DR_SCREENING.bat`, `CHECK_SYSTEM.bat`, and
`STOP_DR_SCREENING.bat` files. `FIRST_RUN.bat` provisions Python dependencies
but requires the release's prebuilt `frontend/dist`; normal startup never runs
npm or rebuilds the frontend. Developer checkouts prepare dependencies manually
with the `uv` and frontend npm commands documented below.

`START_DR_SCREENING.bat` sets the safe workstation invariants (`APP_PROFILE=review`, `MODEL_RUNTIME=remote`, `HOST=127.0.0.1`, `PORT=8000`, `WORKERS=1`), reuses a healthy managed process, waits for `/health`, and opens `/app/`. It does not install or rebuild dependencies on daily starts. `STOP_DR_SCREENING.bat` stops only the process recorded in `local-state/release/workstation.json`.

Logs and runtime metadata are under ignored `local-state/logs/` and
`local-state/release/`. A port-8000 conflict is reported with process
information and is never killed automatically. Private `.env` values such as
`REMOTE_MODEL_URL` and `REMOTE_MODEL_TOKEN` are loaded without being printed;
launcher role variables are forced to the safe workstation values.

## Review workstation

Manual recovery, when a launcher is not suitable, is:

```powershell
git clone https://github.com/siriponsri/dr-support-screening-poc.git
cd dr-support-screening-poc
uv python install 3.12
uv venv --python 3.12 .venv
uv sync --python 3.12 --extra test --extra dicom
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
```

Start the workstation with:

```powershell
START_DR_SCREENING.bat
```

The launcher starts `APP_PROFILE=review`, `MODEL_RUNTIME=remote`, and `127.0.0.1:8000`. Configure `REMOTE_MODEL_URL` and the optional `REMOTE_MODEL_TOKEN` in a private `.env` or approved process environment before starting when model assistance is available. In a developer checkout, run `uv sync --python 3.12 --extra test --extra dicom --extra browser-test`, then `npm.cmd ci` and `npm.cmd run build` under `frontend/` before using the same launcher.

For a development server without the launcher:

```powershell
$env:APP_PROFILE = 'review'
$env:MODEL_RUNTIME = 'remote'
uv run python -m dr_support.run
```

## Hospital Model API

On the GPU host, place the clean checkout at `/opt/dr-support-screening-poc` or use another path consistently with the service configuration. Run the one-time online setup as the deployment operator:

```bash
cd /opt/dr-support-screening-poc
./scripts/model-server/setup.sh
```

The script creates `.venv`, installs `.[models,dicom]`, checks Python 3.11/3.12, acquires pinned RETFound and PRISM-DR assets, verifies source revisions and checkpoint hashes, checks the configured CUDA device, and runs synthetic smoke inference. It prints `READY` only after all selected checks pass.

Normal startup is separate and offline-safe:

```bash
./scripts/model-server/start.sh
```

In another terminal:

```bash
./scripts/model-server/healthcheck.sh
```

The service defaults to `0.0.0.0:7860`, `APP_PROFILE=model_api`, `MODEL_RUNTIME=local`, `INFERENCE_DEVICE=cuda:0`, and one worker. It verifies existing assets before starting and never downloads them during normal startup.

## Clean-clone check

After installation, verify the actual release from the repository root:

```powershell
uv run pytest -q
uv run ruff check dr_support tests
cd frontend
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
cd ..
npm.cmd test
```

The model setup command is intentionally not part of ordinary workstation installation because the review profile must not load model weights.
