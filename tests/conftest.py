import socket
import pytest


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.setenv("DR_SUPPORT_STATE", str(tmp_path / "reviews.sqlite"))
    # Keep ignored local workspace catalogs from restoring a real demo database into tests.
    monkeypatch.setenv("DR_SUPPORT_WORKSPACE_CATALOG", str(tmp_path / "workspaces.sqlite"))

    def blocked(*args, **kwargs):
        raise RuntimeError('Network forbidden in offline tests')

    original_connect = socket.socket.connect

    def allow_localhost_connect(self, address, *args, **kwargs):
        # Permit asyncio socketpair/internal localhost plumbing used by TestClient on Windows.
        if isinstance(address, tuple) and str(address[0]) in ('127.0.0.1', 'localhost', '::1'):
            return original_connect(self, address, *args, **kwargs)
        raise RuntimeError('Network forbidden in offline tests')

    monkeypatch.setattr(socket.socket, 'connect', allow_localhost_connect)
    monkeypatch.setattr(socket, 'create_connection', blocked)
