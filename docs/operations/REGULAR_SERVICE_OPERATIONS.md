# Regular shared Model API: operations, rollback and the installation candidate

Status: TEST_ONLY commissioning on 2026-10-31. Not a clinical service, not a
final release and not accepted by the hospital. Design and contracts:
[M1_REGULAR_SERVICE_DESIGN.md](../milestone/m1/M1_REGULAR_SERVICE_DESIGN.md).
Owner packet (redacted copy): [owner-packet-20261031](../milestone/regular/owner-packet-20261031/README.md).

## What runs where

| Part | Where | Identity |
| --- | --- | --- |
| Control gateway (CPU) | dr-train, `127.0.0.1:7860` | `deployments/regular-20261031-r01` from main `8527c0f` (no later change under `scripts/model-server/`) |
| Daily authority | dr-train, `regular/r01/authority.sqlite3` | new lineage; old ledgers recorded as evidence only (`regular/r01-lineage.json`) |
| GPU child (on demand) | dr-train, `127.0.0.1:7861`, RTX `GPU-044a8b11-…` only | reviewed `m1_session` worker; pins equal to the reviewed files (CPU identity check) |
| Review app | the owner's workstation, `127.0.0.1:8010` | `m1_server_app serve-regular`, own PostgreSQL workspace, backend-held token |

Limits enforced by the authority: 1,500 admitted calls and 43,200 GPU-seconds
per Thai day; AI hours 06:00 to 22:00 (Asia/Bangkok), no new admission after
21:55; one running call; 300 s funded segments, charged in full; child stopped
after 300 s idle.

## Start, status, stop (host)

All over the existing SSH route (strict host key, existing key). Never print the
token.

```bash
P=/home/siripon/projects/dr-model-api-qa; D=$P/deployments/regular-20261031-r01
# start (CPU only; the GPU child starts only for queued work inside AI hours)
setsid nohup $P/environments/prism-qa-torch213/bin/python -I -B $D/scripts/model-server/regular_service.py serve \
  --deploy $D --models $P/m1-continuation-service-20261025/EXPECTED_BATCH_MODELS.json \
  --prism-pins $P/m1-continuation-service-20261025/PRISM_WORKSPACE_PINS.json \
  --state $P/regular/r01 --lineage $P/regular/r01-lineage.json \
  > $P/regular/r01-service.log 2>&1 < /dev/null & echo $! > $P/regular/r01-service.pid
# status: listeners and GPU0 memory (GPU1 is another team's and is never touched)
ss -ltn | grep -E ':786[01] '; nvidia-smi --query-gpu=index,memory.used --format=csv,noheader
# stop: graceful (the gateway drains and stops its child, confirms cleanup)
kill -TERM "$(cat $P/regular/r01-service.pid)"
```

At start the gateway settles anything a previous gateway left open: a call that
may have run becomes UNKNOWN (charged) and pauses new work for the operator; an
unsent call is released. Status per workstation comes from
`GET /v1/regular/status` (authenticated); the review app shows it in the
Worklist "AI batch" panel.

## Start the review app (workstation)

```powershell
.\.venv\Scripts\python.exe -m scripts.qa.m1_server_app serve-regular --allow-remote-token-read `
  --workspace-id <ws_m1_...> --prism-pins <M1PrivateConfig>\regular-20261031\PRISM_WORKSPACE_PINS.json `
  --workstation <simple-name> [--public-samples] --app-port 8010 --model-port 47860
```

`--public-samples` admits only the ten hash-pinned public samples and sets no
hospital roots. Starting needs AI hours: the app waits (bounded) for the GPU
child because the PRISM handshake needs it. Outside AI hours use the manual
`prepare` mode.

## Rollback

Nothing old was changed, so rollback is stopping the new parts:

1. Stop the review app (Ctrl+C or close its window). Clinician data stays in
   PostgreSQL; nothing is deleted.
2. Stop the gateway (`kill -TERM` as above). Confirm `7860` and `7861` have no
   listener and GPU0 is back to about 1 MiB.
3. Keep `regular/r01/` (authority and audit chain) as evidence. Do not delete or
   reset it; a new run needs a new state folder (`regular/r02`).
4. The earlier M1 deployments (`m1-session-20261025-s04` and older), the closed
   finite ledgers and windows, and their 540/540 history are untouched and stay
   closed. They are not reopened by a rollback.
5. To return the workstation to the previous main, check out that commit and
   rebuild `frontend/dist`; the database schema did not change in this work.

## Installation candidate 0.8.0-m1-regular.rc1

Built from clean main `92a91ea4c974549e67fea89c272f43a7ced1f4c9` with
`scripts/release/build_release.py` (artifacts kept outside Git under
`local-state/release/0.8.0-m1-regular.rc1/`).

| File | Bytes | SHA-256 |
| --- | --- | --- |
| `DR-Screening-Workstation-0.8.0-m1-regular.rc1.zip` | 10,156,412 | `a57226cf2691c566817896ade958361ba0572c55c957b1ed46a77dcab5754abd` |
| `DR-Model-API-0.8.0-m1-regular.rc1.zip` | 478,053 | `0adec499c01c2a9029e0ba2bfd350176d46e65c16bca5fa076f6628366d69334` |

Checked: checksums, no weights, databases, logs, env files, keys or local state
in either archive; the extracted workstation started (synthetic, review profile)
with `/health` and `/app/` 200. Known gaps: the Model API archive does not yet
include `scripts/model-server/regular_*.py` (the host runs a `git archive`
deployment instead); `SHA256SUMS.txt` is written with Windows line endings
(strip `\r` before `sha256sum -c` on Linux); dependencies are not bundled. It is
labelled a candidate, not a final release.
