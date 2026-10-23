# M1 app and PostgreSQL context qualification

Status: bounded test-workspace procedure, 23 October 2026. Default PLAN_ONLY;
actual execution requires `--apply-test-workspace`. This proves only actual app
construction and the joined context-reader path, never inference or clinical
validation. Existing source, export, role and privacy gates stay unchanged.

## Fixed scope and ordering

The only credential input is the existing approved
`C:/Users/User/AppData/Local/DRScreening/M1PrivateConfig/m1_runtime.env`.
The existing filesystem privacy/reparse checks must pass before an in-memory,
bounded read. Only the three provisioned variables are accepted: database URL,
schema `dr_support`, and migration mode `verify`. The DSN must explicitly name
`127.0.0.1:54805`, database `dr_support_m1_interactive_test_20261023`, runtime role
`dr_support_m1_runtime_test`, and a password, without other libpq options.
No administrator/authority credential is read or copied. Credentials never
enter argv, receipts, error text or source control.

The process scopes/restores its environment, removing inherited model,
hospital, CVAT, external/test database and libpq selectors; `CODEX_HOME` remains
unchanged. It selects PostgreSQL, migration verify, review/remote and no model
URL. The actual runtime-principal/password preflight and complete migration
checksum verification run before any catalog or factory write.

Every apply creates a new `m1_context_<uuid>` workspace named
`TEST_ONLY m1_context_<uuid>` and a new direct artifact child named
`m1-context-qualification-*`. Existing destinations/workspace IDs are refused.
New input/output directories remain empty. The actual PostgreSQL catalog,
WorkspaceManager and review factory receive the explicit workspace ID and the
same new `SourceMutationGate`; samples/demo fixtures are disabled. All writes
are scoped to that new test workspace. No source files, old case/workspace rows,
roles, passwords, grants, ACLs, schemas, services or volumes are changed.

The single synthetic image exists only in memory. The actual store's `get/put`
seeds its unchanged `legacy_admission`, recorded hashes and default case state
under the gate. No physician review, human annotation or gold label is created.
The exact remote candidate/channel classes use a synthetic cached
`CONTROL_ONLY_NO_MODEL` identity and an HTTPx MockTransport which rejects every
RPC. No negotiation, model preparation, source authority, model load or inference
is attempted; fabricated model pins are explicitly control fixtures only.

After actual store readback, the actual context reader binds and reads twice.
The qualification compares complete raw case and catalog JSON against separate
read-only SQL/readback, all four actual object identities, admission/source hash,
cached pins/runtime identity, unchanged observed caches and gate generation.
The receipt contains checks and canonical hashes, never source bytes, raw case
documents, secrets or DSNs. Timestamp-normalization repair of the reader is a
required dependency before actual apply.

## Interfaces and execution

`qualify(output, *, apply=False)` returns a secret-free result. Default planning
does not open credentials, connect to PostgreSQL, construct the app or create
files. Apply must receive a fresh direct child of the approved artifact base
`C:/Users/User/Documents/Codex/2026-10-21/task`. It preserves all partial state on
failure and never resumes automatically or retries a write.

```powershell
python -m scripts.qa.qualify_m1_workspace_context --output "<new-approved-artifact-child>"
python -m scripts.qa.qualify_m1_workspace_context --output "<same-still-new-child>" --apply-test-workspace
```

`CONTEXT_QUALIFICATION.json` is written exclusively at that new output. Logging
success/failure is reported separately from the context result. A receipt failure
does not become an inference failure; inference remains NOT_RUN with zero actual
requests. Controlled error codes and safe error classes are printed, without
database exceptions, SQL, password material or source data. No test rows or
partial files are deleted, reset, overwritten or archived by this procedure.

## Acceptance boundary

Unit/control tests verify dry-run isolation, privacy-before-read, exact input
scope, preflight-before-write ordering, no-overwrite/partial retention, refusal
before app assembly, synthetic-only fixture provenance, no RPC, raw context and
cache comparisons, environment restoration and independent logging status.
Actual authentication/SQL, app assembly and context read require an explicitly
recorded live apply; mocks cannot satisfy that evidence. Native PRISM, genuine
model identity, inference, entry authority, SSH/GPU, save-export clinical workflow
and hospital deployment remain NOT_RUN in this procedure.
