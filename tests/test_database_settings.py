"""The local test-database route check rejects endpoint redirection before any DB use."""
import pytest

from scripts.demo.database_settings import checked_local_parameters


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
