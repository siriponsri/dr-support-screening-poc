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
