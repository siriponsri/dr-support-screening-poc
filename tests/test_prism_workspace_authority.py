"""Synthetic ports and actual temporary OS locks, never a live model/DB."""
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from dr_support.images import synthetic_image
from dr_support.contracts import InferenceRequest
from dr_support.providers.mock import infer_mock
from dr_support.providers.prism_remote_bound import RemoteBoundTransportCandidate
from dr_support.services import prism_workspace_authority as core
from dr_support.services.prism_preview import PreviewSnapshot, PrismPreviewService, preparation_context
from dr_support.services.prism_remote_transport import TransportError, canonical, sha
from dr_support.services.source_mutation_gate import MutationFenced


class Provider:
    def __init__(self, pins):
        self.pins = pins

    def prism_preview_identity(self):
        return {"model_pins": deepcopy(self.pins), "model_version": self.pins["source_revision"],
                "descriptor": {"ready": False, "status": "SYNTHETIC_PORT_NOT_QUALIFIED"}}


class Reader:
    def __init__(self):
        self.status = None
        self.calls = []

    def __call__(self, binding):
        self.calls.append(deepcopy(binding))
        if self.status is None:
            raise TransportError("OLD_JOB_UNAVAILABLE")
        return deepcopy(self.status)


class Database:
    def __init__(self, reader):
        self.binding = None
        self.reader = reader
        self.calls = []
        self.fail_acquire = self.fail_read = self.fail_release = False
        self.authority = None

    def read(self):
        self.calls.append("read")
        if self.fail_read:
            raise OSError("Synthetic database unavailable")
        return deepcopy(self.binding)

    def acquire(self, **kwargs):
        self.calls.append(("acquire", deepcopy(kwargs)))
        assert self.authority.gate.snapshot().state == "FENCED"
        # Durable consumed evidence must precede any permission to grant.
        envelope = self.authority.path.read_bytes()
        assert kwargs["binding"]["plan_sha256"].encode() in envelope
        assert self.binding is None
        self.binding = deepcopy(kwargs["binding"])
        if self.fail_acquire:
            raise TransportError("SYNTHETIC_COMMIT_OUTCOME_UNKNOWN")
        return Permit(self, self.binding)

    def recover(self):
        self.calls.append("recover")
        if self.binding is not None:
            Permit(self, self.binding).release(None)


class Permit:
    def __init__(self, database, binding):
        self.database, self.binding = database, deepcopy(binding)
        self.fence_id = binding["fence_id"]

    def release(self, proof):
        db = self.database
        db.calls.append("release")
        status = db.reader(self.binding)  # Independent trusted DB-port check.
        assert all(status[key] == self.binding[key] for key in core.STATUS_KEYS)
        assert status["forward_started"] or status["terminal"]
        if db.fail_release:
            raise OSError("Synthetic release commit unknown")
        assert db.binding == self.binding
        db.binding = None

    def quarantine(self, reason):
        pass  # The committed synthetic binding is retained, never reset.


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "private_hospital_root", lambda *args, **kwargs: True)
    image = synthetic_image()
    pins = {"model_id": "prism-dr-5fold", "source_revision": "synthetic-revision", "preprocessing": "synthetic-only",
            "config_sha256": "a" * 64, "checkpoint_sha256": {"fold-0": "b" * 64}}
    provider = Provider(pins)
    admission = {"source_origin": "SYNTHETIC", "source_sha256": image.sha256, "retinal_modality": "CFP",
                 "modality_admission": "FUNDUS_ACCEPTED", "quality_state": "NOT_EVALUATED", "integrity_status": "OK"}
    case = {"image_id": image.image_id, "revision": 2, "source_sha256": image.sha256, "image_sha256": image.sha256,
            "admission": deepcopy(admission), "review_history": [{"reviewer": "Synthetic clinical text never journaled"}]}
    context = {"workspace_id": "synthetic-workspace", "image_id": image.image_id, "case": case,
               "workspace": {"workspace_id": "synthetic-workspace", "revision": 7, "name": "Synthetic profile"},
               "admission": admission, "source_sha256": image.sha256, "preparation_context": preparation_context(case),
               "model_pins": pins, "runtime_context": {"database_identity_sha256": "f" * 64, "route_id": "synthetic-private-route"},
               "objects": (object(), provider, object(), object())}
    value = SimpleNamespace(image=image, context=context, reader=Reader(), instances=[], directory=tmp_path / "private-authority")
    value.database = Database(value.reader)

    def read(image_id):
        assert image_id == image.image_id
        return {**deepcopy({key: item for key, item in value.context.items() if key != "objects"}),
                "objects": value.context["objects"]}

    value.read = read

    def create():
        authority = core.WorkspaceAuthority(value.directory, context_reader=value.read,
            database_fence=value.database, authenticated_status_reader=value.reader)
        value.database.authority = authority
        value.instances.append(authority)
        return authority

    value.create = create
    value.authority = create()
    yield value
    for instance in value.instances:
        instance.close()


