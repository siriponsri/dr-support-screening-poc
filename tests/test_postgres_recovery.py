"""Synthetic/fake-process recovery controls; never a live restore receipt."""
from __future__ import annotations

import json
import io
import os
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from dr_support.persistence import PostgresDatabase, PostgresSettings
from dr_support.persistence import recovery
from dr_support.persistence.migrations import MIGRATIONS
from dr_support.persistence.cases import PostgresCaseStore
from dr_support.images import synthetic_image
from dr_support.services.admission import scan_input_folder
from dr_support.services import admission as hospital_admission
from dr_support.services import source_policy


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class Connection:
    def __init__(self, state):
        self.state = state

    @contextmanager
    def transaction(self):
        yield self

    def close(self):
        pass

    def execute(self, query, values=None):
        text = query if isinstance(query, str) else query.as_string(None)
        self.state.queries.append((text, values))
        if text.startswith("SET TRANSACTION"):
            return Result([])
        if text.startswith("SELECT current_database(),"):
            return Result([(self.state.name, "127.0.0.1", 5432)])
        if text == "SELECT current_database()":
            return Result([(self.state.name,)])
        if "AS recovery_unqualified_guard" in text:
            return Result([(1,)] if getattr(self.state, "unqualified_guard", False) else [])
        if "FROM pg_namespace" in text:
            return Result([("occupied",)] if self.state.occupied else [])
        if "schema_migrations ORDER" in text:
            return Result(self.state.migrations)
        if text == "SELECT pg_export_snapshot()":
            return Result([("synthetic-snapshot-1",)])
        if "SELECT workspace_id, revision, input_folder, output_folder" in text:
            return Result(self.state.workspaces)
        if "SELECT workspace_id, case_id, revision, payload" in text:
            return Result(self.state.cases)
        if text.startswith("UPDATE "):
            incoming, outgoing, workspace_id = values
            self.state.workspaces = [
                (row[0], row[1], incoming, outgoing) if row[0] == workspace_id else row
                for row in self.state.workspaces
            ]
            return Result([])
        raise AssertionError(f"Unexpected SQL in fake: {text}")


def database(name, image_root):
    image_hash = recovery._file_hash(image_root / "synthetic.png")
    reference = "WORKSPACE_INPUT/synthetic.png"
    payload = {"image_id": image_hash, "revision": 3,
               "admission": {"source_sha256": image_hash, "source_origin": "WORKSPACE",
                             "source_reference": reference, "filename": "synthetic.png",
                             "integrity": {"aliases": [{"filename": "synthetic.png", "source_reference": reference}]}},
               "global": {"model_id": "synthetic-only", "grade": 2},
               "reviewed_grade": 1, "review_history": [{"reviewer": "Synthetic reviewer"}],
               "human_annotations": [], "events": [{"action": "SYNTHETIC"}]}
    state = SimpleNamespace(name=name, occupied=False, queries=[],
                            migrations=[(m.version, m.name, m.checksum) for m in MIGRATIONS],
                            workspaces=[("synthetic_workspace", 2, str(image_root), str(image_root / "old-output"))],
                            cases=[("synthetic_workspace", image_hash, 3, payload)])
    db = PostgresDatabase(PostgresSettings(
        dsn=f"host=127.0.0.1 dbname={name} user=synthetic_user password=synthetic_password",
        schema="dr_recovery"), connector=lambda *args, **kwargs: Connection(state))
    return db, state


@pytest.fixture
def rig(tmp_path, monkeypatch):
    for key in list(os.environ):
        if (key in {"DR_SUPPORT_DATABASE_URL", "DR_DEMO_FOLDER", "DR_SUPPORT_WORKSPACE_ID",
                    "DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL"}
                or key.startswith(("DR_SUPPORT_AUTHORIZED_HOSPITAL", "DR_SUPPORT_HOSPITAL_"))):
            monkeypatch.delenv(key)
    images = tmp_path / "source"
    images.mkdir()
    (images / "synthetic.png").write_bytes(synthetic_image().data)
    db, state = database("source_test", images)
    commands = []

    def runner(command, **kwargs):
        commands.append((command, kwargs))
        kwargs["stdout"].write(b"PGDMPsynthetic custom archive")
        return SimpleNamespace(returncode=0)

    return SimpleNamespace(root=tmp_path, images=images, db=db, state=state,
                           commands=commands, runner=runner, bundle=tmp_path / "backup")


def make_bundle(rig):
    result = recovery.backup(rig.db, image_root=rig.images, destination=rig.bundle,
                             release="bbae4b3", apply=True, runner=rig.runner)
    assert result["status"] == "BACKUP_VERIFIED"
    rig.pin = result["manifest_sha256"]
    return rig.bundle


def resign_manifest(bundle, change):
    manifest = json.loads((bundle / "manifest.json").read_text())
    change(manifest)
    (bundle / "manifest.json").write_bytes(recovery._json_bytes(manifest))
    receipt = json.loads((bundle / "receipt.json").read_text())
    receipt["manifest_sha256"] = recovery._digest(manifest)
    (bundle / "receipt.json").write_bytes(recovery._json_bytes(receipt))


def test_backup_plan_is_read_only_and_does_not_spawn_or_create_output(rig):
    result = recovery.backup(rig.db, image_root=rig.images, destination=rig.bundle,
                             release="bbae4b3", runner=rig.runner)
    assert result["status"] == "PLAN_ONLY"
    assert (result["case_count"], result["image_count"]) == (1, 1)
    assert not rig.bundle.exists()
    assert not rig.commands
    assert all(text.startswith(("SELECT", "SET TRANSACTION")) for text, _ in rig.state.queries)
    assert any("REPEATABLE READ READ ONLY" in text for text, _ in rig.state.queries)


def test_custom_backup_keeps_exact_originals_snapshot_and_secrets_out_of_argv(rig):
    before = (rig.images / "synthetic.png").read_bytes()
    bundle = make_bundle(rig)
    manifest = recovery.verify_bundle(bundle)
    assert manifest["workspaces"][0]["input_relative"] == "."
    assert manifest["cases"][0]["revision"] == 3
    assert rig.pin == recovery._file_hash(bundle / "manifest.json")
    assert manifest["cases"][0]["image_paths"] == ["synthetic.png"]
    assert (bundle / "originals/synthetic.png").read_bytes() == before
    assert (rig.images / "synthetic.png").read_bytes() == before
    command, kwargs = rig.commands[0]
    assert "--format=custom" in command
    assert "--snapshot=synthetic-snapshot-1" in command
    assert "synthetic_password" not in str(command)
    assert kwargs["env"]["PGPASSWORD"] == "synthetic_password"
    assert "synthetic_password" not in (bundle / "manifest.json").read_text()
    assert not any(text.startswith(("UPDATE", "DELETE", "DROP", "CREATE")) for text, _ in rig.state.queries)


