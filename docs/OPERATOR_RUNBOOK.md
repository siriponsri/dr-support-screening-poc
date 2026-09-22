# Operator Runbook

## Daily readiness

```bash
sudo systemctl is-active dr-support-model-api
./scripts/model-server/healthcheck.sh
```

Confirm that:

- `/health` reports `status: PASS` and `assets_verified: true`.
- `/v1/models` lists `retfound-aptos5` and `prism-dr-5fold`.
- The review workstation opens `/app/` and shows the Model API connection state honestly.
- The workspace input and output folders are mounted and writable by the workstation account.
- Free space is sufficient for SQLite state and exported manifests.

## Service lifecycle

```bash
sudo systemctl start dr-support-model-api
sudo systemctl stop dr-support-model-api
sudo systemctl restart dr-support-model-api
sudo systemctl status dr-support-model-api
sudo journalctl -u dr-support-model-api -n 100 --no-pager
```

For a foreground check from the release directory:

```bash
./scripts/model-server/start.sh
./scripts/model-server/healthcheck.sh
```

## Logs and escalation

Use systemd journal retention and the hospital host's approved rotation policy. Logs must not contain bearer tokens, raw DICOM headers, patient names, or source image bytes. A sanitized escalation bundle should include the release commit SHA, service status, `/health` response, `/v1/models` response, timestamp, and a case image SHA-256 only.

## Routine review operation

The clinician workstation can continue local Worklist, Review state, annotation, and Dataset export operations while the Model API is down. Do not retry inference indefinitely; restore the service or connectivity first. A remote model failure must not be presented as a local decoder failure.

## Model asset maintenance

Do not replace or edit model assets in place. For a new approved release, run the one-time setup in a separate validated directory, compare the printed revisions and hashes with the approved record, run smoke inference, then perform a controlled service restart. A failed verification is a release blocker.

## Optional CVAT

CVAT Online is an optional dense-annotation integration. Its outage does not block local image review or dataset export when the local review state is sufficient. Keep the URL, project ID, and token in private configuration only.

The connector accepts only the configured CVAT Online project and supported
rectangle, ellipse, polygon, polyline, and point shapes. See
`docs/CVAT_ONLINE_SETUP.md` for the credential and round-trip procedure.
