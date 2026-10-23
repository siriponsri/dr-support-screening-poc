# M1 PRISM database-fence access proposal

Status: isolated test scope OWNER APPROVED; SQL controls PASS (12 tests).
No provider registration or inference allowance is created by this proposal.
Hospital deployment and password-authenticated app startup remain NOT_RUN.
Read `docs/milestone/m1/M1_MUTABLE_PRISM_ENTRY_AUTHORITY.md` first.

Read-only inspection of the current private DB configuration on 23 October found
superuser/CREATEDB/CREATEROLE/BYPASSRLS enabled. That identity cannot establish
the required runtime privilege boundary: a superuser can disable a trigger.
The proposed guard is additive in a separate schema; the four existing migration
records/checksums are unchanged. Its installation needs an explicit operator gate.

The reviewable generator is `dr_support/persistence/entry_fence_plan.py`.
For example, `EntryFencePlan('dr_support', 'dr_support_entry_guard',
'dr_support_release_owner', 'dr_support_runtime',
'dr_support_entry_authority').render()` produces the exact transaction for review.
It creates only the guard schema, one sentinel row, four functions and three
statement triggers; grants only function execution to the existing trusted
authority role. It never creates a role, password or application DML grant.
There is deliberately no automatic apply method or startup migration hook.

The runtime and authority identities must be independently approved, different
from the migration/object owner, non-superuser, without CREATEDB/CREATEROLE,
schema ownership/CREATE, trigger-bypass settings, or membership permitting a
switch to owner/authority. Runtime retains only the existing required SELECT,
INSERT and UPDATE permissions. It cannot write the guard, call its entry/release
functions, alter triggers or grant itself access. The dedicated trusted authority
can call entry/release but cannot directly edit the guard or application data.
Its credential must not become the ordinary case-store connection credential.
Credentials stay outside Git and never appear in the rendered plan or UI.

Every protected DML transaction takes a SHARE lock on the sentinel. Entry takes
its exclusive lock, compares the complete case payload/revision and catalog row,
sets the binding, then commits **before** any remote grant. An uncommitted guard
is never sufficient. Once committed, writers fail even after the Windows/backend
connection dies. The release function is only a permission boundary; it does not
turn supplied JSON into proof. The authority must authenticate the matching old
epoch/job/ticket/plan/pins/challenge through the existing trusted protocol before
release. Timeout, cancel acknowledgement, a new worker or an empty local journal
does not permit release.

Before applying this on any application database, the operator must approve:

1. Exact database/schema/object owners and existing/new role identities; how the
   two private connection configurations are provisioned without exposing secrets.
2. The rendered DDL hash and separate least-privilege grants, including inherited
   privileges and any parameter-level trigger-bypass permission.
3. A new isolated test database for the first role-qualified rehearsal; no changes
   to the main/recovery databases, existing roles, credentials or volumes.
4. Two-connection races, committed-fence/backend-loss persistence, denied runtime
   release/DDL/TRUNCATE, permitted idle edits, restart and authenticated old-job
   recovery. The actual app writer map and source-byte check remain required.

The role-qualified isolated SQL control rehearsal is described below. Runtime
credential login, composed application writer coverage and actual native entry
remain NOT_RUN; the mutable-workspace provider stays unregistered.

## Proposed first isolated Windows qualification scope

The requested access decision is limited to a new database
`dr_support_m1_interactive_test_20261023`; if it or any proposed role already
exists, stop rather than absorb/alter it. Preserve all original and recovery
databases, users/passwords, volumes and current `.env` byte for byte.

- New owner `dr_support_m1_owner_test`: NOLOGIN, owner of this test database's
  `dr_support` and `dr_support_entry_guard` objects.
- New runtime `dr_support_m1_runtime_test`: LOGIN, no elevated attributes or
  owner/authority membership, only this application's required SELECT/INSERT/
  UPDATE and read-only migration-history permission.
- New trusted authority `dr_support_m1_authority_test`: LOGIN, no elevated
  attributes/membership, only CONNECT/guard-USAGE and entry/release EXECUTE.
- Existing approved administrator applies the unchanged four app migrations,
  transfers the new test objects to its new NOLOGIN owner and installs the exact
  reviewed guard plan. No change to existing objects or default/public grants in
  other databases. Existing PUBLIC connection rights elsewhere are not claimed
  to be revoked by this scope.
- Generate two new private passwords only after approval, store them only in an
  already private, permission-checked test configuration directory, and never
  print/commit them. If existing directory permissions are insufficient, stop for
  IT preparation; do not change ACL. Normal app startup uses the new runtime
  connection with migration mode `verify`; only the trusted authority receives
  its separate connection. No automatic fallback to the old administrator.
- Qualify this isolated scope first, including real denied DDL/guard release,
  concurrent-writer/crash behavior and old-job recovery. This does not provision
  hospital production roles or qualify the hospital's network/hardware.

The owner approved this exact isolated test scope on 23 October. The existing
Windows release config directory failed its conservative privacy check. No
password was therefore generated/stored: the two LOGIN roles were provisioned
with PASSWORD NULL. No ACL or original credential was changed. Private credential
storage/startup remains a separate unresolved gate, as detailed in the requested
private permissions report outside Git.

## Executed isolated control rehearsal

The approved new database/three roles above were created once after independent
source review. No existing DB/role was absorbed or altered. The test scope is
retained, and rerunning the provisioning command refuses those existing names.

- Rendered guard SQL SHA-256:
  `6d300927351fe9987f4de50b1782408f8d62c471bcfd3d2b2f6b63545b3e14e0`.
- Exact role SQL SHA-256:
  `da6747ab75354f3ac6e1798d26f1c60facb89dbaa93c71d4dbd34cc55e8d6086`.
- `tests/test_postgres_entry_fence.py`: **12 executed PASS**. Raw pytest output
  SHA-256 `40b77d63511837a494b2a6f1dba3c3773e596aa137c75207903b7dcbcd6acb44`.
- Actual PostgreSQL rejected runtime DDL, trigger disable, guard update/release,
  TRUNCATE, authority-role switch and replication-trigger bypass. Idle case DML
  succeeded. A committed fence persisted after connection close. Two connections
  raced writers/entry; the observer verified the owned PID was actually blocked
  by its counterpart before commit. Same-revision payload changes invalidated
  the final source comparison; a mismatched release could not unlock it.
- Connections used trusted-admin-established `SET SESSION AUTHORIZATION` to test
  effective SQL permissions. That is **not password-authenticated login**, a
  qualified app principal map, Windows-main inference, or hospital acceptance.
- Zero model/GPU requests, no clinical labels and no original database/image
  changes. The new test cases are engineering controls only.

`PostgresEntryFence` sets read-committed isolation and bounded 1s lock/3s statement
timeouts on every authority transaction. It returns an entry permit only after
commit and re-reads matching old-job status through the injected trusted reader
before release. Its composed auth/writer/source implementation is not registered.
The sidecar guard is not yet supported by the existing app-schema-only recovery
bundle; guarded-database backup/restore remains unqualified and must fail closed.