@pytest.mark.parametrize("layout", ["other_workspace", "nested_only", "missing_input"])
def test_global_hash_cannot_substitute_for_workspace_scan_visible_source(rig, layout):
    workspace = rig.images / "workspace-a"
    workspace.mkdir()
    if layout == "missing_input":
        selected_input = None
    else:
        selected_input = str(workspace)
        image_parent = (rig.images / "workspace-b" if layout == "other_workspace" else workspace / "nested")
        image_parent.mkdir()
        (rig.images / "synthetic.png").rename(image_parent / "synthetic.png")
    row = rig.state.workspaces[0]
    rig.state.workspaces[0] = (row[0], row[1], selected_input, row[3])
    if selected_input:
        assert rig.state.cases[0][1] not in scan_input_folder(selected_input).images
    with pytest.raises(recovery.RecoveryError):
        recovery.backup(rig.db, image_root=rig.images, destination=rig.bundle,
                        release="2dc06c3", apply=True, runner=rig.runner)
    assert not rig.commands
    assert not rig.bundle.exists()


def test_valid_per_workspace_mapping_uses_real_scanner_and_preserves_references(rig):
    workspace = rig.images / "workspace-a"
    workspace.mkdir()
    (workspace / "synthetic.png").write_bytes((rig.images / "synthetic.png").read_bytes())
    row = rig.state.workspaces[0]
    rig.state.workspaces[0] = (row[0], row[1], str(workspace), row[3])
    before = json.loads(json.dumps(rig.state.cases[0][3]))
    bundle = make_bundle(rig)
    manifest = recovery.verify_bundle(bundle, expected_manifest_sha256=rig.pin)
    assert manifest["cases"][0]["image_paths"] == ["workspace-a/synthetic.png"]
    assert manifest["cases"][0]["source_reference"] == "WORKSPACE_INPUT/synthetic.png"
    assert rig.state.cases[0][3] == before
    copied_scan = scan_input_folder(bundle / "originals/workspace-a")
    assert copied_scan.images[rig.state.cases[0][1]].sha256 == manifest["cases"][0]["source_sha256"]


@pytest.mark.parametrize("origin,reference", [
    ("HOSPITAL_AUTHORIZED", "HOSPITAL_AUTHORIZED/CASE-0001"),
    ("PUBLIC", "DR-DEMO/synthetic.png"), ("SYNTHETIC", "Generated workflow fixture"),
    ("WORKSPACE", "RUNTIME/synthetic.png"),
])
def test_unqualified_hospital_demo_and_runtime_cases_are_explicitly_blocked(rig, origin, reference):
    admission = rig.state.cases[0][3]["admission"]
    admission.update(source_origin=origin, source_reference=reference)
    admission["integrity"]["aliases"] = []
    with pytest.raises(recovery.RecoveryError):
        recovery.backup(rig.db, image_root=rig.images, destination=rig.bundle,
                        release="2dc06c3", apply=True, runner=rig.runner)
    assert not rig.bundle.exists()


def test_hash_matched_but_undecodable_image_is_not_recovery_visible(rig):
    path = rig.images / "synthetic.png"
    path.write_bytes(b"invalid synthetic image, not a fabricated inference")
    image_hash = recovery._file_hash(path)
    old = rig.state.cases[0]
    payload = old[3]
    payload["image_id"] = image_hash
    payload["admission"]["source_sha256"] = image_hash
    rig.state.cases[0] = (old[0], image_hash, old[2], payload)
    assert image_hash not in scan_input_folder(rig.images).images
    with pytest.raises(recovery.RecoveryError, match="cannot be reopened"):
        recovery.backup(rig.db, image_root=rig.images, destination=rig.bundle,
                        release="2dc06c3", apply=True, runner=rig.runner)
    assert not rig.bundle.exists()


@pytest.mark.parametrize("fault", ["source_hash", "migration", "missing_image", "bad_revision"])
def test_backup_refuses_inconsistent_source_before_creating_files(rig, fault):
    if fault == "source_hash":
        rig.state.cases[0][3]["admission"]["source_sha256"] = "f" * 64
    elif fault == "migration":
        rig.state.migrations[-1] = (4, "changed", "f" * 64)
    elif fault == "missing_image":
        rig.state.cases[0][3]["admission"] = {}
    else:
        rig.state.cases[0][3]["revision"] = 2
    with pytest.raises(recovery.RecoveryError):
        recovery.backup(rig.db, image_root=rig.images, destination=rig.bundle,
                        release="bbae4b3", apply=True, runner=rig.runner)
    assert not rig.bundle.exists()
    assert not rig.commands


def test_backup_refuses_collision_and_overlap_without_overwriting(rig):
    rig.bundle.mkdir()
    marker = rig.bundle / "owner.txt"
    marker.write_text("preserve")
    with pytest.raises(recovery.RecoveryError, match="already exists"):
        recovery.backup(rig.db, image_root=rig.images, destination=rig.bundle, release="bbae4b3")
    assert marker.read_text() == "preserve"
    with pytest.raises(recovery.RecoveryError, match="overlap"):
        recovery.backup(rig.db, image_root=rig.images, destination=rig.images / "nested", release="bbae4b3")


def test_dump_failure_retains_partial_files_and_hides_secret_stderr(rig):
    def failed(command, **kwargs):
        kwargs["stdout"].write(b"PGDMPpartial")
        return SimpleNamespace(returncode=1, stderr=b"synthetic_password")

    with pytest.raises(recovery.RecoveryError) as error:
        recovery.backup(rig.db, image_root=rig.images, destination=rig.bundle,
                        release="bbae4b3", apply=True, runner=failed)
    assert "synthetic_password" not in str(error.value)
    assert (rig.bundle / "database.dump").read_bytes() == b"PGDMPpartial"
    assert not (rig.bundle / "receipt.json").exists()


def test_dump_timeout_is_not_retried_and_partial_output_is_retained(rig):
    calls = []

    def timed_out(command, **kwargs):
        calls.append(command)
        kwargs["stdout"].write(b"PGDMPpartial")
        raise subprocess.TimeoutExpired(command, timeout=1800, stderr=b"synthetic_password")

    with pytest.raises(recovery.RecoveryError) as error:
        recovery.backup(rig.db, image_root=rig.images, destination=rig.bundle,
                        release="bbae4b3", apply=True, runner=timed_out)
    assert len(calls) == 1
    assert "synthetic_password" not in str(error.value)
    assert (rig.bundle / "database.dump").exists()
    assert not (rig.bundle / "receipt.json").exists()


def test_source_change_during_copy_blocks_completion_and_retains_partial(rig):
    def changed(command, **kwargs):
        result = rig.runner(command, **kwargs)
        (rig.images / "synthetic.png").write_bytes(b"changed synthetic bytes")
        return result

    with pytest.raises(recovery.RecoveryError, match="changed"):
        recovery.backup(rig.db, image_root=rig.images, destination=rig.bundle,
                        release="bbae4b3", apply=True, runner=changed)
    assert (rig.bundle / "database.dump").exists()
    assert not (rig.bundle / "receipt.json").exists()


@pytest.mark.parametrize("fault", ["image", "dump", "receipt", "traversal", "migration", "missing_hash",
                                   "duplicate_workspace", "missing_case_workspace", "missing_mapping"])
