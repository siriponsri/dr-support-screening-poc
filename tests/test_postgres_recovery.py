"""Synthetic/fake-process recovery controls; never a live restore receipt."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from dr_support.persistence import PostgresDatabase, PostgresSettings
from dr_support.persistence import recovery
from dr_support.persistence.migrations import MIGRATIONS
from dr_support.images import synthetic_image
from dr_support.services.admission import scan_input_folder


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
    assert "--exit-on-error" in calls[0]
    assert calls[0][-1] == str(args["output_destination"] / "restore-database.dump")
    assert calls[0][-1] != str(rig.bundle / "database.dump")
    assert not any(flag in " ".join(calls[0]) for flag in ("--clean", "--create", "synthetic_password"))
    assert len([q for q, _ in state.queries if "FROM pg_namespace" in q]) == 2
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
        if "FROM pg_namespace" in text:
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
