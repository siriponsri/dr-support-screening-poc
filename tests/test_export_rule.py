"""One export rule for every dataset path (owner decision, 2026-10-24)."""
from pathlib import Path

import pytest

from dr_support.services import dataset, source_policy
from dr_support.services.source_policy import export_authorization, local_export_destination_reason


def test_dataset_uses_the_single_source_policy_rule():
    assert dataset.ENGINEERING_EXPORT_AUTHORIZATION is source_policy.EXPORT_AUTHORIZATION
    assert export_authorization("HOSPITAL_AUTHORIZED") == "ALLOWED_LOCAL_AUTHORIZED_HOSPITAL"
    assert export_authorization("WORKSPACE").startswith("BLOCKED_")
    assert export_authorization("UNKNOWN").startswith("BLOCKED_")
    assert export_authorization("something-new").startswith("BLOCKED_")


def test_local_folder_is_accepted(tmp_path, monkeypatch):
    for name in source_policy._CLOUD_SYNC_ENV:
        monkeypatch.delenv(name, raising=False)
    assert local_export_destination_reason(tmp_path / "exports") is None


@pytest.mark.parametrize("folder", [r"\\server\share\exports", "//server/share/exports"])
def test_network_share_is_refused(folder):
    assert local_export_destination_reason(folder) == "NETWORK_SHARE"


def test_cloud_synced_folders_are_refused(tmp_path, monkeypatch):
    onedrive = tmp_path / "Company OneDrive Root"
    monkeypatch.setenv("OneDrive", str(onedrive))
    assert local_export_destination_reason(onedrive / "exports") == "CLOUD_SYNC_FOLDER"
    monkeypatch.delenv("OneDrive")
    for name in ("Dropbox", "Google Drive", "OneDrive - Hospital"):
        assert local_export_destination_reason(tmp_path / name / "exports") == "CLOUD_SYNC_FOLDER"


def test_hospital_export_to_a_synced_folder_is_blocked_before_writing(tmp_path):
    rows = [{"export_authorization": "ALLOWED_LOCAL_AUTHORIZED_HOSPITAL"}]
    with pytest.raises(dataset.DatasetManifestError, match="local folder on this computer"):
        dataset.DatasetManifestService._assert_local_destination(rows, Path(tmp_path) / "Dropbox" / "out")
    # Public/synthetic engineering exports are not hospital records and keep working anywhere.
    dataset.DatasetManifestService._assert_local_destination(
        [{"export_authorization": "ALLOWED_ENGINEERING_PUBLIC"}], Path(tmp_path) / "Dropbox" / "out")


def test_long_path_prefixes_and_folder_names(tmp_path, monkeypatch):
    for name in source_policy._CLOUD_SYNC_ENV:
        monkeypatch.delenv(name, raising=False)
    assert local_export_destination_reason(r"\\?\UNC\server\share\exports") == "NETWORK_SHARE"
    assert source_policy._network_path(r"\\?\C:\exports") is False
    for name in ("Dropbox (Company)", "Shared drives", "Box Sync"):
        assert local_export_destination_reason(tmp_path / name / "out") == "CLOUD_SYNC_FOLDER"
    # Ordinary folders whose names only resemble sync clients stay allowed.
    assert local_export_destination_reason(tmp_path / "box" / "out") is None


def test_grading_folders_take_their_origins_from_the_single_rule():
    from dr_support.services import grading_folders
    assert grading_folders.AUTHORIZATIONS == {
        origin: decision for origin, decision in source_policy.EXPORT_AUTHORIZATION.items()
        if not decision.startswith("BLOCKED_")}


def test_local_only_records_write_nothing_into_a_refused_folder(tmp_path, monkeypatch):
    """Runs everywhere: ordinary records carry the local-only (hospital) export decision."""
    from fastapi.testclient import TestClient
    from dr_support.api import create_app
    from test_admission import _write_image
    for name in source_policy._CLOUD_SYNC_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(dataset, "_export_authorization", lambda origin: "ALLOWED_LOCAL_AUTHORIZED_HOSPITAL")
    monkeypatch.setenv("DR_SUPPORT_STATE", str(tmp_path / "fallback.sqlite"))
    monkeypatch.setenv("DR_SUPPORT_WORKSPACE_CATALOG", str(tmp_path / "catalog.sqlite"))
    client = TestClient(create_app(include_samples=False))
    source, output = tmp_path / "input", tmp_path / "Dropbox" / "exports"
    source.mkdir()
    output.mkdir(parents=True)
    _write_image(source / "fundus.png", fundus=True)
    assert client.post("/v1/workspaces", json={
        "name": "Refused destination", "input_folder": str(source), "output_folder": str(output),
        "database_path": str(tmp_path / "reviews.sqlite")}).status_code == 200
    assert client.post("/v1/admissions/scan").status_code == 200
    for path, body in (("/v1/dataset/export", None), ("/v1/dataset/export/grouped-by-grade", {}),
                       ("/v2/dataset/snapshot", {})):
        response = client.post(path, json=body)
        assert response.status_code == 409, path
        assert "local folder on this computer" in response.json()["detail"]
    assert list(output.iterdir()) == []


def test_hospital_exports_write_nothing_into_a_refused_folder(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from dr_support.api import create_app
    from test_authorized_hospital import _configure_hospital, _jpeg_bytes
    for name in source_policy._CLOUD_SYNC_ENV:
        monkeypatch.delenv(name, raising=False)
    root = tmp_path / "hospital"
    _configure_hospital(monkeypatch, root)
    (root / "private-source.jpg").write_bytes(_jpeg_bytes())
    output = tmp_path / "Dropbox" / "exports"
    output.mkdir(parents=True)
    monkeypatch.setenv("DR_SUPPORT_WORKSPACE_CATALOG", str(tmp_path / "catalog.sqlite"))
    client = TestClient(create_app(tmp_path / "state.sqlite", include_samples=False, include_demo_fixtures=False))
    assert client.post("/v1/workspaces", json={
        "name": "Refused destination", "input_folder": str(root), "output_folder": str(output),
        "database_path": str(tmp_path / "workspace.sqlite")}).status_code == 200
    for path, body in (("/v1/dataset/export", None), ("/v1/dataset/export/grouped-by-grade", {}),
                       ("/v2/dataset/snapshot", {})):
        response = client.post(path, json=body)
        assert response.status_code == 409, path
        assert "local folder on this computer" in response.json()["detail"]
    assert list(output.iterdir()) == []
