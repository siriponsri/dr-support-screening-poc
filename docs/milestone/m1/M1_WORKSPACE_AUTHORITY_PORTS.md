# M1 unregistered workspace-authority ports

Frozen bounded core contract, baseline `046abe2`. Read with
`M1_MUTABLE_PRISM_ENTRY_AUTHORITY.md` and the Hospital M1 release candidate spec.
This core is not registered by an API, environment variable, application factory
or inference client. It does not qualify the real app binder, private principal,
PostgreSQL role/fence or authenticated GPU/native-entry protocol.

## Trusted construction and context

`WorkspaceAuthority(directory, *, context_reader, database_fence,
authenticated_status_reader)` creates `.gate` before application construction.
These are internal trusted ports, never request-body fields or permission claims.
The existing source/admission policy remains authoritative. No production mode,
source-origin grant, credential, worker or orchestration is introduced.

The context reader accepts one image ID and returns exactly:

```text
workspace_id: existing exact PostgreSQL workspace identity
image_id: exact case identity
case: complete original JSONB document, without defaults/enrichment
workspace: complete original catalog row JSON, including workspace_id
admission: complete current admission projection
source_sha256: SHA-256 of current immutable original bytes
preparation_context: existing preparation_context(case) value
model_pins: existing reviewed non-secret PRISM pin schema
runtime_context: nonempty non-secret DB/route/runtime configuration identity dict
objects: tuple(store, provider, manager, derivative_service)
```

All values except `objects` are canonical JSON and compared in full, including
same-revision fields. Context is limited to 8 MiB canonical bytes; oversize fails
closed. Object references are retained and compared individually with `is`, never
serialized, hashed by address or compared with `==`. The reader must assemble a
consistent snapshot under the existing app/store/catalog synchronization. Its
existence does not grant source access or establish a qualified production binder.
The provider's existing identity read must be cache-only, with no RPC/model load.
`runtime_context` is a required additive port field approved for in-place config
changes that preserve all four outer objects. The core validates only its nonempty
dict shape/canonical bound and compares it in full. The actual binder owns exact
DB/route/runtime identity/hash values and must include every relevant mutable
configuration while excluding secrets, source bytes and credential material. The
field is not permission or qualification. Arbitrary extra top-level fields remain
rejected; raw case/catalog documents are not modified to carry runtime metadata.

Preparation and plan registration occur without active source writers and require
unchanged gate generation across each context read. Their caller must not wrap
these operations in a `gate.writer()` scope. Every real writer must use the same
gate, including full workspace/scan publication operations, before internal locks.
Direct files and privileged administration remain outside these process controls;
the real binder and database role/fence require independent qualification.

## Compatible lifecycle

`authorize_prepare(wire, recorded_context=None, original_bytes=None)` supports the
existing early runtime call with recorded context/original bytes, followed by the
transport's cache-only `authorize_prepare(wire)` call. The first call stages exact
original/wire hashes and the full context/object tuple. The second call re-reads
and compares that context before any prepare bytes can leave. Original/wire data
must be immutable bounded bytes; no source bytes enter the journal. Existing
source eligibility, integrity, recorded hashes, admission and preparation must
agree; hospital provider authorization must remain explicit.

`register_preview_plan(snapshot, binding, plan_hash)` accepts only the exact
existing frozen snapshot/binding, staged hashes, runtime store/provider objects,
and current full context/generation. All mask/transform/source/wire/model fields
remain covered by the existing freeze contract. Plan IDs are one-use. Registration
requires exactly the frozen fields plus `plan_id`, integer nonnegative
`generation` and a timezone-bearing ISO `expires_at`; PreviewService retains TTL
and acknowledgement ownership. Only the latest staged/registered plan is eligible
in this bounded core. Registration does not grant permission to execute.

`authorize_execute(binding, plan_hash)` is the mandatory predispatch check for
cached plans: exclusive owner identity, unpoisoned authority, exact registered
binding/generation and full current context must still agree. Call it before
accounting or any execute send, outside store locks. It creates no entry permit;
the after-load acquisition below still repeats all checks under the real fence.
Gate OPEN alone is insufficient after a verified-release journal failure.

