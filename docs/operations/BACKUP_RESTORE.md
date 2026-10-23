# Backup and Restore

Hospital M1 evidence boundary: synthetic/fake-process tests verify the recovery
controls below. A live dump/restore, restored application reopen/export, service
restart and hospital-target acceptance remain separate measurements. Offline
bundle verification does not establish a live restore or real inference pass.

## What to back up

In managed PostgreSQL mode, back up the configured PostgreSQL database with the approved `pg_dump` process, the configured output folder containing dataset exports, and the hospital-controlled source image storage. Preserve the active workspace identifier and schema configuration. In legacy SQLite mode, back up the active Workspace review database and the catalog configured by `DR_SUPPORT_WORKSPACE_CATALOG` or the local default.

Keep a separate controlled backup of the verified Model API asset directory and its configuration record. Do not place model weights or secrets in Git.

## What is reproducible

The frontend bundle can be rebuilt with `cd frontend && npm ci && npm run build`. Python dependencies can be installed from `pyproject.toml` and the lockfile-backed environment. Model assets can be reacquired through the approved online setup and must pass the pinned revision and hash checks before use. CVAT tasks are external and require the hospital's own retention policy.

## Backup procedure

Stop writes to the review workstation, then take a file-consistent PostgreSQL backup in managed mode or copy the SQLite database/catalog in legacy mode. Back up the output directory as required by local policy. Record the release commit SHA, active workspace configuration, schema name, and model asset hashes. Keep source images in their original hospital-controlled location; a database backup alone does not contain all source bytes.

## Restore procedure

1. Install the same release commit and dependencies.
2. Restore the PostgreSQL database/schema, or the SQLite database/catalog in legacy mode, plus source image folders and output folder to approved locations.
3. In managed mode, verify the active workspace profile and `DR_SUPPORT_DATABASE_URL`/schema configuration. In legacy mode, open or recreate the Workspace profile with the restored paths; profile deletion never deletes source or review files.
4. Run the backend and scan the input folder.
5. Verify case count, patient/eye context, review history, source hashes, and exported manifest contents.
6. On a Model API host, run `python -m dr_support.setup_models --model all --verify` before accepting inference traffic.

## Restore validation

Open one synthetic/public case in Worklist and Review, confirm the original image displays, inspect Models & Audit provenance, and perform a test export to a separate output folder. Never use PHI for a restore demonstration unless the hospital has approved it.

## PostgreSQL backup and restore after cutover

Backup files are runtime artifacts. Keep them in an approved private location;
do not commit them, put them under `local-state/`, or include credentials in a
command transcript. After PostgreSQL becomes authoritative, its backup and
restore path is the supported recovery mechanism. Legacy SQLite files are not
a synchronized rollback target after PostgreSQL-only edits.

### Guarded recovery tool and prerequisites

`dr_support.persistence.recovery` operates on an existing dedicated PostgreSQL
schema and explicitly approved original-image root. It never creates, drops,
resets or truncates a database; changes roles/credentials/firewall; starts/stops a
service; removes a volume; or automatically deletes partial results. Normal
commands are plans until `--apply`/`-Apply` is supplied explicitly.

The operator must already have compatible PostgreSQL `pg_dump` and `pg_restore`
utilities installed on `PATH`. The tool installs neither clients nor Docker. The
database must already be available. Do not run `STOP_DR_SCREENING.bat` immediately
before a managed-local database dump: that launcher also stops its owned DB.

Use a hospital-approved private destination outside Git and the source checkout,
with suitable existing access/retention controls. The tool changes no ACLs and
does not encrypt backups. Use public/synthetic data for initial qualification
unless the data owner approved the actual source and destination.

Source connection material remains in the existing private
`DR_SUPPORT_DATABASE_URL`/`DR_SUPPORT_DATABASE_SCHEMA`. Windows backup can consume
the existing private `.env` or checkout-owned PostgreSQL state. The child utility
receives connection settings only in its process environment, never a DSN/password
argument. Raw utility stderr is not printed because it can reveal credentials.

Source permissions must allow a consistent read-only snapshot and schema dump.
Restore permissions must allow creating the dedicated schema and its objects.
The current application startup still runs migrations; separate migration and
least-privilege runtime roles remain a later bounded requirement. Do not grant
broad privileges automatically to bypass that gap.

### Bundle scope and verification

The bundle contains a custom-format dump of the complete configured schema,
including all its workspaces/cases/migration receipts, and exact original-image
copies under the approved root. Supported suffixes are `.jpg`, `.jpeg`, `.png`,
`.tif`, `.tiff`, `.dcm` and `.dicom`. It preserves release/commit identity,
migration checksums, workspace configuration/revisions, case revisions/payload
hashes and original file paths/sizes/SHA-256. AI and physician fields remain
separate in the original JSONB payload; backup never creates labels.

