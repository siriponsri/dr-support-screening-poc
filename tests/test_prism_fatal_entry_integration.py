"""Actual bound PRISM loop, synthetic bytes and fake ROI/folds only; no live app/DB."""
from copy import deepcopy
import ast
import os
from pathlib import Path
import pytest

from dr_support.providers.prism_bound import BoundPlanError
from dr_support.providers import prism_bound as bound
from test_prism_bound_adapter import (
    rig as _adapter_rig,
    frozen_module as _frozen_module,
    forbid_real_runtime as _forbid_real_runtime,
)

adapter_rig = _adapter_rig
frozen_module = _frozen_module
forbid_real_runtime = _forbid_real_runtime


class EntryRejected(RuntimeError):
    pass


def remote(rig, binding, mask, *, before=lambda: None, entry=lambda: None):
    return rig.provider.infer_remote_fenced_prism(
        rig.request, rig.wire, mask_png=mask, binding=binding,
        plan_sha256=bound.sha(bound.canonical(binding)),
        before_forward=before, on_native_roi_entry=entry)


def test_fatal_entry_rejection_propagates_without_roi_or_fallback(adapter_rig):
    rig = adapter_rig
    rig.provider.device = 'cpu'  # Explicit fake preloaded runtime, not resolution/load.
    binding, mask = rig.prepare()
    order = []
    def reject():
        order.append('fatal_entry')
        raise EntryRejected('synthetic refusal')
    with pytest.raises(EntryRejected):
        remote(rig, binding, mask, before=lambda: order.append('source_revalidated'), entry=reject)
    assert order == ['source_revalidated', 'fatal_entry']
    assert rig.calls['roi'] == rig.calls['fold'] == 0
    with pytest.raises(BoundPlanError, match='REPLAY'):
        remote(rig, binding, mask)


def test_fatal_entry_success_precedes_actual_fake_roi(adapter_rig):
    rig = adapter_rig
    rig.provider.device = 'cpu'
    binding, mask = rig.prepare()
    entered = []
    roi = rig.provider.roi
    def checked_roi(*args, **kwargs):
        assert entered == ['entered']
        return roi(*args, **kwargs)
    rig.provider.roi = checked_roi
    result = remote(rig, binding, mask, entry=lambda: entered.append('entered'))
    assert rig.calls['roi'] == 1 and rig.calls['fold'] == 5
    assert result['result']['state'] == 'AI_SUGGESTION'


@pytest.mark.parametrize('change', ['unloaded', 'device_missing'])
def test_remote_port_refuses_legacy_lazy_load_after_source_check(adapter_rig, change):
    rig = adapter_rig
    rig.provider.device = 'cpu'
    binding, mask = rig.prepare()
    entered = []
    def change_runtime():
        if change == 'unloaded': rig.provider.loaded = False
        else: rig.provider.device = None
    with pytest.raises(RuntimeError, match='REMOTE_PRELOADED_RUNTIME_REQUIRED'):
        remote(rig, binding, mask, before=change_runtime, entry=lambda: entered.append(True))
    assert not entered and rig.calls['roi'] == rig.calls['fold'] == 0


def test_remote_requires_both_callbacks_before_consuming_plan(adapter_rig):
    rig = adapter_rig
    binding, mask = rig.prepare()
    before = deepcopy(rig.provider._consumed)
    with pytest.raises(BoundPlanError, match='FATAL_REMOTE_ENTRY_PORT_REQUIRED'):
        remote(rig, binding, mask, entry=None)
    assert rig.provider._consumed == before


@pytest.mark.parametrize('via_env', [False, True])
def test_disabled_profile_rejected_by_actual_resolver_before_factory_construction(monkeypatch, via_env):
    from dr_support.services.prism_remote_profile import PROFILE, reject_disabled_profile
    # Execute the exact startup resolver, without importing API's eager DB app.
    tree = ast.parse((Path(__file__).parents[1] / 'dr_support/app.py').read_text())
    resolver = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_resolve_profile')
    namespace = {'os': os, 'reject_disabled_profile': reject_disabled_profile, 'VALID_PROFILES': ('review', 'model_api', 'full')}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[resolver], type_ignores=[])), 'actual_startup_profile_resolver', 'exec'), namespace)
    if via_env: monkeypatch.setenv('APP_PROFILE', PROFILE)
    with pytest.raises(RuntimeError, match='REMOTE_ENTRY_FENCE_PROFILE_NOT_QUALIFIED'):
        namespace['_resolve_profile'](None if via_env else PROFILE)
    for normal in ('review', 'model_api', 'full'):
        assert namespace['_resolve_profile'](normal) == normal


def test_no_switch_can_register_candidate_profile():
    from dr_support.services.prism_remote_profile import QUALIFIED, register_isolated_remote_profile
    assert QUALIFIED is False
    with pytest.raises(RuntimeError, match='NOT_QUALIFIED'):
        register_isolated_remote_profile(enabled=True, workers=1)