The private review-runtime hook acquires authority, manager and store locks in
that order for synchronous snapshot/validation. It releases them before remote
execution and never holds a thread lock across an ASGI await. Ordinary factory
and fixed QA construction remain unchanged; this hook does not register M1.

`acquire(binding, status, revalidate)` requires the registered plan/generation and
old-job `WAITING_SOURCE_FENCE` challenge with exact epoch/job/ticket/plan/pins/
challenge fields. It takes `gate.begin_entry(expected_generation=...)` before
reading full context/object identities again and invoking `revalidate`. It repeats
the comparison afterward, then calls the existing database port:

```text
database_fence.read() -> None or exact durable binding
database_fence.acquire(workspace_id=..., image_id=..., case=..., workspace=...,
                       binding=old_status_fields_and_fence_id) -> DB permit
database_fence.recover() -> authenticated release, returning after commit
DB permit.release(proof) -> authenticated release, returning after commit
DB permit.quarantine(reason) -> no release
```

The complete raw case/catalog values are supplied for the database's atomic
comparison; only a committed acquisition may return a lease to the transport.
The local durable journal records consumed binding/plan-ID hashes before this
lease can allow a grant. Any uncertain DB acquisition or pre-grant journal write
quarantines the process gate. A fresh plan, changed epoch, timeout, cancel ACK or
process restart cannot open it.
An abort detected before any DB acquisition attempt/lease may reopen only after
successfully persisting consumed-plan evidence; it never returns a grant lease.
Failure to persist that known abort remains quarantined.

The lease has `fence_id`, `release(proof)` and `quarantine(reason)`. Caller-supplied
proof alone never releases it: the authority re-reads through its injected
authenticated reader, validates every old-job scope field and requires matching
native-entry or terminal proof. The DB permit independently authenticates release.
Only confirmed DB release permits the process gate to open. A local journal I/O
failure after confirmed DB release poisons further inference but does not throw
away the valid model result or block its normal existing writer/save path.

## Durable ownership and recovery

Use one independently approved private absolute directory for the authority.
The existing filesystem privacy check is mandatory; this tool never changes ACLs.
An actual nonblocking OS file lock (`msvcrt`/`fcntl`) is held on a retained owner
file for the complete lifetime. Close/crash releases the OS lock, never removes
the owner file. Replaced/redirected owner files fail closed. The fixed owner ID
binds the hash-checked journal; an existing owner without a journal cannot start
an empty session. No stale-file deletion or reset is implemented.

The bounded 64 KiB journal uses exact fields, SHA-256, atomic replacement and file
fsync (plus directory fsync where supported). Partial pending files are retained
and fail closed; they are not silently selected, truncated or deleted. At most
128 consumed hashes are retained; exhaustion stops new inference rather than
evicting replay evidence. This is a bounded session directory, not a rotation API.
No full case, clinical text, original/wire bytes, secrets, weights or raw errors
are written. Existing private-status IDs and reviewed model pins are metadata.

Constructor inspects both DB fence and local journal before app construction.
An existing/uncertain binding recreates a real local permit using `begin_entry`
then `quarantine`; it never releases a `None` permit. Matching local/DB scopes
must be reconciled, and DB-only consumed hashes retained. The caller must call
`recover()` successfully before building the app. Recovery reauthenticates the
old job; missing/new-epoch/unknown status remains quarantined with no TTL. Corrupt
or interrupted local state is a hard blocker retained for operator inspection.

`close()` releases only OS ownership. It never clears a DB fence or quarantine.

## Acceptance boundary

Synthetic-port tests must cover same-revision full-context drift, object swaps,
writer races, replay, unknown DB/grant/status outcomes, restart and matching old
proof, partial/corrupt journal, retained OS-lock ownership, pre-grant zero grants,
and post-release logging failure preserving the result/save path. Privacy may be
mocked in these tests, never changed. Actual DB/role/native/GPU/app qualification,
source-byte binder coverage and runtime registration remain NOT_RUN.
