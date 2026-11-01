"""Names of the isolated test PostgreSQL database and roles the demo review app uses.

These are the identities the owner provisioned once (the old one-off `qualify_m1_entry_fence.py`
rehearsal, now in the archive tag). The demo launcher (`scripts/demo/server_app.py`) and the credential
tool (`scripts/qa/configure_m1_test_credentials.py`) read them from here. Values are unchanged.
"""
from psycopg.conninfo import conninfo_to_dict

from dr_support.persistence.entry_fence_plan import EntryFencePlan

DATABASE = "dr_support_m1_interactive_test_20261023"
OWNER = "dr_support_m1_owner_test"
RUNTIME = "dr_support_m1_runtime_test"
AUTHORITY = "dr_support_m1_authority_test"
PLAN = EntryFencePlan("dr_support", "dr_support_entry_guard", OWNER, RUNTIME, AUTHORITY)


def checked_local_parameters(dsn, *, environ):
    parameters = conninfo_to_dict(dsn)
    if (any(key.startswith("PG") and value for key, value in environ.items())
            or parameters.get("service") or parameters.get("options")
            or parameters.get("host") not in {"127.0.0.1", "::1"}
            or (parameters.get("hostaddr") and parameters["hostaddr"] != parameters["host"])
            or not all(parameters.get(key) for key in ("port", "dbname", "user", "password"))
            or not parameters["port"].isascii() or not parameters["port"].isdigit()
            or not 1 <= int(parameters["port"]) <= 65535):
        raise RuntimeError("EXPLICIT_LOCAL_DB_ROUTE_WITHOUT_LIBPQ_OVERRIDES_REQUIRED")
    return parameters
