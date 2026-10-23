"""Store/sync controls with generated fixtures; no live DB/CVAT/native entry."""
from contextlib import contextmanager
from copy import deepcopy
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from dr_support.contracts import InferenceRequest, LABELS
from dr_support.cvat import OnlineError
from dr_support.images import synthetic_image
from dr_support.persistence.cases import CaseConflictError, PostgresCaseStore
from dr_support.providers.mock import infer_mock
from dr_support.services.source_mutation_gate import MutationFenced, SourceMutationGate
from dr_support.store import Store
from dr_support.sync import Sync


class FakePostgres:
    """Controlled SQL/CAS harness, never opens a PostgreSQL connection."""

    def __init__(self):
        self.settings = SimpleNamespace(schema="synthetic_store_gate")
        self.rows = {}
        self.calls = []

    @contextmanager
    def session(self, **kwargs):
        yield self

    @contextmanager
    def transaction(self):
        self.calls.append("BEGIN")
        prior = deepcopy(self.rows)
        try:
            yield self
        except BaseException:
            self.rows = prior
            raise

    def execute(self, query, params):
        text = query.as_string(None)
        self.calls.append(text)
        if text.startswith("SELECT revision, payload"):
            value = self.rows.get(tuple(params))
            return SimpleNamespace(fetchone=lambda: deepcopy(value))
        if text.startswith("INSERT") and ".workspaces " in text:
            return SimpleNamespace(rowcount=1)
        if text.startswith("INSERT") and ".review_cases " in text:
            workspace, case_id, revision, payload = params
            key = (workspace, case_id)
            if key in self.rows:
                return SimpleNamespace(rowcount=0)
            self.rows[key] = (revision, deepcopy(payload.obj))
            return SimpleNamespace(rowcount=1)
        if text.startswith("UPDATE") and ".review_cases " in text:
            if len(params) == 6:
                revision, payload, workspace, case_id, observed_revision, observed = params
            else:
                payload, workspace, case_id, observed_revision, observed = params
                revision = observed_revision
            current = self.rows.get((workspace, case_id))
            if current is not None and current == (observed_revision, observed.obj):
                self.rows[(workspace, case_id)] = (revision, deepcopy(payload.obj))
                return SimpleNamespace(rowcount=1)
            return SimpleNamespace(rowcount=0)
        raise AssertionError(f"Unexpected synthetic SQL: {text}")


@pytest.fixture(params=["sqlite", "postgres"])
def store(request, tmp_path):
    if request.param == "sqlite":
        value = Store(tmp_path / "synthetic-review.sqlite")
        yield value
        value.db.close()
    else:
        yield PostgresCaseStore(FakePostgres(), "synthetic-workspace")


def effect_snapshot(store):
    if isinstance(store, Store):
        return store.path.read_bytes(), store.db.total_changes
    return deepcopy(store.database.rows), list(store.database.calls)


def seed_case(store):
    case = store.get("SYNTHETIC_CASE")
    case["review_history"] = [{"reviewer": "Synthetic reviewer", "grade": 2}]
    case["human_annotations"] = [{"id": "synthetic-roi", "source": "HUMAN"}]
    case["raw_prediction"] = {"fixture_only": True}
    store.put(case)
    return case


class UnexpectedLock:
    def __enter__(self):
        pytest.fail("Fenced operation reached the internal store lock")

    def __exit__(self, *_args):
        pass


def fenced_gate(state):
    gate = SourceMutationGate()
    permit = gate.begin_entry(expected_generation=0)
    if state == "QUARANTINED":
        permit.quarantine()
    return gate


def test_legacy_none_preserves_payload_and_durable_reads(store):
    assert store.source_mutation_gate is None
    case = seed_case(store)
    assert store.get(case["image_id"]) == case


@pytest.mark.parametrize("state", ["FENCED", "QUARANTINED"])
def test_put_refuses_before_lock_file_or_database_effect(store, state, monkeypatch):
    case = seed_case(store)
    before = effect_snapshot(store)
    gate = store.source_mutation_gate = fenced_gate(state)
    gate_before = gate.snapshot()
    monkeypatch.setattr(store, "lock", UnexpectedLock())
    case["review_history"].append({"reviewer": "Must not be saved"})
    with pytest.raises(MutationFenced, match="SOURCE_WRITERS_FENCED"):
        store.put(case)
    assert effect_snapshot(store) == before
    assert gate.snapshot() == gate_before


def test_invalid_injected_gate_cannot_silently_fall_back_to_legacy(store):
    case = seed_case(store)
    before = effect_snapshot(store)
    store.source_mutation_gate = object()
    with pytest.raises(ValueError, match="EXPLICIT_SOURCE_MUTATION_GATE_REQUIRED"):
        store.put(case)
    assert effect_snapshot(store) == before