def snapshot(rig):
    image, context = rig.image, rig.context
    width, height = image.size
    recorded = dict(case_source_sha256=image.sha256, admission_source_sha256=image.sha256, image_recorded_sha256=image.sha256,
                    integrity_status="OK", source_origin="SYNTHETIC", case_revision=context["case"]["revision"],
                    admission_sha256=sha(canonical(context["admission"])))
    return PreviewSnapshot(scope="synthetic-scope", image_id=image.image_id, revision=context["case"]["revision"],
        source=image.data, wire=image.data, wire_media_type=image.media_type, modality="CFP", model_version="synthetic-revision",
        model_pins=deepcopy(context["model_pins"]), preparation_context=context["preparation_context"],
        admission=deepcopy(context["admission"]), recorded_source_identity=recorded,
        transform={"version": "synthetic-v1", "transform_id": "identity", "representation_version": "synthetic-v1",
                   "coordinate_mapping": {"scale_x": 1.0, "scale_y": 1.0}, "original_width": width, "original_height": height,
                   "input_width": width, "input_height": height, "original_to_input": [1, 0, 0, 1, 0, 0]},
        external_fov_status="NOT_APPLICABLE", external_fov_reason_code=None, mask=None, mask_version=None,
        runtime=SimpleNamespace(store=context["objects"][0], provider=context["objects"][1]))


def stage(rig, authority=None):
    authority = authority or rig.authority
    snap = snapshot(rig)
    frozen, _ = PrismPreviewService._freeze(snap)
    keys = ("scope", "image_id", "case_revision", "source_sha256", "wire_sha256", "admission_sha256",
            "recorded_source_identity", "admission", "preparation_context", "model_pins")
    authority.authorize_prepare(rig.image, {key: frozen[key] for key in keys}, original_bytes=rig.image.data)
    authority.authorize_prepare(rig.image)  # Existing transport's second gate.
    return snap, frozen


def plan(rig, authority=None, plan_id="synthetic-plan"):
    authority = authority or rig.authority
    snap, frozen = stage(rig, authority)
    binding = dict(frozen, plan_id=plan_id, generation=0, expires_at="2099-01-01T00:00:00+00:00")
    digest = sha(canonical(binding))
    authority.register_preview_plan(snap, binding, digest)
    status = dict(epoch="old-epoch", job_id="old-job", ticket_id="old-ticket", plan_sha256=digest,
                  pins=deepcopy(binding["model_pins"]), challenge_id="old-challenge", state="WAITING_SOURCE_FENCE",
                  forward_started=False, terminal=False)
    rig.reader.status = deepcopy(status)
    return binding, status


def complete(rig, *, state="COMPLETE", started=True):
    rig.reader.status.update(state=state, forward_started=started, terminal=state != "FORWARD_STARTED")


