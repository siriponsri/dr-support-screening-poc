# Isolated M1 credential provisioning

Scope: only `dr_support_m1_interactive_test_20261023` and its newly approved
`dr_support_m1_runtime_test` and `dr_support_m1_authority_test` LOGIN roles.
The separate `dr_support_m1_owner_test` remains NOLOGIN. This procedure cannot
create a role/database, modify ACLs, replace existing credentials or resume an
interrupted provision. Hospital production identities are outside this scope.

The owner separately approved the new Windows directory
`C:\Users\User\AppData\Local\DRScreening\M1PrivateConfig`. Its protected DACL
contains only the actual User SID, SYSTEM and Administrators, with FullControl
inherited by new files. Existing workspace/release/profile ACLs were not changed.
The unchanged privacy checker passed before and after credential creation.

The bounded helper defaults to a secret-free plan:

```powershell
.\.venv\Scripts\python.exe -m scripts.qa.configure_m1_test_credentials `
  --administrator-config .\local-state\release\postgres.env
```

On an explicitly approved, still-empty configuration target only, adding
`--apply-test-credentials` generates the two new passwords. The helper checks the
exact existing test owner, names, unelevated role attributes, no memberships,
PASSWORD NULL and idle entry fence first. It fsyncs each exclusive new private
configuration before its corresponding transactional password change; only a
SCRAM verifier reaches ALTER ROLE. Administrator credentials are read in memory,
never copied into the new files or printed.

The generated files use `DR_SUPPORT_DATABASE_MIGRATION_MODE=verify`; application
startup must not attempt migration under the runtime principal. The authority
DSN uses the separate `DR_SUPPORT_AUTHORITY_DATABASE_URL` setting. No automatic
environment loader or app/provider registration is added by this helper.

Actual scoped execution at 2026-10-23 09:08 UTC passed both independent password
logins. Driver-authenticated user, SQL current/session user and database matched;
libpq confirmed password use; neither role had superuser, CREATEDB, CREATEROLE,
replication or BYPASSRLS attributes. This is credential/role evidence, not
workspace authority, model load, inference, browser or clinical qualification.
No inference request was sent.

Private, secret-free receipt names are `credentials-staged.json` and
`credentials-login-proof.json` in the approved directory. The `.env` files there
contain secrets and must never be printed, committed or included in packages.
The staging receipt deliberately records the pre-commit boundary; the separate
login proof records successful post-commit connections. Existing files now make
another provisioning invocation refuse; do not delete/reset them to rerun.

Interrupted writes, uncertain commit and failed login retain all partial state
for owner inspection. They do not authorize password reset or overwrite. A
post-login receipt I/O failure reports logging separately from actual successful
authentication and blocks further admissions. Existing developer startup and
credentials remain available for rollback; stopping M1 and selecting the previous
release does not delete these new credentials, roles, databases or labels.
