"""Focused regression coverage for the S2 local workspace boundary."""

import sqlite3

from fastapi.testclient import TestClient

from dr_support.api import create_app
from dr_support.contracts import PickerResult
from dr_support.services.pickers import NativePicker


def _workspace_payload(tmp_path, name, database_path):
    input_folder = tmp_path / f"{name}-input"
    output_folder = tmp_path / f"{name}-output"
    input_folder.mkdir(exist_ok=True)
    output_folder.mkdir(exist_ok=True)
    return {
        "name": f"  {name}  ",
        "input_folder": str(input_folder),
        "output_folder": str(output_folder),
        "database_path": str(database_path),
    }


def _app(monkeypatch, tmp_path, *, state_path=None):
    monkeypatch.setenv("DR_SUPPORT_WORKSPACE_CATALOG", str(tmp_path / "workspaces.sqlite"))
    monkeypatch.setenv("DR_SUPPORT_STATE", str(tmp_path / "fallback.sqlite"))
    return create_app(state_path=state_path, include_samples=False)


def test_workspace_save_initializes_catalog_and_database(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)
    client = TestClient(app)
    database_path = tmp_path / "review.sqlite"

    response = client.post("/v1/workspaces", json=_workspace_payload(tmp_path, "April", database_path))

    assert response.status_code == 200
    body = response.json()
    assert body["active"] is True
    assert body["workspace"]["name"] == "April"
    assert body["workspace"]["last_opened"]
    assert database_path.exists()
    assert (tmp_path / "workspaces.sqlite").exists()
    with sqlite3.connect(database_path) as database:
        assert database.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cases'"
        ).fetchone()


def test_workspace_startup_restores_and_switches_active_store(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)
    client = TestClient(app)
    first_path = tmp_path / "first.sqlite"
    second_path = tmp_path / "second.sqlite"

    first = client.post("/v1/workspaces", json=_workspace_payload(tmp_path, "First", first_path)).json()
    first_case = app.state.store.get("SYNTH_001")
    first_case["events"].append({"action": "FIRST_WORKSPACE"})
    app.state.store.put(first_case)
    second = client.post("/v1/workspaces", json=_workspace_payload(tmp_path, "Second", second_path)).json()

    assert client.get("/v1/cases/SYNTH_001").json()["events"] == []
    assert client.post(f"/v1/workspaces/{first['workspace']['id']}/open").status_code == 200
    assert client.get("/v1/cases/SYNTH_001").json()["events"] == [{"action": "FIRST_WORKSPACE"}]

    restored = TestClient(_app(monkeypatch, tmp_path)).get("/v1/workspaces/active")
    assert restored.status_code == 200
    assert restored.json()["workspace"]["id"] == first["workspace"]["id"]
    assert restored.json()["database"]["status"] == "ready"
    assert second["workspace"]["id"] != first["workspace"]["id"]


def test_failed_activation_preserves_previous_active_store(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)
    client = TestClient(app)
    database_path = tmp_path / "review.sqlite"
    created = client.post("/v1/workspaces", json=_workspace_payload(tmp_path, "Stable", database_path)).json()
    active_before = client.get("/v1/workspaces/active").json()

    invalid_request = _workspace_payload(tmp_path, "Stable", tmp_path / "missing" / "review.sqlite")
    response = client.put(f"/v1/workspaces/{created['workspace']['id']}", json=invalid_request)

    assert response.status_code == 409
    active_after = client.get("/v1/workspaces/active").json()
    assert active_after["workspace"]["id"] == active_before["workspace"]["id"]
    assert active_after["database"]["path"] == active_before["database"]["path"]
    assert client.get("/v1/cases/SYNTH_001").status_code == 200


def test_explicit_state_path_precedes_last_opened_workspace(monkeypatch, tmp_path):
    seed = _app(monkeypatch, tmp_path)
    seeded_client = TestClient(seed)
    workspace_path = tmp_path / "workspace.sqlite"
    seeded_client.post("/v1/workspaces", json=_workspace_payload(tmp_path, "Seeded", workspace_path))

    explicit_path = tmp_path / "explicit.sqlite"
    app = _app(monkeypatch, tmp_path, state_path=explicit_path)
    active = TestClient(app).get("/v1/workspaces/active").json()

    assert active["workspace"] is None
    assert active["database"] == {"path": str(explicit_path), "status": "fallback"}


def test_invalid_workspace_paths_are_rejected(monkeypatch, tmp_path):
    client = TestClient(_app(monkeypatch, tmp_path))
    response = client.post(
        "/v1/workspaces",
        json={
            "name": "Bad",
            "input_folder": "relative/input",
            "output_folder": str(tmp_path),
            "database_path": str(tmp_path / "review.sqlite"),
        },
    )
    assert response.status_code == 422


def test_picker_cancel_and_headless_unavailable_are_explicit(monkeypatch, tmp_path):
    monkeypatch.setattr(NativePicker, "_available", staticmethod(lambda: False))
    app = _app(monkeypatch, tmp_path)
    client = TestClient(app)

    unavailable = client.post(
        "/v1/workspaces/pickers/folder",
        json={"purpose": "input", "initial_path": str(tmp_path)},
    )
    assert unavailable.status_code == 200
    assert unavailable.json()["status"] == "unavailable"
    assert unavailable.json()["path"] is None

    class CancelPicker:
        def pick_database(self, **_kwargs):
            return PickerResult(status="cancelled")

        def pick_folder(self, **_kwargs):
            return PickerResult(status="cancelled")

    app.state.workspace_picker = CancelPicker()
    cancelled = client.post(
        "/v1/workspaces/pickers/database",
        json={"mode": "create", "initial_path": str(tmp_path), "suggested_name": "review.sqlite"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json() == {"status": "cancelled", "path": None, "code": None, "message": None}