def test_failed_put_clears_writer_count_and_invalidates_prior_plan(store):
    case = seed_case(store)
    gate = store.source_mutation_gate = SourceMutationGate()
    before, planned = effect_snapshot(store), gate.snapshot()
    case["synthetic_invalid_json"] = float("nan")
    with pytest.raises(ValueError):
        store.put(case)
    assert effect_snapshot(store) == before
    after = gate.snapshot()
    assert after.writers == 0 and after.state == "OPEN"
    assert after.generation == planned.generation + 1
    with pytest.raises(MutationFenced, match="GENERATION_CHANGED"):
        gate.begin_entry(expected_generation=planned.generation)


def test_paused_put_is_a_writer_before_internal_lock_and_blocks_entry(store, monkeypatch):
    case = seed_case(store)
    gate = store.source_mutation_gate = SourceMutationGate()
    planned = gate.snapshot()
    entered, release = Event(), Event()
    original_lock, failures = store.lock, []

    class PausedLock:
        def __enter__(self):
            entered.set()
            assert release.wait(5)
            return original_lock.__enter__()

        def __exit__(self, *args):
            return original_lock.__exit__(*args)

    monkeypatch.setattr(store, "lock", PausedLock())

    def write():
        try:
            store.put(case)
        except BaseException as error:
            failures.append(error)

    worker = Thread(target=write)
    worker.start()
    try:
        assert entered.wait(5)
        assert gate.snapshot().writers == 1
        with pytest.raises(MutationFenced, match="ACTIVE_OR_FENCED"):
            gate.begin_entry(expected_generation=planned.generation)
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive() and not failures
    assert gate.snapshot().writers == 0
    with pytest.raises(MutationFenced, match="GENERATION_CHANGED"):
        gate.begin_entry(expected_generation=planned.generation)


@pytest.mark.parametrize("injected", [False, True])
def test_controlled_postgres_cas_and_workspace_isolation_remain_unchanged(injected):
    database = FakePostgres()
    owner, stale = (PostgresCaseStore(database, "synthetic-workspace") for _ in range(2))
    other = PostgresCaseStore(database, "other-synthetic-workspace")
    gate = SourceMutationGate() if injected else None
    for store in (owner, stale, other):
        store.source_mutation_gate = gate
    seed = seed_case(owner)
    stale_case = stale.get(seed["image_id"])
    current = owner.get(seed["image_id"])
    current["events"].append({"action": "SAME_REVISION_ENRICHMENT"})
    owner.put(current)
    with pytest.raises(CaseConflictError, match="Case changed"):
        stale.put(stale_case)
    fresh = stale.get(seed["image_id"])
    assert fresh == current
    fresh["revision"] += 1
    fresh["events"].append({"action": "CLINICIAN_REVISION_FIXTURE"})
    stale.put(fresh)
    assert owner.get(seed["image_id"]) == fresh
    separate = other.get(seed["image_id"])
    separate["events"].append({"action": "OTHER_WORKSPACE"})
    other.put(separate)
    assert owner.get(seed["image_id"]) == fresh
    assert other.get(seed["image_id"]) == separate
    if gate is not None:
        assert gate.snapshot().writers == 0


class Remote:
    """Deterministic CVAT fake; it never constructs a network client."""

    def __init__(self):
        self.calls = []
        self.task = None
        self.payload = {"version": 0, "tags": [], "tracks": [], "shapes": []}

    def inspect(self):
        self.calls.append("inspect")
        return {}, {label: number for number, label in enumerate(LABELS.values(), 1)}

    def find_task(self, name):
        self.calls.append("find_task")
        return self.task

    def create_task(self, name):
        self.calls.append("create_task")
        self.task = {"id": 7, "size": 0, "name": name}
        return self.task

    def check_task(self, task_id):
        self.calls.append("check_task")
        return self.task

    def upload(self, task_id, image):
        self.calls.append("upload")
        self.task["size"] = 1
        return {"rq_id": "synthetic-upload"}

    def annotations(self, task_id):
        self.calls.append("annotations")
        return deepcopy(self.payload)

    def push(self, task_id, payload):
        self.calls.append("push")
        self.payload = deepcopy(payload)
        return self.payload

    def jobs(self, task_id):
        self.calls.append("jobs")
        return {"results": [{"id": 9}]}


@pytest.fixture
def sync_rig(tmp_path):
    store = Store(tmp_path / "synthetic-cvat.sqlite")
    image = synthetic_image()
    case = store.get(image.image_id)
    case["lesion"] = infer_mock(InferenceRequest(image_id=image.image_id, model_id="mock-lesion"), image).model_dump(mode="json")
    store.put(case)
    remote = Remote()
    yield store, image, remote, Sync(store, remote)
    store.db.close()


