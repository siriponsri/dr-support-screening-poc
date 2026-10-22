from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
import pytest
from test_prism_bound_adapter import rig as adapter_rig  # noqa: F401
from test_prism_bound_adapter import frozen_module as frozen_module
from test_prism_bound_adapter import forbid_real_runtime as forbid_real_runtime
from test_prism_owned_runtime import controller
from dr_support.services.prism_owned_runtime import LoadedPrismExecutor
from dr_support.services.prism_owned_runtime import OwnedWorkerController
from scripts.qa.worker_supervisor import SupervisorBlocked
from dr_support.providers import prism_bound as bound

@contextmanager
def fake_guard():
    yield SimpleNamespace(forward_attempts=0)

def setup_executor(rig,monkeypatch):
    pins=rig.provider._runtime_identity()
    rig.provider.loaded=False
    rig.provider._loaded_identity=None
    calls=[]
    def fake_load():
        calls.append(True)
        rig.provider.loaded=True
        rig.provider.device='cpu'
        rig.provider._loaded_identity=deepcopy(pins)
    monkeypatch.setattr(rig.provider,'load',fake_load)
    executor=LoadedPrismExecutor(rig.provider,expected_pins=pins,load_guard=fake_guard)
    executor.load_until(executor.clock()+1,lambda:False)
    return executor,calls

@pytest.mark.parametrize('status',['READY','UNCERTAIN'])
def test_owned_executor_uses_actual_bound_loop(adapter_rig,monkeypatch,status):  # noqa: F811
    rig=adapter_rig
    rig.calls['status']=status
    executor,loads=setup_executor(rig,monkeypatch)
    executor.prepare(rig.wire.data,'UWF')
    binding,mask=rig.prepare()
    events=[]
    response=executor.execute(rig.wire.data,mask,binding,bound.sha(bound.canonical(binding)),
        before_forward=lambda:events.append('gate'),on_roi_entry=lambda:events.append('entry'))
    assert events==['gate','entry'] and len(loads)==1
    assert rig.calls['roi']==1 and rig.calls['fold']==5
    assert response['preview_receipt']['mask_sha256']==binding['mask_sha256']

def test_owned_executor_fatal_rejection_through_actual_bound_loop(adapter_rig,monkeypatch):  # noqa: F811
    rig=adapter_rig
    executor,_=setup_executor(rig,monkeypatch)
    binding,mask=rig.prepare()
    def deny():raise RuntimeError('INDEPENDENT_ENTRY_DENIAL')
    with pytest.raises(RuntimeError,match='INDEPENDENT_ENTRY_DENIAL'):
        executor.execute(rig.wire.data,mask,binding,bound.sha(bound.canonical(binding)),before_forward=lambda:None,on_roi_entry=deny)
    assert executor.poisoned and rig.calls['roi']==rig.calls['fold']==0

def test_one_second_policy_drains_for_sampler_within_two_second_command_allowance():
    clock,child,owned,_=controller()
    observe=child.observe
    def slow_sample():
        clock.now+=1.1
        return observe()
    child.observe=slow_sample
    assert owned.tick()=='DRAINING'
    assert owned.supervisor.reason=='MONITORING_GAP'

def test_failed_supervisor_construction_can_still_stop_owned_spawn():
    clock,child,prior,_=controller()
    child.observation_fails=True
    owned=OwnedWorkerController(spawn=lambda **kwargs:child,policy=prior.policy,clock=clock)
    with pytest.raises(SupervisorBlocked,match='OBSERVATION_UNAVAILABLE'):
        owned.start()
    assert owned.child is child and owned.supervisor is None
    child.observation_fails=False  # retained owned handle is usable again
    owned.close()
    assert child.signals, 'Spawned child receives no cleanup signal when supervisor construction failed'
