"""Actual runtime/core wiring with synthetic context/DB; no load or inference."""
from copy import deepcopy
from threading import Event, RLock, Thread, current_thread
from types import SimpleNamespace

import pytest

from dr_support.services import prism_workspace_authority as core
from dr_support.services.prism_preview import MODEL_ID, PrismPreviewService, preparation_context
from dr_support.services.prism_preview_runtime import ReviewPrismPreview
from dr_support.services.source_mutation_gate import SourceMutationGate
from test_prism_preview_binding import rig as _review_rig

review_rig = _review_rig


@pytest.fixture
def bound_rig(review_rig, tmp_path, monkeypatch):
    rig = review_rig
    # Privacy is mocked only for this synthetic fixture; never edit native ACLs.
    monkeypatch.setattr(core, 'private_hospital_root', lambda *_: True)
    identity = rig.provider.prism_preview_identity()
    identity['model_version'] = identity['model_pins']['source_revision']
    monkeypatch.setattr(rig.provider, 'prism_preview_identity', lambda: deepcopy(identity))
    rig.store.case.update(image_id='fixture', admission=deepcopy(rig.app.state.admissions['fixture']))
    manager = SimpleNamespace(lock=RLock())
    rig.app.state.workspace_manager = manager

    def context(image_id):
        return dict(workspace_id='synthetic-workspace', image_id=image_id, case=deepcopy(rig.store.case),
                    workspace={'workspace_id': 'synthetic-workspace', 'note': 'Full raw test catalog'},
                    admission=deepcopy(rig.app.state.admissions[image_id]), source_sha256=rig.image.sha256,
                    preparation_context=preparation_context(rig.store.case), model_pins=identity['model_pins'],
                    runtime_context={'scope': 'synthetic-hook-only-no-runtime'},
                    objects=(rig.app.state.store, rig.app.state.providers[MODEL_ID], manager, rig.app.state.derivatives))

    database = SimpleNamespace(read=lambda: None,
        acquire=lambda **_: pytest.fail('No DB entry/native execution in wiring tests'),
        recover=lambda: pytest.fail('No recovery expected'))
    authority = core.WorkspaceAuthority(tmp_path / 'synthetic-authority', context_reader=context,
        database_fence=database, authenticated_status_reader=lambda _: pytest.fail('No remote status expected'))
    rig.app.state.source_mutation_gate = rig.store.source_mutation_gate = manager.source_mutation_gate = authority.gate
    rig.provider.authority = authority
    events = []
    original_authorize = authority.authorize_prepare

    def authorize(*args, **kwargs):
        events.append('stage' if len(args) > 1 else 'check-before-prepare')
        return original_authorize(*args, **kwargs)

    monkeypatch.setattr(authority, 'authorize_prepare', authorize)
    prepare_candidate = rig.provider.prepare_prism_preview_candidate

    def prepare(wire):
        # Same two-step ordering as the actual remote transport. No network.
        authority.authorize_prepare(wire)
        events.append('prepare-control')
        return prepare_candidate(wire)

    monkeypatch.setattr(rig.provider, 'prepare_prism_preview_candidate', prepare)
    monkeypatch.setattr(rig.provider, 'get_prism_preview_candidate', prepare_candidate)
    runtime = ReviewPrismPreview(rig.app, save_result=rig.runtime.save_result,
        source_allowed=rig.runtime.source_allowed, eligible=rig.runtime.eligible, route=rig.runtime.route,
        map_result=rig.runtime.map_result, inference_lock=RLock(), workspace_authority=authority)
    service = PrismPreviewService(runtime.snapshot, runtime.execute, refresh=runtime.refresh,
                                  register_plan=runtime.register_workspace_plan)
    rig.runtime, rig.service, rig.authority, rig.events = runtime, service, authority, events
    try:
        yield rig
    finally:
        authority.close()


def test_runtime_stages_before_prepare_and_registers_exact_core_plan(bound_rig, monkeypatch):
    rig = bound_rig
    registered = []
    original = rig.authority.register_preview_plan

    def register(*args):
        original(*args)
        registered.append(args[2])

    monkeypatch.setattr(rig.authority, 'register_preview_plan', register)
    before = deepcopy(rig.store.case)
    plan = rig.service.prepare('fixture', 0)
    assert rig.events == ['stage', 'check-before-prepare', 'prepare-control']
    assert registered == [plan['plan_sha256']]
    assert rig.store.case == before and not rig.saved and rig.provider.calls == 0
    rig.service.asset('fixture', plan['plan_id'], 'original')
    assert rig.events == ['stage', 'check-before-prepare', 'prepare-control']


def test_full_context_drift_during_preparation_cannot_register_a_usable_plan(bound_rig, monkeypatch):
    rig = bound_rig
    prepare = rig.provider.prepare_prism_preview_candidate

    def mutate(wire):
        candidate = prepare(wire)
        with rig.authority.gate.writer():
            rig.store.case['same_revision_automatic_context'] = 'changed'
        return candidate

    monkeypatch.setattr(rig.provider, 'prepare_prism_preview_candidate', mutate)
    with pytest.raises(Exception, match='registration failed'):
        rig.service.prepare('fixture', 0)
    assert not rig.service.plans and rig.provider.calls == 0