@pytest.mark.parametrize("operation", ["send", "pull"])
@pytest.mark.parametrize("state", ["FENCED", "QUARANTINED"])
def test_sync_whole_operation_stops_before_store_or_remote_effect(sync_rig, operation, state, monkeypatch):
    store, image, remote, sync = sync_rig
    if operation == "pull":
        sync.send(image)
    before = effect_snapshot(store)
    calls = list(remote.calls)
    store.source_mutation_gate = fenced_gate(state)
    monkeypatch.setattr(store, "lock", UnexpectedLock())
    with pytest.raises(MutationFenced):
        getattr(sync, operation)(image)
    assert effect_snapshot(store) == before
    assert remote.calls == calls


@pytest.mark.parametrize("operation", ["send", "pull"])
def test_sync_paused_remote_operation_blocks_entry_through_later_nested_put(sync_rig, operation, monkeypatch):
    store, image, remote, sync = sync_rig
    if operation == "pull":
        sync.send(image)
        remote.payload["version"] += 1
    gate = store.source_mutation_gate = SourceMutationGate()
    planned = gate.snapshot()
    entered, release, failures, write_scopes = Event(), Event(), [], []
    inspect = remote.inspect

    def paused():
        entered.set()
        assert release.wait(5)
        return inspect()

    def traced_sql(query):
        if query.startswith("INSERT OR REPLACE"):
            write_scopes.append(gate.snapshot().writers)

    monkeypatch.setattr(remote, "inspect", paused)
    store.db.set_trace_callback(traced_sql)

    def run():
        try:
            getattr(sync, operation)(image)
        except BaseException as error:
            failures.append(error)

    worker = Thread(target=run)
    worker.start()
    try:
        assert entered.wait(5)
        assert gate.snapshot().writers == 1
        with pytest.raises(MutationFenced, match="ACTIVE_OR_FENCED"):
            gate.begin_entry(expected_generation=planned.generation)
    finally:
        release.set()
        worker.join(5)
        store.db.set_trace_callback(None)
    assert not worker.is_alive() and not failures
    assert write_scopes and all(count == 2 for count in write_scopes)
    assert gate.snapshot().writers == 0
    with pytest.raises(MutationFenced, match="GENERATION_CHANGED"):
        gate.begin_entry(expected_generation=planned.generation)


@pytest.mark.parametrize("operation", ["send", "pull"])
def test_failed_sync_preserves_exception_and_clears_counter_but_invalidates_plan(sync_rig, operation, monkeypatch):
    store, image, remote, sync = sync_rig
    if operation == "pull":
        sync.send(image)
    gate = store.source_mutation_gate = SourceMutationGate()
    before, planned = effect_snapshot(store), gate.snapshot()

    def failed():
        raise OnlineError("Synthetic CVAT failure")

    monkeypatch.setattr(remote, "inspect", failed)
    with pytest.raises(OnlineError, match="Synthetic CVAT failure"):
        getattr(sync, operation)(image)
    assert effect_snapshot(store) == before
    assert gate.snapshot().writers == 0 and gate.snapshot().state == "OPEN"
    with pytest.raises(MutationFenced, match="GENERATION_CHANGED"):
        gate.begin_entry(expected_generation=planned.generation)


def test_sync_resolves_current_store_gate_instead_of_caching_constructor_store(sync_rig, tmp_path):
    store, image, remote, sync = sync_rig
    replacement = Store(tmp_path / "replacement-synthetic.sqlite")
    try:
        replacement.source_mutation_gate = SourceMutationGate(quarantined=True)
        sync.store = replacement
        before = effect_snapshot(replacement), effect_snapshot(store)
        with pytest.raises(MutationFenced):
            sync.send(image)
        assert not remote.calls
        assert (effect_snapshot(replacement), effect_snapshot(store)) == before
    finally:
        replacement.db.close()


def test_gated_sync_keeps_uncertain_push_intent_without_automatic_retry(sync_rig, monkeypatch):
    store, image, remote, sync = sync_rig
    gate = store.source_mutation_gate = SourceMutationGate()

    def unknown(*args):
        remote.calls.append("uncertain_push")
        raise OnlineError("Synthetic push outcome unknown")

    monkeypatch.setattr(remote, "push", unknown)
    with pytest.raises(OnlineError, match="outcome unknown"):
        sync.send(image)
    assert store.get(image.image_id)["cvat"]["push_started"] is True
    assert gate.snapshot().writers == 0
    with pytest.raises(OnlineError, match="manual reconciliation"):
        sync.send(image)
    assert remote.calls.count("uncertain_push") == 1
    assert gate.snapshot().writers == 0
