"""Private authorized-hospital provenance and fail-closed export tests."""

import hashlib
import io
import json
import os
import subprocess

from fastapi.testclient import TestClient
from PIL import Image

from dr_support.api import create_app
from dr_support.services.model_api import create_app as create_model_api_app
from dr_support.services.admission import scan_authorized_hospital_roots, scan_input_folder
from dr_support.services.source_policy import (
    HOSPITAL_ORIGIN,
    hospital_ingest_enabled,
    source_allowed_for_model,
)


def _jpeg_bytes(color=(30, 90, 60)) -> bytes:
    image = Image.new("RGB", (192, 128), color)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=90)
    return output.getvalue()



def _private_test_root(root) -> None:
    """Apply privacy to synthetic fixtures using the host's actual permission model."""
    if os.name != "nt":
        root.chmod(0o700)
        return
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
         "$p = $env:DR_TEST_PRIVATE_ROOT; $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value; "
         "& icacls.exe $p /inheritance:r /grant:r "
         "('*' + $sid + ':(OI)(CI)F') '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F'; "
         "exit $LASTEXITCODE"],
        check=True, capture_output=True, env={**os.environ, "DR_TEST_PRIVATE_ROOT": str(root)},
    )


def _configure_hospital(monkeypatch, root, *, modality="UWF") -> None:
    monkeypatch.setenv("DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOT", str(root))
    monkeypatch.setenv("DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL", "1")
    monkeypatch.setenv("DR_SUPPORT_AUTHORIZED_HOSPITAL_MODALITY", modality)
    root.mkdir(parents=True, exist_ok=True)
    _private_test_root(root)


def test_authorized_hospital_linkage_is_opaque_and_sequence_bound(tmp_path, monkeypatch):
    root = tmp_path / "hospital"
    _configure_hospital(monkeypatch, root)
    monkeypatch.setenv("DR_SUPPORT_HOSPITAL_LINKAGE_KEY", "test-private-linkage-key-0123456789012345")
    (root / "PATIENT01_L2.jpg").write_bytes(_jpeg_bytes())
    record = next(iter(scan_input_folder(
        root, source_origin=HOSPITAL_ORIGIN, retinal_modality="UWF",
        retinal_modality_method="AUTHORIZED_SOURCE",
    ).records.values()))
    assert record["trusted_patient_key"].startswith("HOSPITAL-")
    assert record["trusted_patient_key"] != "PATIENT01"
    assert record["trusted_laterality"] == "LEFT"
    assert record["trusted_capture_sequence"] == 2
    assert "PATIENT01" not in json.dumps(record)


def test_default_workspace_remains_workspace_and_unrelated_root_is_not_promoted(tmp_path, monkeypatch):
    root = tmp_path / "hospital"
    root.mkdir()
    _private_test_root(root)
    (root / "source.jpg").write_bytes(_jpeg_bytes())
    _configure_hospital(monkeypatch, root)

    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    (unrelated / "source.jpg").write_bytes(_jpeg_bytes())
    scan = scan_input_folder(unrelated)

    assert not hospital_ingest_enabled(unrelated)
    record = next(iter(scan.records.values()))
    assert record["source_origin"] == "WORKSPACE"
    assert record["retinal_modality"] == "UNKNOWN"
    assert record["retinal_modality_method"] == "NONE"


def test_hospital_admission_is_neutral_source_bound_and_preserves_bytes(tmp_path, monkeypatch):
    root = tmp_path / "hospital"
    _configure_hospital(monkeypatch, root)
    original_name = "patient-label-sensitive.jpg"
    source = _jpeg_bytes()
    path = root / original_name
    path.write_bytes(source)

    scan = scan_input_folder(
        root, source_origin=HOSPITAL_ORIGIN, retinal_modality="UWF",
        retinal_modality_method="AUTHORIZED_SOURCE",
    )
    record = next(iter(scan.records.values()))
    image = next(iter(scan.images.values()))
    serialized = json.dumps(record)

    assert hospital_ingest_enabled(root)
    assert record["source_origin"] == HOSPITAL_ORIGIN
    assert record["retinal_modality"] == "UWF"
    assert record["retinal_modality_method"] == "AUTHORIZED_SOURCE"
    assert record["filename"] == "hospital-case-0001.jpg"
    assert record["source_reference"] == "HOSPITAL_AUTHORIZED/CASE-0001"
    assert original_name not in serialized
    assert record["source_sha256"] == hashlib.sha256(source).hexdigest()
    assert image.source_type == HOSPITAL_ORIGIN
    assert image.source_origin == HOSPITAL_ORIGIN
    assert image.source == record["source_reference"]
    assert image.filename == record["filename"]
    assert path.read_bytes() == source