def test_offline_verification_rejects_corrupt_or_incomplete_bundle(rig, fault):
    bundle = make_bundle(rig)
    if fault in {"image", "dump"}:
        path = bundle / ("database.dump" if fault == "dump" else "originals/synthetic.png")
        path.write_bytes(b"corrupt synthetic bytes")
    elif fault == "receipt":
        (bundle / "receipt.json").write_text("{}")
    elif fault == "traversal":
        resign_manifest(bundle, lambda m: m["images"][0].update(path="../outside.png"))
    elif fault == "migration":
        resign_manifest(bundle, lambda m: m["migrations"][0].update(checksum="f" * 64))
    elif fault == "missing_hash":
        resign_manifest(bundle, lambda m: m["cases"][0].update(source_sha256="f" * 64))
    elif fault == "duplicate_workspace":
        resign_manifest(bundle, lambda m: m["workspaces"].append(dict(m["workspaces"][0])))
    elif fault == "missing_case_workspace":
        resign_manifest(bundle, lambda m: m["cases"][0].update(workspace_id="missing_synthetic_workspace"))
    else:
        resign_manifest(bundle, lambda m: m["workspaces"][0].update(input_relative=None))
    with pytest.raises(recovery.RecoveryError):
        recovery.verify_bundle(bundle)


def restore_args(rig):
    return dict(bundle=rig.bundle, expected_database="restore_test",
                expected_manifest_sha256=rig.pin,
                image_destination=rig.root / "restored-images",
                output_destination=rig.root / "restored-outputs")


@pytest.mark.parametrize("fault", ["same_source", "wrong_name", "not_test", "occupied", "wrong_schema"])
def test_restore_refuses_source_mismatched_or_occupied_target_without_writes(rig, fault):
    make_bundle(rig)
    name = "source_test" if fault == "same_source" else "restore_test"
    if fault == "not_test":
        name = "hospital_live"
    target, state = database(name, rig.images)
    arguments = restore_args(rig)
    if fault in {"same_source", "not_test"}:
        arguments["expected_database"] = name
    if fault == "wrong_name":
        arguments["expected_database"] = "another_test"
    if fault == "occupied":
        state.occupied = True
    if fault == "wrong_schema":
        target.settings = PostgresSettings(dsn=target.settings.dsn, schema="wrong_schema")
    with pytest.raises(recovery.RecoveryError):
        recovery.restore(target, **arguments, apply=True, target_quiesced=True)
    assert not arguments["image_destination"].exists()
    assert not arguments["output_destination"].exists()
    assert not any(text.startswith("UPDATE") for text, _ in state.queries)


def test_restore_plan_and_quiescence_gate_never_create_files(rig):
    make_bundle(rig)
    target, _ = database("restore_test", rig.images)
    arguments = restore_args(rig)
    assert recovery.restore(target, **arguments)["status"] == "PLAN_ONLY"
    with pytest.raises(recovery.RecoveryError, match="concurrent writers"):
        recovery.restore(target, **arguments, apply=True)
    assert not arguments["image_destination"].exists()


def test_restore_requires_independent_pin_before_target_inspection_or_writes(rig):
    make_bundle(rig)
    target, state = database("restore_test", rig.images)
    arguments = restore_args(rig)
    arguments.pop("expected_manifest_sha256")
    with pytest.raises(recovery.RecoveryError, match="retained independently"):
        recovery.restore(target, **arguments, apply=True, target_quiesced=True)
    assert not state.queries
    assert not arguments["image_destination"].exists()


def test_self_consistent_foreign_archive_cannot_replace_independently_pinned_backup(rig):
    bundle = make_bundle(rig)
    trusted_pin = rig.pin  # Captured from backup result before supplied bytes change.
    (bundle / "database.dump").write_bytes(b"PGDMPuntrusted self-consistent synthetic archive")
    resign_manifest(bundle, lambda m: m.update(dump_sha256=recovery._file_hash(bundle / "database.dump")))
    # Internal integrity checks alone cannot establish origin/trust.
    assert recovery.verify_bundle(bundle)["dump_sha256"] == recovery._file_hash(bundle / "database.dump")
    target, state = database("restore_test", rig.images)
    assert restore_args(rig)["expected_manifest_sha256"] == trusted_pin
    with pytest.raises(recovery.RecoveryError, match="independently retained trusted pin"):
        recovery.restore(target, **restore_args(rig), apply=True, target_quiesced=True,
                         runner=lambda *a, **kw: pytest.fail("Foreign archive must not execute"))
    assert not state.queries
    assert not (rig.root / "restored-images").exists()


def test_independent_pin_binds_exact_manifest_bytes_not_only_parsed_self_hash(rig):
    bundle = make_bundle(rig)
    manifest = json.loads((bundle / "manifest.json").read_text())
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    assert recovery._digest(manifest) == rig.pin
    assert recovery._file_hash(bundle / "manifest.json") != rig.pin
    target, state = database("restore_test", rig.images)
    with pytest.raises(recovery.RecoveryError, match="independently retained trusted pin"):
        recovery.restore(target, **restore_args(rig), apply=True, target_quiesced=True)
    assert not state.queries


@pytest.mark.parametrize("key,value", [
    ("DR_DEMO_FOLDER", "synthetic-source-override"),
    ("DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOT", "synthetic-source-override"),
    ("DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOTS", '{"UWF":"synthetic-source-override"}'),
    ("DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL", "1"),
    ("DR_SUPPORT_DATABASE_URL", "dbname=source_test password=synthetic_private"),
    ("DR_SUPPORT_WORKSPACE_ID", "source_workspace"),
])
def test_restore_rejects_inherited_source_selectors_without_clearing_them(rig, monkeypatch, key, value):
    make_bundle(rig)
    monkeypatch.setenv(key, value)
    target, state = database("restore_test", rig.images)
    with pytest.raises(recovery.RecoveryError, match="isolated target environment") as error:
        recovery.restore(target, **restore_args(rig), apply=True, target_quiesced=True)
    assert value not in str(error.value)
    assert os.environ[key] == value
    assert not state.queries
    assert not (rig.root / "restored-images").exists()


def test_restore_preserves_case_history_and_bytes_and_remaps_only_target_paths(rig):
    make_bundle(rig)
    target, state = database("restore_test", rig.images)
    calls = []

    def restored(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0)

    args = restore_args(rig)
    result = recovery.restore(target, **args, apply=True, target_quiesced=True, runner=restored)
    assert result["status"] == "RESTORE_DATA_VERIFIED"
    assert result["application_reopen_export"] == "NOT_RUN"
    assert (args["image_destination"] / "synthetic.png").read_bytes() == (rig.images / "synthetic.png").read_bytes()
    assert state.cases == rig.state.cases
    assert state.workspaces[0][2] == str(args["image_destination"])
    assert state.workspaces[0][2] != rig.state.workspaces[0][2]
    assert "--single-transaction" in calls[0]
    assert "--dbname=restore_test" in calls[0]
    assert "--exit-on-error" in calls[0]
    assert calls[0][-1] == str(args["output_destination"] / "restore-database.dump")
    assert calls[0][-1] != str(rig.bundle / "database.dump")
    assert not any(flag in " ".join(calls[0]) for flag in ("--clean", "--create", "synthetic_password"))
    assert len([q for q, _ in state.queries if "SELECT nspname FROM pg_namespace" in q]) == 2
    assert (args["output_destination"] / "recovery-receipt.json").exists()


