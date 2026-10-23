# PostgreSQL release and runtime roles

Hospital M1 candidate controls are implemented; effective hospital grants and
live role-qualified application startup remain NOT_RUN. No launcher provisions
roles, changes credentials, or silently grants privileges.

The existing developer default, `DR_SUPPORT_DATABASE_MIGRATION_MODE=apply`, keeps
the established startup migration behavior. A hospital operator can instead
set `DR_SUPPORT_DATABASE_MIGRATION_MODE=verify` in private review configuration.
The latter reads the complete migration sequence and checks names/checksums in
a read-only transaction before opening the case store. Missing, old, unknown,
gapped or changed history fails startup; there is no automatic DDL fallback.

Use a separately approved release/migration principal to apply the reviewed
`SchemaMigrator.migrate()` before switching a runtime principal to `verify`.
Do this in an operator process using the approved private connection environment,
not by placing the migration credential in the UI or normal runtime settings.
The migration sequence and checksums remain unchanged.

The runtime principal needs CONNECT to the selected database, USAGE on its
dedicated application schema, SELECT on `schema_migrations`, and the existing
application DML on `workspaces`, `review_cases` and `legacy_migration_receipts`.
Grant only the operations the enabled workflows actually need after review;
do not give runtime schema ownership, CREATE, superuser, CREATEDB or CREATEROLE
merely to get through startup. The legacy migration workflow may need a
separately scoped operator process. There is no multi-user authentication/RLS
claim from database role separation: the current UI is single-user localhost.

Backup needs a read-only snapshot and schema dump under the approved backup
principal. Restore needs an independently provisioned, empty test database and
a separately approved restoration principal. Runtime verification is neither a
backup nor a restore test. Qualify actual denied-DDL, permitted case edits,
revision history, restart and readback against the target roles before hospital
acceptance. Keep all existing volumes/databases and role credentials intact.
