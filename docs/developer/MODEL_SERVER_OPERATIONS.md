# Model server operations

Two ways to serve the models:

1. **Regular shared gateway on dr-train** (team server, development and demos, TEST_ONLY): a CPU gateway with
   a daily authority that starts a GPU child on demand. This is what the one-click demo uses.
2. **Model API on a hospital GPU host** (`APP_PROFILE=model_api`): `scripts/model-server/setup.sh` and
   `start.sh` natively, or the Docker package in `deployment/hospital-server`.

Neither is a clinical service or a final release.

## 1. Regular shared gateway on dr-train

### What runs where

| Part | Where | Identity |
| --- | --- | --- |
| Control gateway (CPU) | dr-train, `127.0.0.1:7860` | current deployment folder `deployments/regular-20261031-r05` (identity equal to r04, so the r04 PRISM pins stay in use) |
| Daily authority | dr-train, `regular/r01/` | one lineage since 31 October; reopened by later deployments, never reset |
| GPU child (on demand) | dr-train, `127.0.0.1:7861`, GPU0 only | reviewed `m1_session` worker, pins checked by a CPU identity check per deployment (`regular/r0N-identity.json`) |
| Review app | the owner's workstation, `127.0.0.1:8010` | `scripts.demo.server_app serve-regular`, own PostgreSQL workspace, backend-held token |

Limits enforced by the authority: 1,500 admitted calls and 43,200 GPU-seconds per Thai day; AI hours 06:00
to 22:00 Asia/Bangkok (no new admission after 21:55); one running call; 300 s funded segments, charged in
full; the child stops after 300 s idle. The owner allows extending this budget during development, but a
change of the authority config needs a new authority record (new state folder, old one kept as evidence).

Each deployment is a new folder made by `git archive` from a reviewed main commit; old folders, pins and
logs are kept. Never edit a deployment in place.

### Start, status, stop (on dr-train)

Over the existing SSH route (strict host key, existing key). Never print the token.

```bash
P=/home/siripon/projects/dr-model-api-qa; D=$P/deployments/regular-20261031-r05
# start (CPU only; the GPU child starts only for queued work inside AI hours)
setsid nohup $P/environments/prism-qa-torch213/bin/python -I -B $D/scripts/model-server/regular_service.py serve \
  --deploy $D --models $P/m1-continuation-service-20261025/EXPECTED_BATCH_MODELS.json \
  --prism-pins $P/regular/r04-inputs/PRISM_WORKSPACE_PINS.json \
  --state $P/regular/r01 --lineage $P/regular/r01-lineage.json \
  > $P/regular/r05-service.log 2>&1 < /dev/null & echo $! > $P/regular/r05-service.pid
# status: listeners and GPU0 memory (GPU1 belongs to another team and is never touched)
ss -ltn | grep -E ':786[01] '; nvidia-smi --query-gpu=index,memory.used --format=csv,noheader
# stop: graceful (the gateway drains and stops its child)
kill -TERM "$(cat $P/regular/r05-service.pid)"
```

`scripts/demo/remote-start-gateway.sh` runs the same start command for the one-click demo (it writes
`regular/oneclick-service.pid`). At start the gateway settles anything a previous gateway left open: a call
that may have run becomes UNKNOWN (charged) and pauses new work for the operator; an unsent call is
released. Status per workstation: `GET /v1/regular/status` (authenticated), shown in the Worklist "AI batch"
panel.

### One click (owner workstation)

Desktop shortcut "DR Screening Demo" (made by `scripts/demo/install-desktop-shortcut.ps1`) or
`scripts/demo/start-dr-train-demo.bat`: checks the SSH route, starts the gateway if nothing listens on 7860,
starts the review app (which warms the GPU child inside AI hours) and opens the browser. Settings live in
the private `%LOCALAPPDATA%\DRScreening\M1PrivateConfig\demo.env` (template `scripts/demo/demo.env.example`).
On first start it asks the owner once to type YES that the workspace holds only public or consented images;
the answer is recorded as the Admin page's AI-server choice and can be changed there. Closing the window
stops the app; `scripts/demo/stop-dr-train-demo.sh --gateway` also stops the gateway. Outside AI hours it
stops with a plain message.

### Review app by hand (workstation)

```powershell
.\.venv\Scripts\python.exe -m scripts.demo.server_app serve-regular --allow-remote-token-read `
  --workspace-id <ws_m1_...> --prism-pins <M1PrivateConfig>\regular-20261031-r04\PRISM_WORKSPACE_PINS.json `
  --workstation <simple-name> [--public-samples] --app-port 8010 --model-port 47860
```

`--public-samples` admits only the ten hash-pinned public samples; `--public-demo-folder` admits an
owner-confirmed public folder. Starting needs AI hours (the PRISM handshake needs the GPU child); outside AI
hours use the `prepare` mode.

### Rollback

1. Stop the review app. Clinician data stays in PostgreSQL; nothing is deleted.
2. Stop the current gateway (`kill -TERM` its pid) and start the previous deployment folder with its pins
   (r05 back to r04 uses the same command with `D=.../regular-20261031-r04`). Confirm `7860` and `7861` have
   no stray listener and GPU0 is idle.
3. Keep `regular/r01/` (authority and audit chain). Never delete or reset it; a new authority config needs a
   new state folder.