def test_hospital_lane_requires_explicit_modality_binding(tmp_path, monkeypatch):
    root = tmp_path / "hospital"
    root.mkdir()
    _private_test_root(root)
    monkeypatch.setenv("DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOT", str(root))
    monkeypatch.setenv("DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL", "1")
    monkeypatch.delenv("DR_SUPPORT_AUTHORIZED_HOSPITAL_MODALITY", raising=False)
    assert not hospital_ingest_enabled(root)


def test_hospital_model_boundary_requires_private_scope_and_model_token(monkeypatch):
    monkeypatch.delenv("DR_SUPPORT_HOSPITAL_SCOPE", raising=False)
    monkeypatch.delenv("MODEL_HOSPITAL_SCOPE", raising=False)
    monkeypatch.delenv("MODEL_ALLOW_AUTHORIZED_HOSPITAL", raising=False)
    monkeypatch.delenv("REMOTE_MODEL_TOKEN", raising=False)
    assert not source_allowed_for_model(HOSPITAL_ORIGIN)
    assert not source_allowed_for_model(HOSPITAL_ORIGIN, model_api=True)

    monkeypatch.setenv("DR_SUPPORT_HOSPITAL_SCOPE", "PRIVATE_PROJECT_EVALUATION")
    monkeypatch.setenv("DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL", "1")
    assert source_allowed_for_model(HOSPITAL_ORIGIN)
    assert not source_allowed_for_model(HOSPITAL_ORIGIN, model_api=True)

    monkeypatch.setenv("MODEL_HOSPITAL_SCOPE", "PRIVATE_PROJECT_EVALUATION")
    monkeypatch.setenv("MODEL_ALLOW_AUTHORIZED_HOSPITAL", "1")
    monkeypatch.setenv("REMOTE_MODEL_TOKEN", "test-only-token")
    assert source_allowed_for_model(HOSPITAL_ORIGIN, model_api=True)


def test_model_api_rejects_hospital_origin_without_model_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_PROFILE", "model_api")
    monkeypatch.setenv("MODEL_RUNTIME", "local")
    monkeypatch.setenv("MODEL_API_PROVIDER_SET", "uspec")
    monkeypatch.delenv("MODEL_REQUIRE_VERIFIED_ASSETS", raising=False)
    monkeypatch.delenv("MODEL_HOSPITAL_SCOPE", raising=False)
    monkeypatch.delenv("MODEL_ALLOW_AUTHORIZED_HOSPITAL", raising=False)
    monkeypatch.delenv("REMOTE_MODEL_TOKEN", raising=False)
    app = create_model_api_app(device_strict=False)
    client = TestClient(app)
    source = _jpeg_bytes()
    digest = hashlib.sha256(source).hexdigest()
    body = {
        "image_id": "HOSPITAL_CASE_0001",
        "modality": "UWF",
        "model_id": "uspec-uwf-grading",
        "image_b64": __import__("base64").b64encode(source).decode("ascii"),
        "image_sha256": digest,
        "source_type": HOSPITAL_ORIGIN,
        "width": 192,
        "height": 128,
    }
    response = client.post("/v1/predict/dr", json=body)
    assert response.status_code == 409
    assert "source origin is blocked" in response.json()["detail"]
    descriptors = client.get("/v1/models").json()
    assert all("HOSPITAL_AUTHORIZED" not in item["authorized_source_origins"] for item in descriptors)

    monkeypatch.setenv("MODEL_HOSPITAL_SCOPE", "PRIVATE_PROJECT_EVALUATION")
    monkeypatch.setenv("MODEL_ALLOW_AUTHORIZED_HOSPITAL", "1")
    monkeypatch.setenv("REMOTE_MODEL_TOKEN", "test-only-token")
    authorized_app = create_model_api_app(device_strict=False)
    authorized_descriptors = TestClient(authorized_app).get("/v1/models").json()
    assert all("HOSPITAL_AUTHORIZED" in item["authorized_source_origins"] for item in authorized_descriptors)


