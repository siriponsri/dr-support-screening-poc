# M1 PostgreSQL workspace context reader

Status: unregistered internal port. Synthetic controls only; actual authenticated
runtime-role PostgreSQL qualification is NOT_RUN. Read with
`M1_MUTABLE_PRISM_ENTRY_AUTHORITY.md` and the shared
`M1_WORKSPACE_AUTHORITY_PORTS.md` contract. No environment selector, API route,
factory registration, provider promotion, credential, access grant or model call
is introduced here.

## Construction and ordering

```python
reader = WorkspaceContextReader(
    role_config=EntryFencePlan(
        "dr_support", "dr_support_entry_guard",
        "dr_support_m1_owner_test", "dr_support_m1_runtime_test",
        "dr_support_m1_authority_test",
    ),
    database_name="dr_support_m1_interactive_test_20261023",
    max_source_bytes=32 * 1024 * 1024,
)
reader.preflight_runtime_database(runtime_database)
# Only after successful preflight may a separately approved factory construct or
# write the runtime stores. The reader itself never constructs the application.
reader.bind(app, authority.gate)
context = reader(image_id)
```

These exact existing test names are the only approved construction scope. An
arbitrary hospital database/principal is refused. The optional source limit must
be a positive integer no larger than the existing PRISM preview byte limit.

`preflight_runtime_database(database) -> None` accepts an actual
`PostgresDatabase` and uses its explicit connection. It starts a read-only
transaction with a five-second statement timeout, checks the principal, and closes
the connection. It neither obtains nor changes credentials, grants, ACLs, roles,
schema or data. Success is not cached as authorization for another connection.

The SQL current user and session user and the driver's authenticated startup
`connection.info.user` must all equal the configured runtime role. Both actual SQL
database and driver database must match the approved test database. Administrative
`SET SESSION AUTHORIZATION` is not genuine runtime authentication and is rejected
when the driver still identifies the administrative connection.

The catalog check rejects missing roles/tables, non-login runtime identities,
superuser/CREATEDB/CREATEROLE/BYPASSRLS/replication privileges including privileged
role memberships, owner/authority membership, effective ownership of protected
tables, guard-schema/table write capability, direct execution of guard-authority
functions and a non-origin replication mode. The complete fence installation and
effective role boundary still need their separate SQL qualification.

Unprovisioned PASSWORD NULL roles or missing private runtime configuration block
actual authenticated login. Mock results do not remove that boundary; any
separately authorized credential provisioning is outside this reader.

`bind(app, gate) -> None` is a one-use internal binding after app/store/provider
assembly. It requires the exact `SourceMutationGate` already on `app.state`.
It performs no registration, SQL, source authorization or app-state write.

## Consistent read contract

Before preparing a plan, the caller must have loaded the case through the existing
PostgreSQL store. `__call__(image_id)` requires its existing `_observed` raw payload
and `_observed_revision` caches; a missing/stale baseline fails closed. It never
calls `store.get`, applies defaults, repairs a projection or updates a cache.

The reader accepts an actual `PostgresCaseStore`, `WorkspaceManager`,
`DerivativeService` and `RemoteBoundTransportCandidate`. Their app/store/manager
must share the exact injected gate and PostgreSQL database/workspace identity.
Unknown or duck-typed stores/providers are refused. The remote candidate's
descriptor/protocol remains unqualified and unregistered; reading its cached
identity does not promote it. A future qualified provider implementation requires
a separately reviewed extension.

The reader captures the gate, then takes the existing manager and store locks in
that order. One joined SQL SELECT reads row revision, complete original JSONB case,
complete `to_jsonb(workspaces)` catalog row and principal metadata from one
statement snapshot in a read-only transaction. Identity/revision, loaded raw case,
current admission and active workspace profile must agree. Raw catalog fields
outside the profile projection remain in the returned context.

The admitted source must be an exact `BridgeImage` with bounded immutable `bytes`.
Its SHA-256 must agree with current admission and recorded case/source metadata.
No file is reopened, decoded, modified or recompressed. Disk replacement and
out-of-process filesystem changes are outside this process ownership; this reader
does not invent protection against them or grant source-origin permission.

Only the existing reviewed five-field non-secret PRISM pin schema is returned:
`model_id`, `source_revision`, `preprocessing`, `config_sha256`,
`checkpoint_sha256`. The known cache-only remote implementation is called
directly, so an instance override cannot introduce an identity RPC. No negotiation,
weight read, model load, inference or enrichment occurs.

The returned mapping has exactly:

```text
workspace_id, image_id, case, workspace, admission, source_sha256,
preparation_context, model_pins, objects
```

`preparation_context` is the existing helper's value. `objects` is
`(store, provider, manager, derivative_service)`, retaining references for the
authority's individual `is` comparisons. All other values together must fit the
shared eight-MiB canonical-JSON bound. Originals are not included in this mapping.

The reader requires zero active writers and unchanged gate generation/state,
objects, image identity, admission and cached pins through the read. OPEN, FENCED
and QUARANTINED inspection are supported: final authority acquisition reads while
already fenced, and inspection never releases that fence. An idle legitimate
provider/workspace replacement appears as new object identities for the authority
to compare with its prepared plan.

## Evidence boundary

Tests use actual model-independent classes with synthetic raw documents and mock
driver/connection results. They verify refusal, binding, immutable source limits,
same-revision drift, complete payload/catalog preservation, object/pin/gate races
and read-only query construction. They are not PostgreSQL SQL execution, genuine
runtime authentication, database-fence qualification, app registration, native
entry, GPU inference or clinical validation evidence.
