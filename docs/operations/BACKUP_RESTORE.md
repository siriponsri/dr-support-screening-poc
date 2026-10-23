# Backup and Restore

## Frozen additive hospital recovery v3 contract

This section freezes the bounded Hospital M1 recovery v3 implementation contract
at source baseline `02ff0bc`. Ordinary-workspace v2 remains supported unchanged.
This is a supervised evaluation/annotation recovery feature, not clinical approval.

Hospital activation requires two independently approved private JSON files and
their externally retained **exact file SHA-256** pins. Approval IDs or copies of
pins inside a bundle do not establish authority. Actual maps, source names,
private paths, reader bindings, images and linkage secrets stay out of Git.

The source map has exactly these fields:

```json
{
  "version": "dr-support-hospital-source-map.v1",
  "approval_id": "<owner-it-record>",
  "workspace_id": "<existing-hospital-workspace>",
  "scope": "PRIVATE_PROJECT_EVALUATION",
  "backup_destination": "<approved-new-absolute-bundle-directory>",
  "linkage_key_ref": "<existing-secret-reference-or-null>",
  "roots": [
    {"root_id":"uwf","modality":"UWF","path":"<approved-original-root>","candidate_inventory_sha256":"<approved-sha256>","read_only_sids":[]},
    {"root_id":"cfp","modality":"CFP","path":"<approved-original-root>","candidate_inventory_sha256":"<approved-sha256>","read_only_sids":[]}
  ]
}
```

The restore map has exactly these fields:

```json
{
  "version": "dr-support-hospital-restore-map.v1",
  "approval_id": "<owner-it-record>",
  "source_map_sha256": "<independently-approved-source-map-pin>",
  "expected_manifest_sha256": "<trusted-backup-creation-pin>",
  "workspace_id": "<same-hospital-workspace>",
  "scope": "PRIVATE_PROJECT_EVALUATION",
  "target_database": "<exact-new-test-database>",
  "bundle_path": "<approved-current-absolute-bundle-directory>",
  "image_destination": "<approved-new-private-image-parent>",
  "output_destination": "<approved-new-private-output-directory>",
  "linkage_key_ref": "<same-existing-secret-reference-or-null>",
  "roots": [
    {"root_id":"uwf","modality":"UWF","path":"<image_destination>/uwf","read_only_sids":[]},
    {"root_id":"cfp","modality":"CFP","path":"<image_destination>/cfp","read_only_sids":[]}
  ]
}
```

Roots are always ordered UWF then CFP, distinct, disjoint and non-redirected.
The source map's reader bindings cover its approved backup destination too; the
restore map's reader bindings cover its approved current bundle and new roots.
This permits an explicitly approved private bundle transfer without inspecting
the old source roots or treating bundle contents as access authority.
An approved reader SID is configuration recognizing an existing read-only grant,
not a new grant. Existing privacy/admission/export checks remain unchanged. The
tool never modifies ACLs, roles, credentials, the original `.env` or source files.
Its temporary hospital binding is confined to the dedicated recovery CLI process;
never invoke it inside a running multi-user FastAPI process.

The complete top-level candidate set and exact basenames must be retained.
Candidate ordering is `(name.casefold(), name)`; duplicate handling, generated
CASE references and cross-modality UNKNOWN behavior come from the existing
`scan_authorized_hospital_roots()` unchanged. Unknown/unsupported or undecodable
candidates block this initial v3 increment rather than being omitted. Ancillary
files ignored by the existing scanner are outside the image backup. A source-map
candidate digest may be null only for a read-only plan; applying a backup requires
both non-null approved snapshot digests. A plan can report observed digests, but
cannot approve them or generate an activating map/pin itself.

The v3 manifest binds the source-map pin, ordered candidate inventories, scanner
identity projection, one hospital workspace and each case's exact source hashes,
aliases, modality and trusted linkage fields. A private domain-separated key
challenge proves that the existing linkage secret is unchanged, without storing
or printing it or creating a patient/clinical record. Key absence is explicit;
recovery never creates or rotates a linkage key. Case payload/provenance and
historical migration paths remain byte-for-byte unchanged in the restored DB.

