"""Qualification scope rejects endpoint redirection before any DB mutation."""
import pytest
from types import SimpleNamespace

from scripts.qa.qualify_m1_entry_fence import checked_local_parameters, executed_sql_controls


BASE = "host=127.0.0.1 port=54805 dbname=source user=operator password=not-a-real-secret"


@pytest.mark.parametrize("extra", ["hostaddr=198.51.100.4", "service=elsewhere", "options='-c search_path=other'",
                                   "host=localhost", "port=54805,5432", "port=70000", "host=127.0.0.1,198.51.100.4"])
def test_existing_configuration_cannot_redirect_test_provisioning(extra):
    with pytest.raises(RuntimeError, match="WITHOUT_LIBPQ_OVERRIDES"):
        checked_local_parameters(BASE + " " + extra, environ={})


@pytest.mark.parametrize("name", ["PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS", "PGHOST", "PGUSER", "PGDATABASE"])
def test_ambient_libpq_configuration_blocks_before_connect(name):
    with pytest.raises(RuntimeError, match="WITHOUT_LIBPQ_OVERRIDES"):
        checked_local_parameters(BASE, environ={name: "unexpected"})


def test_complete_explicit_loopback_configuration_has_no_ambient_dependency():
    assert checked_local_parameters(BASE, environ={})["host"] == "127.0.0.1"
    assert checked_local_parameters(BASE + " hostaddr=127.0.0.1", environ={})["hostaddr"] == "127.0.0.1"


@pytest.mark.parametrize("output", ["12 tests collected in 0.1s", "12 skipped in 0.1s",
                                    "1 passed, 11 skipped in 0.1s", "SECRETLIKE_RAW_STDOUT",
                                    "12 failed in 0.1s", "11 passed in 0.1s"])
def test_exit_zero_does_not_qualify_collection_skip_or_arbitrary_output(output):
    assert not executed_sql_controls(SimpleNamespace(returncode=0, stdout=output))


def test_owned_executed_count_qualifies_only_success():
    assert executed_sql_controls(SimpleNamespace(returncode=0, stdout="............ [100%]\n12 passed in 0.23s\n"))
    assert not executed_sql_controls(SimpleNamespace(returncode=1, stdout="12 passed in 0.23s\n"))