def test_authorized_hospital_local_exports_preserve_unreviewed_sources(tmp_path, monkeypatch):
    root = tmp_path / "hospital"
    _configure_hospital(monkeypatch, root)
    original_bytes = _jpeg_bytes()
    source = root / "private-source.jpg"
    source.write_bytes(original_bytes)
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setenv("DR_SUPPORT_WORKSPACE_CATALOG", str(tmp_path / "catalog.sqlite"))
    app = create_app(tmp_path / "state.sqlite", include_samples=False, include_demo_fixtures=False)
    client = TestClient(app)
    response = client.post("/v1/workspaces", json={
        "name": "Private hospital engineering lane",
        "input_folder": str(root),
        "output_folder": str(output),
        "database_path": str(tmp_path / "workspace.sqlite"),
    })
    assert response.status_code == 200, response.text
    case = client.get("/v1/cases").json()[0]
    assert case["source_origin"] == HOSPITAL_ORIGIN
    assert case["filename"] == "hospital-case-0001.jpg"

    manifest = client.get("/v1/dataset/manifest").json()
    row = manifest["images"][0]
    assert row["source_origin"] == HOSPITAL_ORIGIN
    assert row["export_authorization"] == "ALLOWED_LOCAL_AUTHORIZED_HOSPITAL"
    assert manifest["can_export"] is True
    assert row["dr_grade_training_ready"] is False
    assert row["lesion_training_ready"] is False
    assert client.post("/v1/dataset/export").status_code == 200
    assert client.post("/v1/dataset/export/grouped-by-grade", json={}).status_code == 200
    assert source.read_bytes() == original_bytes
    assert client.get(f"/v1/cases/{case['image_id']}").json()["clinician_review"] is None