def test_failed_restore_keeps_copied_images_and_does_not_claim_success(rig):
    make_bundle(rig)
    target, state = database("restore_test", rig.images)
    args = restore_args(rig)
    with pytest.raises(recovery.RecoveryError):
        recovery.restore(target, **args, apply=True, target_quiesced=True,
                         runner=lambda *a, **kw: SimpleNamespace(returncode=1))
    assert (args["image_destination"] / "synthetic.png").exists()
    assert not (args["output_destination"] / "recovery-receipt.json").exists()
    assert not any(q.startswith("UPDATE") for q, _ in state.queries)


def test_restore_rejects_payload_drift_without_writing_success_receipt(rig):
    make_bundle(rig)
    target, state = database("restore_test", rig.images)

    def drifted(command, **kwargs):
        state.cases[0][3]["review_history"].append({"action": "UNEXPECTED_SYNTHETIC_CHANGE"})
        return SimpleNamespace(returncode=0)

    args = restore_args(rig)
    with pytest.raises(recovery.RecoveryError, match="payload hashes differ"):
        recovery.restore(target, **args, apply=True, target_quiesced=True, runner=drifted)
    assert (args["image_destination"] / "synthetic.png").exists()
    assert not (args["output_destination"] / "recovery-receipt.json").exists()


def test_restore_detects_concurrent_target_change_before_db_mutation(rig):
    make_bundle(rig)
    target, state = database("restore_test", rig.images)
    original_execute = Connection.execute
    occupancy_checks = 0

    def concurrent(connection, query, values=None):
        nonlocal occupancy_checks
        text = query if isinstance(query, str) else query.as_string(None)
        if "SELECT nspname FROM pg_namespace" in text:
            occupancy_checks += 1
            if occupancy_checks == 2:
                state.occupied = True
        return original_execute(connection, query, values)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Connection, "execute", concurrent)
        with pytest.raises(recovery.RecoveryError, match="occupied"):
            recovery.restore(target, **restore_args(rig), apply=True, target_quiesced=True,
                             runner=lambda *a, **kw: pytest.fail("Must not run restore"))
    assert occupancy_checks == 2
    assert not any(q.startswith("UPDATE") for q, _ in state.queries)


def test_archive_swap_after_initial_verification_is_blocked_before_restore(rig, monkeypatch):
    make_bundle(rig)
    target, _ = database("restore_test", rig.images)
    original = recovery._empty_target
    checks = 0

    def swap_after_target_check(*args):
        nonlocal checks
        original(*args)
        checks += 1
        if checks == 2:
            (rig.bundle / "database.dump").write_bytes(b"PGDMPswapped synthetic archive")

    monkeypatch.setattr(recovery, "_empty_target", swap_after_target_check)
    with pytest.raises(recovery.RecoveryError, match="archive changed"):
        recovery.restore(target, **restore_args(rig), apply=True, target_quiesced=True,
                         runner=lambda *a, **kw: pytest.fail("Swapped archive must not execute"))
    assert not (rig.root / "restored-outputs/recovery-receipt.json").exists()


def test_restored_acceptance_environment_must_select_target_without_source_roots(rig):
    target, _ = database("restore_test", rig.images)
    clean = {"DR_SUPPORT_DATABASE_URL": target.settings.dsn,
             "DR_SUPPORT_DATABASE_SCHEMA": target.settings.schema,
             "DR_SUPPORT_CASE_STORE": "postgres", "APP_PROFILE": "review", "MODEL_RUNTIME": "remote"}
    assert recovery.validate_restored_app_environment(
        target.settings, expected_database="restore_test", environ=clean)["application_reopen_export"] == "NOT_RUN"
    for override in ({"DR_DEMO_FOLDER": "synthetic-source"},
                     {"DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOTS": "synthetic-source"},
                     {"DR_SUPPORT_DATABASE_URL": rig.db.settings.dsn},
                     {"DR_SUPPORT_CASE_STORE": "sqlite"},
                     {"PGSERVICE": "unapproved_service"},
                     {"PGHOSTADDR": "192.0.2.1"},
                     {"DR_SUPPORT_DATABASE_URL": "dbname=restore_test service=unapproved"},
                     {"DR_SUPPORT_STATE": "synthetic-legacy-state"}):
        with pytest.raises(recovery.RecoveryError):
            recovery.validate_restored_app_environment(
                target.settings, expected_database="restore_test", environ={**clean, **override})
    with pytest.raises(recovery.RecoveryError, match="independently recorded test target"):
        recovery.validate_restored_app_environment(
            rig.db.settings, expected_database="restore_test",
            environ={**clean, "DR_SUPPORT_DATABASE_URL": rig.db.settings.dsn})


def test_recovery_output_inside_any_checkout_is_rejected(rig):
    checkout = rig.root / "other-checkout"
    checkout.mkdir()
    (checkout / ".git").write_text("synthetic worktree marker")
    with pytest.raises(recovery.RecoveryError, match="outside source checkouts"):
        recovery.backup(rig.db, image_root=rig.images, destination=checkout / "private", release="bbae4b3")


@pytest.mark.parametrize("name", ["backup", "restore"])
def test_windows_wrapper_syntax_without_running_it(name):
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell parser is unavailable")
    script = Path(__file__).resolve().parents[1] / f"scripts/windows/release-{name}.ps1"
    command = ("$null=[scriptblock]::Create([IO.File]::ReadAllText('"
               + str(script).replace("'", "''") + "')); exit 0")
    result = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command", command],
                            capture_output=True, text=True, check=False, timeout=20)
    assert result.returncode == 0, result.stderr


def test_cli_offline_verify_requires_no_database_and_sanitizes_failures(rig, monkeypatch, capsys):
    bundle = make_bundle(rig)
    monkeypatch.delenv("DR_SUPPORT_DATABASE_URL", raising=False)
    assert recovery.main(["verify", "--bundle", str(bundle)]) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["live_restore"] == "NOT_RUN"
    assert verified["trust"] == "INTEGRITY_ONLY_NO_ARCHIVE_TRUST"
    assert recovery.main(["verify", "--bundle", str(rig.root / "missing")]) == 2
    result = capsys.readouterr().out
    assert "synthetic_password" not in result
    assert str(rig.root) not in result


def test_windows_wrappers_do_not_start_stop_or_provision_services():
    root = Path(__file__).resolve().parents[1]
    for name in ("backup", "restore"):
        content = (root / f"scripts/windows/release-{name}.ps1").read_text()
        if name == "backup":
            assert "Read-ReleaseDotEnv" in content
        else:
            assert "Read-ReleaseDotEnv" not in content
            assert "--expected-manifest-sha256" in content
        assert "dr_support.persistence.recovery" in content
        assert "--apply" in content
        assert "Ensure-ReleasePostgres" not in content
        assert "Start-Process" not in content
        assert "Stop-Process" not in content


def write_map(path, value):
    path.write_bytes(recovery._json_bytes(value))
    return recovery._file_hash(path)


def clear_hospital_configuration(monkeypatch):
    for key in list(os.environ):
        if ((key.startswith(("DR_SUPPORT_AUTHORIZED_HOSPITAL", "DR_SUPPORT_HOSPITAL_"))
             and key != source_policy.HOSPITAL_LINKAGE_KEY_ENV)
                or key in {"DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL", "DR_SUPPORT_DATABASE_URL", "DR_DEMO_FOLDER"}):
            monkeypatch.delenv(key)