4. To return the workstation to an earlier main, check out that commit and rebuild `frontend/dist`.

### Known limits

- Batch PRISM on images whose quality is NOT_EVALUATED is refused by the host (it requires GRADABLE) while
  the app still offers it.
- Opening the app warms the GPU child, so each app start costs a segment.
- A call waiting for its queue turn holds that app's inference lock (at most the 300 s queue wait).
- The release Model API ZIP does not include `scripts/model-server/regular_*.py`; dr-train runs a
  `git archive` deployment instead.

## 2. Model API on a GPU host

### Setup and start

```bash
cd /opt/dr-support-screening-poc
./scripts/model-server/setup.sh     # once, online: venv, pinned sources, weights, hash checks, smoke inference
./scripts/model-server/start.sh     # verifies assets first (never downloads), then serves on 0.0.0.0:7860
./scripts/model-server/healthcheck.sh
```

`start.sh` sets `APP_PROFILE=model_api`, `MODEL_RUNTIME=local`, `INFERENCE_DEVICE=cuda:0`, `WORKERS=1` and
`MODEL_REQUIRE_VERIFIED_ASSETS=1`, and runs `python -m dr_support.setup_models --model <provider set> --verify`
before serving. A missing GPU is a readiness failure, not a CPU fallback. Assets live under
`local-state/bridge` (runtime state, never committed).

Provider sets (`MODEL_API_PROVIDER_SET`): `legacy` (RETFound CFP + PRISM), `retfound` (loopback 7864),
`prism` (loopback 7862, read-only `PRISM_SOURCE`/`PRISM_WEIGHTS`), `uspec` (UWF grading, isolated
interpreter, `USPEC_MODEL_DIR`, `USPEC_ENABLE_CANDIDATE_LOAD=1`), `combined`.

### Pinned provenance

Changing any of these is a provenance change that needs the owner.

- RETFound source revision `ae9a9ecf37857cf47b8aa9f87cd6f710d75db287`, checkpoint SHA-256
  `a96b9dbcb78eff373912fb0a48d316dc35ffb0715bb2a1b9128b096d780edbbf` (`providers/retfound.py`).
- PRISM-DR source revision `79637440a535e4f8118e939d3787121f82180125`, archive SHA-256
  `966a38bade7ed9049d5bc4b91a3adebb8f4c92afba64386abf6ab13a537c3b49`, file hashes in
  `dr_support/providers/prism_assets.json`.
- USPEC: exact `manifest.json` and `grading_state.pt` identity, research identity `NBeye-research/USPEC`,
  app capability `uspec-uwf-grading`. Rights `UNVERIFIED`, clinical validation `NOT_ESTABLISHED`,
  production `NOT_AUTHORIZED`.

Licences: RETFound CC BY-NC 4.0; PRISM-DR code MIT, weights for academic use, Ultralytics AGPL-3.0 (see
`THIRD_PARTY_NOTICES.md`). These do not clear commercial or clinical use. PRISM is trained for CFP; UWF use
is an experimental adaptation (`NOT_VALIDATED_FOR_UWF`).

### Health and contract

- `/health` reports `status` and `assets_verified`; a verified service reports `PASS` and `true`.
- `/v1/models` is the discovery surface: a capability is usable only when it advertises its task,
  modalities, ready status and a non-blocked release status. `/v1/capabilities` lists the full registry.
- `POST /v1/predict/dr` (RETFound for CFP, USPEC for UWF) and `POST /v1/predict/lesions` (PRISM). The v2
  routes carry explicit source, analysis, transform, capability and case-revision context. PRISM UWF uses
  the additive `bridge.v2.1` envelope.
- Rectangles are in original-image pixels. Empty lesion output is valid and is not proof of no lesions.
  Scores are raw model output, not calibrated probabilities.
- The review app routes DR grading only to a ready capability for the clinician-confirmed modality (CFP or
  UWF); PRISM is lesion assistance, never a grader.

## 3. PRISM one-use input receipts

PRISM runs only through a prepared, one-use receipt (`services/prism_preview*.py`):

1. `POST /v1/cases/{image_id}/prism-input-preview`: CPU-only preparation. Freezes source and wire bytes,
   the UWF mask (mask A2, `imaging/uwf_rubber_rim_mask.py`), transform and model pins; returns a receipt.
2. `GET .../prism-input-preview/{token}/assets/{name}`: same-origin preview PNGs, `Cache-Control: no-store`.
3. `POST .../prism-input-preview/{token}/infer`: receipt fields must match exactly. Source, wire, mask,
   pins, configuration, transform, admission, revision and workspace are rechecked right before the model
   runs. Success or failure consumes the token; sibling tokens are invalidated; there is no automatic
   retry or resend.

The cache is process-local (at most 16 plans or 128 MiB, 300 s expiry), so the review app must run with
exactly one worker; restart or expiry needs a new preparation. Legacy v1/v2 review PRISM routes are
refused (409). The provider must implement the `prism-wire-binding.source-attested.v2` protocol
(`providers/prism_bound.py`, `prism_remote_bound.py`, `prism_workspace_remote.py`); adding an attribute is
not qualification. The external FOV mask is conditional on the native ROI succeeding; if it fails the run
falls back to the full original and reports FALLBACK. Raw lesion proposals stay review suggestions.
