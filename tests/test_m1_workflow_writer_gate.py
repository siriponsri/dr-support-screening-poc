"""Actual workflow/manager entry controls, not composed PRISM qualification."""
from threading import Event, Thread

from fastapi.testclient import TestClient
import pytest

from dr_support.api import create_app
from dr_support.contracts import WorkspaceInput
from dr_support.services.source_mutation_gate import MutationFenced, SourceMutationGate
from dr_support.services.workspaces import WorkspaceManager


def app_with_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("DR_SUPPORT_WORKSPACE_CATALOG", str(tmp_path / "catalog.sqlite"))
    app = create_app(state_path=tmp_path / "case.sqlite", case_store_mode="sqlite", include_samples=False)
    client = TestClient(app)
    image_id = next(iter(app.state.images))
    assert client.get(f"/v1/cases/{image_id}").status_code == 200
    gate = SourceMutationGate()
    app.state.source_mutation_gate = gate
    app.state.workspace_manager.source_mutation_gate = gate
    app.state.store.source_mutation_gate = gate
    return app, client, image_id, gate


def test_all_physician_and_artifact_writer_routes_refuse_before_business_effects(tmp_path, monkeypatch):
    app, _, image_id, gate = app_with_gate(tmp_path, monkeypatch)
    names = {"review", "queue_action", "lesion_review", "review_admission", "review_resolver",
             "confirm_image", "save_human_annotations", "update_annotation_completeness",
             "derive_human_annotation", "cvat", "manual", "refresh", "restore"}
    routes = [r for r in app.routes if getattr(r, "name", None) in names]
    assert {r.name for r in routes} == names
    before = app.state.store.get(image_id)
    gate.begin_entry(expected_generation=gate.snapshot().generation)
    for route in routes:
        assert route.endpoint.__source_writer_scope__
        kwargs = {"image_id": image_id, "action": "sync"} if route.name == "cvat" else {"image_id": image_id, "request": None}
        with pytest.raises(MutationFenced):
            route.endpoint(**kwargs)
    assert app.state.store.get(image_id) == before


def test_case_read_does_not_invalidate_plan_but_blocks_entry_while_reading(tmp_path, monkeypatch):
    app, client, image_id, gate = app_with_gate(tmp_path, monkeypatch)
    original, entered, release, results = app.state.store.get, Event(), Event(), []
    generation = gate.snapshot().generation
    assert client.get(f"/v1/cases/{image_id}").status_code == 200
    assert gate.snapshot().generation == generation
    def paused_get(key):
        entered.set()
        assert release.wait(5)
        return original(key)
    monkeypatch.setattr(app.state.store, "get", paused_get)
    thread = Thread(target=lambda: results.append(client.get(f"/v1/cases/{image_id}").status_code))
    thread.start()
    try:
        assert entered.wait(5)
        with pytest.raises(MutationFenced, match="ACTIVE"):
            gate.begin_entry(expected_generation=generation)
    finally:
        release.set()
        thread.join(6)
    assert not thread.is_alive() and results == [200]
    assert gate.snapshot().generation == generation


def test_manager_direct_calls_and_new_store_share_the_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("DR_SUPPORT_WORKSPACE_CATALOG", str(tmp_path / "catalog.sqlite"))
    gate = SourceMutationGate()
    manager = WorkspaceManager(tmp_path, state_path=tmp_path / "fallback.sqlite", source_mutation_gate=gate)
    assert manager.store.source_mutation_gate is gate
    profile = manager.create_and_open(WorkspaceInput(name="Engineering only",
        input_folder=str(tmp_path / "images"), output_folder=str(tmp_path / "output"),
        database_path=str(tmp_path / "workspace.sqlite")))
    assert manager.store.source_mutation_gate is gate
    store = manager.store
    gate.begin_entry(expected_generation=gate.snapshot().generation)
    with pytest.raises(MutationFenced):
        manager.open(profile.id)
    with pytest.raises(MutationFenced):
        manager.delete(profile.id)
    assert manager.store is store and manager.active_workspace.id == profile.id


def test_quarantined_manager_cannot_open_or_create_storage(tmp_path):
    with pytest.raises(ValueError, match="RECOVERY_REQUIRED"):
        WorkspaceManager(tmp_path / "not_created", source_mutation_gate=SourceMutationGate(quarantined=True))
    assert not (tmp_path / "not_created").exists()