This increment uses bundle format `dr-support-recovery.v2` and supports only
ordinary `WORKSPACE` admissions with preserved `WORKSPACE_INPUT/<filename>`
references and content-hash case identities. For each persisted case the existing
application scanner must decode a matching original at the **top level of that
case's own workspace input folder**. A matching hash in another workspace or a
nested directory is insufficient. Workspaces containing cases need an input
folder inside the approved image root. The manifest binds each case to those
scan-visible relative paths; verification repeats the same scanner on copied
originals, and post-restore verification scans only the new restored roots.

Hospital-authorized, demo, generated/runtime-registry admissions and their
external root/linkage configuration are explicitly **BLOCKED** in this increment.
Their recovery contract needs separate qualification; moving a catalog folder
does not reproduce those source lanes. No admission, source origin, logical
reference, historical migration path or case payload is rewritten to fit the
ordinary lane. Old v1 bundles remain unchanged and are not accepted by this tool.
This bounded recovery increment does not complete Hospital M1 acceptance E.

Missing hashes, missing/undecodable or non-visible originals, inconsistent case
identities, redirected paths and incompatible migration history fail closed.
Dump and metadata share one exported read-only PostgreSQL snapshot. Originals
are copied without moving/recompressing; hashes are checked again during copying.
Completion is recorded only after verification.

Historical export archives, model weights/dependencies, credentials/environment
files, roles and server configuration are not included. Preserve these separately
according to approved hospital retention/offline-install/secret-management policy.
Dataset export alone is not a full recovery backup. Bundle self-hashes detect
changes but do not establish archive trust. Restore requires an independent
manifest pin retained from the trusted backup-creation result before the bundle
is transferred or supplied for restore. `pg_restore` can execute archive SQL;
a self-consistent foreign archive is not safe merely because its own receipt
matches. Never calculate the expected pin from an untrusted supplied bundle.

### Plan, back up and verify on Windows

Create only the approved parent destination directory first. The final bundle
directory must not exist or overlap the image root. Replace example paths and
release identifier with approved values; none of these arguments is a secret:

```powershell
.\BACKUP_DR_SCREENING.bat -ImageRoot "D:\Approved-QA\originals" -Destination "E:\QA-Backups\recovery-001" -Release "<release-or-commit>"
```

Default `PLAN_ONLY` checks database/image state read-only without starting a dump
or creating output. Review counts/scope, then explicitly apply and verify:

```powershell
.\BACKUP_DR_SCREENING.bat -ImageRoot "D:\Approved-QA\originals" -Destination "E:\QA-Backups\recovery-001" -Release "<release-or-commit>" -Apply
.\BACKUP_DR_SCREENING.bat -Destination "E:\QA-Backups\recovery-001" -Verify
```

`BACKUP_VERIFIED` includes `manifest_sha256`. Retain that value in a separate
trusted operator-controlled record, outside the bundle, together with the release
and source/target approval. This pin covers manifest metadata and the exact dump/
image hashes. Without that independently retained pin, restore remains blocked.
Do not use the supplied bundle's `receipt.json` as the independent record.

`-Verify` reads only saved bytes/migration metadata/scanner results: no DB/model
request. Without an independent pin it establishes integrity only, not origin or
permission to execute archive SQL. Portable verification can also compare the pin:

```bash
python -m dr_support.persistence.recovery verify --bundle <absolute-bundle> --expected-manifest-sha256 <independently-retained-64-hex-pin>
```

The existing application's DB lifecycle is unchanged. If a maintenance window
requires quiescing review writers, use the approved operating procedure while
keeping the DB available.

Equivalent portable commands in the installed project environment:

```bash
python -m dr_support.persistence.recovery plan --image-root <absolute-image-root> --destination <new-absolute-bundle> --release <release-or-commit>
python -m dr_support.persistence.recovery backup --image-root <absolute-image-root> --destination <new-absolute-bundle> --release <release-or-commit> --apply
python -m dr_support.persistence.recovery verify --bundle <absolute-bundle>
```

### Isolated restore

An approved DB operator must provision a **new empty test database** through the
existing administration process. Its exact name must contain a distinct `test`
token, such as `dr_review_restore_test`. The tool rejects the source database
name even on another host, mismatched configured/actual/expected names, occupied
targets (including custom schemas), mismatched schema, corrupt/missing image
hashes, redirected paths and existing destinations. It never empties a target.