def acquire_count(rig):
    return sum(isinstance(call, tuple) and call[0] == "acquire" for call in rig.database.calls)


def test_composed_lease_commits_raw_database_fence_before_grant_and_reauthenticates_release(rig):
    binding, status = plan(rig)
    revalidated = []
    lease = rig.authority.acquire(binding, status, lambda: revalidated.append(True))
    assert revalidated == [True] and acquire_count(rig) == 1
    saved = next(call[1] for call in rig.database.calls if isinstance(call, tuple))
    assert saved["case"] == rig.context["case"] and saved["workspace"] == rig.context["workspace"]
    assert rig.database.binding["fence_id"] == lease.fence_id
    assert rig.authority.gate.snapshot().state == "FENCED"
    complete(rig)
    lease.release({"kind": "AUTHENTICATED_STATUS", "status": {"forged": "ignored"}})
    assert rig.database.binding is None and rig.authority.gate.snapshot().state == "OPEN"
    assert len(rig.reader.calls) >= 3  # Core acquire/release and independent DB release.
    data = rig.authority.path.read_bytes()
    assert rig.image.data not in data and b"Synthetic clinical text" not in data
    assert b"Synthetic profile" not in data


@pytest.mark.parametrize("field", ["case", "workspace", "admission", "source_sha256", "preparation_context", "model_pins", "runtime_context"])
def test_full_same_revision_context_drift_never_reaches_database_or_grant(rig, field):
    binding, status = plan(rig)
    revision = rig.context["case"]["revision"]
    if field in {"case", "workspace", "admission", "runtime_context"}:
        rig.context[field]["same_revision_change"] = True
    elif field == "model_pins":
        rig.context[field]["config_sha256"] = "c" * 64
    else:
        rig.context[field] = "c" * 64
    with pytest.raises(TransportError):
        rig.authority.acquire(binding, status, lambda: None)
    assert rig.context["case"]["revision"] == revision
    assert acquire_count(rig) == 0 and rig.database.binding is None


@pytest.mark.parametrize("position", range(4))
def test_actual_store_provider_manager_and_derivative_identity_are_compared_with_is(rig, position):
    binding, status = plan(rig)
    objects = list(rig.context["objects"])
    objects[position] = Provider(rig.context["model_pins"]) if position == 1 else object()
    rig.context["objects"] = tuple(objects)
    with pytest.raises(TransportError, match="OBJECT_CHANGED"):
        rig.authority.acquire(binding, status, lambda: None)
    assert acquire_count(rig) == 0


def test_admission_origin_or_quality_cannot_be_promoted_by_reader_port(rig):
    stage(rig)
    recorded = deepcopy(rig.authority._stage["recorded"])
    for changed in ({"source_origin": "WORKSPACE"}, {"quality_state": "UNGRADABLE"}, {"integrity_status": "SOURCE_CHANGED"}):
        admission = rig.context["admission"]
        original = deepcopy(admission)
        admission.update(changed)
        rig.context["case"]["admission"] = deepcopy(admission)
        with pytest.raises(TransportError, match="RECORDED_WORKSPACE_CONTEXT"):
            rig.authority.authorize_prepare(rig.image, recorded, original_bytes=rig.image.data)
        admission.clear()
        admission.update(original)
        rig.context["case"]["admission"] = deepcopy(original)
    assert acquire_count(rig) == 0


def test_stage_and_registration_refuse_active_or_intervening_writers(rig):
    with rig.authority.gate.writer():
        with pytest.raises(TransportError, match="BUSY"):
            stage(rig)
    snap, frozen = stage(rig)
    binding = dict(frozen, plan_id="writer-race", generation=0, expires_at="2099")
    with rig.authority.gate.writer():
        pass  # Even a failed/no-op writer invalidates a recorded plan.
    with pytest.raises(TransportError):
        rig.authority.register_preview_plan(snap, binding, sha(canonical(binding)))


