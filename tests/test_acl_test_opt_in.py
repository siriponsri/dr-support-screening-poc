"""Ordinary validation must not silently run native permission mutations."""
from importlib import import_module

import pytest


def test_permission_setup_and_reader_grants_skip_before_any_mutation(tmp_path, monkeypatch):
    helper = import_module("test_authorized_hospital")
    monkeypatch.delenv("DR_SUPPORT_TEST_ALLOW_PERMISSION_MUTATIONS", raising=False)
    monkeypatch.setattr(helper.subprocess, "run", lambda *a, **k: pytest.fail("Unapproved native command"))
    root = tmp_path / "not_created"
    for operation in (lambda: helper._private_test_root(root),
                      lambda: helper._grant_synthetic_reader(root, "unresolved-fixture-sid")):
        with pytest.raises(pytest.skip.Exception, match="explicit owner-approved opt-in"):
            operation()
    assert not root.exists()


@pytest.mark.parametrize("value", ["", "0", "true", "yes"])
def test_only_explicit_permission_mutation_opt_in_is_accepted(monkeypatch, value):
    helper = import_module("test_authorized_hospital")
    monkeypatch.setenv("DR_SUPPORT_TEST_ALLOW_PERMISSION_MUTATIONS", value)
    with pytest.raises(pytest.skip.Exception):
        helper._require_permission_test_opt_in()


def test_opt_in_check_itself_performs_no_permission_change(monkeypatch):
    helper = import_module("test_authorized_hospital")
    monkeypatch.setenv("DR_SUPPORT_TEST_ALLOW_PERMISSION_MUTATIONS", "1")
    monkeypatch.setattr(helper.subprocess, "run", lambda *a, **k: pytest.fail("Check must be inert"))
    helper._require_permission_test_opt_in()
