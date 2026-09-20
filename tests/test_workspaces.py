"""Focused regression coverage for the S2 local workspace boundary."""

import sqlite3

from fastapi.testclient import TestClient

from dr_support.api import create_app
from dr_support.contracts import PickerResult
from dr_support.services.pickers import NativePicker
from dr_support.services.workspaces import WorkspaceCatalogError


def _workspace_payload(tmp_path, name, database_path, *, note=None):
    input_folder = tmp_path / f"{name}-input"
    output_folder = tmp_path / f"{name}-output"
    input_folder.mkdir(exist_ok=True)
    output_folder.mkdir(exist_ok=True)
    payload = {
        "name": f"  {name}  ",
        "input_folder": str(input_folder),
        "output_folder": str(output_folder),
        "database_path": str(database_path),
    }
    if note is not None:
        payload["note"] = note
    return payload


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


def test_legacy_catalog_without_note_remains_readable(monkeypatch, tmp_path):
    catalog_path = tmp_path / "workspaces.sqlite"
    database_path = tmp_path / "legacy.sqlite"
    input_folder = tmp_path / "legacy-input"
    output_folder = tmp_path / "legacy-output"
    input_folder.mkdir()
    output_folder.mkdir()
    with sqlite3.connect(catalog_path) as database:
        database.execute(
            "CREATE TABLE workspaces (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
            "input_folder TEXT NOT NULL, output_folder TEXT NOT NULL, database_path TEXT NOT NULL, "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, last_opened TEXT)"
        )
        database.execute(
            "INSERT INTO workspaces VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "ws_legacy",
                "Legacy",
                str(input_folder),
                str(output_folder),
                str(database_path),
                "2026-09-20T05:00:00+00:00",
                "2026-09-20T05:00:00+00:00",
                None,
            ),
        )
        database.commit()

    response = TestClient(_app(monkeypatch, tmp_path)).get("/v1/workspaces")

    assert response.status_code == 200
    assert response.json()["workspaces"] == [
        {
            "id": "ws_legacy",
            "name": "Legacy",
            "input_folder": str(input_folder),
            "output_folder": str(output_folder),
            "database_path": str(database_path),
            "note": None,
            "created_at": "2026-09-20T05:00:00+00:00",
            "updated_at": "2026-09-20T05:00:00+00:00",
            "last_opened": None,
        }
    ]


def test_workspace_note_can_be_created_updated_and_cleared(monkeypatch, tmp_path):
    client = TestClient(_app(monkeypatch, tmp_path))
    database_path = tmp_path / "noted.sqlite"

    created = client.post(
        "/v1/workspaces",
        json=_workspace_payload(tmp_path, "Noted", database_path, note=" Mobile unit "),
    )
    assert created.status_code == 200
    assert created.json()["workspace"]["note"] == "Mobile unit"

    workspace_id = created.json()["workspace"]["id"]
    update_payload = _workspace_payload(tmp_path, "Noted", database_path, note="September clinic")
    updated = client.put(f"/v1/workspaces/{workspace_id}", json=update_payload)
    assert updated.status_code == 200
    assert updated.json()["workspace"]["note"] == "September clinic"

    cleared = client.put(
        f"/v1/workspaces/{workspace_id}",
        json=_workspace_payload(tmp_path, "Noted", database_path, note="   "),
    )
    assert cleared.status_code == 200
    assert cleared.json()["workspace"]["note"] is None


def test_delete_inactive_workspace_removes_only_catalog_profile(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)
    client = TestClient(app)
    active_path = tmp_path / "active.sqlite"
    inactive_path = tmp_path / "inactive.sqlite"
    active = client.post("/v1/workspaces", json=_workspace_payload(tmp_path, "Active", active_path)).json()
    inactive = client.post("/v1/workspaces", json=_workspace_payload(tmp_path, "Inactive", inactive_path)).json()
    client.post(f"/v1/workspaces/{active['workspace']['id']}/open")

    response = client.delete(f"/v1/workspaces/{inactive['workspace']['id']}")

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert inactive_path.exists()
    assert (tmp_path / "workspaces.sqlite").exists()
    assert client.get("/v1/workspaces/active").json()["workspace"]["id"] == active["workspace"]["id"]
    assert client.get("/v1/cases/SYNTH_001").status_code == 200
    assert all(item["id"] != inactive["workspace"]["id"] for item in client.get("/v1/workspaces").json()["workspaces"])


def test_active_workspace_cannot_be_deleted(monkeypatch, tmp_path):
    client = TestClient(_app(monkeypatch, tmp_path))
    database_path = tmp_path / "active.sqlite"
    created = client.post("/v1/workspaces", json=_workspace_payload(tmp_path, "Active", database_path)).json()

    response = client.delete(f"/v1/workspaces/{created['workspace']['id']}")

    assert response.status_code == 409
    assert "active workspace cannot be deleted" in response.json()["detail"]
    assert client.get("/v1/workspaces/active").json()["workspace"]["id"] == created["workspace"]["id"]
    assert database_path.exists()


def test_unknown_workspace_delete_is_not_found(monkeypatch, tmp_path):
    client = TestClient(_app(monkeypatch, tmp_path))

    response = client.delete("/v1/workspaces/ws_missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown workspace"


def test_failed_delete_preserves_active_workspace(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)
    client = TestClient(app)
    active_path = tmp_path / "active.sqlite"
    inactive_path = tmp_path / "inactive.sqlite"
    active = client.post("/v1/workspaces", json=_workspace_payload(tmp_path, "Active", active_path)).json()
    inactive = client.post("/v1/workspaces", json=_workspace_payload(tmp_path, "Inactive", inactive_path)).json()
    client.post(f"/v1/workspaces/{active['workspace']['id']}/open")

    def fail_delete(_workspace_id):
        raise WorkspaceCatalogError("catalog is locked")

    monkeypatch.setattr(app.state.workspace_manager.catalog, "delete", fail_delete)
    response = client.delete(f"/v1/workspaces/{inactive['workspace']['id']}")

    assert response.status_code == 503
    assert client.get("/v1/workspaces/active").json()["workspace"]["id"] == active["workspace"]["id"]
    assert client.get("/v1/cases/SYNTH_001").status_code == 200
    assert active_path.exists()
    assert inactive_path.exists()


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
