# Finite local case16 bootstrap/acquisition — review before execution

This command creates a NEW clearly labeled engineering test workspace using the
real approved demo source. It does not recover or alter an existing clinical
case, start a server, run inference or upload an image. Genuine execution is
NOT_RUN; this checkpoint is source and synthetic tests for focused review.

## Source established offline

The existing approved `task/qa-comparison-workspace-20261021/input-map-private.json`
matches the frozen driver's manifest digest
`e863a62f0a11aff938bdb8e1b60453aea9a3d70bee04308c3f4ff43ffdd8ffa6`.
Exactly one entry matches case16 source SHA256
`07bc59b885de06bdd0260c771aabde195c26125e824269a691eb566a61a5cd19`;
its declared modality is UWF and size is884251bytes. Its source exists under
the approved `C:/Users/User/Desktop/demoImages` root. The source filename/path
remains in that existing locally controlled map, not duplicated here. Actual
original-byte rehash/inspection is deferred to reviewed execution.

The command pins that map/digest/root and image identity; it offers no argument
to replace the image, expected hash or modality. Traversal, duplicate matches,
changed manifest, redirected source, missing source or changed bytes fail.

## Supported command after focused review

From `C:/Users/User/Documents/Codex/2026-10-21/task-3/integration-review`, with
the **existing** test DSN already supplied as `DR_SUPPORT_TEST_DATABASE_URL` by
its approved credential workflow:

```powershell
& 'C:/Users/User/Desktop/myProject/dr-support-screening-poc/.venv/Scripts/python.exe' -B -m dr_support.case16_acquire --output-root 'C:/Users/User/Documents/Codex/2026-10-21/task-3/evidence' --execute-reviewed-local-ingestion
```

No runtime handle, case JSON or guessed metadata is an operator input. There is
no env-file reader: do not probe qa-private, paste a DSN into arguments/logs,
change credentials or select another DB if the existing credential route is
unavailable. Missing/invalid DSN blocks before DB mutation. It must explicitly
name only `dr_support_model_api_test` on127.0.0.1:54805 with existing user/password;
service/options/hostaddr/multi-host and credential fallback are rejected.
The command never starts PostgreSQL/Docker or changes their settings.

## Concrete effects and isolation

1. Verify pinned source bytes before mutations. Generate a fresh random test
   schema `dr_support_test_case16_<32hex>`, workspace `ws_case16_test_<32hex>`
   and a new exclusive `case16-local-<32hex>` evidence directory. No reuse.
2. Connect only to the explicit local test DB and check `current_database()`.
   Execute **CREATE SCHEMA without IF NOT EXISTS**; collision fails. Apply
   existing application migrations only to that NEW schema, then create the
   ordinary PostgreSQL workspace catalog profile there. Original schema,
   acceptance schema, B schema and clinical rows are never selected/migrated.
3. In the dedicated process clear inherited DR/private-root/remote-model/PG
   configuration, set only the selected test schema/workspace and review/remote
   single-worker mode, with no remote endpoint. Restore environment on exit.
   Build the actual app factory with demo/sample fixtures disabled and the
   new workspace's empty input folder. Clear unused providers; no listener.
4. Use the normal `inspect_file` image ingestion path for the approved original,
   PUBLIC provenance, and UWF modality declared by the pinned authorized source
   map. Preserve measured source metadata, source hashes, integrity, quality and
   uncertainty as returned. No hospital-origin privilege is asserted.
   Literal PUBLIC is compatibility provenance, not a claim that the patient
   image is public/deidentified or licensed for redistribution.
5. Require an empty new case store. Initialize the standard `new_case()` shape
   and record its actual ingested source/image hashes. Execute the real normal
   case GET workflow in-process to persist automatic admission/history/resolver
   state; no HTTP socket, inference, manual review or confirmation action.
6. Call the reviewed original-metadata snapshot helper against that app/store
   and expected revision0. Exclusively write `CASE16_INPUT_RECORD.json` and
   `ACQUISITION_RECEIPT.json` in the new evidence directory. Print only receipt
   path/hash. No image copy, original mutation or external transfer.

The output root must be an existing controlled directory under task-3/evidence,
outside source/original-image roots and any Git-controlled ancestor; symlink or
junction redirection fails. Existing local privacy controls must be appropriate;
the command neither changes ACLs nor guarantees deidentification. The snapshot
can include original source references and is private local evidence. Do not
commit, chat or upload it. Share only receipt path/hash and redacted results.

Failure retains any NEW schema and evidence directory, with bounded stage/error
class. No drop/reset/delete, automatic retry or partial-state adoption occurs.
There are no owned servers/ports to stop. If privileges are insufficient, stop
and report; do not grant access. A subsequent attempt would need review and a
fresh scope, not repair of the failed state.

## Admission is not manufactured to satisfy the runner

Normal automatic raster ingestion returns `NOT_EVALUATED` or `NEEDS_REVIEW`
quality; it does not assert `GRADABLE`. This command preserves that state.
It records the existing exact case16 execution guard's result separately as
`execution_eligibility`, without changing any gate. A consistent genuine JSON
can pass the finite driver's byte-digest reader while **still being blocked by
the case16 admission guard**. No clinician ground truth or gold label is added.

Do not replace uncertainty with GRADABLE, simulate a clinician confirmation, or
weaken ordinary/finite-runner rules to force PASS. If fresh normal ingestion is
not execution-eligible, a separate reviewed admission decision/policy is needed;
the two approved inference requests remain unused until all runtime gates pass.
Snapshot acquisition alone does not authorize execution or normal endpoint use.

## Validation and rollback

Synthetic tests run the actual app factory, normal inspector/workflow and
concrete PostgreSQL case-store/helper with injected SQL transport. Generated PNG
bytes and fixture-local pin overrides are used; no live DB/model/GPU, private
configuration or genuine source bytes are accessed. They cover original clinical
defaults staying unconfirmed, provenance/actual metadata, environment isolation,
DSN/manifest/source mismatch, scope freshness, failure retention/redaction,
Git-output rejection and snapshot hashes. Live PostgreSQL migrations/catalog
and genuine source classification remain NOT_RUN.

Rollback source through a reviewed revert of this bounded commit only. Preserve
new QA schema/output if execution later occurs; no automated DB deletion or
original-state rollback is part of this command. Refreeze and review the finite
driver's snapshot digest/manifest/ZIP/argv before any separately approved model
execution. Main merge, push, deployment and persistent endpoint remain separate.