Backup must match the currently authorized source roots and existing source gates.
Restore must match all three independent pins (source map, manifest, restore map),
exact target DB/directories and approved target private-root bindings. No source
root may be a target, ancestor or descendant. The restored catalog input is the
new image parent, containing only the `uwf` and `cfp` subdirectories; missing
hospital configuration cannot silently expose originals through workspace fallback.
The app must use an isolated fixtures-disabled target environment with exactly the
restored roots, no original root/legacy/demo/libpq overrides and no Model API/CVAT
connection for recovery acceptance. All inference remains NOT_RUN.

Acceptance requires: source/bundle/restored scanner identity equality; independent
pin and layout failure regressions; exact DB revisions/clinical payload; actual
Original endpoint hashes from copied UWF/CFP roots with original-root reads
forbidden in the acceptance process; reopened physician state; and export bytes
and physician-only grade folders through existing authorization gates. A denied
export remains denied. Unit/fake-process tests prove controls only. Actual maps,
permissions, PostgreSQL restore, app reopen/export and hospital-target acceptance
remain separate activation/qualification gates, never synthetic proof.

### Hospital v3 operator activation

The data owner/IT must independently approve and retain both maps and their file
pins outside the bundle. Do not derive approval or a manifest pin from supplied
bundle contents. `approval_id` is a reference to that external approval, not a
permission token. Source names and paths in these private maps may be sensitive.
The source and restore maps must not be placed inside a bundle or a new recovery
output/image directory. Their pins are exact bytes: editing whitespace changes
the pin. The tool does not create or approve either map.

For initial inventory discovery only, an independently approved source map may
have null candidate digests. With the existing source environment already active,
run the source plan below without `-Apply`; it returns ordered observed candidate
digests. Stop for the owner's independent snapshot approval. An activating source
map must then contain both approved non-null digests and a new independently
retained file pin. Keep the source candidate set quiescent throughout the backup.

```powershell
.\BACKUP_DR_SCREENING.bat -HospitalSourceMap "D:\Approved-QA\authority\source-map.json" -ExpectedHospitalSourceMapSha256 "<approved-source-map-file-pin>" -Destination "E:\QA-Backups\hospital-v3-001" -Release "<release-or-commit>"
```

After the activating map and source/destination permissions are approved, repeat
the same command with `-Apply`. No image root argument is used in the v3 lane.
Retain `manifest_sha256` from the trusted `BACKUP_VERIFIED` result outside the
bundle. The new directory's existing inherited permissions must pass the unchanged
private-storage check before dump bytes are written; failure retains any empty
partial directory. Verification also checks the whole private bundle and both
copied roots; no ACLs are changed.

```powershell
.\BACKUP_DR_SCREENING.bat -Destination "E:\QA-Backups\hospital-v3-001" -Verify -ExpectedManifestSha256 "<trusted-backup-result-pin>" -HospitalSourceMap "D:\Approved-QA\authority\source-map.json" -ExpectedHospitalSourceMapSha256 "<approved-source-map-file-pin>"
```

Verification needs the same existing linkage secret privately available, or the
explicit approved absent state. It does not load the source `.env` in verify mode.
After a private transfer, verification additionally needs `-HospitalRestoreMap`
and `-ExpectedHospitalRestoreMapSha256` approving the current exact `bundle_path`.

The isolated restore shell must have no source DB/workspace/root/scope/demo
selectors. It carries only the separate target connection/schema and, when the
map requires one, the unchanged existing linkage secret via the approved private
secret mechanism. Never paste a linkage secret or DSN into a command or transcript.
The operator must provision the new empty test DB and approve existing private
permissions on the target parents first. The restore-map roots are exactly
`image_destination/uwf` and `image_destination/cfp` in UWF/CFP order.

