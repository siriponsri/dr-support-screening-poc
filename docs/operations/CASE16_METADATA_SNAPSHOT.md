# Read-only case16 application metadata snapshot

Engineering helper for the finite QA runner; not a public export endpoint,
clinical action, image export or permission to read a hospital database.
No genuine snapshot has been acquired by this implementation.

Use `dr_support.services.case16_snapshot.case16_metadata_json` with the **existing,
already authorized application object** and explicit designated workspace,
schema and observed revision. Do not construct `create_app()`, run START, read
private configuration, initialize/migrate a database or reconstruct a case to
obtain this object. Integration into the coordinating lane's authorized existing
app context is still required before genuine acquisition. There is no new HTTP
route, credential reader, CLI that starts an app, or runtime registration.

```python
# In the authorized existing app context only; placeholders are not input data.
from dr_support.services.case16_snapshot import case16_metadata_json

document = case16_metadata_json(
    app,
    workspace_id=designated_workspace_id,
    database_schema=designated_test_schema,
    revision=observed_case16_revision,
)
# Only after local destination authorization/privacy checks, save NEW file:
# with open(new_owner_controlled_path, "xb") as target:
#     target.write(document)
# Report only that path and hashlib.sha256(document).hexdigest().
```

Do not use the denied qa-private folder. Do not print the document, upload it to
QA, put it in Git, copy it into logs or send it in chat. It can contain private
context and human annotations even though image bytes are excluded. The helper
returns bytes and writes no file; destination approval and existing private
storage controls belong to the authorized acquisition step. `xb` must not be
replaced with an overwrite of an existing record.

## Data and consistency contract

The output has exactly `case`, `admission`, `image`:

- `case` is the full original persisted JSONB document. No `get()`, additive
  defaults, absent-row case, clinical projection or eligibility repair is used.
  Missing versus null, human grades/reviews/annotations, events, inference
  history, derivatives, preparation context and unknown future fields survive.
- `admission` is the full registered application projection; if the case has an
  embedded admission it must equal that projection, including null versus absent.
  Required identity/modality/quality/integrity keys must exist and be non-null.
  Existing uncertainty and source-change evidence is preserved, not set to pass.
- `image` contains original registered `source_type`, `source_origin`, `source`,
  `modality`, `media_type` only. No image bytes, filename, token or DSN is added.
  Source references already in original objects are not redacted or invented.

The helper holds the existing workspace-manager lock, then the selected store
lock. The concrete PostgreSQL store executes one schema-qualified, workspace-
and-case-scoped SELECT in `REPEATABLE READ READ ONLY`, fetching only the pinned
case16 row. Row/document ID and integer revision must agree; caller's revision
must match. No observed-payload/revision write cache is updated, no table is
created and no mutation query is issued. Missing case fails instead of creating
an in-memory default.

Both recorded case hashes, admission source hash and the hash of the already
registered in-memory image bytes must equal the fixed case16 identity. An
explicit nested source-metadata hash cannot conflict. No recorded hash is filled
from current bytes. Image origin/modality must agree with the admission;
missing image metadata fails. App store/workspace/image/admission projections
are checked again before release. The helper does not open source image files.

Only a concrete `PostgresCaseStore` in a matching manager/app workspace/schema
and single-worker runtime is supported. No SQLite/memory fallback. The SQL row
is one database snapshot; registered image metadata is process-local immutable
`BridgeImage` state checked against its admission projection. This does not
provide distributed locking or freeze arbitrary external file writers. Later
QA preparation must revalidate the frozen document, actual original bytes,
admission eligibility and model pins; snapshot success is not execution approval.

Failures have bounded metadata-free helper codes for missing/inconsistent rows,
scope/revision/projection drift, missing metadata or conflicting hashes. Database
access failures propagate without fallback; do not log raw exception/context
or manufacture a replacement snapshot. Retry requires a legitimate refreshed
operator selection, not changed eligibility or invented revision.

## Qualification and remaining gates

Synthetic tests use the actual `PostgresCaseStore` and helper with an injected
SQL connection/transaction transport and generated in-memory bytes. They check
read-only SQL/one-row scope, lock ownership, original clinical/unknown fields,
absent/null, cache immutability, revision and row identity mismatch, missing
metadata/row, source conflicts, projection changes, multiple-worker rejection
and transaction closure on failure. Tests do not connect to PostgreSQL or create
an app/server. Synthetic pins are overridden only inside fixture scope; the
production case16 constant is asserted unchanged.

Live PostgreSQL transaction behavior and acquisition of the actual case16 record
are NOT_RUN. The coordinating lane must select the authorized existing isolated
workspace/app context and verify access before calling this helper. Retain
original DB/source/clinical state. Supply only the resulting local path/hash to
the finite-runner preparation; refreeze/review its changed manifest/ZIP/argv
digests before any separately approved execution. Live PRISM registration stays
disabled; no inference allowance, clinician privileges or hospital export gates
change. Rollback is a reviewed revert of this bounded source commit, without
database rollback/deletion or removal of existing snapshots.
