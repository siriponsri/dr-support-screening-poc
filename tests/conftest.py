import socket
import pytest


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.setenv("DR_SUPPORT_STATE", str(tmp_path / "reviews.sqlite"))
    def blocked(*args, **kwargs):
        raise RuntimeError('Network forbidden in offline tests')
    monkeypatch.setattr(socket.socket, 'connect', blocked)
    monkeypatch.setattr(socket, 'create_connection', blocked)
