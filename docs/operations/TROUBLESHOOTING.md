# Troubleshooting

## Review application does not start

For an extracted release, run `CHECK_SYSTEM.bat`, then `FIRST_RUN.bat` if the project-managed Python is missing. For a developer checkout, rerun the documented `uv sync` and frontend `npm.cmd ci` / `npm.cmd run build` commands. `START_DR_SCREENING.bat` writes stdout/stderr to `local-state/logs/`. Do not set `APP_PROFILE=review` with `MODEL_RUNTIME=local`.

If the system check reports managed PostgreSQL as not ready, start Docker Desktop for the project-owned local path, or configure `DR_SUPPORT_DATABASE_URL` in the private server environment and verify that the target accepts `SELECT 1`. The launcher does not print the DSN or switch to SQLite. An explicit `DR_SUPPORT_CASE_STORE=sqlite` run is legacy compatibility mode and is not normal managed review readiness.

## uv or Python provisioning is blocked

The first release setup downloads uv and Python 3.12 from their official sources. Use an approved proxy or internal mirror if hospital policy blocks those downloads, then rerun `FIRST_RUN.bat`. Do not replace the machine Python or manually point the workstation at an untested interpreter. `CHECK_SYSTEM.bat` is read-only.

## Developer frontend dependencies are unavailable

The packaged workstation does not require Node.js or npm. In a developer checkout, install the supported Node.js version, run `npm.cmd ci` under `frontend/`, and rebuild with `npm.cmd run build`.

## Frontend build is stale or missing

The release launcher requires the prebuilt `frontend/dist/index.html` and the release builder verifies `frontend/dist/build-identity.json` against the source commit and deterministic frontend source digest. In a developer checkout, rebuild it with `npm.cmd run build`; in an extracted release, re-extract the package if the bundle or identity is missing or stale.

## Port 8000 is already in use

`START_DR_SCREENING.bat` reports the owning PID and executable name only and never kills an unrelated process. Stop the known owner using its own service controls, then rerun `START_DR_SCREENING.bat`. Do not change the workstation bind address to `0.0.0.0`.

If startup reports legacy or cross-checkout PostgreSQL state, preserve or back up any data before removing only the ignored `local-state/release/postgres.env` file. Rerun startup to provision checkout-isolated state; the old named volume is not removed automatically and requires a separate owner-approved migration or cleanup.

## Browser does not open

Open `http://127.0.0.1:8000/app/` manually after `START_DR_SCREENING.bat` reports a healthy service. The start launcher can be rerun without starting a second server.

## Review cannot reach the Model API

Check `REMOTE_MODEL_URL`, the host firewall, and the service status. From the review host, request `/health` and `/v1/models` from the configured base URL. The model list must advertise the requested task, modalities, ready status, and release state. If a bearer token is required, set `REMOTE_MODEL_TOKEN` privately and restart the review process. Review state remains local; inference is unavailable until connectivity is restored, but manual review remains available.

## No compatible capability for the image type

The review app does not guess a model domain. Confirm the image type in
**Confirm Image**, then check **Settings** for a ready capability advertising
that type. UWF grading requires a ready global capability advertising `UWF`;
CFP grading requires a ready global capability advertising `CFP`; `Other / Unknown`
is manual-only. PRISM is lesion assistance and is never selected as a DR grader.

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