def configure_hospital(monkeypatch, roots):
    clear_hospital_configuration(monkeypatch)
    monkeypatch.setenv(source_policy.HOSPITAL_ROOTS_ENV, json.dumps({row["modality"]: row["path"] for row in roots}))
    monkeypatch.setenv("DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL", "1")
    monkeypatch.setenv("DR_SUPPORT_HOSPITAL_SCOPE", source_policy.PRIVATE_PROJECT_SCOPE)
    readers = recovery._reader_bindings(roots)
    if readers:
        monkeypatch.setenv(source_policy.HOSPITAL_WINDOWS_READERS_ENV, json.dumps(readers))


def hospital_cases(scan):
    return [("synthetic_workspace", case_id, 3,
             {"image_id": case_id, "revision": 3, "admission": json.loads(json.dumps(record)),
              "reviewed_grade": 2, "human_annotations": [{"id": "synthetic-clinician-roi"}],
              "review_history": [{"reviewer": "Synthetic reviewer"}],
              "raw_predictions": [{"id": "synthetic-only-retained"}]})
            for case_id, record in sorted(scan.records.items())]


@pytest.fixture
def hospital_rig(rig, monkeypatch):
    # No ACL subprocess, grants, model, network or live database. The real
    # source-policy and admission scanner run against generated image bytes.
    monkeypatch.setattr(source_policy, "private_hospital_root", lambda *args, **kwargs: True)
    roots = []
    for root_id, modality in (("uwf", "UWF"), ("cfp", "CFP")):
        folder = rig.root / f"source-{root_id}"
        folder.mkdir()
        image = Image.open(io.BytesIO(synthetic_image().data)).copy()
        if root_id == "cfp":
            image.putpixel((0, 0), (40, 50, 60))
        image.save(folder / "PATIENT01_L1.png")
        roots.append({"root_id": root_id, "modality": modality, "path": str(folder), "read_only_sids": []})
    monkeypatch.setenv(source_policy.HOSPITAL_LINKAGE_KEY_ENV, "synthetic-only-existing-key-" * 2)
    configure_hospital(monkeypatch, roots)
    scan = hospital_admission.scan_authorized_hospital_roots()
    assert len(scan.images) == 2
    assert {row["trusted_patient_key"] for row in scan.records.values()} != {None}
    rig.state.cases = hospital_cases(scan)
    # Bootstrap metadata without a usable input folder is allowed only for the
    # independently named hospital workspace; actual roots are server binding.
    rig.state.workspaces[0] = ("synthetic_workspace", 2, None, None)
    _, summaries = recovery._hospital_candidates(roots)
    mapping = {"version": recovery.SOURCE_MAP_VERSION, "approval_id": "synthetic-owner-it-approval",
               "workspace_id": "synthetic_workspace", "scope": source_policy.PRIVATE_PROJECT_SCOPE,
               "backup_destination": str(rig.bundle), "linkage_key_ref": "synthetic-existing-ref",
               "roots": [{**row, "candidate_inventory_sha256": summary["candidate_inventory_sha256"]}
                         for row, summary in zip(roots, summaries, strict=True)]}
    rig.source_map = rig.root / "approved-source-map.json"
    rig.source_pin = write_map(rig.source_map, mapping)
    rig.mapping, rig.hospital_roots, rig.scan = mapping, roots, scan
    return rig


def hospital_backup_args(rig):
    return {"destination": rig.bundle, "release": "02ff0bc",
            "hospital_source_map": rig.source_map, "expected_hospital_source_map_sha256": rig.source_pin}


def make_hospital_bundle(rig):
    result = recovery.backup(rig.db, **hospital_backup_args(rig), apply=True, runner=rig.runner)
    rig.pin = result["manifest_sha256"]
    return result


def hospital_restore_args(rig):
    images, outputs = rig.root / "restored-images", rig.root / "restored-outputs"
    mapping = {"version": recovery.RESTORE_MAP_VERSION, "approval_id": "synthetic-restore-approval",
               "source_map_sha256": rig.source_pin, "expected_manifest_sha256": rig.pin,
               "workspace_id": rig.mapping["workspace_id"], "scope": rig.mapping["scope"],
               "target_database": "restore_test", "bundle_path": str(rig.bundle),
               "image_destination": str(images), "output_destination": str(outputs),
               "linkage_key_ref": rig.mapping["linkage_key_ref"],
               "roots": [{**row, "path": str(images / row["root_id"])} for row in rig.hospital_roots]}
    rig.restore_map = rig.root / "approved-restore-map.json"
    rig.restore_mapping = mapping
    rig.restore_pin = write_map(rig.restore_map, mapping)
    return {"bundle": rig.bundle, "expected_database": "restore_test", "expected_manifest_sha256": rig.pin,
            "image_destination": images, "output_destination": outputs,
            "hospital_source_map": rig.source_map, "expected_hospital_source_map_sha256": rig.source_pin,
            "hospital_restore_map": rig.restore_map, "expected_hospital_restore_map_sha256": rig.restore_pin}


def target_hospital_db(rig):
    target, state = database("restore_test", rig.images)
    state.cases = json.loads(json.dumps(rig.state.cases))
    state.cases = [tuple(row) for row in state.cases]
    state.workspaces = list(rig.state.workspaces)
    return target, state


def test_hospital_v3_exact_scanner_backup_and_isolated_restore_without_original_reads(hospital_rig, monkeypatch):
    rig = hospital_rig
    before = json.loads(json.dumps(rig.state.cases))
    originals = {row["path"]: {path.name: path.read_bytes() for path in Path(row["path"]).iterdir()}
                 for row in rig.hospital_roots}
    result = make_hospital_bundle(rig)
    assert result["snapshot_approved"] is True
    assert rig.pin == recovery._file_hash(rig.bundle / "manifest.json")
    manifest = json.loads((rig.bundle / "manifest.json").read_text())
    assert manifest["version"] == recovery.HOSPITAL_BUNDLE_VERSION
    assert manifest["source_layout"]["source_map_sha256"] == rig.source_pin
    assert [case["source_reference"] for case in manifest["cases"]] == [row[3]["admission"]["source_reference"]
                                                                        for row in rig.state.cases]
    assert all(row["source_reference"].startswith("HOSPITAL_AUTHORIZED/CASE-") for row in manifest["cases"])
    assert "synthetic-only-existing-key" not in (rig.bundle / "manifest.json").read_text()
    arguments = hospital_restore_args(rig)
    target, state = target_hospital_db(rig)
    clear_hospital_configuration(monkeypatch)
    # Deny even filesystem metadata/read access to original roots during
    # restore. Lexical source-map paths remain audit/deny-list metadata only.
    original_lstat, original_open = Path.lstat, Path.open
    source_roots = [Path(row["path"]) for row in rig.hospital_roots]

    def deny_original(path):
        if any(path == root or path.is_relative_to(root) for root in source_roots):
            pytest.fail("Restore attempted to inspect an original source root")

    def guarded_lstat(path, *args, **kwargs):
        deny_original(path)
        return original_lstat(path, *args, **kwargs)

    def guarded_open(path, *args, **kwargs):
        deny_original(path)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", guarded_lstat)
    monkeypatch.setattr(Path, "open", guarded_open)
    calls = []
    restored = recovery.restore(target, **arguments, apply=True, target_quiesced=True,
                                runner=lambda command, **kw: calls.append(command) or SimpleNamespace(returncode=0))
    assert restored["status"] == "RESTORE_DATA_VERIFIED"
    assert restored["application_reopen_export"] == "NOT_RUN"
    assert "--dbname=restore_test" in calls[0]
    assert json.loads(json.dumps(state.cases)) == before
    assert state.workspaces[0][2] == str(arguments["image_destination"])
    assert not list(arguments["image_destination"].glob("*.png"))
    for row in rig.hospital_roots:
        for name, data in originals[row["path"]].items():
            assert (arguments["image_destination"] / row["root_id"] / name).read_bytes() == data
    assert not os.environ.get(source_policy.HOSPITAL_ROOTS_ENV)
    receipt = json.loads((arguments["output_destination"] / "recovery-receipt.json").read_text())
    assert receipt["restore_map_sha256"] == rig.restore_pin
    assert receipt["source_map_sha256"] == rig.source_pin
    assert receipt["workspace_id"] == rig.mapping["workspace_id"]


