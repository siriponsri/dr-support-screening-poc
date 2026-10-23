"""Review plan controls; these are not effective PostgreSQL-role qualification."""
import pytest

from dr_support.persistence.entry_fence_plan import EntryFencePlan


def plan(**overrides):
    values = dict(application_schema="m1_application", guard_schema="m1_entry_authority",
                  owner_role="m1_release_owner", runtime_role="m1_runtime",
                  authority_role="m1_entry_authority")
    return EntryFencePlan(**(values | overrides))


@pytest.mark.parametrize("field", ["application_schema", "guard_schema", "owner_role",
                                  "runtime_role", "authority_role"])
@pytest.mark.parametrize("value", ["public; DROP DATABASE original", "UPPER", "", None])
def test_operator_plan_cannot_interpolate_arbitrary_sql_or_missing_identity(field, value):
    values = dict(application_schema="m1_application", guard_schema="m1_guard",
                  owner_role="m1_owner", runtime_role="m1_runtime", authority_role="m1_authority")
    values[field] = value
    with pytest.raises(ValueError, match="IDENTITIES_REQUIRED"):
        EntryFencePlan(**values)


def test_operator_plan_refuses_collapsed_privilege_boundary():
    with pytest.raises(ValueError, match="SEPARATE"):
        EntryFencePlan("app", "guard", "owner", "runtime", "runtime")
    with pytest.raises(ValueError, match="SEPARATE"):
        EntryFencePlan("app", "app", "owner", "runtime", "authority")


@pytest.mark.parametrize("field", ["owner_role", "runtime_role", "authority_role"])
@pytest.mark.parametrize("value", ["public", "current_user", "current_role", "session_user",
                                  "none", "pg_read_all_data"])
def test_role_tokens_cannot_expand_to_everyone_current_or_system_role(field, value):
    with pytest.raises(ValueError, match="NON_SYSTEM"):
        plan(**{field: value})


def test_all_operator_schema_and_role_identifiers_remain_quoted():
    rendered = plan().render()
    assert 'CREATE SCHEMA "m1_entry_authority" AUTHORIZATION "m1_release_owner";' in rendered
    assert 'ON "m1_application".review_cases' in rendered
    assert 'TO "m1_entry_authority";' in rendered


def test_plan_has_no_credentials_role_provisioning_or_automatic_application():
    rendered = plan().render()
    assert "CREATE ROLE" not in rendered and "PASSWORD" not in rendered
    assert "OR REPLACE" not in rendered and "IF NOT EXISTS" not in rendered
    assert rendered.startswith("-- NOT APPLIED")
    assert not hasattr(plan(), "apply")