def test_authorized_hospital_api_pairs_previous_same_eye_and_sequence(tmp_path, monkeypatch):
    root = tmp_path / "hospital"
    _configure_hospital(monkeypatch, root)
    monkeypatch.setenv("DR_SUPPORT_HOSPITAL_SCOPE", "PRIVATE_PROJECT_EVALUATION")
    monkeypatch.setenv("DR_SUPPORT_HOSPITAL_LINKAGE_KEY", "test-private-linkage-key-0123456789012345")
    for index, name in enumerate((
        "P01_L1.jpg", "P01_L2.jpg", "P01_R1.jpg", "P01_R2.jpg", "P02_R2.jpg",
    )):
        (root / name).write_bytes(_jpeg_bytes((30 + index * 30, 90, 60)))

    app = create_app(
        tmp_path / "state.sqlite", include_samples=False, include_demo_fixtures=False,
    )
    client = TestClient(app)
    output = tmp_path / "output"
    response = client.post("/v1/workspaces", json={
        "name": "Authorized hospital comparison test",
        "input_folder": str(root),
        "output_folder": str(output),
        "database_path": str(tmp_path / "workspace.sqlite"),
    })
    assert response.status_code == 200, response.text

    cases = client.get("/v1/cases").json()
    assert len(cases) == 5
    assert all(item["source_origin"] == HOSPITAL_ORIGIN for item in cases)
    assert all("P01" not in json.dumps(item) for item in cases)

    left_current = next(
        item for item in cases
        if item["laterality"] == "LEFT" and item["visit_context"]["capture_sequence"] == 2
    )
    left_response = client.get(
        f"/v1/cases/{left_current['image_id']}/comparison"
    )
    assert left_response.status_code == 200
    left_comparison = left_response.json()
    assert left_comparison["eligible"] is True
    assert left_comparison["comparison_state"] == "AUTO_PREVIOUS"
    assert [visit["label"] for visit in left_comparison["visits"]] == [
        "PREVIOUS EXAM", "CURRENT EXAM",
    ]
    assert [visit["visit_context"]["capture_sequence"] for visit in left_comparison["visits"]] == [1, 2]
    assert all(visit["laterality"] == "LEFT" for visit in left_comparison["visits"])
    assert all(visit["modality"] == "UWF" for visit in left_comparison["visits"])

    right_current = next(
        item for item in cases
        if item["laterality"] == "RIGHT" and item["visit_context"]["capture_sequence"] == 2
        and item["patient_key"] == left_current["patient_key"]
    )
    right_comparison = client.get(
        f"/v1/cases/{right_current['image_id']}/comparison"
    ).json()
    assert right_comparison["eligible"] is True
    assert all(visit["laterality"] == "RIGHT" for visit in right_comparison["visits"])

    unmatched = next(
        item for item in cases
        if item["patient_key"] != left_current["patient_key"]
        and item["visit_context"]["capture_sequence"] == 2
    )
    assert client.get(
        f"/v1/cases/{unmatched['image_id']}/comparison"
    ).json() == {"eligible": False, "reason": "NO_VERIFIED_PREVIOUS_EXAM"}

    cross_eye = client.get(
        f"/v1/cases/{left_current['image_id']}/comparison?other_image_id={right_current['image_id']}"
    ).json()
    assert cross_eye == {"eligible": False, "reason": "EYE_MISMATCH"}


def test_multi_root_hospital_admission_keeps_one_mixed_modality_queue(tmp_path, monkeypatch):
    uwf = tmp_path / "uwf"
    cfp = tmp_path / "cfp"
    for root in (uwf, cfp):
        root.mkdir()
        _private_test_root(root)
    (uwf / "PRIVATE_L1.jpg").write_bytes(_jpeg_bytes((30, 90, 60)))
    (cfp / "PRIVATE_R1.jpg").write_bytes(_jpeg_bytes((70, 30, 20)))
    monkeypatch.setenv(
        "DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOTS",
        json.dumps({"UWF": str(uwf), "CFP": str(cfp)}),
    )
    monkeypatch.setenv("DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL", "1")
    monkeypatch.setenv("DR_SUPPORT_HOSPITAL_LINKAGE_KEY", "test-private-linkage-key-0123456789012345")

    scan = scan_authorized_hospital_roots()

    assert len(scan.records) == 2
    assert {record["retinal_modality"] for record in scan.records.values()} == {"UWF", "CFP"}
    assert all(record["source_origin"] == HOSPITAL_ORIGIN for record in scan.records.values())
    serialized = json.dumps(scan.records)
    assert "PRIVATE_L1" not in serialized
    assert "PRIVATE_R1" not in serialized
    assert "HOSPITAL_AUTHORIZED/CASE-0001" in serialized
    assert "HOSPITAL_AUTHORIZED/CASE-0002" in serialized


def test_multi_root_app_scans_without_workspace_profile_and_preserves_one_queue(tmp_path, monkeypatch):
    uwf = tmp_path / "uwf"
    cfp = tmp_path / "cfp"
    for root in (uwf, cfp):
        root.mkdir()
        _private_test_root(root)
    (uwf / "patient-a.jpg").write_bytes(_jpeg_bytes((30, 90, 60)))
    (cfp / "patient-b.jpg").write_bytes(_jpeg_bytes((70, 30, 20)))
    monkeypatch.setenv(
        "DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOTS",
        json.dumps({"UWF": str(uwf), "CFP": str(cfp)}),
    )
    monkeypatch.setenv("DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL", "1")
    monkeypatch.setenv("DR_SUPPORT_HOSPITAL_LINKAGE_KEY", "test-private-linkage-key-0123456789012345")

    app = create_app(tmp_path / "state.sqlite", include_samples=False, include_demo_fixtures=False)
    client = TestClient(app)
    cases = client.get("/v1/cases").json()

    assert len(cases) == 2
    assert {case["modality"] for case in cases} == {"UWF", "CFP"}
    assert all(case["source_origin"] == HOSPITAL_ORIGIN for case in cases)
    assert client.get("/v1/workspaces/active").json()["workspace"] is None
    assert str(uwf) not in json.dumps(cases)
    assert str(cfp) not in json.dumps(cases)


