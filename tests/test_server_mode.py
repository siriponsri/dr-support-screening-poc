"""Admin server mode: only the administrator changes it; the team server needs a workspace marked consented."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dr_support.services import server_mode
from dr_support.services.pilot_auth import UserStore, install_pilot_auth

PASSWORD = "synthetic-test-pass-7"


def app_for(tmp_path):
    users = tmp_path / "users.json"
    store = UserStore(users)
    store.set_user("admin1", PASSWORD, role="admin", must_change=False, enforce_policy=False)
    store.set_user("doc1", PASSWORD, role="physician", must_change=False, enforce_policy=False)
    app = FastAPI()
    app.state.workspace_id = "ws_demo_consented"
    install_pilot_auth(app, users)
    return app


def signed_in(app, name):
    client = TestClient(app)
    assert client.post("/v1/auth/login", json={"username": name, "password": PASSWORD}).status_code == 200
    return client


def test_default_is_the_hospital_server_and_only_the_admin_changes_it(tmp_path):
    app = app_for(tmp_path)
    admin = signed_in(app, "admin1")
    assert admin.get("/v1/admin/server-mode").json()["mode"] == "hospital_local"
    assert signed_in(app, "doc1").put("/v1/admin/server-mode", json={"mode": "team_server"}).status_code == 403
    reply = admin.put("/v1/admin/server-mode", json={"mode": "team_server", "consented_workspaces": ["ws_demo_consented"]})
    assert reply.status_code == 200 and reply.json()["mode"] == "team_server"
    assert reply.json()["applies"] == "at the next start"
    assert admin.put("/v1/admin/server-mode", json={"mode": "cloud"}).status_code == 422
    assert admin.put("/v1/admin/server-mode", json={"mode": "team_server", "consented_workspaces": ["../etc"]}).status_code == 422


def test_the_launcher_check_refuses_unmarked_workspaces(tmp_path, capsys):
    assert server_mode.main(["check", "--config-dir", str(tmp_path), "--workspace", "ws_x"]) == 3
    app = app_for(tmp_path)
    signed_in(app, "admin1").put("/v1/admin/server-mode", json={"mode": "team_server", "consented_workspaces": ["ws_ok"]})
    assert server_mode.main(["check", "--config-dir", str(tmp_path), "--workspace", "ws_ok"]) == 0
    assert server_mode.main(["check", "--config-dir", str(tmp_path), "--workspace", "ws_hospital"]) == 3
    assert "not marked as public or consented" in capsys.readouterr().err



def test_connection_check_reports_only_the_outcome_and_needs_the_admin(tmp_path, monkeypatch):
    app = app_for(tmp_path)
    monkeypatch.delenv("REMOTE_MODEL_URL", raising=False)
    assert signed_in(app, "doc1").get("/v1/admin/server-mode/test").status_code == 403
    reply = signed_in(app, "admin1").get("/v1/admin/server-mode/test").json()
    assert reply == {"reachable": False, "message": "No AI server is configured for this app."}
    import httpx

    def down_server(*args, **kwargs):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", down_server)
    monkeypatch.setenv("REMOTE_MODEL_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("REMOTE_MODEL_TOKEN", "secret-token-value-123456789012345")
    down = signed_in(app, "admin1").get("/v1/admin/server-mode/test").json()
    assert down["reachable"] is False and "secret-token" not in str(down)
