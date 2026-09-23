# Deployment

## Supported topology

```text
Clinician browser
      |
Review workstation: APP_PROFILE=review, MODEL_RUNTIME=remote
      |  REMOTE_MODEL_URL (+ optional bearer token)
Hospital LAN / protected boundary
      |
GPU Model API: APP_PROFILE=model_api, MODEL_RUNTIME=local
      |
Verified RETFound + PRISM-DR assets on local storage
```

The workstation owns the review database, workspace catalog, source references, annotations, and dataset exports. The Model API is stateless for clinical records and serves only model metadata and inference. Do not expose the GPU service to the public internet.

## Review workstation

Build the frontend once with `npm run build`, then start `START.cmd` on Windows. The process listens on `127.0.0.1:8000` by default and serves the app at `/app/`. The workstation can admit and review stored cases while the Model API is unavailable; model actions report unavailable rather than silently switching to local weights.

## Model API

The supported Linux service is the included systemd unit:

```bash
cd /opt/dr-support-screening-poc
sudo ./scripts/model-server/install-service.sh
sudo systemctl start dr-support-model-api
sudo systemctl status dr-support-model-api
./scripts/model-server/healthcheck.sh
```

The unit reads `/etc/dr-support/model-server.env`, runs as `drsupport`, uses one worker, and starts `scripts/model-server/start.sh`. Stop, restart, and inspect logs with:

```bash
sudo systemctl stop dr-support-model-api
sudo systemctl restart dr-support-model-api
sudo journalctl -u dr-support-model-api -n 100 --no-pager
```

The service helper expects the release at `/opt/dr-support-screening-poc`; edit the environment file before first start. Keep the model port behind the hospital firewall and use an approved reverse proxy or protected LAN boundary for any cross-host connection.

## Connectivity

Set `REMOTE_MODEL_URL` on the review workstation to the Model API base URL, for example `http://model-host.example:7860`. Use HTTPS when traffic crosses an untrusted segment. If the server requires bearer authentication, set `REMOTE_MODEL_TOKEN` through the workstation's private environment or secret manager. The token is not stored in SQLite, returned to the UI, or logged.

## Restart and offline check

After a successful setup, disconnect external network access and restart the service. `start.sh` runs read-only verification and then starts FastAPI. `healthcheck.sh` must report `"status":"PASS"`; `/v1/models` must return the expected RETFound and PRISM-DR descriptors. A missing or modified asset is a deliberate startup failure and requires operator intervention.

## Rollback

Keep the previous validated release directory and its verified model asset directory until the replacement passes health and smoke checks. Roll back by stopping the unit, restoring the previous release path/configuration, and restarting the unit. Do not overwrite model assets in place without recording their hashes.