@pytest.mark.parametrize("fault", ["missing_pin", "wrong_pin", "source_roots", "source_scope", "privacy",
                                   "wrong_workspace", "mixed_workspace", "missing_case", "wrong_key", "no_key"])
def test_hospital_backup_activation_fails_closed_before_dump(hospital_rig, monkeypatch, fault):
    rig = hospital_rig
    args = hospital_backup_args(rig)
    if fault == "missing_pin":
        args["expected_hospital_source_map_sha256"] = None
    elif fault == "wrong_pin":
        args["expected_hospital_source_map_sha256"] = "f" * 64
    elif fault == "source_roots":
        monkeypatch.setenv(source_policy.HOSPITAL_ROOTS_ENV, "{}")
    elif fault == "source_scope":
        monkeypatch.setenv("DR_SUPPORT_HOSPITAL_SCOPE", "UNAPPROVED")
    elif fault == "privacy":
        monkeypatch.setattr(source_policy, "private_hospital_root", lambda *a, **kw: False)
    elif fault == "wrong_workspace":
        rig.mapping["workspace_id"] = "not_the_hospital_workspace"
    elif fault == "mixed_workspace":
        rig.state.workspaces.append(("other", 0, str(rig.images), None))
    elif fault == "missing_case":
        rig.state.cases.pop()
    elif fault in {"wrong_key", "no_key"}:
        if fault == "wrong_key":
            monkeypatch.setenv(source_policy.HOSPITAL_LINKAGE_KEY_ENV, "different-synthetic-key-" * 2)
        else:
            monkeypatch.delenv(source_policy.HOSPITAL_LINKAGE_KEY_ENV)
    if fault == "wrong_workspace":
        args["expected_hospital_source_map_sha256"] = write_map(rig.source_map, rig.mapping)
    with pytest.raises(recovery.RecoveryError):
        recovery.backup(rig.db, **args, apply=True, runner=rig.runner)
    assert not rig.commands
    assert not rig.bundle.exists()


@pytest.mark.parametrize("change", ["added", "deleted", "renamed", "bytes", "unsupported", "decode_failed"])
def test_hospital_complete_candidate_set_cannot_shift_or_renumber(hospital_rig, change):
    rig = hospital_rig
    folder = Path(rig.hospital_roots[0]["path"])
    path = next(folder.iterdir())
    if change == "added":
        (folder / "A_SYNTHETIC_R2.png").write_bytes(path.read_bytes())
    elif change == "deleted":
        path.unlink()  # Synthetic fixture only, never runtime/original data.
    elif change == "renamed":
        path.rename(folder / "B_SYNTHETIC_L2.png")
    elif change == "unsupported":
        (folder / "unexpected.bin").write_bytes(b"synthetic unsupported candidate")
    else:
        path.write_bytes(b"not a decodable image")
        if change == "decode_failed":
            _, summaries = recovery._hospital_candidates(rig.hospital_roots)
            rig.mapping["roots"][0]["candidate_inventory_sha256"] = summaries[0]["candidate_inventory_sha256"]
            rig.source_pin = write_map(rig.source_map, rig.mapping)
    with pytest.raises(recovery.RecoveryError):
        recovery.backup(rig.db, **hospital_backup_args(rig), apply=True, runner=rig.runner)
    assert not rig.commands
    assert not rig.bundle.exists()


def test_hospital_null_snapshot_is_read_only_plan_not_authority(hospital_rig):
    rig = hospital_rig
    for row in rig.mapping["roots"]:
        row["candidate_inventory_sha256"] = None
    rig.source_pin = write_map(rig.source_map, rig.mapping)
    report = recovery.backup(rig.db, **hospital_backup_args(rig), runner=rig.runner)
    assert report["status"] == "PLAN_ONLY"
    assert report["snapshot_approved"] is False
    assert all(recovery._HASH.fullmatch(row["candidate_inventory_sha256"]) for row in report["hospital_candidate_snapshots"])
    with pytest.raises(recovery.RecoveryError, match="non-null"):
        recovery.backup(rig.db, **hospital_backup_args(rig), apply=True, runner=rig.runner)
    assert not rig.commands
    assert not rig.bundle.exists()


@pytest.mark.parametrize("duplicate", ["same_root", "cross_modality"])
def test_hospital_duplicates_preserve_existing_scanner_alias_and_unknown_semantics(hospital_rig, duplicate):
    rig = hospital_rig
    uwf, cfp = (Path(row["path"]) for row in rig.hospital_roots)
    destination = uwf if duplicate == "same_root" else cfp
    (destination / "A_SYNTHETIC_DUP_R2.png").write_bytes(next(uwf.iterdir()).read_bytes())
    scan = hospital_admission.scan_authorized_hospital_roots()
    rig.state.cases = hospital_cases(scan)
    _, summaries = recovery._hospital_candidates(rig.hospital_roots)
    for row, summary in zip(rig.mapping["roots"], summaries, strict=True):
        row["candidate_inventory_sha256"] = summary["candidate_inventory_sha256"]
    rig.source_pin = write_map(rig.source_map, rig.mapping)
    make_hospital_bundle(rig)
    manifest = recovery.verify_bundle(rig.bundle, hospital_source_map=rig.source_map,
                                      expected_hospital_source_map_sha256=rig.source_pin,
                                      expected_manifest_sha256=rig.pin)
    assert len(manifest["images"]) == 3
    assert len(manifest["cases"]) == 2
    assert manifest["source_layout"]["scanner_identity_projection_sha256"] == recovery._digest(recovery._scanner_projection(scan))
    if duplicate == "cross_modality":
        assert "UNKNOWN" in {case["hospital_admission"]["retinal_modality"] for case in manifest["cases"]}


@pytest.mark.parametrize("fault", ["source_pin", "restore_pin", "manifest_pin", "no_restore_map", "target",
                                   "image_root", "root_order", "original_root", "key", "source_env", "privacy"])
