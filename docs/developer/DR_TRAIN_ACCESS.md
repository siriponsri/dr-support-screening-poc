# dr-train access: working against the team GPU server

dr-train is the team GPU server used for development, demos and emergencies. Real hospital use runs on the
hospital package (`deployment/hospital-server`). Only public or consented images may be sent to dr-train.
Nothing here is done automatically by the app or by Claude Code.

## Level 0: no access needed

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

Run the app with synthetic and public samples and no AI server:

```powershell
$env:APP_PROFILE = "full"; $env:MODEL_RUNTIME = "local"; $env:DR_SUPPORT_CASE_STORE = "sqlite"
.\.venv\Scripts\python.exe -m uvicorn dr_support.api:app --host 127.0.0.1 --port 8000
```

Or run the web app package in Docker (`deployment/webapp/README.md`); AI then shows as not available. The
live AI demo runs from the owner's workstation (desktop button "DR Screening Demo").

## Level 1: personal access (owner approved 31 October 2026; nobody added yet)

Today the AI path uses the owner's SSH key and one shared model token; neither is handed out. Personal access
gives each person their own restricted account and token. The code is ready and runs on dr-train since
deployment `regular-20261031-r05`; no account, token or device has been created yet.

| Item | Who makes it | Where it lives | Never |
| --- | --- | --- | --- |
| SSH key pair | the person (`ssh-keygen -t ed25519`) | private key stays on their PC | send the private key to anyone |
| Restricted dr-train account `drgw-<name>` | dr-train administrator | dr-train | give it a shell or sudo |
| Personal model token | operator on dr-train | `%LOCALAPPDATA%\DRScreening\M1PrivateConfig\personal-token.txt` | paste it in chat, email, Git, logs or screenshots |
| Private network invitation | owner | Tailscale admin console | allow anything except dr-train SSH |

Steps:

1. **Person:** sends only the public key (`id_ed25519.pub`) to the administrator.
2. **Administrator (on dr-train, with sudo):**
   `sudo sh scripts/model-server/admin/create-restricted-user.sh drgw-ann /tmp/ann.pub`.
   The account can only forward a local port to `127.0.0.1:7860`.
3. **Operator (on dr-train, project account):**
   ```bash
   P=/home/siripon/projects/dr-model-api-qa; D=$P/deployments/<current deployment>
   $P/environments/prism-qa-torch213/bin/python -I -B $D/scripts/model-server/regular_service.py \
     principal-add --principals $P/config/private/regular-principals.json --name ann --workstation ann-laptop
   ```
   The token is shown once. The running gateway rereads the file on the next request (no restart). The file
   keeps only the token's SHA-256, the name and the allowed workstation IDs.
4. **Hand-over:** in person or through a password manager's secure share, never by chat or email body.
5. **Owner:** invites the person's device to the private network, allowing only dr-train port 22.
6. **Person:** in the private `demo.env` sets `DR_HOST=drgw-ann@<dr-train address>`,
   `DR_KEY=<private key path>`, `DR_TOKEN_FILE=<path to personal-token.txt>`, `DR_WORKSTATION=ann-laptop`,
   then uses the desktop button. With a personal token the launcher does not start the gateway; the
   operator keeps it running. The person's PC still needs its own workspace, sign-in accounts and a copy of
   the PRISM pins.

Revoke: `regular_service.py principal-revoke --principals ... --name ann` (next request), account
`sudo userdel --remove drgw-ann` (administrator), device in the Tailscale console (owner).

Each person's tickets are recorded under `user:<name>`; one person cannot see or cancel another's. A
personal token reaches only the service paths (status, tickets, grading, PRISM) and only from its listed
workstations. The owner's shared token keeps working for the owner only.

## Level 2: the hospital package on a GPU machine

Package 2 needs a Linux GPU machine where the account may run Docker (`deployment/hospital-server/README.md`).
On dr-train the project account is not in the `docker` group; adding it is the dr-train administrator's
decision.

## Rules that do not change

- No patient images on dr-train unless consented; the launcher checks the Admin page's AI-server choice and
  consent mark.
- GPU0 only. Never GPU1, Ollama or other teams' work.
- Daily limits on the team server: calls, GPU-seconds, AI hours 06:00 to 22:00 Thai time
  ([MODEL_SERVER_OPERATIONS.md](MODEL_SERVER_OPERATIONS.md)).