def test_invalid_multi_root_binding_fails_closed(tmp_path, monkeypatch):
    uwf = tmp_path / "uwf"
    uwf.mkdir()
    uwf.chmod(0o700)
    monkeypatch.setenv(
        "DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOTS",
        json.dumps({"UWF": str(uwf), "CFP": str(tmp_path / "missing-cfp")}),
    )
    monkeypatch.setenv("DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL", "1")

    scan = scan_authorized_hospital_roots()

    assert scan.records == {}
    assert scan.images == {}
    assert scan.warnings == ["Authorized hospital roots are not configured."]


def test_multi_root_case_references_remain_unique_when_content_is_duplicated(tmp_path, monkeypatch):
    uwf = tmp_path / "uwf"
    cfp = tmp_path / "cfp"
    for root in (uwf, cfp):
        root.mkdir()
        _private_test_root(root)
    duplicate = _jpeg_bytes((30, 90, 60))
    (uwf / "same-a.jpg").write_bytes(duplicate)
    (uwf / "same-b.jpg").write_bytes(duplicate)
    (cfp / "different.jpg").write_bytes(_jpeg_bytes((70, 30, 20)))
    monkeypatch.setenv(
        "DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOTS",
        json.dumps({"UWF": str(uwf), "CFP": str(cfp)}),
    )
    monkeypatch.setenv("DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL", "1")
    monkeypatch.setenv("DR_SUPPORT_HOSPITAL_LINKAGE_KEY", "test-private-linkage-key-0123456789012345")

    scan = scan_authorized_hospital_roots()

    references = [
        alias["source_reference"]
        for record in scan.records.values()
        for alias in (record.get("integrity") or {}).get("aliases", [])
    ]
    assert scan.candidate_count == 3
    assert len(scan.records) == 2
    assert len(references) == len(set(references))
    assert set(references) == {
        "HOSPITAL_AUTHORIZED/CASE-0001",
        "HOSPITAL_AUTHORIZED/CASE-0002",
        "HOSPITAL_AUTHORIZED/CASE-0003",
    }


def test_root_privacy_rejects_broad_access_and_preserves_source(tmp_path):
    from dr_support.services.filesystem_privacy import private_hospital_root

    root = tmp_path / "synthetic-private"
    root.mkdir()
    _private_test_root(root)
    image = root / "synthetic.jpg"
    source = _jpeg_bytes()
    image.write_bytes(source)
    assert private_hospital_root(root)
    if os.name == "nt":
        subprocess.run(
            ["icacls.exe", str(image), "/grant", "*S-1-1-0:R"],
            check=True, capture_output=True,
        )
    else:
        root.chmod(0o755)
    assert not private_hospital_root(root)
    assert image.read_bytes() == source


def test_windows_privacy_probe_errors_and_invalid_json_fail_closed(tmp_path, monkeypatch):
    import pytest
    from dr_support.services import filesystem_privacy

    if os.name != "nt":
        pytest.skip("Windows ACL probe behavior")
    root = tmp_path / "private"
    root.mkdir()
    for output in ('{}', '[]', 'null', '{"private":false}', 'not-json', '{"private":1}'):
        monkeypatch.setattr(
            filesystem_privacy.subprocess, "run",
            lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, output, ""),
        )
        assert not filesystem_privacy.private_hospital_root(root)
    def unavailable(*args, **kwargs):
        raise subprocess.TimeoutExpired("privacy-probe", 30)
    monkeypatch.setattr(filesystem_privacy.subprocess, "run", unavailable)
    assert not filesystem_privacy.private_hospital_root(root)