def test_hospital_restore_independent_maps_and_environment_gates_precede_target_queries(hospital_rig, monkeypatch, fault):
    rig = hospital_rig
    make_hospital_bundle(rig)
    args = hospital_restore_args(rig)
    target, state = target_hospital_db(rig)
    clear_hospital_configuration(monkeypatch)
    if fault in {"source_pin", "restore_pin", "manifest_pin"}:
        key = {"source_pin": "expected_hospital_source_map_sha256", "restore_pin": "expected_hospital_restore_map_sha256",
               "manifest_pin": "expected_manifest_sha256"}[fault]
        args[key] = "f" * 64
    elif fault == "no_restore_map":
        args["hospital_restore_map"] = None
    elif fault == "target":
        rig.restore_mapping["target_database"] = "different_test"
    elif fault == "image_root":
        args["image_destination"] = rig.root / "unapproved-images"
    elif fault == "root_order":
        rig.restore_mapping["roots"].reverse()
    elif fault == "original_root":
        rig.restore_mapping["image_destination"] = rig.hospital_roots[0]["path"]
    elif fault == "key":
        monkeypatch.setenv(source_policy.HOSPITAL_LINKAGE_KEY_ENV, "different-synthetic-key-" * 2)
    elif fault == "source_env":
        configure_hospital(monkeypatch, rig.hospital_roots)
    elif fault == "privacy":
        monkeypatch.setattr(source_policy, "private_hospital_root", lambda *a, **kw: False)
    if fault in {"target", "root_order", "original_root"}:
        args["expected_hospital_restore_map_sha256"] = write_map(rig.restore_map, rig.restore_mapping)
    with pytest.raises(recovery.RecoveryError):
        recovery.restore(target, **args, apply=True, target_quiesced=True,
                         runner=lambda *a, **kw: pytest.fail("Gate must run before restore"))
    assert not state.queries
    assert not (rig.root / "restored-images").exists()


def test_hospital_transferred_bundle_requires_explicit_current_bundle_approval(hospital_rig, monkeypatch):
    rig = hospital_rig
    make_hospital_bundle(rig)
    transferred = rig.root / "approved-private-transfer"
    shutil.copytree(rig.bundle, transferred)
    with pytest.raises(recovery.RecoveryError, match="Transferred"):
        recovery.verify_bundle(transferred, expected_manifest_sha256=rig.pin, hospital_source_map=rig.source_map,
                               expected_hospital_source_map_sha256=rig.source_pin)
    rig.bundle = transferred
    args = hospital_restore_args(rig)
    clear_hospital_configuration(monkeypatch)
    target, _ = target_hospital_db(rig)
    assert recovery.restore(target, **args)["status"] == "PLAN_ONLY"


def test_hospital_scoped_binding_restores_process_configuration_after_failure(hospital_rig):
    rig = hospital_rig
    before = dict(os.environ)
    roots = recovery._copy_roots(rig.root / "unavailable-copies", rig.mapping)
    with pytest.raises(recovery.RecoveryError, match="privacy/authorization"):
        with recovery._hospital_binding(roots):
            pytest.fail("Unavailable roots must not activate")
    assert dict(os.environ) == before


def test_hospital_acceptance_environment_requires_exact_restored_process_roots(hospital_rig, monkeypatch):
    rig = hospital_rig
    make_hospital_bundle(rig)
    args = hospital_restore_args(rig)
    target, _ = target_hospital_db(rig)
    clear_hospital_configuration(monkeypatch)
    recovery.restore(target, **args, apply=True, target_quiesced=True,
                     runner=lambda *a, **kw: SimpleNamespace(returncode=0))
    configure_hospital(monkeypatch, rig.restore_mapping["roots"])
    monkeypatch.delenv("DR_SUPPORT_STATE", raising=False)
    monkeypatch.delenv("DR_SUPPORT_WORKSPACE_CATALOG", raising=False)
    environment = {"DR_SUPPORT_DATABASE_URL": target.settings.dsn, "DR_SUPPORT_DATABASE_SCHEMA": target.settings.schema,
                   "DR_SUPPORT_CASE_STORE": "postgres", "APP_PROFILE": "review", "MODEL_RUNTIME": "remote"}
    environment.update({key: value for key, value in os.environ.items()
                        if key.startswith(("DR_SUPPORT_AUTHORIZED_HOSPITAL", "DR_SUPPORT_HOSPITAL_"))
                        or key == "DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL"})
    kwargs = {key: value for key, value in args.items()
              if key not in {"image_destination", "output_destination"}}
    kwargs["workspace_id"] = rig.mapping["workspace_id"]
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    assert recovery.validate_restored_app_environment(target.settings, **kwargs)["status"] == "ENVIRONMENT_VERIFIED"
    app = SimpleNamespace(state=SimpleNamespace(case_store_mode="postgres", workspace_id=rig.mapping["workspace_id"],
                                                store=PostgresCaseStore(target, rig.mapping["workspace_id"])))
    assert recovery.validate_restored_app_selection(app, target.settings, **kwargs)["status"] == "APP_SELECTION_VERIFIED"
    for mismatch in (None, "ws_bootstrap", "another-synthetic-workspace"):
        with pytest.raises(recovery.RecoveryError, match="explicitly select"):
            recovery.validate_restored_app_environment(target.settings, **{**kwargs, "workspace_id": mismatch})
    for mismatch in ("ws_bootstrap", "another-synthetic-workspace"):
        app.state.store = PostgresCaseStore(target, mismatch)
        with pytest.raises(recovery.RecoveryError, match="did not select"):
            recovery.validate_restored_app_selection(app, target.settings, **kwargs)
    app.state.store = PostgresCaseStore(rig.db, rig.mapping["workspace_id"])
    with pytest.raises(recovery.RecoveryError, match="verified restored target"):
        recovery.validate_restored_app_selection(app, target.settings, **kwargs)
    for override in ({source_policy.HOSPITAL_ROOTS_ENV: json.dumps({"UWF": rig.hospital_roots[0]["path"], "CFP": rig.hospital_roots[1]["path"]})},
                     {"DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOT": rig.hospital_roots[0]["path"]},
                     {"REMOTE_MODEL_URL": "http://unapproved.invalid"}, {"CVAT_URL": "https://unapproved.invalid"},
                     {"PGHOST": "unapproved.invalid"}):
        with pytest.MonkeyPatch.context() as changed:
            for key, value in override.items():
                changed.setenv(key, value)
            with pytest.raises(recovery.RecoveryError):
                recovery.validate_restored_app_environment(target.settings, **kwargs)
    # A supplied environment dictionary cannot conceal the process's old roots.
    configure_hospital(monkeypatch, rig.hospital_roots)
    monkeypatch.setenv("DR_SUPPORT_DATABASE_URL", target.settings.dsn)
    with pytest.raises(recovery.RecoveryError):
        recovery.validate_restored_app_environment(target.settings, **kwargs, environ=environment)
    with pytest.raises(recovery.RecoveryError):
        recovery.validate_restored_app_environment(target.settings, **kwargs)


