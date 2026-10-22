"""Partial-start cleanup and aggregate sampler budget; fake handles/clocks only."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from dr_support.services import prism_owned_runtime as runtime
from dr_support.services.prism_remote_transport import TransportError
from scripts.qa import linux_owned_child as linux
from test_prism_owned_runtime import controller


@pytest.mark.parametrize('failure', ['observation', 'constructor', 'watchdog'])
def test_session_partial_start_confirms_exact_owned_cleanup(monkeypatch, failure):
    clock, child, prior, _ = controller()
    child.inspect = lambda:child.alive
    confirmed = []
    child.close_confirmed = lambda:confirmed.append(not child.alive)
    owned = runtime.OwnedWorkerController(spawn=lambda **kwargs:child, policy=prior.policy, clock=clock)
    if failure == 'observation': child.observation_fails = True
    if failure == 'constructor':
        def reject(*args, **kwargs): raise ValueError('FIXTURE_CONSTRUCTOR_VALIDATION')
        monkeypatch.setattr(runtime, 'WorkerSupervisor', reject)
    events = []
    class Watchdog:
        def __init__(self, controller): pass
        def start(self):
            events.append('start')
            if failure == 'watchdog': raise RuntimeError('FIXTURE_WATCHDOG_START')
        def close(self): events.append('close')
    session = runtime.OwnedRuntimeSession(owned, watchdog_factory=Watchdog,
        wait=lambda seconds:setattr(clock, 'now', clock.now+seconds))
    with pytest.raises((RuntimeError, ValueError)):
        session.start()
    assert confirmed == [True] and not child.alive and events[-1] == 'close'
    assert child.signals and all(identity == child.identity for identity, force in child.signals)
    assert child.signals[-1][1] is True and clock.now <= 125
    with pytest.raises(TransportError, match='NO_RESTART'): session.start()


def test_unconfirmed_partial_start_survivor_preserves_handle_and_quarantine():
    clock, child, prior, _ = controller()
    child.observation_fails = True
    child.force_succeeds = False
    child.inspect = lambda:True
    child.close_confirmed = lambda:pytest.fail('Surviving child must not be reaped as confirmed')
    owned = runtime.OwnedWorkerController(spawn=lambda **kwargs:child, policy=prior.policy, clock=clock)
    events = []
    class Watchdog:
        def __init__(self, controller): pass
        def start(self): pytest.fail('Supervisor failed before watchdog start')
        def close(self): events.append('close')
    session = runtime.OwnedRuntimeSession(owned, watchdog_factory=Watchdog,
        wait=lambda seconds:setattr(clock, 'now', clock.now+seconds))
    with pytest.raises(TransportError, match='UNCONFIRMED_QUARANTINE'):
        session.start()
    assert owned.child is child and child.alive and owned.cleanup_state == 'UNCONFIRMED_STOP'
    assert events == ['close'] and clock.now <= 126
    assert len(child.signals) == 2 and child.signals[-1][1] is True


def test_partial_start_foreign_identity_never_signaled():
    clock, child, prior, _ = controller()
    child.identity = replace(child.identity, parent_pid=999)
    child.live_identity = child.identity
    owned = runtime.OwnedWorkerController(spawn=lambda **kwargs:child, policy=prior.policy, clock=clock)
    with pytest.raises(RuntimeError, match='UNSAFE_OR_UNRECOGNIZED'):
        owned.start()
    owned.close()
    assert not child.signals and owned.tick() == 'UNCONFIRMED_STOP'


def test_real_watchdog_object_thread_start_failure_still_confirms_owned_cleanup(monkeypatch):
    clock, child, prior, _ = controller()
    confirmed = []
    child.close_confirmed = lambda:confirmed.append(not child.alive)
    class FailedThread:
        ident = None
        def __init__(self, **kwargs): pass
        def start(self): raise RuntimeError('FIXTURE_THREAD_START_FAILURE')
        def join(self, **kwargs): pytest.fail('Cannot join a thread that never started')
    monkeypatch.setattr(runtime, 'Thread', FailedThread)
    owned = runtime.OwnedWorkerController(spawn=lambda **kwargs:child, policy=prior.policy, clock=clock)
    session = runtime.OwnedRuntimeSession(owned, wait=lambda seconds:setattr(clock, 'now', clock.now+seconds))
    with pytest.raises(RuntimeError, match='FIXTURE_THREAD_START_FAILURE'):
        session.start()
    assert confirmed == [True] and not child.alive and session.watchdog.done.is_set()


def test_cached_monitor_reads_share_half_second_resource_budget(tmp_path, monkeypatch):
    now = [10.0]
    calls = []
    def gpu_sample():
        calls.append('gpu')
        measured = now[0]
        now[0] += .18
        return dict(gpu_uuid='GPU-fixture-00000000', vram_mib=123, gpu_observed_at=measured)
    def disk_sample():
        calls.append('disk'); now[0] += .18
        return 456
    monkeypatch.setattr(linux.subprocess, 'run', lambda *a, **k:pytest.fail('No per-tick subprocess scan'))
    monkeypatch.setattr(linux.Path, 'read_text', lambda self:'VmRSS: 8 kB\n')
    sample = linux.LinuxResources(tmp_path, clock=lambda:now[0],
        gpu_monitor=SimpleNamespace(sample=gpu_sample, failure_detail=None),
        disk_monitor=SimpleNamespace(sample=disk_sample, failure_detail=None))(77)
    assert sample['rss_bytes'] == 8192 and sample['vram_mib'] == 123
    assert sample['gpu_observed_at'] == 10.0
    assert calls == ['gpu', 'disk'] and now[0] < 10.5


def test_late_gpu_monitor_read_cannot_start_disk_read(tmp_path, monkeypatch):
    now, calls = [10.0], []
    def slow():
        calls.append('gpu'); now[0] += .51
        return dict(gpu_uuid='GPU-fixture-00000000', vram_mib=123, gpu_observed_at=10.0)
    def disk():
        pytest.fail('Expired sample cannot continue to disk read')
    with pytest.raises(RuntimeError, match='RESOURCE_SAMPLE_DEADLINE'):
        linux.LinuxResources(tmp_path, clock=lambda:now[0],
            gpu_monitor=SimpleNamespace(sample=slow, failure_detail=None),
            disk_monitor=SimpleNamespace(sample=disk, failure_detail=None))(77)
    assert calls == ['gpu']


def test_late_disk_monitor_result_is_rejected_before_rss_read(tmp_path, monkeypatch):
    now = [10.0]
    def gpu():
        now[0] += .4
        return dict(gpu_uuid='GPU-fixture-00000000', vram_mib=123, gpu_observed_at=10.0)
    def disk():
        now[0] += .11
        return 456
    monkeypatch.setattr(linux.Path, 'read_text', lambda self:pytest.fail('Late sample cannot read RSS'))
    with pytest.raises(RuntimeError, match='RESOURCE_SAMPLE_DEADLINE'):
        linux.LinuxResources(tmp_path, clock=lambda:now[0],
            gpu_monitor=SimpleNamespace(sample=gpu, failure_detail=None),
            disk_monitor=SimpleNamespace(sample=disk, failure_detail=None))(77)