def test_configured_root_rejects_redirected_ancestor(tmp_path, monkeypatch):
    import pytest
    from dr_support.services.source_policy import authorized_hospital_roots

    real = tmp_path / "real"
    real.mkdir()
    nested = real / "nested"
    nested.mkdir()
    redirect = tmp_path / "redirect"
    if os.name == "nt":
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(redirect), str(real)],
            capture_output=True,
        )
        if result.returncode:
            pytest.skip("junction creation unavailable")
    else:
        redirect.symlink_to(real, target_is_directory=True)
    try:
        monkeypatch.setenv("DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOT", str(redirect / "nested"))
        monkeypatch.setenv("DR_SUPPORT_AUTHORIZED_HOSPITAL_MODALITY", "UWF")
        monkeypatch.delenv("DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOTS", raising=False)
        assert authorized_hospital_roots() == ()
    finally:
        if os.name == "nt":
            redirect.rmdir()
        else:
            redirect.unlink()


_WINDOWS_FIXTURE_READER_SID = "S-1-5-21-111111111-222222222-333333333-9999"


def _grant_synthetic_reader(root, sid, rights="RX"):
    rights_name = {"RX": "ReadAndExecute", "W": "Write", "D": "Delete",
                   "WDAC": "ChangePermissions", "WO": "TakeOwnership"}[rights]
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
         "$env:PSModulePath=Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/Modules'; "
         "$ErrorActionPreference='Stop'; "
         "$acl=[IO.Directory]::GetAccessControl($env:DR_TEST_PRIVATE_ROOT, "
         "[Security.AccessControl.AccessControlSections]::Access); "
         "$sid=[Security.Principal.SecurityIdentifier]::new($env:DR_TEST_READER_SID); "
         "$rule=[Security.AccessControl.FileSystemAccessRule]::new($sid, "
         "[Security.AccessControl.FileSystemRights]$env:DR_TEST_READER_RIGHTS, "
         "'ContainerInherit,ObjectInherit','None','Allow'); "
         "$acl.AddAccessRule($rule); [IO.Directory]::SetAccessControl($env:DR_TEST_PRIVATE_ROOT,$acl)"],
        capture_output=True, check=True,
        env={**os.environ, "DR_TEST_PRIVATE_ROOT": str(root),
             "DR_TEST_READER_SID": sid, "DR_TEST_READER_RIGHTS": rights_name},
    )


def test_windows_managed_reader_requires_explicit_sid_and_exact_root(tmp_path, monkeypatch):
    import pytest
    if os.name != "nt":
        pytest.skip("Real Windows ACL permissions")
    from dr_support.services.source_policy import HOSPITAL_WINDOWS_READERS_ENV

    uwf, cfp = tmp_path / "uwf", tmp_path / "cfp"
    for root in (uwf, cfp):
        root.mkdir()
        _private_test_root(root)
        (root / "synthetic.jpg").write_bytes(_jpeg_bytes())
        _grant_synthetic_reader(root, _WINDOWS_FIXTURE_READER_SID)
    monkeypatch.setenv("DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOTS", json.dumps({"UWF": str(uwf), "CFP": str(cfp)}))
    monkeypatch.setenv("DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL", "1")
    monkeypatch.setenv("DR_SUPPORT_HOSPITAL_SCOPE", "PRIVATE_PROJECT_EVALUATION")
    monkeypatch.delenv(HOSPITAL_WINDOWS_READERS_ENV, raising=False)
    assert not hospital_ingest_enabled(uwf)
    monkeypatch.setenv(HOSPITAL_WINDOWS_READERS_ENV, json.dumps({str(uwf): [_WINDOWS_FIXTURE_READER_SID]}))
    assert hospital_ingest_enabled(uwf)
    assert not hospital_ingest_enabled(cfp)  # Same principal does not authorize another root.
    monkeypatch.setenv(HOSPITAL_WINDOWS_READERS_ENV, json.dumps({
        str(uwf): [_WINDOWS_FIXTURE_READER_SID], str(cfp): [_WINDOWS_FIXTURE_READER_SID],
    }))
    assert hospital_ingest_enabled(cfp)
    assert not hospital_ingest_enabled(uwf / "synthetic.jpg")
    monkeypatch.setenv("DR_SUPPORT_HOSPITAL_SCOPE", "UNAPPROVED")
    assert not hospital_ingest_enabled(uwf)