def test_entry_gate_blocks_thread_writer_before_full_reread_and_revalidate(rig):
    binding, status = plan(rig)
    original = rig.read
    entered, release, leases, errors = Event(), Event(), [], []

    def paused(image_id):
        entered.set()
        assert release.wait(5)
        return original(image_id)

    rig.authority.context_reader = paused
    def run():
        try:
            leases.append(rig.authority.acquire(binding, status, lambda: None))
        except BaseException as error:
            errors.append(error)
    thread = Thread(target=run)
    thread.start()
    try:
        assert entered.wait(5)
        with pytest.raises(MutationFenced):
            with rig.authority.gate.writer():
                pytest.fail("Writer crossed grant-to-entry gate")
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive() and not errors and len(leases) == 1
    complete(rig)
    leases[0].release({"kind": "AUTHENTICATED_STATUS"})


def test_revalidate_full_same_revision_mutation_is_detected_before_db_commit(rig):
    binding, status = plan(rig)
    def changed():
        rig.context["case"]["review_history"].append({"synthetic_change": True})
    with pytest.raises(TransportError, match="CONTEXT_OR_OBJECT_CHANGED"):
        rig.authority.acquire(binding, status, changed)
    assert acquire_count(rig) == 0


def test_unknown_acquire_quarantines_until_matching_old_terminal_and_survives_restart(rig):
    binding, status = plan(rig)
    rig.database.fail_acquire = True
    with pytest.raises(TransportError, match="COMMIT_OUTCOME_UNKNOWN"):
        rig.authority.acquire(binding, status, lambda: None)
    assert rig.authority.gate.snapshot().state == "QUARANTINED"
    rig.authority.close()
    authority = rig.create()
    assert authority.gate.snapshot().state == "QUARANTINED"
    assert authority._permit is not None
    with pytest.raises(TransportError, match="ENTRY_OR_TERMINAL"):
        authority.recover()  # No TTL or WAITING_SOURCE_FENCE release.
    complete(rig, state="ABORTED", started=False)
    rig.reader.status["epoch"] = "new-epoch"
    with pytest.raises(TransportError, match="OLD_JOB"):
        authority.recover()
    rig.reader.status["epoch"] = status["epoch"]
    authority.recover()
    assert authority.gate.snapshot().state == "OPEN" and rig.database.binding is None


def test_local_pending_binding_with_empty_db_still_requires_old_authenticated_proof(rig):
    binding, status = plan(rig)
    rig.authority.acquire(binding, status, lambda: None)
    rig.authority.close()
    rig.database.binding = None  # Simulated known release before local journal completion.
    authority = rig.create()
    with pytest.raises(TransportError):
        authority.recover()
    assert authority.gate.snapshot().state == "QUARANTINED"
    complete(rig)
    authority.recover()
    assert authority.gate.snapshot().state == "OPEN"


def test_consumed_plan_id_and_binding_hash_cannot_replay_after_restart(rig):
    binding, status = plan(rig)
    lease = rig.authority.acquire(binding, status, lambda: None)
    complete(rig)
    lease.release({"kind": "AUTHENTICATED_STATUS"})
    rig.authority.close()
    authority = rig.create()
    with pytest.raises(TransportError, match="PLAN_REPLAY"):
        plan(rig, authority)  # Same ID even if a fresh outer binding were supplied.
    assert acquire_count(rig) == 1


def test_closed_authority_retained_lease_never_calls_db_after_new_owner(rig):
    binding, status = plan(rig)
    lease = rig.authority.acquire(binding, status, lambda: None)
    rig.authority.close()
    replacement = rig.create()
    before = deepcopy(rig.database.calls), replacement.path.read_bytes()
    complete(rig)
    for call in (lambda: lease.release({"kind": "AUTHENTICATED_STATUS"}), lambda: lease.quarantine("unknown")):
        with pytest.raises(TransportError, match="CLOSED"):
            call()
    assert before == (rig.database.calls, replacement.path.read_bytes())


