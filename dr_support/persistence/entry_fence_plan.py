"""Review-only DDL for a crash-persistent PRISM source fence.

Nothing installs this plan or registers a provider. Existing release migrations
remain unchanged. Applying it and provisioning its distinct principals requires
the separate owner/IT access decision described in the M1 authority contract.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class EntryFencePlan:
    application_schema: str
    guard_schema: str
    owner_role: str
    runtime_role: str
    authority_role: str

    def __post_init__(self):
        values = (self.application_schema, self.guard_schema, self.owner_role,
                  self.runtime_role, self.authority_role)
        if any(not isinstance(value, str) or not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", value)
               for value in values):
            raise ValueError("EXPLICIT_SIMPLE_POSTGRES_IDENTITIES_REQUIRED")
        if self.application_schema == self.guard_schema or len(set(values[2:])) != 3:
            raise ValueError("SEPARATE_GUARD_AND_PRINCIPALS_REQUIRED")
        if (any(value in {"public", "current_user", "current_role", "session_user", "none"}
                or value.startswith("pg_") for value in values[2:])
                or self.guard_schema == "public" or self.guard_schema.startswith("pg_")):
            raise ValueError("NAMED_NON_SYSTEM_AUTHORITY_REQUIRED")

    def render(self) -> str:
        """Return an unapplied, single-transaction operator review plan.

        No IF NOT EXISTS/OR REPLACE: a collision must fail, never absorb a
        previously installed authority. No CREATE ROLE, passwords or login grants.
        Only an already approved owner can execute this DDL. The runtime must not
        inherit that owner or authority, own protected objects, or bypass triggers.
        """
        # Quoting remains mandatory even after validation: SQL role tokens such
        # as PUBLIC/current_user must never acquire pseudo-role semantics.
        app, guard, owner, runtime, authority = (
            '"' + value + '"' for value in (
                self.application_schema, self.guard_schema,
                self.owner_role, self.runtime_role, self.authority_role))
        return f"""-- NOT APPLIED: owner/IT-reviewed installation only.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
CREATE SCHEMA {guard} AUTHORIZATION {owner};
SET LOCAL ROLE {owner};
REVOKE ALL ON SCHEMA {guard} FROM PUBLIC, {runtime}, {authority};
CREATE TABLE {guard}.entry_fence (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    binding JSONB,
    CHECK (binding IS NULL OR jsonb_typeof(binding) = 'object')
);
INSERT INTO {guard}.entry_fence (singleton, binding) VALUES (TRUE, NULL);

CREATE FUNCTION {guard}.check_source_write() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $guard$
DECLARE active JSONB;
BEGIN
    -- SHARE is held to transaction end. Acquisition waits for earlier writers
    -- to commit, and later writers observe the committed fence or are refused.
    SELECT binding INTO STRICT active FROM {guard}.entry_fence
        WHERE singleton FOR SHARE;
    IF active IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = '55000', MESSAGE = 'SOURCE_ENTRY_FENCED';
    END IF;
    RETURN NULL; -- statement trigger
END;
$guard$;

CREATE FUNCTION {guard}.begin_entry(
    workspace TEXT, image TEXT, expected_case JSONB, expected_workspace JSONB,
    requested_binding JSONB
) RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $guard$
DECLARE active JSONB; actual_case JSONB; actual_workspace JSONB;
BEGIN
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE = '25000', MESSAGE = 'READ_COMMITTED_ENTRY_REQUIRED';
    END IF;
    IF requested_binding IS NULL OR jsonb_typeof(requested_binding) <> 'object'
       OR NOT (requested_binding ?& ARRAY['fence_id','epoch','job_id','ticket_id',
                                          'plan_sha256','pins','challenge_id'])
       OR expected_case IS NULL OR expected_workspace IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'ENTRY_BINDING_REQUIRED';
    END IF;
    SELECT binding INTO STRICT active FROM {guard}.entry_fence
        WHERE singleton FOR UPDATE;
    IF active IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = '55000', MESSAGE = 'SOURCE_ENTRY_FENCED';
    END IF;
    -- READ COMMITTED, after obtaining the sentinel, sees all preceding writes.
    -- No writer may commit a protected DML without holding its SHARE lock.
    SELECT c.payload INTO actual_case FROM {app}.review_cases c
        WHERE c.workspace_id = workspace AND c.case_id = image;
    SELECT to_jsonb(w) INTO actual_workspace FROM {app}.workspaces w
        WHERE w.workspace_id = workspace;
    IF actual_case IS DISTINCT FROM expected_case
       OR actual_workspace IS DISTINCT FROM expected_workspace
       OR actual_case->>'image_id' IS DISTINCT FROM image
       OR NOT EXISTS (SELECT 1 FROM {app}.review_cases c
           WHERE c.workspace_id = workspace AND c.case_id = image
             AND to_jsonb(c.revision) = actual_case->'revision') THEN
        RAISE EXCEPTION USING ERRCODE = '40001', MESSAGE = 'SOURCE_CONTEXT_CHANGED';
    END IF;
    UPDATE {guard}.entry_fence SET binding = requested_binding WHERE singleton;
    -- Caller MUST COMMIT before returning permission to send the remote grant.
END;
$guard$;

CREATE FUNCTION {guard}.release_entry(expected_binding JSONB) RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $guard$
DECLARE active JSONB;
BEGIN
    SELECT binding INTO STRICT active FROM {guard}.entry_fence
        WHERE singleton FOR UPDATE;
    IF active IS NULL OR active IS DISTINCT FROM expected_binding THEN
        RAISE EXCEPTION USING ERRCODE = '55000', MESSAGE = 'MATCHING_ENTRY_AUTHORITY_REQUIRED';
    END IF;
    -- EXECUTE belongs only to the trusted authority principal. This function
    -- does not authenticate arbitrary caller JSON as a native-entry proof.
    UPDATE {guard}.entry_fence SET binding = NULL WHERE singleton;
END;
$guard$;

CREATE FUNCTION {guard}.read_entry() RETURNS JSONB
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $guard$
    SELECT binding FROM {guard}.entry_fence WHERE singleton;
$guard$;

REVOKE ALL ON ALL TABLES IN SCHEMA {guard} FROM PUBLIC, {runtime}, {authority};
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA {guard} FROM PUBLIC, {runtime}, {authority};
GRANT USAGE ON SCHEMA {guard} TO {authority};
GRANT EXECUTE ON FUNCTION {guard}.begin_entry(TEXT,TEXT,JSONB,JSONB,JSONB)
    TO {authority};
GRANT EXECUTE ON FUNCTION {guard}.release_entry(JSONB) TO {authority};
GRANT EXECUTE ON FUNCTION {guard}.read_entry() TO {authority};
RESET ROLE;
CREATE TRIGGER m1_entry_fence BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE
    ON {app}.workspaces FOR EACH STATEMENT
    EXECUTE FUNCTION {guard}.check_source_write();
CREATE TRIGGER m1_entry_fence BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE
    ON {app}.review_cases FOR EACH STATEMENT
    EXECUTE FUNCTION {guard}.check_source_write();
CREATE TRIGGER m1_entry_fence BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE
    ON {app}.legacy_migration_receipts FOR EACH STATEMENT
    EXECUTE FUNCTION {guard}.check_source_write();
COMMIT;
"""