def test_windows_reader_rejects_extra_rights_and_unrelated_principals(tmp_path, monkeypatch):
    import pytest
    if os.name != "nt":
        pytest.skip("Real Windows ACL permissions")
    from dr_support.services.source_policy import HOSPITAL_WINDOWS_READERS_ENV

    for index, rights in enumerate(("W", "D", "WDAC", "WO")):
        root = tmp_path / f"private-{index}"
        _configure_hospital(monkeypatch, root)
        (root / "synthetic.jpg").write_bytes(_jpeg_bytes())
        monkeypatch.setenv("DR_SUPPORT_HOSPITAL_SCOPE", "PRIVATE_PROJECT_EVALUATION")
        monkeypatch.setenv(HOSPITAL_WINDOWS_READERS_ENV, json.dumps({str(root): [_WINDOWS_FIXTURE_READER_SID]}))
        _grant_synthetic_reader(root, _WINDOWS_FIXTURE_READER_SID)
        assert hospital_ingest_enabled(root)
        _grant_synthetic_reader(root, _WINDOWS_FIXTURE_READER_SID, rights)
        assert not hospital_ingest_enabled(root), rights

    root = tmp_path / "unrelated-principal"
    _configure_hospital(monkeypatch, root)
    monkeypatch.setenv(HOSPITAL_WINDOWS_READERS_ENV, json.dumps({str(root): [_WINDOWS_FIXTURE_READER_SID]}))
    _grant_synthetic_reader(root, "S-1-5-21-111111111-222222222-333333333-8888")
    assert not hospital_ingest_enabled(root)


def test_windows_reader_config_rejects_broad_sids_unapproved_roots_and_names(tmp_path, monkeypatch):
    import pytest
    if os.name != "nt":
        pytest.skip("Windows-only operator config")
    from dr_support.services.source_policy import HOSPITAL_WINDOWS_READERS_ENV

    root = tmp_path / "private"
    _configure_hospital(monkeypatch, root)
    unrelated = tmp_path / "unapproved"
    unrelated.mkdir()
    monkeypatch.setenv("DR_SUPPORT_HOSPITAL_SCOPE", "PRIVATE_PROJECT_EVALUATION")
    for value in ("S-1-1-0", "S-1-5-11", "S-1-5-32-545", "CodexSandboxUsers", "S-1-5-21-bad"):
        monkeypatch.setenv(HOSPITAL_WINDOWS_READERS_ENV, json.dumps({str(root): [value]}))
        assert not hospital_ingest_enabled(root)
    for payload in ([], {}, {str(unrelated): [_WINDOWS_FIXTURE_READER_SID]}, {str(root): []}):
        monkeypatch.setenv(HOSPITAL_WINDOWS_READERS_ENV, json.dumps(payload))
        assert not hospital_ingest_enabled(root)
    monkeypatch.setenv(HOSPITAL_WINDOWS_READERS_ENV, "not-json")
    assert not hospital_ingest_enabled(root)


def test_posix_private_modes_are_not_relaxed_by_windows_reader_config(tmp_path, monkeypatch):
    import pytest
    if os.name == "nt":
        pytest.skip("POSIX privacy regression")
    from dr_support.services.source_policy import HOSPITAL_WINDOWS_READERS_ENV

    root = tmp_path / "private"
    _configure_hospital(monkeypatch, root)
    monkeypatch.setenv(HOSPITAL_WINDOWS_READERS_ENV, json.dumps({str(root): [_WINDOWS_FIXTURE_READER_SID]}))
    assert hospital_ingest_enabled(root)
    root.chmod(0o755)
    assert not hospital_ingest_enabled(root)