@pytest.mark.parametrize("key", core.STATUS_KEYS)
def test_caller_supplied_terminal_json_never_substitutes_for_matching_authenticated_old_job(rig, key):
    binding, status = plan(rig)
    lease = rig.authority.acquire(binding, status, lambda: None)
    complete(rig)
    if key == "pins":
        rig.reader.status["pins"]["config_sha256"] = "d" * 64
    else:
        rig.reader.status[key] = "wrong-old-job-field"
    with pytest.raises(TransportError):
        lease.release({"kind": "AUTHENTICATED_STATUS", "status": {**status, "terminal": True}})
    assert rig.database.binding is not None and rig.authority.gate.snapshot().state == "QUARANTINED"


def test_local_write_failure_before_grant_has_zero_db_acquisitions_and_retains_pending(rig, monkeypatch):
    binding, status = plan(rig)
    def failed(_fd):
        raise OSError("Synthetic fsync failure")
    monkeypatch.setattr(core.os, "fsync", failed)
    with pytest.raises(TransportError, match="JOURNAL_WRITE_FAILED"):
        rig.authority.acquire(binding, status, lambda: None)
    assert acquire_count(rig) == 0 and rig.authority.pending.exists()
    assert rig.authority.poisoned and rig.authority.gate.snapshot().state == "QUARANTINED"
    before = rig.authority.pending.read_bytes()
    rig.authority.close()
    with pytest.raises(TransportError, match="PARTIAL"):
        rig.create()
    assert rig.authority.pending.read_bytes() == before


def test_journal_io_after_verified_db_release_preserves_result_and_normal_save(rig, monkeypatch):
    binding, status = plan(rig)
    lease = rig.authority.acquire(binding, status, lambda: None)
    complete(rig)
    result = {"result": {"synthetic_native_result": True}}
    def failed(_fd):
        raise OSError("Synthetic evidence fsync failure")
    monkeypatch.setattr(core.os, "fsync", failed)
    lease.release({"kind": "AUTHENTICATED_STATUS"})  # Must not turn result into logging error.
    saved = []
    with rig.authority.gate.writer():
        saved.append(deepcopy(result))
    assert saved == [result] and rig.database.binding is None
    assert rig.authority.poisoned and rig.authority.gate.snapshot().state == "OPEN"
    with pytest.raises(TransportError, match="POISONED"):
        stage(rig)


def test_database_release_unknown_never_opens_writer_gate(rig):
    binding, status = plan(rig)
    lease = rig.authority.acquire(binding, status, lambda: None)
    complete(rig)
    rig.database.fail_release = True
    with pytest.raises(OSError):
        lease.release({"kind": "AUTHENTICATED_STATUS"})
    assert rig.authority.gate.snapshot().state == "QUARANTINED" and rig.database.binding is not None


def test_idle_database_outcome_unknown_poison_and_quarantines_real_permit(rig):
    rig.database.fail_read = True
    with pytest.raises(TransportError, match="DATABASE_FENCE_OUTCOME_UNKNOWN"):
        rig.authority.recover()
    assert rig.authority.poisoned and rig.authority._permit is not None
    assert rig.authority.gate.snapshot().state == "QUARANTINED"


def test_corrupt_or_missing_journal_cannot_reset_retained_owner(rig):
    authority = rig.authority
    owner = authority.owner_id.encode()
    authority.close()
    authority.path.write_bytes(b'{"body": "synthetic-corruption"}')
    with pytest.raises(TransportError, match="CORRUPT"):
        rig.create()
    assert authority.owner_path.read_bytes() == owner
    authority.path.unlink()  # Synthetic corruption fixture only.
    with pytest.raises(TransportError, match="MISSING"):
        rig.create()
    assert authority.owner_path.read_bytes() == owner


