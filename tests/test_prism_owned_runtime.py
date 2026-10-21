"""Fake models/process handles/clocks, synthetic PNG, no live runtime proof."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace

import httpx
import pytest

from test_prism_remote_transport import rig as _guarded_rig
from test_qa_worker_supervisor import FakeClock, FakeChild
from dr_support.services.prism_remote_transport import BASE, TransportError, canonical, sha
from dr_support.services.prism_owned_runtime import LoadedPrismExecutor, OwnedWorkerController, OwnedWorkerChannel, OwnedRuntimeSession, child_application, owned_gateway_application, register_fixed_owned_runtime
from dr_support.providers.prism_owned_channel import DeadlineHttpExchange, OwnedFixedSessionRemoteProvider, PrivateGatewayChannel
from scripts.qa.worker_supervisor import Policy, SupervisorBlocked


@pytest.fixture
def rig(monkeypatch):
    yield from _guarded_rig.__wrapped__(monkeypatch)


@contextmanager
def fake_load_guard():
    yield SimpleNamespace(forward_attempts=0)


def finish_without_event_loop(coroutine):
    # All awaited fixture operations complete immediately. No Windows socketpair
    # or listener is needed to run these ASGI coroutine contracts.
    with pytest.raises(StopIteration):
        coroutine.send(None)


class BoundProviderFake:
    def __init__(self, backend):
        self.backend, self.loaded, self._loaded_identity = backend, False, None
        self.loads, self.calls = 0, []
        self.fail_load = False
    def _runtime_identity(self):return self.backend.identity()
    def load(self):
        self.loads += 1
        if self.fail_load:raise RuntimeError('SYNTHETIC_LOAD_FAILURE')
        self.loaded = self.backend.loaded = True
        self._loaded_identity = self.backend.identity()
    def prepare_prism_preview_candidate(self, image):return self.backend.prepare(image.data, image.modality)
    def infer_remote_fenced_prism(self, request, image, *, mask_png, binding, plan_sha256, before_forward, on_native_roi_entry):
        self.calls.append((image.data, mask_png, deepcopy(binding)))
        return self.backend.execute(image.data, mask_png, binding, plan_sha256,
            before_forward=before_forward, on_roi_entry=on_native_roi_entry)


def executor(rig):
    provider = BoundProviderFake(rig.executor)
    owned = LoadedPrismExecutor(provider, expected_pins=rig.executor.pins, load_guard=fake_load_guard)
    return provider, owned


@pytest.mark.parametrize('applied_mask', [False, True])
def test_bound_provider_reuses_one_load_and_exact_prepared_wire_mask(rig, applied_mask):
    provider, owned = executor(rig)
    rig.executor.ready_mask = applied_mask
    owned.load_until(owned.clock()+1, lambda: False)
    owned.load_until(owned.clock()+1, lambda: False)
    rig.host.executor = owned
    binding, mask = rig.prepare()
    assert (mask is not None) is applied_mask
    result = rig.run(binding, mask)
    assert provider.loads == owned.load_attempts == 1 and rig.executor.roi == 1
    assert provider.calls[0] == (rig.wire.data, mask, binding)
    assert result['preview_receipt']['wire_sha256'] == binding['wire_sha256']
    assert result['preview_receipt']['mask_sha256'] == binding['mask_sha256']
    with pytest.raises(TransportError):rig.run(binding, mask)
    assert provider.loads == 1 and rig.executor.roi == 1


def test_failed_load_poisoned_no_second_attempt(rig):
    provider, owned = executor(rig)
    provider.fail_load = True
    with pytest.raises(RuntimeError):owned.load_until(owned.clock()+1, lambda: False)
    with pytest.raises(TransportError):owned.load_until(owned.clock()+1, lambda: False)
    assert provider.loads == owned.load_attempts == 1 and rig.executor.roi == 0


def test_hidden_warmup_attempt_detected_even_if_loader_swallowed_exception(rig):
    provider, owned = executor(rig)
    @contextmanager
    def guard():yield SimpleNamespace(forward_attempts=1)
    owned.load_guard = guard
    with pytest.raises(TransportError, match='DURING_LOAD'):
        owned.load_until(owned.clock()+1, lambda: False)
    assert owned.poisoned and owned.load_attempts == 1


def test_model_change_after_grant_stays_fatal_before_fake_roi(rig):
    provider, owned = executor(rig)
    owned.load_until(owned.clock()+1, lambda: False)
    rig.host.executor = owned
    binding, mask = rig.prepare()
    rig.executor.after_gate = lambda: rig.executor.pins.update(config_sha256='f'*64)
    with pytest.raises(TransportError):rig.run(binding, mask)
    assert owned.poisoned and rig.executor.roi == 0 and provider.loads == 1


def controller():
    clock = FakeClock()
    child = FakeChild(clock)
    child.identity = replace(child.identity, model_id='prism-dr-5fold')
    child.live_identity = child.identity
    policy = Policy('prism-dr-5fold', 66, child.identity.owner_scope, 'a'*64, 'GPU-fixture-00000000',
                    max_jobs=2, max_seconds=270, request_seconds=30, drain_seconds=25, monitor_seconds=1)
    calls = []
    def spawn(*, hard_seconds):calls.append(hard_seconds);return child
    owned = OwnedWorkerController(spawn=spawn, policy=policy, clock=clock)
    owned.start()
    return clock, child, owned, calls


def test_one_spawn_request_timeout_force_stop_and_no_restart():
    clock, child, owned, calls = controller()
    owned.supervisor.admit('synthetic_job')
    clock.now += 31
    assert owned.tick() == 'DRAINING'
    clock.now += 24
    assert owned.tick() == 'STOPPED'
    assert [force for _, force in child.signals] == [False, True]
    with pytest.raises(TransportError):owned.start()
    assert calls == [300]


def test_identity_drift_never_signals_unrecognized_pid():
    _, child, owned, _ = controller()
    child.live_identity = replace(child.identity, birth_marker='reused_synthetic_birth_01')
    with pytest.raises(SupervisorBlocked):owned.tick()
    assert child.signals == []


@pytest.mark.parametrize('field,value', [('vram_mib',10241),('rss_bytes',24*1024**3+1),('project_bytes',40*1024**3+1)])
def test_resource_limit_drains_only_owned_fake_child(field, value):
    _, child, owned, _ = controller()
    child.override[field] = value
    assert owned.tick() == 'DRAINING' and child.signals[0] == (child.identity, False)


def test_unknown_exchange_poisoned_and_never_retried():
    _, _, owned, _ = controller()
    calls = []
    def exchange(*a, **k):calls.append(True);raise httpx.ReadError('SYNTHETIC_LOST_ACK')
    channel = OwnedWorkerChannel(owned, exchange=exchange, listener_owned=lambda identity: True)
    with pytest.raises(httpx.ReadError):channel.request('GET', BASE+'/capabilities')
    with pytest.raises(TransportError):channel.request('GET', BASE+'/capabilities')
    assert calls == [True] and channel.quarantined


def test_foreign_listener_refused_before_exchange():
    _, _, owned, _ = controller()
    channel = OwnedWorkerChannel(owned, exchange=lambda *a, **k: pytest.fail('NO_RPC'), listener_owned=lambda identity: False)
    with pytest.raises(TransportError, match='LISTENER'):channel.request('GET',BASE+'/capabilities')


def test_registration_hard_disabled_and_provider_requires_owned_channel():
    with pytest.raises(RuntimeError):register_fixed_owned_runtime(approved=True)
    with pytest.raises(TransportError):OwnedFixedSessionRemoteProvider(object())


@pytest.mark.parametrize('authorization', [None, b'Bearer invalid'])
def test_asgi_auth_before_body_or_preload(rig, authorization):
    provider, owned = executor(rig)
    app, _ = child_application(owned, token='x'*64, issue_id=lambda:'synthetic_0001', epoch='synthetic_epoch')
    async def run():
        sent=[]
        async def never():pytest.fail('UNAUTHORIZED_BODY_MUST_NOT_BE_READ')
        async def send(value):sent.append(value)
        headers=[] if authorization is None else [(b'authorization',authorization)]
        await app({'type':'http','method':'POST','path':BASE+'/execute','headers':headers},never,send)
        assert sent[0]['status'] == 401
    finish_without_event_loop(run())
    assert provider.loads == 0


def test_asgi_start_once_health_exact_pins_and_no_runtime_imports(rig, monkeypatch):
    provider, owned = executor(rig)
    app, _ = child_application(owned, token='x'*64, issue_id=lambda:'synthetic_0001', epoch='synthetic_epoch')
    async def immediate_wait(coroutine, timeout):return await coroutine
    async def immediate_thread(function, *args):return function(*args)
    monkeypatch.setattr('dr_support.services.prism_owned_runtime.asyncio',
        SimpleNamespace(wait_for=immediate_wait,to_thread=immediate_thread,TimeoutError=TimeoutError))
    async def run():
        events=[]
        async def send(value):events.append(value)
        sent=[]
        async def receive():return {'type':'http.request','body':b''}
        async def capture(value):sent.append(value)
        life_calls=[]
        async def life_receive():
            if not life_calls:
                life_calls.append(True)
                return {'type':'lifespan.startup'}
            assert events[0]['type']=='lifespan.startup.complete'
            await app({'type':'http','method':'GET','path':BASE+'/readiness','query_string':b'',
                       'headers':[(b'authorization',b'Bearer '+b'x'*64)]},receive,capture)
            return {'type':'lifespan.shutdown'}
        await app({'type':'lifespan'},life_receive,send)
        assert sent[0]['status']==200 and json.loads(sent[1]['body'])['pins']==rig.executor.pins
    finish_without_event_loop(run())
    assert provider.loads == 1 and rig.executor.roi == 0


def test_absolute_http_deadline_and_no_alternate_destination():
    now=[10.];calls=[]
    def endpoint(request):calls.append(request.url);now[0]=16.;return httpx.Response(200,json={})
    exchange=DeadlineHttpExchange(token='x'*64, transport=httpx.MockTransport(endpoint),clock=lambda:now[0])
    try:
        with pytest.raises(TransportError, match='PRIVATE_ROUTE'):
            exchange('GET','https://other.invalid/',deadline=15)
        assert not calls
        with pytest.raises(TransportError, match='DEADLINE'):
            exchange('GET',BASE+'/capabilities',deadline=15)
        assert len(calls)==1 and calls[0].host=='127.0.0.1'
    finally:exchange.close()


@pytest.mark.parametrize('lost_grant', [False, True])
def test_private_gateway_client_actual_fence_handshake_no_retry_and_unknown_quarantine(rig, lost_grant):
    binding, mask = rig.prepare()
    state={'lost':False,'execute':0}
    def endpoint(request):
        assert request.headers['authorization']=='Bearer '+'x'*64
        if state['lost']:raise httpx.ReadError('SYNTHETIC_PARTITION')
        if request.url.path==BASE+'/readiness':
            return httpx.Response(200,json={'state':'LOADED','epoch':rig.host.epoch,'pins':rig.executor.pins})
        if request.url.path==BASE+'/execute':state['execute']+=1
        headers=dict(request.headers)
        headers['authorization']='Bearer FIXTURE_AUTHORITY'
        code,value=rig.host.handle(request.method,request.url.path,headers,request.content)
        if lost_grant and request.url.path.endswith('/grant'):
            state['lost']=True
            raise httpx.ReadError('SYNTHETIC_LOST_GRANT_ACK')
        return httpx.Response(code,json=value)
    exchange=DeadlineHttpExchange(token='x'*64,transport=httpx.MockTransport(endpoint),port=17860)
    private=PrivateGatewayChannel(exchange,expected_epoch=rig.host.epoch,expected_pins=rig.executor.pins)
    private.establish()
    provider=OwnedFixedSessionRemoteProvider(private,source_authority=rig.authority,wait_seconds=1,poll_seconds=.002)
    try:
        provider.negotiate();provider.prepare_prism_preview_candidate(rig.wire)
        def invoke():
            return provider.infer_bound_prism(rig.request,rig.wire,mask_png=mask,binding=binding,
                plan_sha256=sha(canonical(binding)),before_forward=lambda:None)
        if lost_grant:
            with pytest.raises(TransportError):invoke()
            assert private.quarantined and rig.authority.quarantined
        else:
            assert invoke()['preview_receipt']['wire_sha256']==rig.wire.sha256
        with pytest.raises(TransportError):invoke()
        assert state['execute']==1
    finally:exchange.close()


def test_owned_runtime_session_close_uses_verified_fake_handle_and_bounded_drain():
    clock,child,owned,_=controller()
    # This controller was already started by the fixture; exercise its owned
    # teardown through the session helper, not an arbitrary PID target.
    events=[]
    class FakeWatchdog:
        def __init__(self,controller):pass
        def start(self):events.append('watch-start')
        def close(self):events.append('watch-close')
    def confirmed():
        assert not child.alive
        events.append('reaped-owned-child')
    child.close_confirmed=confirmed
    session=OwnedRuntimeSession(owned,watchdog_factory=FakeWatchdog,wait=lambda seconds:setattr(clock,'now',clock.now+seconds))
    assert session.close()=={'state':'STOPPED','termination_confirmed':True}
    assert clock.now<126 and events==['reaped-owned-child','watch-close']
    with pytest.raises(TransportError):session.start()


def test_http_transport_retry_configuration_refused_without_any_network():
    transport=httpx.HTTPTransport(retries=1)
    try:
        with pytest.raises(ValueError,match='RETRIES'):
            DeadlineHttpExchange(token='x'*64,transport=transport)
    finally:transport.close()


def test_wrong_terminal_scope_cannot_finish_current_supervised_job():
    _,_,owned,_=controller()
    value={'ticket_id':'synthetic_ticket','plan_sha256':'a'*64,'binding':{'model_pins':{'fixture':'pins'}}}
    def exchange(method,path,value=None,**kwargs):
        if method=='POST':return {'job_id':'synthetic_job_01','epoch':'synthetic_epoch'}
        return {'terminal':True,'state':'COMPLETE','job_id':'OTHER','epoch':'synthetic_epoch'}
    channel=OwnedWorkerChannel(owned,exchange=exchange,listener_owned=lambda identity:True)
    channel.request('POST',BASE+'/execute',value,epoch='synthetic_epoch')
    with pytest.raises(TransportError,match='SCOPE'):
        channel.request('GET',BASE+'/jobs/synthetic_job_01',epoch='synthetic_epoch')
    assert channel.quarantined and owned.supervisor.state=='DRAINING'


def test_previously_loaded_provider_cannot_escape_load_guard(rig):
    provider=BoundProviderFake(rig.executor)
    provider.loaded=True
    with pytest.raises(TransportError,match='FRESH_OWNED_PROVIDER'):
        LoadedPrismExecutor(provider,expected_pins=rig.executor.pins,load_guard=fake_load_guard)


def test_surviving_child_stays_unconfirmed_after_bounded_force_once():
    clock,child,owned,calls=controller()
    child.force_succeeds=False
    class FakeWatchdog:
        def __init__(self,controller):pass
        def close(self):pass
    session=OwnedRuntimeSession(owned,watchdog_factory=FakeWatchdog,wait=lambda seconds:setattr(clock,'now',clock.now+seconds))
    with pytest.raises(TransportError,match='UNCONFIRMED'):
        session.close()
    assert clock.now<=126 and [force for _,force in child.signals]==[False,True]
    with pytest.raises(TransportError):owned.start()
    assert calls==[300]


def test_streaming_chunks_cannot_reset_absolute_rpc_deadline():
    now=[0.]
    class SlowSyntheticStream(httpx.SyncByteStream):
        def __iter__(self):
            for chunk in [b'{',b'"fixture":',b'1',b'}']:
                now[0]+=1
                yield chunk
    exchange=DeadlineHttpExchange(token='x'*64,clock=lambda:now[0],
        transport=httpx.MockTransport(lambda request:httpx.Response(200,stream=SlowSyntheticStream())))
    try:
        with pytest.raises(TransportError,match='DEADLINE'):
            exchange('GET',BASE+'/capabilities',deadline=2.5)
        assert now[0]==3
    finally:exchange.close()


def test_owned_gateway_duplicate_auth_never_forwards_or_reads_body():
    app=owned_gateway_application(SimpleNamespace(request=lambda *a,**k:pytest.fail('NO_FORWARD')),token='x'*64)
    async def invoke():
        sent=[]
        async def receive():pytest.fail('NO_UNAUTHORIZED_BODY')
        async def send(value):sent.append(value)
        await app({'type':'http','path':BASE+'/execute','method':'POST',
            'headers':[(b'authorization',b'Bearer '+b'x'*64),(b'authorization',b'Bearer '+b'x'*64)]},receive,send)
        assert sent[0]['status']==401
    finish_without_event_loop(invoke())


@pytest.mark.parametrize('wrong_pin',[False,True])
def test_startup_wait_requires_owned_listener_and_exact_loaded_pins(wrong_pin):
    clock,_,owned,_=controller()
    session=OwnedRuntimeSession(owned,wait=lambda seconds:setattr(clock,'now',clock.now+seconds))
    session.started=True  # Fake fixture has already completed its sole spawn.
    checks=[]
    def listener(identity):checks.append(True);return len(checks)>2
    channel=OwnedWorkerChannel(owned,listener_owned=listener,
        exchange=lambda *a,**k:{'state':'LOADED','pins':{'pin':'wrong' if wrong_pin else 'expected'},'epoch':'fake_epoch'})
    if wrong_pin:
        with pytest.raises(TransportError,match='ATTESTATION'):
            session.wait_loaded(channel,expected_pins={'pin':'expected'},expected_epoch='fake_epoch',seconds=1)
        assert channel.quarantined and owned.supervisor.state=='DRAINING'
    else:
        assert session.wait_loaded(channel,expected_pins={'pin':'expected'},expected_epoch='fake_epoch',seconds=1)['state']=='LOADED'
    assert clock.now<101


def test_absent_startup_listener_times_out_without_second_spawn():
    clock,_,owned,calls=controller()
    session=OwnedRuntimeSession(owned,wait=lambda seconds:setattr(clock,'now',clock.now+seconds))
    session.started=True
    channel=OwnedWorkerChannel(owned,listener_owned=lambda identity:False,exchange=lambda *a,**k:pytest.fail('NO_RPC'))
    with pytest.raises(TransportError,match='STARTUP_DEADLINE'):
        session.wait_loaded(channel,expected_pins={},expected_epoch='fake_epoch',seconds=.3)
    assert owned.supervisor.state=='DRAINING' and calls==[300]
