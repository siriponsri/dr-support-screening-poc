"""Unregistered fixed-session owned-worker candidate. No startup on import.

Child owns BoundLocalPRISM; parent owns LinuxOwnedChild/WorkerSupervisor. Tests
inject fake models, child handles and exchanges. This does NOT qualify Linux
termination or a real network/model path. Existing backend credentials must be
injected; no env discovery, tokens, listeners or subprocesses are created here.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from threading import Event, Lock, RLock, Thread
import time
from types import SimpleNamespace

from dr_support.images import BridgeImage
from dr_support.services.prism_remote_transport import BASE, BoundTransportHost, Principal, TransportError, canonical, sha
from scripts.qa.private_gateway_auth import PrivateGatewayAuth
from scripts.qa.worker_supervisor import ChildIdentity, WorkerSupervisor

MAX_BODY = 20_100_000


@contextmanager
def torch_load_forward_guard():
    # Lazy, future authorized worker only. Offline tests inject a fake guard.
    import torch
    count = SimpleNamespace(forward_attempts=0)
    def deny(module, args):
        count.forward_attempts += 1
        raise TransportError('WARMUP_OR_FORWARD_DURING_LOAD_FORBIDDEN')
    handle = torch.nn.modules.module.register_module_forward_pre_hook(deny)
    try:
        yield count
    finally:
        handle.remove()


class LoadedPrismExecutor:
    """Use the pinned da164ac adapter API; no custom inference/cropping loop."""
    entry_fence_port = True

    def __init__(self, provider, *, expected_pins, clock=time.monotonic, load_guard=torch_load_forward_guard, demo_authorization=None):
        from .case16_qualification import checked_authorization
        self.demo_authorization = checked_authorization(demo_authorization)
        self.demo_prepares = self.demo_executions = 0
        required = ('_runtime_identity', 'load', 'prepare_prism_preview_candidate', 'infer_remote_fenced_prism')
        if not all(callable(getattr(provider, name, None)) for name in required):
            raise TransportError('PINNED_BOUND_PROVIDER_PORT_REQUIRED', 503)
        if getattr(provider, 'loaded', False) or getattr(provider, '_loaded_identity', None) is not None:
            raise TransportError('FRESH_OWNED_PROVIDER_REQUIRED', 503)
        self.provider, self.pins, self.clock = provider, deepcopy(expected_pins), clock
        self.load_guard = load_guard
        self.lock, self.load_attempts, self.loaded, self.poisoned = Lock(), 0, False, False

    def identity(self):
        from .identity_budget import check_identity_budget
        check_identity_budget()
        if self.poisoned or self.provider._runtime_identity() != self.pins:
            raise TransportError('OWNED_PROVIDER_IDENTITY_CHANGED', 503)
        check_identity_budget()
        return deepcopy(self.pins)

    def load_until(self, deadline, cancelled):
        # Called at child startup before listening. Later host jobs reuse it.
        with self.lock:
            self.identity()
            if self.clock() >= deadline or cancelled():
                raise TransportError('OWNED_LOAD_DEADLINE', 503)
            if self.loaded:
                self.loaded_identity()
                return
            if self.load_attempts:
                raise TransportError('LOAD_ONCE_NO_RETRY', 503)
            self.load_attempts = 1
            try:
                # Blocking real load is bounded by the PARENT owned supervisor.
                with self.load_guard() as guard:
                    self.provider.load()
                    if guard.forward_attempts != 0:
                        raise TransportError('WARMUP_OR_FORWARD_DURING_LOAD_FORBIDDEN')
                if self.clock() >= deadline or cancelled():
                    raise TransportError('OWNED_LOAD_DEADLINE', 503)
                self.loaded = True
                self.loaded_identity()
            except BaseException:
                self.poisoned = True
                raise

    def loaded_identity(self):
        self.identity()
        if (not self.loaded or not self.provider.loaded
                or self.provider._loaded_identity != self.pins):
            raise TransportError('OWNED_MODEL_NOT_LOADED_WITH_PINS', 503)
        return deepcopy(self.pins)

    def _wire(self, data, image_id='prepared_wire'):
        if not isinstance(data, bytes):
            raise TransportError('IMMUTABLE_WIRE_REQUIRED')
        # Use the ticket's encoding, never re-encode/resize or reopen a source path.
        media = 'image/png' if data.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg'
        origin = "SYNTHETIC"
        if self.demo_authorization is not None:
            self.demo_authorization.wire(data)
            origin = self.demo_authorization.origin
        return BridgeImage(image_id, data, origin, "fixed-qa-wire", modality="UWF",
                           media_type=media, source_origin=origin)

    def prepare(self, wire, modality):
        self.loaded_identity()
        if modality != 'UWF':
            raise TransportError('FIXED_QA_UWF_ONLY')
        if self.demo_authorization is not None:
            with self.lock:
                if self.demo_prepares >= self.demo_authorization.max_requests:
                    raise TransportError("CASE16_TWO_PREPARATIONS_MAXIMUM")
                self.demo_prepares += 1
        candidate = self.provider.prepare_prism_preview_candidate(self._wire(wire))
        if self.demo_authorization is not None:
            self.demo_authorization.candidate(candidate)
        self.loaded_identity()
        return candidate

    def execute(self, wire, mask, binding, plan_hash, *, before_forward, on_roi_entry):
        self.loaded_identity()
        origin = "SYNTHETIC" if self.demo_authorization is None else self.demo_authorization.origin
        if self.demo_authorization is not None:
            self.demo_authorization.binding(binding)
            if mask is not None:
                raise TransportError("CASE16_NO_APPLIED_MASK")
            with self.lock:
                if self.demo_executions >= self.demo_authorization.max_requests:
                    raise TransportError("CASE16_TWO_EXECUTIONS_MAXIMUM")
                self.demo_executions += 1
        if (binding['admission']['source_origin'] != origin or binding['modality'] != 'UWF'
                or sha(wire) != binding['wire_sha256'] or sha(canonical(binding)) != plan_hash):
            raise TransportError('OWNED_FROZEN_BINDING_CHANGED')
        image = self._wire(wire, binding['image_id'])
        request = SimpleNamespace(image_id=image.image_id, model_id=binding['model_id'], modality='UWF')
        def gate():
            self.loaded_identity()
            before_forward()  # Actual source fence AFTER child loading and queueing.
        def entry():
            self.loaded_identity()
            on_roi_entry()  # Pinned provider calls this OUTSIDE the ROI fallback try.
        try:
            authorization_args = ({'demo_authorization': self.demo_authorization}
                                  if self.demo_authorization is not None else {})
            return self.provider.infer_remote_fenced_prism(request, image, mask_png=mask, binding=deepcopy(binding),
                plan_sha256=plan_hash, before_forward=gate, on_native_roi_entry=entry,
                **authorization_args)
        except BaseException:
            self.poisoned = True  # Failed model work is never retried in this worker.
            raise


def child_application(executor, *, token, issue_id, epoch, clock=time.monotonic, load_seconds=60):
    """Authenticated worker ASGI, no listener registration; preload exactly once.

    Credentials are the existing private backend token supplied by the caller.
    Only that trusted backend receives all three protocol scopes; UI never does.
    Outer auth handles duplicate/missing/invalid headers BEFORE body/dispatch.
    """
    if not 0 < load_seconds <= 120:
        raise ValueError('BOUNDED_CHILD_STARTUP_REQUIRED')
    authorization = getattr(executor, "demo_authorization", None)
    from .case16_qualification import Case16Authorization, checked_authorization
    checked_authorization(authorization)
    if authorization is not None:
        origins = frozenset({authorization.origin}) if type(authorization) is Case16Authorization else authorization.origins
    else:
        origins = frozenset({"SYNTHETIC"})
    principal = Principal('fixed-qa-backend', frozenset({'review-client', 'prepare-source', 'forward-authority'}))
    host = BoundTransportHost(executor, authenticate=lambda headers: principal, issue_id=issue_id,
                              epoch=epoch, clock=clock, job_seconds=30, allowed_origins=origins)
    started = ready = closed = False
    async def app(scope, receive, send):
        nonlocal started, ready, closed
        if scope['type'] == 'lifespan':
            while True:
                event = await receive()
                if event['type'] == 'lifespan.startup':
                    if started:
                        raise TransportError('CHILD_STARTUP_REPLAY_NO_RELOAD')
                    started = True
                    try:
                        await asyncio.to_thread(executor.load_until, clock()+load_seconds, lambda: False)
                        ready = True
                        await send({'type': 'lifespan.startup.complete'})
                    except BaseException:
                        await send({'type': 'lifespan.startup.failed', 'message': 'OWNED_LOAD_FAILED_NO_RETRY'})
                        return
                elif event['type'] == 'lifespan.shutdown':
                    closed = True
                    for job in host.jobs.values():
                        with job.condition:
                            job.cancelled = True
                            job.condition.notify_all()
                    # No success/termination proof is invented for a live job.
                    await send({'type': 'lifespan.shutdown.complete'})
                    return
        else:
            deadline = clock()+5
            identity_cancelled = Event()
            try:
                if not ready or closed:
                    raise TransportError('CHILD_NOT_STARTED', 503)
                if scope.get('query_string'):
                    raise TransportError('UNSUPPORTED_QUERY', 422)
                headers = {key.decode().lower(): value.decode() for key, value in scope.get('headers', [])}
                body = bytearray()
                while True:
                    remaining = deadline-clock()
                    if remaining <= 0:
                        raise TransportError('ABSOLUTE_BODY_DEADLINE', 408)
                    message = await asyncio.wait_for(receive(), remaining)
                    if message['type'] == 'http.disconnect':
                        raise TransportError('CLIENT_DISCONNECTED_NO_RETRY', 409)
                    body.extend(message.get('body', b''))
                    if len(body) > MAX_BODY:
                        raise TransportError('BODY_LIMIT', 413)
                    if not message.get('more_body', False):
                        break
                from .identity_budget import identity_budget
                with identity_budget(deadline, cancelled=identity_cancelled.is_set, clock=clock):
                    if scope['method'] == 'GET' and scope['path'] == BASE+'/readiness':
                        pins = await asyncio.wait_for(asyncio.to_thread(executor.loaded_identity), max(.001, deadline-clock()))
                        status, value = 200, {'state': 'LOADED', 'pins': pins, 'epoch': epoch}
                    else:
                        status, value = await asyncio.wait_for(asyncio.to_thread(host.handle, scope['method'],
                            scope['path'], headers, bytes(body)), max(.001, deadline-clock()))
            except (asyncio.TimeoutError, TransportError) as error:
                status, value = (error.status, {'error': error.code}) if isinstance(error, TransportError) else (408, {'error': 'ABSOLUTE_CONTROL_DEADLINE_NO_RETRY'})
            except Exception as error:
                # No exception text/path/checkpoint details leave this boundary.
                kind = type(error).__name__
                safe = kind if kind in {'RuntimeError','ValueError','TypeError','KeyError','OSError','PermissionError','FileNotFoundError','JSONDecodeError','TimeoutExpired'} else 'OTHER'
                status, value = 503, {'error': 'CONTROL_IDENTITY_OR_HANDLER_FAILED', 'error_class': safe}
            finally:
                identity_cancelled.set()
            if clock() >= deadline and status < 400:
                status, value = 408, {'error': 'ABSOLUTE_CONTROL_DEADLINE_NO_RETRY'}
            data = canonical(value)
            if len(data) > MAX_BODY:
                status, data = 502, b'{"error":"RESPONSE_LIMIT"}'
            await asyncio.wait_for(send({'type': 'http.response.start', 'status': status,
                'headers': [(b'content-type', b'application/json'), (b'cache-control', b'no-store')]}), 1)
            await asyncio.wait_for(send({'type': 'http.response.body', 'body': data}), 1)
    return PrivateGatewayAuth(app, token), host


class OwnedWorkerController:
    """Spawn-only parent lifecycle; independent caller must tick at <=1 second.

    No PID attach/kill, no retry, no new process after STOPPED/unknown identity.
    Existing LinuxOwnedChild provides pidfd signals + hard process alarm. A
    caller cannot use a bool or successful port connect as ownership proof.
    """
    def __init__(self, *, spawn, policy, clock=time.monotonic):
        if policy.model_id != 'prism-dr-5fold' or policy.max_seconds > 270 or policy.drain_seconds > 25 or policy.monitor_seconds > 1:
            raise ValueError('FIXED_300_SECOND_POLICY_REQUIRED')
        self.spawn, self.policy, self.clock = spawn, policy, clock
        self.lock = RLock()
        self.child = self.supervisor = None
        self.attempted = self.poisoned = False
        self.cleanup_identity = None
        self.cleanup_state = None

    def start(self):
        with self.lock:
            if self.attempted:
                raise TransportError('OWNED_WORKER_START_ONCE_NO_RETRY', 503)
            self.attempted = True
            try:
                self.child = self.spawn(hard_seconds=300)
                identity = self.child.identity
                # Only the exact spawn-owned, identity-verifying handle may be
                # used for partial-start cleanup; never reconstruct a PID target.
                if (isinstance(identity, ChildIdentity) and type(identity.pid) is int
                        and identity.pid > 1 and identity.pid != self.policy.parent_pid
                        and identity.parent_pid == self.policy.parent_pid
                        and identity.owner_scope == self.policy.owner_scope
                        and identity.command_sha256 == self.policy.command_sha256
                        and identity.model_id == self.policy.model_id
                        and isinstance(identity.birth_marker, str) and 16 <= len(identity.birth_marker) <= 256
                        and self.child.atomic_identity_signals is True):
                    self.cleanup_identity = identity
                self.supervisor = WorkerSupervisor(self.policy, self.child, clock=self.clock)
            except BaseException:
                self.poisoned = True
                self.close()
                raise

    def tick(self):
        with self.lock:
            if self.cleanup_state is not None:
                return self._cleanup_tick()
            if not self.supervisor:
                raise TransportError('OWNED_WORKER_NOT_STARTED', 503)
            state = self.supervisor.tick()
            if state not in {'IDLE', 'BUSY'}:
                self.poisoned = True
            return state

    def _cleanup_tick(self):
        if self.cleanup_state in {'STOPPED', 'UNCONFIRMED_STOP'}:
            return self.cleanup_state
        try:
            inspect = getattr(self.child, 'inspect', None)
            if callable(inspect):
                alive = inspect()  # Pinned-handle liveness, without resource sampling.
            else:
                observation = self.child.observe()
                if observation.identity != self.cleanup_identity:
                    raise RuntimeError('OWNED_CLEANUP_IDENTITY_CHANGED')
                alive = observation.alive
            if alive is False:
                self.cleanup_state = 'STOPPED'
                return self.cleanup_state
        except Exception:
            pass  # Missing observation never counts as termination proof.
        now = self.clock()
        if now >= self.cleanup_force_at and self.cleanup_state == 'DRAINING':
            self.cleanup_state = 'FORCE_PENDING'
            try: self.child.signal_verified(self.cleanup_identity, force=True)
            except Exception: pass
        if now >= self.cleanup_deadline:
            self.cleanup_state = 'UNCONFIRMED_STOP'
        return self.cleanup_state

    def close(self):
        with self.lock:
            if self.cleanup_state is not None:
                return
            if self.supervisor:
                try:
                    self.supervisor.close()
                    if self.supervisor.state not in {'UNVERIFIED', 'UNCONFIRMED_STOP'}:
                        return
                except Exception:
                    pass
            self.poisoned = True
            if self.cleanup_identity is None:
                self.cleanup_state = 'UNCONFIRMED_STOP'
                return
            now = self.clock()
            self.cleanup_deadline = now + self.policy.drain_seconds
            self.cleanup_force_at = self.cleanup_deadline - min(1, self.policy.drain_seconds / 2)
            self.cleanup_state = 'DRAINING'
            try: self.child.signal_verified(self.cleanup_identity, force=False)
            except Exception: pass

    def require_live(self):
        if self.tick() not in {'IDLE', 'BUSY'} or self.poisoned:
            raise TransportError('OWNED_WORKER_CLOSED_OR_QUARANTINED', 503)


class OwnedWorkerChannel:
    """Parent channel port for the app's existing before_forward protocol.

    exchange MUST implement deadline-bound HTTP with injected credentials and
    zero retries. In tests it is a synthetic endpoint. No default live exchange
    is provided/registered. listener_owned must use the existing inode/PID check.
    Any unknown RPC poisons new work; the app's existing grant journal retains
    quarantine when it cannot obtain authentic matching terminal/entry proof.
    """
    def __init__(self, controller, *, exchange, listener_owned):
        self.controller, self.exchange, self.listener_owned = controller, exchange, listener_owned
        self.seen, self.job_id, self.quarantined = set(), None, False
        self.lock = Lock()
        self.remote_scope = None

    def request(self, method, path, value=None, *, epoch=None, authority=False):
        self.controller.require_live()
        try:
            listener_matches = self.listener_owned(self.controller.child.identity)
        except BaseException:
            self.quarantined = True
            self.controller.close()
            raise
        if self.quarantined or not listener_matches:
            self.quarantined = True
            self.controller.close()
            raise TransportError('OWNED_LISTENER_OR_TRANSPORT_QUARANTINED', 503)
        admission = method == 'POST' and path == BASE+'/execute'
        key = sha(canonical(value)) if admission else None
        if admission:
            with self.lock:
                if key in self.seen or self.job_id is not None:
                    raise TransportError('OWNED_RPC_REPLAY_OR_CONCURRENT_ADMISSION')
                self.seen.add(key)
                self.job_id = 'owned_'+key[:32]
                self.controller.supervisor.admit(self.job_id)
        try:
            status = self.exchange(method, path, value, epoch=epoch, authority=authority,
                                   deadline=self.controller.clock()+5)
            with self.lock:
                if admission:
                    if not isinstance(status.get('job_id'), str) or status.get('epoch') != epoch:
                        raise TransportError('OWNED_START_SCOPE_INVALID')
                    self.remote_scope = {'job_id': status['job_id'], 'epoch': epoch, 'ticket_id': value['ticket_id'],
                        'plan_sha256': value['plan_sha256'], 'pins': value['binding']['model_pins']}
                if method == 'GET' and '/jobs/' in path and self.job_id:
                    if not self.remote_scope or any(status.get(k) != v for k, v in self.remote_scope.items()):
                        raise TransportError('OWNED_TERMINAL_SCOPE_CHANGED')
                if method == 'GET' and '/jobs/' in path and status.get('terminal') is True and self.job_id:
                    self.controller.supervisor.finish(self.job_id, success=status.get('state') == 'COMPLETE')
                    self.job_id = None
            return status
        except BaseException:
            self.quarantined = True
            self.controller.close()
            raise


def register_fixed_owned_runtime(*args, **kwargs):
    raise RuntimeError('OWNED_FIXED_RUNTIME_NOT_REVIEWED_OR_HOST_QUALIFIED')


def owned_gateway_application(channel, *, token):
    """Mount under existing QA gateway, no listener or auth-settings changes.

    Start/preload/qualify the child before serving this app. Parent ownership
    and resources are checked on EVERY forwarded RPC, including status/grant.
    The existing app authority and child host perform the grant/entry handshake.
    """
    async def app(scope, receive, send):
        if scope['type'] == 'lifespan':
            raise TransportError('OWNED_RUNTIME_LIFECYCLE_MUST_BE_EXTERNAL')
        try:
            if scope.get('query_string'):
                raise TransportError('UNSUPPORTED_QUERY', 422)
            body = bytearray()
            deadline = time.monotonic()+5
            while True:
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    raise TransportError('ABSOLUTE_BODY_DEADLINE', 408)
                event = await asyncio.wait_for(receive(), remaining)
                if event['type'] == 'http.disconnect':
                    raise TransportError('CLIENT_DISCONNECTED_NO_RETRY')
                body.extend(event.get('body', b''))
                if len(body) > MAX_BODY:
                    raise TransportError('BODY_LIMIT', 413)
                if not event.get('more_body', False):
                    break
            import json
            headers = {k.lower(): v for k, v in scope['headers']}
            value = json.loads(body) if body else None
            value = await asyncio.wait_for(asyncio.to_thread(channel.request, scope['method'], scope['path'], value,
                epoch=headers.get(b'x-prism-epoch', b'').decode() or None, authority=True), max(.001, deadline-time.monotonic()))
            status = 202 if scope['method'] == 'POST' and scope['path'] == BASE+'/execute' else 200
        except Exception as error:
            channel.quarantined = True
            channel.controller.close()
            status = error.status if isinstance(error, TransportError) else 503
            value = {'error': error.code if isinstance(error, TransportError) else 'OWNED_GATEWAY_FAILED_NO_RETRY'}
        data = canonical(value)
        if len(data) > MAX_BODY:
            status, data = 502, b'{"error":"RESPONSE_LIMIT"}'
        await asyncio.wait_for(send({'type': 'http.response.start', 'status': status,
            'headers': [(b'content-type', b'application/json'), (b'cache-control', b'no-store')]}), 1)
        await asyncio.wait_for(send({'type': 'http.response.body', 'body': data}), 1)
    return PrivateGatewayAuth(app, token)


class IndependentWatchdog:
    """Separate from model/RPC threads; existing child hard alarm is backstop."""
    def __init__(self, controller):
        self.controller, self.done, self.failure = controller, Event(), None
        self.thread = None

    def start(self):
        if self.thread is not None:
            raise TransportError('WATCHDOG_START_ONCE')
        def watch():
            try:
                while not self.done.wait(.25):
                    if self.controller.tick() in {'STOPPED', 'UNVERIFIED', 'UNCONFIRMED_STOP'}:
                        return
            except BaseException:
                self.failure = 'OWNED_CONTROL_FAILED_QUARANTINED'
                self.controller.poisoned = True
        self.thread = Thread(target=watch, daemon=False)
        self.thread.start()

    def close(self):
        self.done.set()
        if self.thread and self.thread.ident is not None:
            self.thread.join(timeout=2)
            if self.thread.is_alive():
                raise TransportError('CONTROL_STOP_UNCONFIRMED', 503)


# One fixed-session factory call runs in its parent's context. Publish ownership
# before starting either monitor so a failed assignment cannot lose resources.
_PARTIAL_MONITORS = ContextVar('owned_prism_partial_monitors', default=None)


def pending_monitor_cleanup():
    return _PARTIAL_MONITORS.get()


def acknowledge_monitor_transfer(controller):
    owner = _PARTIAL_MONITORS.get()
    if (owner is None or getattr(controller, 'gpu_monitor', None) is not owner.gpu_monitor
            or getattr(controller, 'project_disk_monitor', None) is not owner.project_disk_monitor):
        raise TransportError('OWNED_MONITOR_TRANSFER_MISMATCH', 503)
    _PARTIAL_MONITORS.set(None)


def linux_owned_controller(argv, *, owner_scope, env, max_jobs=2):
    """Concrete existing pidfd adapter binding; NEVER invoked by offline tests.

    Source/runtime/GPU pins and private credential files remain the deployment
    caller's reviewed responsibility. No shell, sudo, PID attachment or defaults.
    """
    import os
    from pathlib import Path
    from types import SimpleNamespace
    if _PARTIAL_MONITORS.get() is not None:
        raise TransportError('PARTIAL_MONITOR_CLEANUP_UNCONFIRMED', 503)
    from scripts.qa.linux_owned_child import LinuxOwnedChild, LinuxResources, command_digest
    from scripts.qa.worker_supervisor import Policy
    gpu = 'GPU-044a8b11-4729-458b-a07b-297e45439419'
    if env.get('CUDA_VISIBLE_DEVICES') != gpu:
        raise TransportError('GPU0_EXPLICIT_UUID_REQUIRED')
    from scripts.qa.disk_monitor import ProjectDiskMonitor
    disk = ProjectDiskMonitor(Path('/home/siripon/projects/dr-model-api-qa'))
    from scripts.qa.gpu_monitor import GPU0Monitor
    gpu_monitor = GPU0Monitor(gpu)
    resources = LinuxResources(Path('/home/siripon/projects/dr-model-api-qa'), disk_monitor=disk, gpu_monitor=gpu_monitor)
    policy = Policy('prism-dr-5fold', os.getpid(), owner_scope, command_digest(argv), gpu,
                    max_jobs=max_jobs, max_seconds=270, request_seconds=30, drain_seconds=25, monitor_seconds=1)
    def spawn(*, hard_seconds):
        return LinuxOwnedChild.spawn(argv, model_id=policy.model_id, owner_scope=owner_scope,
            resource_provider=resources, hard_seconds=hard_seconds, env=env)
    ownership = SimpleNamespace(project_disk_monitor=disk, gpu_monitor=gpu_monitor)
    _PARTIAL_MONITORS.set(ownership)
    try:
        disk.start()
        gpu_monitor.start()
        controller = OwnedWorkerController(spawn=spawn, policy=policy)
        controller.project_disk_monitor = disk
        controller.gpu_monitor = gpu_monitor
        # Caller acknowledges only AFTER assignment; an interruption between
        # return and assignment must still leave parent-visible ownership.
        return controller
    except BaseException:
        cleanup_error = None
        try:
            gpu_monitor.close()
        except BaseException as error:
            cleanup_error = error
        try:
            disk.close()
        except BaseException as error:
            if cleanup_error is None:
                cleanup_error = error
        if cleanup_error is not None:
            # Retain exact partial resources for parent finally. No restart or
            # closed-port-only cleanup proof can discard this owned handle.
            raise cleanup_error
        _PARTIAL_MONITORS.set(None)
        raise


class OwnedRuntimeSession:
    """Wire spawn/watchdog and a bounded verified teardown; never restart.

    start() is an explicit future deployment action, not registration. After
    close, STOPPED plus LinuxOwnedChild.close_confirmed is the termination proof.
    Unknown identity/stop never permits a new worker or journal reset.
    """
    def __init__(self, controller, *, watchdog_factory=IndependentWatchdog, wait=time.sleep):
        self.controller, self.watchdog, self.wait = controller, watchdog_factory(controller), wait
        self.started, self.closed = False, False

    def start(self):
        if self.started or self.closed:
            raise TransportError('RUNTIME_SESSION_NO_RESTART')
        self.started = True
        try:
            self.controller.start()
            self.watchdog.start()
        except BaseException:
            # Partial controller/watchdog startup still owns a child. Confirm
            # bounded teardown or surface explicit quarantine, never restart.
            self.close()
            raise

    def close(self):
        self.closed = True
        deadline = self.controller.clock()+26
        try:
            self.controller.close()
            while self.controller.clock() < deadline:
                state = self.controller.tick()
                if state == 'STOPPED':
                    self.controller.child.close_confirmed()
                    return {'state': 'STOPPED', 'termination_confirmed': True}
                if state in {'UNVERIFIED', 'UNCONFIRMED_STOP'}:
                    break
                self.wait(.25)
            raise TransportError('OWNED_TERMINATION_UNCONFIRMED_QUARANTINE_REQUIRED', 503)
        except Exception:
            raise TransportError('OWNED_TERMINATION_UNCONFIRMED_QUARANTINE_REQUIRED', 503) from None
        finally:
            self.watchdog.close()

    def wait_loaded(self, channel, *, expected_pins, expected_epoch, seconds=60):
        if not self.started or self.closed or not 0 < seconds <= 120:
            raise TransportError('BOUNDED_OWNED_STARTUP_REQUIRED')
        deadline = self.controller.clock()+seconds
        while self.controller.clock() < deadline:
            self.controller.require_live()
            # False means not yet listening. The existing Linux inode checker
            # RAISES for a listener belonging to any other process/address.
            try:
                listener_matches = channel.listener_owned(self.controller.child.identity)
            except BaseException:
                channel.quarantined = True
                self.controller.close()
                raise
            if listener_matches:
                try:
                    status = channel.request('GET', BASE+'/readiness')
                    if status != {'state': 'LOADED', 'pins': expected_pins, 'epoch': expected_epoch}:
                        raise TransportError('OWNED_LOADED_ATTESTATION_MISMATCH')
                    return status
                except BaseException:
                    channel.quarantined = True
                    self.controller.close()
                    raise
            self.wait(.1)
        self.controller.close()
        raise TransportError('OWNED_STARTUP_DEADLINE_NO_RETRY', 503)