def test_actual_cross_process_os_lock_retains_owner_and_never_deletes_stale_file(rig):
    owner = rig.authority.owner_path
    original = rig.authority.owner_id.encode()
    script = """import os, sys
fd = os.open(sys.argv[1], os.O_RDWR)
try:
    if os.name == 'nt':
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    sys.exit(17)
finally:
    os.close(fd)
"""
    def attempt():
        return subprocess.run([sys.executable, "-c", script, str(owner)], capture_output=True, timeout=10, check=False)
    assert attempt().returncode == 17
    with pytest.raises(TransportError, match="OS_AUTHORITY_LOCK"):
        rig.create()
    assert attempt().returncode == 17  # Failed contender did not unlock first owner.
    rig.authority.close()
    assert owner.exists() and owner.read_bytes() == original
    assert attempt().returncode == 0
    restored = rig.create()
    assert restored.owner_id.encode() == original


def test_two_opener_interleaving_preserves_exclusively_created_owner_id(rig, monkeypatch):
    rig.authority.close()
    rig.directory = rig.directory.parent / "two-racing-openers"
    owner_path = rig.directory / "workspace-authority.owner"
    opened, release, errors, authorities = Event(), Event(), [], []
    original_open = core.os.open
    def delayed(path, flags, *args, **kwargs):
        from threading import current_thread
        if Path(path) == owner_path and flags & core.os.O_EXCL and current_thread().name == "second-opener":
            opened.set()
            assert release.wait(5)
        return original_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(core.os, "open", delayed)
    def create():
        try:
            authorities.append(rig.create())
        except BaseException as error:
            errors.append(error)
    thread = Thread(target=create, name="second-opener")
    thread.start()
    try:
        assert opened.wait(5)
        first = rig.create()
        before = first.owner_id.encode()
        first.close()
    finally:
        release.set()
        thread.join(5)
    assert not errors and not thread.is_alive() and len(authorities) == 1
    assert authorities[0].owner_id.encode() == before
    authorities[0].close()
    assert owner_path.read_bytes() == before


def test_privacy_denial_prevents_owner_file_creation(rig, monkeypatch):
    rig.authority.close()
    rig.directory = rig.directory.parent / "denied-private-directory"
    monkeypatch.setattr(core, "private_hospital_root", lambda *args, **kwargs: False)
    with pytest.raises(TransportError, match="PRIVATE_AUTHORITY_DIRECTORY"):
        rig.create()
    assert not (rig.directory / "workspace-authority.owner").exists()


def test_redirected_existing_parent_is_checked_before_new_directory_write(rig, monkeypatch):
    rig.authority.close()
    rig.directory = rig.directory.parent / "must-not-create"
    parent = rig.directory.parent
    original = core.has_reparse_component
    monkeypatch.setattr(core, "has_reparse_component", lambda path: path == parent or original(path))
    with pytest.raises(TransportError, match="REDIRECTED_AUTHORITY_DIRECTORY"):
        rig.create()
    assert not rig.directory.exists()


def test_actual_temporary_redirect_never_creates_leaf_under_target(rig):
    rig.authority.close()
    target = rig.directory.parent / "synthetic-redirect-target"
    target.mkdir()
    link = rig.directory.parent / "synthetic-redirect"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Native temporary symlink unavailable; no privilege or ACL changes attempted")
    rig.directory = link / "must-not-create"
    with pytest.raises(TransportError, match="REDIRECTED_AUTHORITY_DIRECTORY"):
        rig.create()
    assert not (target / "must-not-create").exists()


