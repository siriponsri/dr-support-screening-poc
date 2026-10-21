"""Linux poll constants for Windows fake handles; never a real poll or signal."""

import pytest
from scripts.qa import linux_owned_child as module


@pytest.fixture(autouse=True)
def fake_linux_poll_constants(monkeypatch):
    for name, value in {
        "POLLIN": 1,
        "POLLERR": 8,
        "POLLHUP": 16,
        "POLLNVAL": 32,
    }.items():
        monkeypatch.setattr(module.select, name, value, raising=False)
