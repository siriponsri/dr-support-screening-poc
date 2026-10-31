"""Pilot sign-in: hashed users file, session cookie, lockout, admin user management. Offline only."""

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from dr_support.services import pilot_auth
from dr_support.services.pilot_auth import AuthError, Authenticator, UserStore, install_pilot_auth

TEST_PASSWORD = "synthetic-test-pass"


def app_with(tmp_path, *users):
    store_file = tmp_path / "users.json"
    store = UserStore(store_file)
    for username, password, role, must_change in users:
        store.set_user(username, password, role=role, must_change=must_change)
    app = FastAPI()
    install_pilot_auth(app, store_file)

    @app.get("/v1/cases")
    def cases():
        return []
    return app, store_file


def test_the_users_file_holds_salted_hashes_only(tmp_path):
    store = UserStore(tmp_path / "users.json")
    store.set_user("admin", TEST_PASSWORD, role="admin", must_change=False)
    store.set_user("doctor1", TEST_PASSWORD, role="user", must_change=True)
    raw = (tmp_path / "users.json").read_text(encoding="utf-8")
    assert TEST_PASSWORD not in raw
    data = json.loads(raw)["users"]
    assert data["admin"]["hash"] != data["doctor1"]["hash"]  # Different salts.
    assert store.verify("admin", TEST_PASSWORD) and store.verify("admin", "wrong") is None
    assert store.verify("nobody", TEST_PASSWORD) is None


def test_every_api_route_needs_a_session_but_sign_in_and_health_do_not(tmp_path):
    app, _ = app_with(tmp_path, ("admin", TEST_PASSWORD, "admin", False))
    client = TestClient(app)
    assert client.get("/v1/cases").status_code == 401
    assert client.get("/v1/auth/me").status_code == 401
    reply = client.post("/v1/auth/login", json={"username": "Admin", "password": TEST_PASSWORD})
    assert reply.status_code == 200 and reply.json() == {"username": "admin", "role": "admin",
                                                          "must_change": False, "short_password": False}
    cookie = reply.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and TEST_PASSWORD not in cookie
    assert client.get("/v1/cases").status_code == 200
    client.post("/v1/auth/logout")
    assert client.get("/v1/cases").status_code == 401


def test_a_wrong_password_never_says_which_part_was_wrong_and_locks_after_five(tmp_path):
    app, _ = app_with(tmp_path, ("admin", TEST_PASSWORD, "admin", False))
    client = TestClient(app)
    for _ in range(5):
        reply = client.post("/v1/auth/login", json={"username": "admin", "password": "nope"})
        assert reply.status_code == 401 and reply.json()["detail"] == "The username or password is not correct."
    locked = client.post("/v1/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
    assert locked.status_code == 401 and "Too many attempts" in locked.json()["detail"]


def test_a_new_user_must_change_the_password_before_using_the_app(tmp_path):
    app, _ = app_with(tmp_path, ("doctor1", TEST_PASSWORD, "user", True))
    client = TestClient(app)
    assert client.post("/v1/auth/login", json={"username": "doctor1", "password": TEST_PASSWORD}).json()["must_change"]
    assert client.get("/v1/cases").status_code == 403
    bad = client.post("/v1/auth/password", json={"current_password": "x", "new_password": "another-pass"})
    assert bad.status_code == 400
    ok = client.post("/v1/auth/password", json={"current_password": TEST_PASSWORD, "new_password": "another-pass"})
    assert ok.status_code == 200 and ok.json()["must_change"] is False
    assert client.get("/v1/cases").status_code == 200


def test_a_short_owner_chosen_password_works_and_is_flagged(tmp_path):
    app, _ = app_with(tmp_path, ("admin", "4321", "admin", False))
    client = TestClient(app)
    reply = client.post("/v1/auth/login", json={"username": "admin", "password": "4321"})
    assert reply.status_code == 200 and reply.json()["short_password"] is True


def test_only_an_admin_manages_users_and_cannot_disable_itself(tmp_path):
    app, store_file = app_with(tmp_path, ("admin", TEST_PASSWORD, "admin", False),
                               ("doctor1", TEST_PASSWORD, "user", False))
    doctor = TestClient(app)
    doctor.post("/v1/auth/login", json={"username": "doctor1", "password": TEST_PASSWORD})
    assert doctor.get("/v1/admin/users").status_code == 403
    admin = TestClient(app)
    admin.post("/v1/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
    created = admin.post("/v1/admin/users", json={"username": "doctor2", "password": "first-pass", "role": "user"})
    assert created.status_code == 200
    row = next(user for user in created.json()["users"] if user["username"] == "doctor2")
    assert row["must_change"] is True and "hash" not in row and "salt" not in row
    assert admin.post("/v1/admin/users", json={"username": "admin", "disabled": True}).status_code == 400
    admin.post("/v1/admin/users", json={"username": "doctor1", "disabled": True})
    assert doctor.get("/v1/cases").status_code == 401  # Disabling ends the session.
    assert "first-pass" not in store_file.read_text(encoding="utf-8")


def test_a_session_expires(tmp_path):
    store = UserStore(tmp_path / "users.json")
    store.set_user("admin", TEST_PASSWORD, role="admin", must_change=False)
    now = [1000.0]
    auth = Authenticator(store, clock=lambda: now[0])
    token, _ = auth.login("admin", TEST_PASSWORD)
    assert auth.session(token)
    now[0] += pilot_auth.SESSION_SECONDS + 1
    assert auth.session(token) is None


def test_the_setup_command_reads_the_password_from_input_and_never_prints_it(tmp_path, monkeypatch, capsys):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO(TEST_PASSWORD + "\n"))
    assert pilot_auth.main(["set-user", "--file", str(tmp_path / "u.json"), "--username", "admin", "--role",
                            "admin"]) == 0
    assert TEST_PASSWORD not in capsys.readouterr().out
    assert UserStore(tmp_path / "u.json").verify("admin", TEST_PASSWORD)


def test_invalid_usernames_and_too_short_passwords_are_refused(tmp_path):
    store = UserStore(tmp_path / "users.json")
    with pytest.raises(AuthError):
        store.set_user("A B", TEST_PASSWORD, role="user", must_change=True)
    with pytest.raises(AuthError):
        store.set_user("doctor3", "12", role="user", must_change=True)
