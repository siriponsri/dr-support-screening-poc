"""Pilot sign-in: hashed users file, session cookie, lockout, admin user management. Offline only."""

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from dr_support.services import pilot_auth
from dr_support.services.pilot_auth import AuthError, Authenticator, UserStore, install_pilot_auth

TEST_PASSWORD = "synthetic-test-pass-7"


def app_with(tmp_path, *users):
    store_file = tmp_path / "users.json"
    store = UserStore(store_file)
    for username, password, role, must_change in users:
        store.set_user(username, password, role=role, must_change=must_change, enforce_policy=False)
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
    bad = client.post("/v1/auth/password", json={"current_password": "x", "new_password": "another-pass-9"})
    assert bad.status_code == 400
    ok = client.post("/v1/auth/password", json={"current_password": TEST_PASSWORD, "new_password": "another-pass-9"})
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
    created = admin.post("/v1/admin/users", json={"username": "doctor2", "password": "first-pass-1", "role": "user"})
    assert created.status_code == 200
    row = next(user for user in created.json()["users"] if user["username"] == "doctor2")
    assert row["must_change"] is True and "hash" not in row and "salt" not in row
    assert admin.post("/v1/admin/users", json={"username": "admin", "disabled": True}).status_code == 400
    admin.post("/v1/admin/users", json={"username": "doctor1", "disabled": True})
    assert doctor.get("/v1/cases").status_code == 401  # Disabling ends the session.
    assert "first-pass-1" not in store_file.read_text(encoding="utf-8")


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


def test_the_admin_database_view_is_read_only_and_admin_only(tmp_path):
    from types import SimpleNamespace
    app, _ = app_with(tmp_path, ("admin", TEST_PASSWORD, "admin", False), ("doctor1", TEST_PASSWORD, "user", False))
    stored = {"img1": {"image_id": "img1", "revision": 3, "reviewed_grade": 3, "grade_status": "CONFIRMED",
                       "grade_review_source": "AI_CORRECTED", "annotations": [{"id": "a"}],
                       "admission": {"retinal_modality": "UWF", "source_origin": "PUBLIC"},
                       "inference_history": [{"task": "global", "model_id": "uspec-uwf-grading", "result": {"grade": 2}}]}}

    class Store:
        def all_cases(self):
            return list(stored.values())

        def get(self, image_id):
            return stored[image_id]
    app.state.store = Store()
    app.state.workspace_manager = SimpleNamespace(active_workspace=SimpleNamespace(id="ws_1", name="TEST_ONLY pilot"))
    doctor = TestClient(app)
    doctor.post("/v1/auth/login", json={"username": "doctor1", "password": TEST_PASSWORD})
    assert doctor.get("/v1/admin/db/summary").status_code == 403
    admin = TestClient(app)
    admin.post("/v1/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
    summary = admin.get("/v1/admin/db/summary").json()
    assert summary["cases"] == 1 and summary["grade_corrected"] == 1 and summary["workspace"]["name"] == "TEST_ONLY pilot"
    rows = admin.get("/v1/admin/db/cases", params={"limit": 500}).json()
    assert rows["limit"] == 100 and rows["rows"][0]["ai_grade"] == 2 and rows["rows"][0]["clinician_grade"] == 3
    assert admin.get("/v1/admin/db/cases/img1").json()["record"]["revision"] == 3
    assert admin.get("/v1/admin/db/cases/missing").status_code == 404
    assert admin.post("/v1/admin/db/cases/img1").status_code == 405


def test_the_admin_policy_is_bounded_and_enforced_on_new_passwords(tmp_path):
    app, _ = app_with(tmp_path, ("admin", TEST_PASSWORD, "admin", False))
    admin = TestClient(app)
    admin.post("/v1/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
    assert admin.get("/v1/admin/policy").json()["policy"]["min_length"] == 8
    assert admin.post("/v1/admin/policy", json={"min_length": 3}).status_code == 400
    assert admin.post("/v1/admin/policy", json={"letters_and_numbers": "yes"}).status_code == 400
    saved = admin.post("/v1/admin/policy", json={"min_length": 10, "idle_minutes": 15})
    assert saved.json()["policy"]["min_length"] == 10
    weak = admin.post("/v1/admin/users", json={"username": "doctor2", "password": "abc12345", "role": "user"})
    assert weak.status_code == 400 and "at least 10 characters" in weak.json()["detail"]
    ok = admin.post("/v1/admin/users", json={"username": "doctor2", "password": "abcdef12345", "role": "user"})
    assert ok.status_code == 200
    assert TestClient(app).get("/v1/auth/policy").json() == {"min_length": 10, "letters_and_numbers": True}


def test_idle_sessions_end_by_policy(tmp_path):
    store = UserStore(tmp_path / "users.json")
    store.set_user("admin", TEST_PASSWORD, role="admin", must_change=False)
    store.set_policy({"idle_minutes": 5})
    now = [1000.0]
    auth = Authenticator(store, clock=lambda: now[0])
    token, _ = auth.login("admin", TEST_PASSWORD)
    now[0] += 4 * 60
    assert auth.session(token)          # Activity keeps it alive.
    now[0] += 6 * 60
    assert auth.session(token) is None


def test_lockout_follows_the_policy(tmp_path):
    store = UserStore(tmp_path / "users.json")
    store.set_user("admin", TEST_PASSWORD, role="admin", must_change=False)
    store.set_policy({"max_failures": 3, "lockout_minutes": 2})
    auth = Authenticator(store)
    for _ in range(3):
        with pytest.raises(AuthError):
            auth.login("admin", "wrong")
    with pytest.raises(AuthError, match="Wait 2 minutes"):
        auth.login("admin", TEST_PASSWORD)


def test_an_operator_set_short_password_is_flagged_as_below_policy(tmp_path):
    app, _ = app_with(tmp_path, ("admin", "4321", "admin", False))
    client = TestClient(app)
    assert client.post("/v1/auth/login", json={"username": "admin", "password": "4321"}).json()["short_password"]
