"""Bootstrap host controls with injected executor types; no qualification/model."""
import base64
import itertools
import sys
from types import ModuleType

from PIL import Image
import pytest

from dr_support.services.prism_remote_transport import BASE, PROTOCOL, BoundTransportHost, Principal, TransportError, sha
from test_prism_remote_transport import FakeExecutor, png


@pytest.fixture
def rig(monkeypatch):
    # This fixture tests the exact-type bootstrap seam, not the actual model
    # adapter. The additive adapter has separate joint integration controls.
    class SyntheticWorkspaceExecutor(FakeExecutor):
        def prepare(self, wire, modality):
            if modality == 'CFP':
                return {'status': 'NOT_APPLICABLE', 'mask_png': None, 'mask_version': None, 'reason_code': None}
            return super().prepare(wire, modality)

    module = ModuleType('dr_support.services.prism_workspace_executor')
    module.LoadedWorkspacePrismExecutor = SyntheticWorkspaceExecutor
    monkeypatch.setitem(sys.modules, module.__name__, module)
    executor = SyntheticWorkspaceExecutor()
    sequence = itertools.count()
    principal = Principal('synthetic-backend', frozenset({'review-client', 'prepare-source', 'forward-authority'}))
    host = BoundTransportHost(executor, authenticate=lambda _: principal,
        issue_id=lambda: f'synthetic_{next(sequence):08}', epoch='synthetic_epoch')
    wire = png(Image.new('RGB', (32, 24), (80, 50, 40)))
    envelope = dict(wire_b64=base64.b64encode(wire).decode(), wire_sha256=sha(wire),
                    wire_media_type='image/png', modality='CFP')
    return host, executor, principal, envelope


def test_default_fixed_host_still_rejects_cfp_and_request_flag_cannot_enable(rig):
    host, executor, principal, envelope = rig
    with pytest.raises(TransportError, match='WIRE_CONTEXT'):
        host._prepare(principal, envelope)
    with pytest.raises(TransportError, match='PREPARE_SCHEMA'):
        host._prepare(principal, envelope | {'workspace_mode': True})
    assert executor.loads == executor.roi == executor.prepares == 0


def test_explicit_exact_bootstrap_accepts_cfp_without_loading_or_forward(rig):
    host, executor, principal, envelope = rig
    host.enable_workspace_executor(executor)
    ticket = host._prepare(principal, envelope)
    assert ticket['external_fov_status'] == 'NOT_APPLICABLE' and ticket['mask_b64'] is None
    assert executor.loads == executor.roi == 0
    with pytest.raises(TransportError, match='FRESH_EXACT'):
        host.enable_workspace_executor(executor)


@pytest.mark.parametrize('wrong', ['other-instance', 'subclass', 'foreign-type', 'old-id', 'ticket', 'job'])
def test_bootstrap_rejects_foreign_executor_or_used_host(rig, wrong):
    host, executor, _, _ = rig
    target = executor
    if wrong == 'other-instance':
        target = type(executor)()
    elif wrong == 'subclass':
        class Subclass(type(executor)):
            pass
        target = Subclass()
        host.executor = target
    elif wrong == 'foreign-type':
        target = host.executor = FakeExecutor()
    elif wrong == 'old-id':
        host.issued_ids.add('retained_prior_id')
    elif wrong == 'ticket':
        host.tickets['retained_ticket'] = object()
    else:
        host.jobs['retained_job'] = object()
    with pytest.raises(TransportError, match='FRESH_EXACT'):
        host.enable_workspace_executor(target)


def test_executor_swap_after_bootstrap_cannot_prepare_or_read_pins(rig):
    host, executor, principal, envelope = rig
    host.enable_workspace_executor(executor)
    host.executor = type(executor)()
    with pytest.raises(TransportError, match='SCOPE_CHANGED'):
        host._prepare(principal, envelope)
    with pytest.raises(TransportError, match='SCOPE_CHANGED'):
        host._pins()


def test_workspace_capability_reports_actual_loaded_pins_without_inference_claim(rig):
    host, executor, _, _ = rig
    host.enable_workspace_executor(executor)
    code, _ = host.handle('GET', BASE + '/capabilities', {}, b'')
    assert code == 503  # Identity metadata alone cannot claim a loaded runtime.
    executor.loaded = True
    code, value = host.handle('GET', BASE + '/capabilities', {}, b'')
    assert code == 200
    assert value['workspace_runtime'] == {
        'profile': 'HOSPITAL_M1', 'modalities': ['CFP', 'UWF'],
        'authorized_source_origins': ['SYNTHETIC'], 'native_entry_protocol': PROTOCOL, 'load_state': 'LOADED'}
    assert 'inference_pass' not in value and 'clinical_validation' not in value
    assert executor.loads == executor.roi == 0


@pytest.mark.parametrize('modality,status', [('CFP', 'UNCERTAIN'), ('UWF', 'NOT_APPLICABLE')])
def test_workspace_mask_fallback_stays_specific_to_modality(rig, monkeypatch, modality, status):
    host, executor, principal, envelope = rig
    host.enable_workspace_executor(executor)
    monkeypatch.setattr(executor, 'prepare', lambda *_: {
        'status': status, 'mask_png': None, 'mask_version': None, 'reason_code': None})
    with pytest.raises(TransportError, match='READY_MASK_MISSING'):
        host._prepare(principal, envelope | {'modality': modality})
    assert not host.tickets and executor.loads == executor.roi == 0