def test_active_writer_blocks_before_any_prepare_control(bound_rig):
    rig = bound_rig
    with rig.authority.gate.writer():
        with pytest.raises(Exception, match='AUTHORITY_FENCED_BUSY_OR_POISONED'):
            rig.runtime.snapshot('fixture')
    assert rig.events == ['stage'] and not rig.saved and rig.provider.calls == 0


@pytest.mark.parametrize('drift', ['store-gate', 'manager-gate', 'app-gate', 'fixed-session', 'batch-profile'])
def test_shared_gate_or_isolated_mode_drift_refuses_before_prepare(bound_rig, drift):
    rig = bound_rig
    if drift == 'store-gate':
        rig.store.source_mutation_gate = SourceMutationGate()
    elif drift == 'manager-gate':
        rig.app.state.workspace_manager.source_mutation_gate = SourceMutationGate()
    elif drift == 'app-gate':
        rig.app.state.source_mutation_gate = SourceMutationGate()
    elif drift == 'fixed-session':
        rig.app.state.qa_fixed_session = object()
    else:
        rig.app.state.qa_batch_profile = object()
    with pytest.raises(ValueError, match='SHARED_WRITER_GATE_REQUIRED'):
        rig.runtime.snapshot('fixture')
    assert not rig.events and rig.provider.calls == 0


def test_provider_authority_swap_is_rejected_without_prepare(bound_rig):
    rig = bound_rig
    rig.provider.authority = object()
    with pytest.raises(Exception, match='does not own this workspace authority'):
        rig.runtime.snapshot('fixture')
    assert not rig.events and rig.provider.calls == 0


@pytest.mark.parametrize('drift', ['poison', 'closed', 'writer-generation', 'same-revision'])
def test_cached_plan_cannot_dispatch_after_authority_changes(bound_rig, monkeypatch, drift):
    rig = bound_rig
    plan = rig.service.prepare('fixture', 0)
    snapshot = rig.service.plans[plan['plan_id']].snapshot
    binding = deepcopy(rig.service.plans[plan['plan_id']].binding)
    monkeypatch.setattr(rig.provider, 'infer_bound_prism',
                        lambda *a, **k: pytest.fail('No remote execute/accounting permitted'))
    if drift == 'poison':
        # A verified-release journal failure intentionally keeps this gate OPEN
        # so the already valid result can save. It must refuse the NEXT dispatch.
        rig.authority.poisoned = True
        assert rig.authority.gate.snapshot().state == 'OPEN'
    elif drift == 'closed':
        rig.authority.close()
    elif drift == 'writer-generation':
        with rig.authority.gate.writer():
            pass
    else:
        rig.store.case['same_revision_automatic_context'] = 'changed outside cooperating writer'
    with pytest.raises(core.TransportError):
        rig.runtime.execute(snapshot, binding, plan['plan_sha256'], still_valid=lambda: True)
    assert not rig.saved and rig.provider.calls == 0


def test_ordinary_factory_has_no_workspace_authority_registration(review_rig):
    assert review_rig.runtime.workspace_authority is None
    with pytest.raises(ValueError, match='WORKSPACE_AUTHORITY_REQUIRED'):
        review_rig.runtime.register_workspace_plan(None, {}, 'a' * 64)


class ObservedLock:
    """Real RLock with a barrier when the preview thread attempts acquisition."""
    def __init__(self):
        self.lock = RLock()
        self.attempted = Event()

    def __enter__(self):
        if current_thread().name == 'workspace-preview':
            self.attempted.set()
        self.lock.acquire()
        return self

    def __exit__(self, *args):
        self.lock.release()


@pytest.mark.parametrize('outer', ['authority', 'manager'])
def test_snapshot_never_holds_store_while_waiting_for_outer_context_lock(bound_rig, outer):
    rig = bound_rig
    observed = ObservedLock()
    if outer == 'authority':
        rig.authority.lock = observed
    else:
        rig.app.state.workspace_manager.lock = observed
    outcome = []

    def preview():
        try:
            outcome.append(rig.runtime.snapshot('fixture'))
        except BaseException as error:
            outcome.append(error)

    with observed:
        worker = Thread(target=preview, name='workspace-preview')
        worker.start()
        try:
            assert observed.attempted.wait(5), 'Preview did not reach the outer lock'
            acquired = rig.store.lock.acquire(timeout=1)
            assert acquired, 'Preview held store while waiting for outer authority/manager'
            rig.store.lock.release()
        finally:
            # The outer lock releases even on failure, so the actual thread
            # never remains deadlocked in this regression fixture.
            pass
    worker.join(timeout=5)
    assert not worker.is_alive() and len(outcome) == 1
    assert not isinstance(outcome[0], BaseException), outcome
    assert rig.provider.calls == 0 and not rig.saved
