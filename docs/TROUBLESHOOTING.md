# Troubleshooting

## Review application does not start

Check that Python is 3.11 or 3.12, `.venv` exists, and the frontend bundle exists at `frontend/dist/index.html`. Run the workstation install steps in `INSTALLATION.md`, then rebuild with `cd frontend && npm run build`. Do not set `APP_PROFILE=review` with `MODEL_RUNTIME=local`.

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
