# Installation

This guide installs the review workstation and the separate hospital Model API from a clean checkout. The repository slug and Python import namespace remain `dr_support`; the product display name is Retinal Review Workbench.

## Prerequisites

- Python 3.11 or 3.12.
- Node.js/npm for the React build.
- Linux with an NVIDIA CUDA-capable GPU for the supported Model API deployment.
- Internet access only for the initial server dependency and asset setup.

## Review workstation

From a clean clone on Windows PowerShell:

```powershell
git clone https://github.com/siriponsri/dr-support-screening-poc.git
cd dr-support-screening-poc
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -e ".[test,dicom]"
npm ci
cd frontend
npm ci
npm run build
cd ..
```

Start the workstation with:

```powershell
START.cmd
```

The launcher starts `APP_PROFILE=review`, `MODEL_RUNTIME=remote`, and `127.0.0.1:8000`. Configure `REMOTE_MODEL_URL` and the optional `REMOTE_MODEL_TOKEN` outside Git before starting when model assistance is available.

For a development server without the launcher:

```powershell
$env:APP_PROFILE = 'review'
$env:MODEL_RUNTIME = 'remote'
.venv\Scripts\python.exe -m dr_support.run
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
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check dr_support tests
cd frontend
npm test
npm run typecheck
npm run build
cd ..
npm test
```

The model setup command is intentionally not part of ordinary workstation installation because the review profile must not load model weights.