def test_db_only_binding_adopts_consumed_evidence_and_rehydrates_real_quarantine(rig):
    before = rig.authority.path.read_bytes()
    binding, status = plan(rig)
    rig.authority.acquire(binding, status, lambda: None)
    durable = deepcopy(rig.database.binding)
    rig.authority.close()
    rig.authority.path.write_bytes(before)  # Synthetic lost-local-intent rehearsal.
    restored = rig.create()
    assert restored.gate.snapshot().state == "QUARANTINED" and restored._permit is not None
    assert durable["local_plan_key"] in restored._body["consumed"]
    assert durable["plan_sha256"] in restored._body["consumed"]
    complete(rig)
    restored.recover()
    assert restored.gate.snapshot().state == "OPEN"


def test_mismatched_local_and_database_old_job_never_releases_either(rig):
    binding, status = plan(rig)
    rig.authority.acquire(binding, status, lambda: None)
    rig.authority.close()
    before = rig.authority.path.read_bytes()
    rig.database.binding["job_id"] = "different-old-job"
    with pytest.raises(TransportError, match="FENCE_SCOPE_MISMATCH"):
        rig.create()
    assert rig.authority.path.read_bytes() == before
    assert "release" not in rig.database.calls


def test_consumed_session_limit_never_evicts_replay_evidence(rig):
    consumed = [sha(str(index).encode()) for index in range(128)]
    rig.authority._body["consumed"] = list(consumed)
    rig.authority._persist()
    binding, status = plan(rig)
    with pytest.raises(TransportError, match="SESSION_EXHAUSTED"):
        rig.authority.acquire(binding, status, lambda: None)
    assert rig.authority._body["consumed"] == consumed
    assert acquire_count(rig) == 0


def test_oversize_journal_fails_before_database_or_grant(rig):
    rig.context["model_pins"]["checkpoint_sha256"] = {f"fold-{index}": "d" * 64 for index in range(1000)}
    binding, status = plan(rig)
    before = rig.authority.path.read_bytes()
    with pytest.raises(TransportError, match="JOURNAL_LIMIT"):
        rig.authority.acquire(binding, status, lambda: None)
    assert rig.authority.path.read_bytes() == before and len(before) < core.LIMIT
    assert acquire_count(rig) == 0 and rig.authority.gate.snapshot().state == "QUARANTINED"


def test_full_context_memory_limit_rejects_before_prepare_or_journal_payload(rig):
    before = rig.authority.path.read_bytes()
    rig.context["case"]["synthetic_oversize"] = "x" * (8 * 1024 * 1024)
    with pytest.raises(TransportError, match="RECORDED_WORKSPACE_CONTEXT"):
        stage(rig)
    assert rig.authority.path.read_bytes() == before and acquire_count(rig) == 0


@pytest.mark.parametrize("runtime", [None, {}, [], "not-a-context"])
def test_runtime_context_is_required_nonempty_and_not_a_permission_claim(rig, runtime):
    rig.context["runtime_context"] = runtime
    with pytest.raises(TransportError, match="RECORDED_WORKSPACE_CONTEXT"):
        stage(rig)
    assert acquire_count(rig) == 0


def test_runtime_config_change_is_detected_with_all_four_outer_objects_unchanged(rig):
    binding, status = plan(rig)
    objects = rig.context["objects"]
    rig.context["runtime_context"]["database_identity_sha256"] = "e" * 64
    with pytest.raises(TransportError, match="CONTEXT_OR_OBJECT_CHANGED"):
        rig.authority.acquire(binding, status, lambda: None)
    assert all(left is right for left, right in zip(objects, rig.context["objects"], strict=True))
    assert acquire_count(rig) == 0


@pytest.mark.parametrize("field,value", [("generation", None), ("expires_at", None), ("generation", True),
                                         ("generation", -1), ("expires_at", "not-an-iso-time"), ("expires_at", "2099-01-01")])
def test_exact_frozen_plan_requires_complete_typed_metadata_without_ttl_reset(rig, field, value):
    snap, frozen = stage(rig)
    binding = dict(frozen, plan_id="exact-plan", generation=0, expires_at="2099-01-01T00:00:00+00:00")
    if value is None:
        binding.pop(field)
    else:
        binding[field] = value
    with pytest.raises(TransportError, match="EXACT_FROZEN"):
        rig.authority.register_preview_plan(snap, binding, sha(canonical(binding)))
    assert acquire_count(rig) == 0


