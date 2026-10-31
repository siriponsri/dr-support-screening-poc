# Team access: working on the project and testing against dr-train

Who this is for: developers who clone the repository. dr-train is the team GPU
server used for development, demos and emergencies; real hospital use runs on
the hospital package (`deployment/hospital-server`). Only public or consented
images may be sent to dr-train.

## Level 0: works today, no access needed

Most work needs no GPU and no dr-train.

```powershell
git clone https://github.com/siriponsri/dr-support-screening-poc.git
cd dr-support-screening-poc
uv sync --python 3.12 --extra test --extra dicom --extra browser-test
npm.cmd ci
cd frontend; npm.cmd ci; npm.cmd run build; cd ..
.\.venv\Scripts\python.exe -m pytest -q        # backend, offline (model calls are mocked)
cd frontend; npm.cmd test; cd ..               # frontend
```

Run the app with synthetic and public samples, no AI server:

```powershell
$env:APP_PROFILE = "full"; $env:MODEL_RUNTIME = "local"; $env:DR_SUPPORT_CASE_STORE = "sqlite"
.\.venv\Scripts\python.exe -m uvicorn dr_support.api:app --host 127.0.0.1 --port 8000
```

Or the web app package in Docker (`deployment/webapp/README.md`); AI then shows
as not available.

The live AI demo runs from the owner's workstation (desktop button "DR
Screening Demo"); ask the owner to run it or share the screen.

## Level 1: your own access to dr-train (needs the owner and the dr-train administrator)

Today the AI path uses the owner's SSH key and one shared model token. Neither
is handed out. Per-person access needs these approved first (proposal:
[REGULAR_SERVICE_SECURITY_REQUEST_20261031.md](../planning/REGULAR_SERVICE_SECURITY_REQUEST_20261031.md)):

| Step | Who | What |
| --- | --- | --- |
| 1 | Owner | Invite the developer's device to the private network (Tailscale) with a rule that allows only dr-train SSH |
| 2 | dr-train administrator | Create a restricted account for the developer that can only forward to `127.0.0.1:7860` (no shell), using the developer's own public key |
| 3 | Owner (operator on dr-train) | Issue the developer a personal model token; the gateway maps it to that person (per-user principal) |
| 4 | Developer | Keep the key and token in `%LOCALAPPDATA%\DRScreening\M1PrivateConfig\` only (never in Git, chat or logs) |

After approval, the engineering changes are: the launcher reads the host,
key and a personal token from the private settings file instead of the owner's
fixed values, and the gateway checks personal tokens. Until then, Level 0 is the
team path.

## Level 2: run the hospital package on a GPU machine

Package 2 needs a Linux GPU machine where the account may run Docker
(`deployment/hospital-server/README.md`). On dr-train the account is not in the
`docker` group; adding it is the dr-train administrator's decision. A spare
Linux GPU machine works the same way.

## Rules that do not change

- No patient images on dr-train unless they are consented; the launcher checks
  the Admin page's AI-server choice and consent mark.
- No GPU1, Ollama or other teams' work on dr-train; GPU0 only.
- Daily limits on the team server (calls, GPU-seconds, AI hours 06:00 to 22:00).
