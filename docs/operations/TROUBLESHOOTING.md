# Troubleshooting

## Review application does not start

Run `SETUP.cmd --check`, then `SETUP.cmd` if the project-managed Python, npm dependencies, or frontend bundle are missing. `START.cmd` writes stdout/stderr to `local-state/logs/`. Do not set `APP_PROFILE=review` with `MODEL_RUNTIME=local`.

## uv or Python provisioning is blocked

The first setup downloads uv and Python 3.12 from their official sources. Use an approved proxy or internal mirror if hospital policy blocks those downloads, then rerun `SETUP.cmd`. Do not replace the machine Python or manually point the workstation at an untested interpreter. `SETUP.cmd --check` is read-only.

## Node/npm is unavailable

`SETUP.cmd` accepts compatible system Node.js 18+ or downloads the pinned official Node.js distribution into ignored `local-state/tools/`. It uses `npm.cmd`, so PowerShell execution-policy changes are not required. Rerun setup to repair the managed fallback.

## Frontend build is stale or missing

`START.cmd` hashes the frontend source, Vite/TypeScript configuration, and npm lockfile. If those inputs changed, it runs one build and records the signature under `local-state/setup/`. If the build is missing, run `SETUP.cmd` and inspect `frontend/dist/index.html`.

## Port 8000 is already in use

`START.cmd` reports the owning PID and command line and never kills an unrelated process. Stop the known owner using its own service controls, then rerun `START.cmd`. Do not change the workstation bind address to `0.0.0.0`.

## Browser does not open

Open `http://127.0.0.1:8000/app/` manually after `START.cmd` reports a healthy service. `OPEN_APP.cmd` can be rerun without starting a second server.

## Review cannot reach the Model API

Check `REMOTE_MODEL_URL`, the host firewall, and the service status. From the review host, request `/health` from the configured base URL. If a bearer token is required, set `REMOTE_MODEL_TOKEN` privately and restart the review process. Review state remains local; inference is unavailable until connectivity is restored.

## `/health` is not `PASS`

Run `./scripts/model-server/healthcheck.sh` locally on the server and inspect `journalctl -u dr-support-model-api`. Check `assets_verified`, CUDA availability, requested device, and `/v1/models`. Do not treat `PASS_WITH_WARNINGS` as a verified production asset state.

## Asset revision or hash mismatch

Stop the service. Do not edit or substitute files in place. Confirm the asset paths and rerun `./scripts/model-server/setup.sh` in an approved online environment. If the mismatch persists, escalate with the expected and observed path/revision information without sending weights or secrets.

## CUDA unavailable

Check the NVIDIA driver, `INFERENCE_DEVICE`, and the host's CUDA visibility. The production `model_api` profile fails closed rather than silently falling back to CPU. CPU is suitable only for explicit local development or contract tests.

## Unsupported DICOM modality

If the Worklist says `Unsupported modality`, the object was recognized as DICOM but is not supported ophthalmic retinal input, such as MRI or another non-fundus modality. Do not treat this as a generic image-read failure and do not broaden model support. Codec-required, multi-frame, and decode failures have separate messages and require their corresponding technical fix.

## Image display or admission failure

PNG, JPEG, and TIFF use the raster path. For DICOM, check the optional DICOM dependencies and the displayed admission note. A corrupt or unrecognized source should be replaced or manually reviewed; do not modify the original source in place.

## Dataset export fails

Verify that the active Workspace output folder exists and is writable, that the case is eligible for export, and that there is sufficient disk space. Preserve the error response without exposing internal paths in clinician-facing notes.

## CVAT is unavailable

CVAT Online is optional. Continue with local human review and export where possible. Retry the dense annotation round-trip only after the CVAT URL, project, credentials, and network access are confirmed.