def test_hospital_absent_linkage_state_is_explicit_and_cannot_silently_gain_a_key(hospital_rig, monkeypatch):
    rig = hospital_rig
    monkeypatch.delenv(source_policy.HOSPITAL_LINKAGE_KEY_ENV)
    rig.mapping["linkage_key_ref"] = None
    rig.source_pin = write_map(rig.source_map, rig.mapping)
    rig.state.cases = hospital_cases(hospital_admission.scan_authorized_hospital_roots())
    make_hospital_bundle(rig)
    manifest = recovery.verify_bundle(rig.bundle, hospital_source_map=rig.source_map,
                                      expected_hospital_source_map_sha256=rig.source_pin)
    assert manifest["source_layout"]["linkage"] == {"state": "ABSENT", "key_ref": None, "challenge": None, "response": None}
    monkeypatch.setenv(source_policy.HOSPITAL_LINKAGE_KEY_ENV, "unexpected-synthetic-key-" * 2)
    with pytest.raises(recovery.RecoveryError, match="key absence"):
        recovery.verify_bundle(rig.bundle, hospital_source_map=rig.source_map,
                               expected_hospital_source_map_sha256=rig.source_pin)


@pytest.mark.parametrize("fault", ["inner_hash", "inner_reference", "inner_alias", "trusted_linkage"])
def test_hospital_stored_admission_cannot_detach_from_case_or_scanner_identity(hospital_rig, fault):
    rig = hospital_rig
    record = rig.state.cases[0][3]["admission"]
    if fault == "inner_hash":
        record["image_id"] = "f" * 64
    elif fault == "inner_reference":
        record["source_reference"] = "HOSPITAL_AUTHORIZED/CASE-9999"
    elif fault == "inner_alias":
        record["integrity"]["aliases"] = []
    else:
        record["trusted_patient_key"] = "HOSPITAL-SYNTHETIC-OTHER"
    with pytest.raises(recovery.RecoveryError, match="references or trusted linkage"):
        recovery.backup(rig.db, **hospital_backup_args(rig), apply=True, runner=rig.runner)
    assert not rig.commands


def test_hospital_manual_modality_decision_survives_without_retyping_raw_scanner(hospital_rig):
    rig = hospital_rig
    record = rig.state.cases[0][3]["admission"]
    record.update(retinal_modality="CFP", retinal_modality_state="CONFIRMED", retinal_modality_method="MANUAL")
    make_hospital_bundle(rig)
    manifest = recovery.verify_bundle(rig.bundle, expected_manifest_sha256=rig.pin,
                                      hospital_source_map=rig.source_map,
                                      expected_hospital_source_map_sha256=rig.source_pin)
    assert manifest["cases"][0]["hospital_admission"] == record
    assert manifest["source_layout"]["scanner_identity_projection_sha256"] == recovery._digest(recovery._scanner_projection(rig.scan))


@pytest.mark.parametrize("fault", ["map_in_bundle", "duplicate_map_key", "wrong_reader_sid"])
def test_hospital_map_authority_is_external_strict_and_reader_bound(hospital_rig, monkeypatch, fault):
    rig = hospital_rig
    if fault == "map_in_bundle":
        make_hospital_bundle(rig)
        supplied = rig.bundle / "self-approved-map.json"
        supplied.write_bytes(rig.source_map.read_bytes())
        with pytest.raises(recovery.RecoveryError, match="outside the supplied bundle"):
            recovery.verify_bundle(rig.bundle, hospital_source_map=supplied,
                                   expected_hospital_source_map_sha256=rig.source_pin)
        return
    if fault == "duplicate_map_key":
        content = rig.source_map.read_bytes()
        rig.source_map.write_bytes(b'{"approval_id":"untrusted-duplicate",' + content[1:])
        rig.source_pin = recovery._file_hash(rig.source_map)
    else:
        monkeypatch.setenv(source_policy.HOSPITAL_WINDOWS_READERS_ENV,
                           json.dumps({rig.hospital_roots[0]["path"]: ["S-1-5-21-1-2-3-4000"]}))
    with pytest.raises(recovery.RecoveryError):
        recovery.backup(rig.db, **hospital_backup_args(rig), apply=True, runner=rig.runner)
    assert not rig.commands


def test_hospital_private_bundle_gate_runs_before_dump_and_retains_empty_partial(hospital_rig, monkeypatch):
    rig = hospital_rig
    known_roots = {Path(row["path"]) for row in rig.hospital_roots}
    monkeypatch.setattr(source_policy, "private_hospital_root", lambda root, **kwargs: root in known_roots)
    with pytest.raises(recovery.RecoveryError, match="private-storage gate"):
        recovery.backup(rig.db, **hospital_backup_args(rig), apply=True, runner=rig.runner)
    assert rig.bundle.is_dir()
    assert not list(rig.bundle.iterdir())
    assert not rig.commands


def test_hospital_cli_verify_forwards_maps_without_database_or_model_call(hospital_rig, monkeypatch, capsys):
    rig = hospital_rig
    make_hospital_bundle(rig)
    clear_hospital_configuration(monkeypatch)
    assert recovery.main(["verify", "--bundle", str(rig.bundle), "--expected-manifest-sha256", rig.pin,
                          "--hospital-source-map", str(rig.source_map),
                          "--expected-hospital-source-map-sha256", rig.source_pin]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "BUNDLE_VERIFIED"
    assert result["trust"] == "MATCHED_INDEPENDENT_PIN"
    assert result["live_restore"] == "NOT_RUN"


@pytest.mark.parametrize("lane", ["ordinary", "hospital"])
def test_entry_guard_source_is_not_qualified_and_never_starts_dump(rig, hospital_rig, lane):
    selected = hospital_rig if lane == "hospital" else rig
    selected.state.unqualified_guard = True
    args = (hospital_backup_args(selected) if lane == "hospital" else
            {"image_root": selected.images, "destination": selected.bundle, "release": "02ff0bc"})
    with pytest.raises(recovery.RecoveryError, match="M1 guard-aware recovery is NOT_QUALIFIED"):
        recovery.backup(selected.db, **args, apply=True, runner=selected.runner)
    assert not selected.commands
    assert not selected.bundle.exists()


def test_entry_guard_target_is_not_qualified_before_any_restore_write(rig):
    make_bundle(rig)
    target, state = database("restore_test", rig.images)
    state.unqualified_guard = True
    with pytest.raises(recovery.RecoveryError, match="guard-aware recovery"):
        recovery.restore(target, **restore_args(rig), apply=True, target_quiesced=True,
                         runner=lambda *a, **kw: pytest.fail("Guard-aware restore must not run"))
    assert not (rig.root / "restored-images").exists()
    query = next(text for text, _ in state.queries if "AS recovery_unqualified_guard" in text)
    assert "p.pronamespace<>c.relnamespace" in query
    assert "m1_entry_fence" in query and "entry_fence" in query


def test_entry_guard_found_after_restore_cannot_receive_success_receipt(rig):
    make_bundle(rig)
    target, state = database("restore_test", rig.images)

    def restored_with_unqualified_guard(*args, **kwargs):
        state.unqualified_guard = True
        return SimpleNamespace(returncode=0)

    with pytest.raises(recovery.RecoveryError, match="guard-aware recovery"):
        recovery.restore(target, **restore_args(rig), apply=True, target_quiesced=True,
                         runner=restored_with_unqualified_guard)
    assert not (rig.root / "restored-outputs/recovery-receipt.json").exists()