def test_owner_identity_change_stops_every_retained_lease_callback(rig):
    binding, status = plan(rig)
    lease = rig.authority.acquire(binding, status, lambda: None)
    before = list(rig.database.calls), rig.authority.path.read_bytes()
    stat = rig.authority._owner_stat
    rig.authority._owner_stat = SimpleNamespace(st_dev=stat.st_dev, st_ino=stat.st_ino + 1)
    complete(rig)
    for operation in (lambda: lease.release({"kind": "AUTHENTICATED_STATUS"}), lambda: lease.quarantine("unknown")):
        with pytest.raises(TransportError, match="OWNER_OR_PRIVACY_CHANGED"):
            operation()
    assert before == (rig.database.calls, rig.authority.path.read_bytes())
    assert rig.database.binding is not None


def test_existing_bound_transport_returns_verified_result_despite_post_release_local_io_failure(rig, monkeypatch):
    from dr_support.services.prism_remote_transport import BASE, PROTOCOL, TRANSPORT
    value = SimpleNamespace(binding=None, digest=None, granted=False, result=None)

    class Channel:
        def request(self, method, path, body=None, **kwargs):
            if path.endswith("/capabilities"):
                return {"transport": TRANSPORT, "binding_protocol": PROTOCOL, "pins": rig.context["model_pins"], "epoch": "old-epoch"}
            if path == BASE + "/prepare":
                return {"epoch": "old-epoch", "pins": rig.context["model_pins"], "ticket_id": "old-ticket", "mask_b64": None,
                        "external_fov_status": "NOT_APPLICABLE", "external_fov_reason_code": None, "mask_version": None}
            if path == BASE + "/execute":
                return {"job_id": "old-job"}
            if path.endswith("/grant"):
                value.granted = True
                def failed(_fd):
                    raise OSError("Synthetic log fsync failure after native grant")
                monkeypatch.setattr(core.os, "fsync", failed)
                return {}
            if path == BASE + "/jobs/old-job":
                if value.granted:
                    complete(rig)
                    return {**rig.reader.status, "result": value.result}
                return deepcopy(rig.reader.status)
            raise AssertionError("Unexpected synthetic channel call")

    candidate = RemoteBoundTransportCandidate(Channel(), source_authority=rig.authority)
    candidate.negotiate()
    objects = list(rig.context["objects"])
    objects[1] = candidate
    rig.context["objects"] = tuple(objects)
    binding, status = plan(rig)
    digest = sha(canonical(binding))
    candidate.prepare_prism_preview_candidate(rig.image)
    raw = infer_mock(InferenceRequest(image_id=rig.image.image_id, model_id="mock-lesion"), rig.image).model_dump(mode="json")
    raw.update(model_id=binding["model_id"], model_version=binding["model_version"])
    raw["provenance"].update(source_revision=binding["model_pins"]["source_revision"],
        checkpoint_sha256=binding["model_pins"]["checkpoint_sha256"], preprocessing=binding["model_pins"]["preprocessing"])
    value.result = {"result": raw, "preview_receipt": {"plan_sha256": digest, "wire_sha256": binding["wire_sha256"],
                    "mask_sha256": binding["mask_sha256"], "transform_sha256": binding["transform"]["sha256"]}}
    returned = candidate.infer_bound_prism(InferenceRequest(image_id=rig.image.image_id, model_id="prism-dr-5fold"),
        rig.image, mask_png=None, binding=binding, plan_sha256=digest, before_forward=lambda: None)
    assert returned == value.result
    assert value.granted and rig.database.binding is None and rig.authority.poisoned
    with rig.authority.gate.writer():
        saved = deepcopy(returned)
    assert saved == value.result
