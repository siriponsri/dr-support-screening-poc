# Operator Runbook

## Daily readiness

```bash
sudo systemctl is-active dr-support-model-api
./scripts/model-server/healthcheck.sh
```

Confirm that:

- `CHECK_SYSTEM.bat` reports PostgreSQL `SELECT 1` readiness, frontend build
  identity/readiness, workspace API readiness when the app is running, and
  either Model API connectivity or explicit manual mode.
- If no external `DR_SUPPORT_DATABASE_URL` is configured, Docker Desktop is
  running for the project-owned local PostgreSQL service. The service is
  named and stopped only through this checkout's release scripts.
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

The Worklist exposes modality, review, DR-grade, lesion-review, and AI-state
filters. Model state is assistance state only: an AI suggestion never replaces
the clinician-confirmed grade or lesion-review decision.

## Legacy SQLite migration (P1-I candidate)

This procedure is an explicit, operator-controlled migration. It does not
switch a real workspace automatically and it does not enable SQLite/PostgreSQL
dual-write. Use only an approved public or synthetic source set for
development qualification; never place credentials, PHI, runtime databases, or
backup files in Git.

Before inventory, stop every legacy writer for the catalog and all referenced
workspace databases, or obtain an approved consistent snapshot. Record the
quiescence window or snapshot identity. The importer opens SQLite in read-only
mode and verifies the catalog and database source-set identity before writing.

Set the PostgreSQL target explicitly in the server environment. Replace every
placeholder before execution; do not paste the resulting value into a log or
committed document:

```powershell
$env:DR_SUPPORT_DATABASE_URL = "postgresql://<user>:<password>@<host>:<port>/<database>"
$env:DR_SUPPORT_DATABASE_SCHEMA = "dr_support"
$env:DR_SUPPORT_CASE_STORE = "postgres"
```

Before the first dry run against a new PostgreSQL schema, explicitly bootstrap
the managed schema. This applies schema migrations only; it does not import
legacy rows, alter source SQLite files, or make the dry run mutate application
data. Run it as a separate operator step and stop if it fails:

```powershell
.\.venv\Scripts\python.exe -c "from dr_support.persistence import PostgresDatabase, PostgresSettings, SchemaMigrator; SchemaMigrator(PostgresDatabase(PostgresSettings.from_env())).migrate()"
```

Run the dry run against the explicit authoritative catalog. Add one or more
`--orphan-root` arguments for configured runtime locations that should be
inventoried. A successful report must end with `Safe to proceed: YES`:

```powershell
.\.venv\Scripts\python.exe -m dr_support.persistence.legacy_migration dry-run `
  --catalog "<absolute-path-to-authoritative-catalog.sqlite>" `
  --orphan-root "<absolute-path-to-legacy-runtime>" `
  --writer-quiesced "<approved-quiescence-window-id>"
```

Use `--snapshot-id "<approved-snapshot-id>"` instead of
`--writer-quiesced` when the source set is an approved consistent snapshot.
The report includes source sizes, modification times, SHA-256 values, case
counts, mappings, conflicts, and orphan files. Do not continue if authority is
ambiguous, a source is missing or invalid, or the source-set hash changed.
Readable SQLite WAL, shared-memory, or rollback-journal sidecars are part of
the effective source state. If sidecar or journal state is unstable between
inventory and verification, stop the migration and establish a new consistent
source boundary.

After reviewing the dry-run report, execute the import with the same catalog,
orphan roots, exact consistency boundary, and exact source-set SHA-256 copied
from the reviewed dry-run report. The import must use that exact reviewed hash;
do not substitute a newly calculated or different value:

```powershell
.\.venv\Scripts\python.exe -m dr_support.persistence.legacy_migration import `
  --catalog "<absolute-path-to-authoritative-catalog.sqlite>" `
  --orphan-root "<absolute-path-to-legacy-runtime>" `
  --writer-quiesced "<approved-quiescence-window-id>" `
  --expected-source-set-sha256 "<sha-from-reviewed-dry-run>"
```

Verify the reported workspace and case counts, IDs, revisions, deterministic
payload content, source-set receipt, and unchanged SQLite file hashes. An
identical rerun is safe and idempotent. A changed source raises a conflict and
rolls back the PostgreSQL transaction; it is not merged automatically.

### Explicit cutover

Cutover is a separate operator action after the same-boundary import has been
verified. Record the stopped legacy writers or snapshot identity, the
pre/post source hashes, PostgreSQL counts and revisions, and the time of the
authority switch. Then restart the workstation with PostgreSQL mode enabled
and confirm the active workspace reports managed PostgreSQL storage. Do not
start the PostgreSQL runtime while legacy writers continue, and do not fall
back to SQLite when PostgreSQL is unavailable.

After PostgreSQL-only edits begin, legacy SQLite files remain intact but are
not a synchronized rollback target. PostgreSQL backup/restore is the
supported recovery path after cutover.

## Model asset maintenance

Do not replace or edit model assets in place. For a new approved release, run the one-time setup in a separate validated directory, compare the printed revisions and hashes with the approved record, run smoke inference, then perform a controlled service restart. A failed verification is a release blocker.

## Optional CVAT

CVAT Online is an optional dense-annotation integration. Its outage does not block local image review or dataset export when the local review state is sufficient. Keep the URL, project ID, and token in private configuration only.

The connector accepts only the configured CVAT Online project and supported
rectangle, ellipse, polygon, polyline, and point shapes. See
`docs/operations/CVAT_ONLINE_SETUP.md` for the credential and round-trip procedure.