```powershell
.\RESTORE_DR_SCREENING.bat -Bundle "E:\QA-Backups\hospital-v3-001" -ExpectedTargetDatabase "dr_review_restore_test" -ExpectedManifestSha256 "<trusted-backup-result-pin>" -HospitalSourceMap "D:\Approved-QA\authority\source-map.json" -ExpectedHospitalSourceMapSha256 "<approved-source-map-file-pin>" -HospitalRestoreMap "D:\Approved-QA\authority\restore-map.json" -ExpectedHospitalRestoreMapSha256 "<approved-restore-map-file-pin>" -ImageDestination "D:\Approved-QA\restored-images-v3-001" -OutputDestination "D:\Approved-QA\restored-output-v3-001"
```

After a successful plan and an approved quiescent target, repeat with
`-TargetQuiesced -Apply`. Root privacy checks and the real scanner run on copied
bytes before the database is mutated, then repeat after restore. Logical source
references, historical migration paths and clinical case payloads remain intact.
Original roots are deny-list metadata during restore and are never probed as a
fallback. New images/outputs must be disjoint from every original root. Unreviewed
and conflicting-modality records retain the existing admission/export behavior.

For app acceptance, use a separate process with the exact restored root JSON,
scope, enable flag and approved existing reader bindings from the independently
pinned restore map. No source root, legacy selector, fixtures, model URL/token,
CVAT connection or inherited libpq endpoint override may be configured. The
`validate_restored_app_environment` preflight must receive `bundle`,
`expected_manifest_sha256`, `hospital_source_map`,
`expected_hospital_source_map_sha256`, `hospital_restore_map` and
`expected_hospital_restore_map_sha256` as well as target settings/name. For v3 it
validates the actual process environment; a substituted environment dictionary is
not accepted. The preflight rechecks copied scanner identity but is not a DB/app
acceptance receipt. Construct the existing app with both fixtures flags false,
without importing any further configuration. There is no new application launcher
or orchestration in this increment.

### M1 entry-guard limitation

**M1 guard-aware recovery is NOT_QUALIFIED.** Current app-schema-only dumps do
not include the optional cross-schema entry guard. A read-only source/post-restore
catalog check therefore rejects the conventional guard schema, an `entry_fence`
table, `m1_entry_fence` triggers on protected app tables, or another non-system
cross-schema trigger function on those tables. The same check precedes target
mutation; an occupied guard target is never emptied. An extension detected after
restore prevents any success receipt and leaves private partial output for review.
This detection is not a guard-aware restore implementation. Do not disable/remove
the guard to bypass it; a separately approved recovery contract and real rehearsal
must qualify that extension first. Offline integrity verification alone cannot
qualify guard dependencies or establish app readiness.

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

The ordinary-workspace lane uses bundle format `dr-support-recovery.v2` and supports only
ordinary `WORKSPACE` admissions with preserved `WORKSPACE_INPUT/<filename>`
references and content-hash case identities. For each persisted case the existing
application scanner must decode a matching original at the **top level of that
case's own workspace input folder**. A matching hash in another workspace or a
nested directory is insufficient. Workspaces containing cases need an input
folder inside the approved image root. The manifest binds each case to those
scan-visible relative paths; verification repeats the same scanner on copied
originals, and post-restore verification scans only the new restored roots.

Hospital-authorized admissions are **BLOCKED** in the v2 lane and require the
independently activated v3 lane below. Demo and generated/runtime-registry lanes
remain blocked. Moving a catalog folder does not reproduce those source lanes.
No admission, source origin, logical
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
`DR_DEMO_FOLDER`, hospital root/scope configuration and enabled hospital
ingest. V3 permits only the same independently mapped existing linkage secret;
v2 also rejects inherited linkage configuration. It does not clear or modify
source configuration for you. This prevents a
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
without legacy state/catalog/workspace overrides or demo folders. V2 has no
hospital roots; v3 must use only its independently approved restored roots.

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