Use a fresh, isolated target shell and privately set
`DR_SUPPORT_RESTORE_DATABASE_URL` and the matching `DR_SUPPORT_DATABASE_SCHEMA`.
The restore launcher deliberately does **not** load the source checkout's `.env`.
Restore rejects inherited `DR_SUPPORT_DATABASE_URL`, `DR_SUPPORT_WORKSPACE_ID`,
`DR_DEMO_FOLDER`, hospital root/linkage/scope configuration and enabled hospital
ingest. It does not clear or modify source configuration for you. This prevents a
source-root override from concealing broken restored workspace paths.

Never paste connection values into commands/logs. Keep the target isolated from
concurrent application/admin writers throughout plan/apply. The tool repeats its
empty-target check just before restore, but cannot stop unrelated admin writes.

Use separate new image/output directories whose approved parents already exist:

```powershell
.\RESTORE_DR_SCREENING.bat -Bundle "E:\QA-Backups\recovery-001" -ExpectedTargetDatabase "dr_review_restore_test" -ExpectedManifestSha256 "<independently-retained-64-hex-pin>" -ImageDestination "D:\Approved-QA\restored-originals-001" -OutputDestination "D:\Approved-QA\restored-output-001"
```

After `PLAN_ONLY` and confirming target writers are quiescent:

```powershell
.\RESTORE_DR_SCREENING.bat -Bundle "E:\QA-Backups\recovery-001" -ExpectedTargetDatabase "dr_review_restore_test" -ExpectedManifestSha256 "<independently-retained-64-hex-pin>" -ImageDestination "D:\Approved-QA\restored-originals-001" -OutputDestination "D:\Approved-QA\restored-output-001" -TargetQuiesced -Apply
```

Originals are copied and verified before DB mutation. The dump is also copied to
the new private output root and its hash checked against the independently pinned
manifest immediately before execution. A changed supplied archive is rejected;
`pg_restore` reads the verified private copy. Include space for this additional
dump copy in restore storage planning. `pg_restore` uses
`--single-transaction --exit-on-error --no-owner --no-privileges`, without
`--clean`/`--create`. Only restored target workspace input/output paths are remapped
to new roots; case payloads and label revisions remain unchanged. Per-workspace
output directories use a hash of the workspace ID. Historical exports are not
restored. The source DB, original source bytes and existing exports are untouched.

`RESTORE_DATA_VERIFIED` requires matching migrations, case IDs/revisions/payload
hashes, workspace IDs/revisions and original hashes. It explicitly leaves app
reopen/export and inference `NOT_RUN`.

Portable restore uses the same private target environment:

```bash
python -m dr_support.persistence.recovery restore --bundle <absolute-bundle> --expected-target-database dr_review_restore_test --expected-manifest-sha256 <independently-retained-64-hex-pin> --image-destination <new-absolute-images> --output-destination <new-absolute-outputs> --target-quiesced --apply
```

### Acceptance, failure handling and rollback

After a live restore, start an isolated app against the exact `target_database`
recorded in the verified restore result/receipt. Do not reuse the ordinary source
launcher or reload its `.env` for restore acceptance. Use a fresh target app
environment with explicit target `DR_SUPPORT_DATABASE_URL`/schema,
`DR_SUPPORT_CASE_STORE=postgres`, `APP_PROFILE=review`, `MODEL_RUNTIME=remote`,
without legacy state/catalog/workspace overrides, demo folders or hospital roots.

Before constructing the existing app, the acceptance harness must call
`validate_restored_app_environment(target_settings, expected_database=<recorded-test-target>)`
and then `create_app(include_samples=False, include_demo_fixtures=False)` without
loading any additional source configuration between validation and construction.
The environment guard does not start an app or establish an application pass.
This fixtures-disabled acceptance launch is **NOT_RUN** until measured, and the
standard no-code source launcher is not a validated restored-app selector.

Check workspace selection, original display/source
hashes, patient/eye context, AI/physician separation, audit/history, save/reopen/
edit and export to the new output directory. Record exact release, PostgreSQL
version, counts/revisions and hash comparisons without secret/identifying data.
Repeat for the applicable QA_SERVER/QA_LOCAL profile; fake-process tests and health
200 are not substitutes.

Failure returns exit code `2`, without automatic retry or deletion. Keep partial
directories/DB state private for diagnosis. Do not rerun into them, delete a volume
or treat a missing receipt as success. After resolving the cause, an operator must
approve another clean isolated test target/new destination. If execution policy
denies a launcher, stop and involve IT; do not change execution policy or ACLs.

Application rollback selects a validated compatible release while preserving
current clinician data. Restoring an old backup over current work is a separate
destructive cutover requiring owner/IT approval and is not implemented here.
The historical Phase 1 restore receipt in `M1_PHASE1_POSTGRES.md` §18.1 remains
historical evidence, not a new Hospital M1/hospital-target restore pass.
