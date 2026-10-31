"""Regular-service control gateway on dr-train (owner-approved 2026-10-31).

One CPU process owns 127.0.0.1:7860, the daily authority (regular_authority.py)
and the scheduler. The GPU child is the reviewed m1_session worker, started on
demand on 127.0.0.1:7861 only for funded work inside AI hours, and stopped when
idle. Charged calls keep their existing routes (``/v1/predict/dr``,
``/v1/prism-bound/execute``) and carry ``X-DR-Ticket``. The child's admission
receipts are answered here: a hold becomes a durable intent BEFORE the child may
dispatch. See docs/milestone/m1/M1_REGULAR_SERVICE_DESIGN.md.

Import is inert. ``ControlService`` takes an injected runtime and clocks so the
gateway, scheduler and lifecycle are tested offline with a fake child; the real
``HostRuntime`` exists only on the approved host.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from hmac import compare_digest
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import regular_authority as ra  # noqa: E402

CONTROL_PORT = 7860
CHILD_PORT = 7861
REGULAR = '/v1/regular'
GLOBAL_ROUTE = '/v1/predict/dr'
PRISM_BASE = '/v1/prism-bound'
PRISM_EXECUTE = PRISM_BASE + '/execute'
CHARGED = {GLOBAL_ROUTE: 'grader', PRISM_EXECUTE: 'prism'}
PRISM_CONTROL_POST = re.compile(re.escape(PRISM_BASE) + r'/(?:prepare|jobs/[A-Za-z0-9_-]{8,80}/(?:grant|cancel))')
CACHED_GETS = ('/health', '/v1/models')
PRINCIPAL = 'shared-backend'  # The only principal until per-user credentials are approved.
WORKSTATION = re.compile(r'[A-Za-z0-9_.:-]{1,120}')
TICKET = re.compile(r'tkt_[a-f0-9]{32}')
REQUEST_ID = re.compile(r'm1_[0-9]{4}_[a-f0-9]{16}')
SHA = re.compile(r'[a-f0-9]{64}')
MAX_BODY = 20_100_000
LOAD_DEADLINE_SECONDS = 240
RETIRE_JOBS, RETIRE_SECONDS = 42, 2640   # Inside WorkerSupervisor's 42 jobs / 2700 s.
FUND_AHEAD_SECONDS = 100                 # Fund the next segment this long before the current one ends.
STOP_MARGIN_SECONDS = 40                 # Drain (20 s) plus force/reap margin before funded time ends.
PROMOTE_MIN_SECONDS = 90                 # Never open a dispatch window the funded time cannot cover.
FAILURE_BACKOFF_SECONDS = 600            # No automatic restart storm after a failed load.
GLOBAL_TERMINAL_SECONDS = 45             # Native 30 s request limit plus receipt margin.
DISPATCH_WAIT_SECONDS = 10               # Well inside the review app's 30 s grading client timeout.
PRISM_TERMINAL_SECONDS = 60              # PRISM job 24 s plus status and receipt margin.
ON_DEMAND_WARNING = ('The model server starts on demand inside AI hours (06:00-22:00 Bangkok); '
                     'the first request may wait while it loads.')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def new_json(path, value):
    """Create-only receipt, as the child's own m1_session receipts."""
    path = Path(path)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as handle:
        handle.write(canonical(value))
        handle.flush()
        os.fsync(handle.fileno())


def read_json(path, limit=65536):
    raw = Path(path).read_bytes()
    if len(raw) > limit:
        raise ValueError('RECEIPT_TOO_LARGE')
    return json.loads(raw)


class ControlService:
    """ASGI gateway plus the scheduler/lifecycle step. Every refusal is a fixed code."""

    def __init__(self, authority, runtime, *, token, models, operations, discovery_path=None,
                 monotonic=time.monotonic, principal=PRINCIPAL):
        if not isinstance(token, str) or not 32 <= len(token) <= 1024 or not token.isascii():
            raise ValueError('PRIVATE_TOKEN_CONFIGURATION_REQUIRED')
        self.authority, self.runtime, self.monotonic = authority, runtime, monotonic
        self.expected = b'Bearer ' + token.encode('ascii')
        self.models, self.operations, self.principal = models, operations, principal
        self.discovery_path = Path(discovery_path) if discovery_path else None
        self.discovery = self._load_discovery()
        self.dispatch_lock = asyncio.Lock()
        self.current = None              # The one ticket whose call is being forwarded.
        self.receipts = {}               # request_id -> handled state
        self.funded_until = None         # UTC end of the child's funded time
        self.epoch = None
        self.last_activity = None        # monotonic time of the last open ticket or call
        self.warm_until = None
        self.backoff_until = None
        self.discovery_epoch = None
        self.refresh = None
        self.last_reason = None

    # ------------------------------------------------------------------ ASGI

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'lifespan':
            message = await receive()
            if message['type'] == 'lifespan.startup':
                await send({'type': 'lifespan.startup.complete'})
                message = await receive()
            if message['type'] == 'lifespan.shutdown':
                await send({'type': 'lifespan.shutdown.complete'})
            return
        if scope['type'] != 'http':
            return
        headers = {}
        for key, value in scope.get('headers', []):
            headers.setdefault(key.lower(), []).append(value)
        authorization = headers.get(b'authorization', [])
        if len(authorization) != 1 or len(authorization[0]) > 2048 or not compare_digest(authorization[0], self.expected):
            return await self.respond(send, 401, {'detail': 'Unauthorized'}, extra=[(b'www-authenticate', b'Bearer')])
        path, method = scope['path'], scope['method']
        try:
            if path.startswith(REGULAR + '/') or path == REGULAR:
                return await self.regular(scope, receive, send, headers)
            if method == 'POST' and path in CHARGED:
                return await self.charged(scope, receive, send, headers)
            if method == 'GET' or (method == 'POST' and PRISM_CONTROL_POST.fullmatch(path)):
                return await self.passthrough(scope, receive, send, headers)
            return await self.respond(send, 405, {'detail': 'Outside the regular service scope'})
        except ra.AuthorityError as error:
            return await self.respond(send, 409, {'detail': 'Request not admitted; no inference dispatched',
                                                  'code': str(error)})

    async def respond(self, send, status, value, *, extra=()):
        await send({'type': 'http.response.start', 'status': status,
                    'headers': [(b'content-type', b'application/json'), (b'cache-control', b'no-store'), *extra]})
        await send({'type': 'http.response.body', 'body': canonical(value)})

    async def body(self, receive):
        data = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                raise ra.AuthorityError('CLIENT_DISCONNECTED_BEFORE_ADMISSION')
            data.extend(message.get('body', b''))
            if len(data) > MAX_BODY:
                raise ra.AuthorityError('BODY_LIMIT')
            if not message.get('more_body'):
                return bytes(data)

    @staticmethod
    def one(headers, name, pattern):
        values = headers.get(name, [])
        if len(values) != 1:
            return None
        value = values[0].decode('ascii', 'replace')
        return value if pattern.fullmatch(value) else None

    # ------------------------------------------------------------------ regular API

    async def regular(self, scope, receive, send, headers):
        workstation = self.one(headers, b'x-dr-workstation', WORKSTATION)
        if workstation is None:
            return await self.respond(send, 400, {'detail': 'Workstation ID required', 'code': 'WORKSTATION_REQUIRED'})
        path, method = scope['path'][len(REGULAR):], scope['method']
        if method == 'GET' and path == '/status':
            return await self.respond(send, 200, self.status(workstation))
        if method == 'POST' and path == '/tickets':
            value = json.loads(await self.body(receive))
            if not isinstance(value, dict) or set(value) - {'idempotency_key', 'request_digest', 'kind', 'model_id',
                                                            'modality', 'source_sha256', 'pair_key'}:
                raise ra.AuthorityError('TICKET_REQUEST_INVALID')
            ticket = self.authority.submit(principal=self.principal, workstation=workstation, **value)
            self.last_activity = self.monotonic()
            return await self.respond(send, 200, self.public_ticket(ticket))
        match = re.fullmatch(r'/tickets/(tkt_[a-f0-9]{32})(/cancel)?', path)
        if match and method == 'GET' and not match.group(2):
            ticket = self.own_ticket(match.group(1), workstation)
            return await self.respond(send, 200, self.public_ticket(ticket))
        if match and method == 'POST' and match.group(2):
            self.own_ticket(match.group(1), workstation)
            ticket = self.authority.cancel(match.group(1), principal=self.principal)
            return await self.respond(send, 200, self.public_ticket(ticket))
        if method == 'POST' and path == '/images/release':
            value = json.loads(await self.body(receive))
            if not isinstance(value, dict) or set(value) != {'pair_key'}:
                raise ra.AuthorityError('RELEASE_REQUEST_INVALID')
            released = self.authority.release_image(principal=self.principal, workstation=workstation,
                                                    pair_key=value['pair_key'])
            return await self.respond(send, 200, {'released': released})
        if method == 'POST' and path == '/warm':
            self.warm_until = self.monotonic() + self.authority.config.idle_seconds
            self.last_activity = self.monotonic()
            return await self.respond(send, 200, {'model_server': self.runtime.state})
        return await self.respond(send, 404, {'detail': 'Not found'})

    def own_ticket(self, ticket_id, workstation):
        ticket = self.authority.get(ticket_id, principal=self.principal)
        if ticket['workstation'] != workstation:
            raise ra.AuthorityError('TICKET_NOT_FOUND')
        return ticket

    @staticmethod
    def public_ticket(ticket):
        return {key: ticket.get(key) for key in ('ticket_id', 'kind', 'model_id', 'modality', 'state', 'last_reason',
                                                 'ready_deadline_utc', 'idempotency_key')}

    def status(self, workstation):
        value = self.authority.status(principal=self.principal, workstation=workstation)
        value.update(model_server=self.runtime.state, model_epoch=self.epoch if self.runtime.state == 'READY' else None,
                     funded_until_utc=self.funded_until.isoformat() if self.funded_until else None,
                     identity='SHARED_BACKEND_WORKSTATION_NOT_AUTHENTICATED', last_reason=self.last_reason)
        return value

    # ------------------------------------------------------------------ model routes

    def _load_discovery(self):
        if self.discovery_path is None or not self.discovery_path.is_file():
            return {}
        try:
            value = read_json(self.discovery_path, limit=2_000_000)
            return {path: value[path] for path in CACHED_GETS if isinstance(value.get(path), (dict, list))}
        except (OSError, ValueError):
            return {}

    def _store_discovery(self, path, value):
        self.discovery[path] = value
        if self.discovery_path is not None:
            temporary = self.discovery_path.with_suffix('.tmp')
            temporary.write_bytes(canonical(self.discovery))
            os.replace(temporary, self.discovery_path)

    async def passthrough(self, scope, receive, send, headers):
        path = scope['path']
        body = await self.body(receive) if scope['method'] == 'POST' else b''
        if self.runtime.state != 'READY':
            if scope['method'] == 'GET' and path in self.discovery:
                value = self.discovery[path]
                if path == '/health' and isinstance(value, dict):
                    value = {**value, 'warnings': [*value.get('warnings', []), ON_DEMAND_WARNING]}
                return await self.respond(send, 200, value)
            return await self.respond(send, 503, {'detail': 'The model server is not running now.',
                                                  'code': 'MODEL_SERVER_NOT_READY'})
        status, content_type, data = await self.runtime.forward(scope['method'], path, headers, body)
        if scope['method'] == 'GET' and path in CACHED_GETS and status == 200:
            try:
                self._store_discovery(path, json.loads(data))
            except (ValueError, OSError):
                pass
        if scope['method'] == 'POST':
            self.last_activity = self.monotonic()
        await send({'type': 'http.response.start', 'status': status,
                    'headers': [(b'content-type', content_type), (b'cache-control', b'no-store')]})
        await send({'type': 'http.response.body', 'body': data})

    async def charged(self, scope, receive, send, headers):
        workstation = self.one(headers, b'x-dr-workstation', WORKSTATION)
        ticket_id = self.one(headers, b'x-dr-ticket', TICKET)
        if workstation is None or ticket_id is None:
            return await self.respond(send, 409, {'detail': 'A scheduled ticket is required; no inference dispatched',
                                                  'code': 'REGULAR_TICKET_REQUIRED'})
        ticket = self.own_ticket(ticket_id, workstation)
        if ticket['kind'] != CHARGED[scope['path']]:
            raise ra.AuthorityError('TICKET_STAGE_MISMATCH')
        body = await self.body(receive)
        self.authority.mark_arrived(ticket_id, principal=self.principal, workstation=workstation)
        self.last_activity = self.monotonic()
        try:
            await asyncio.wait_for(self.dispatch_lock.acquire(), DISPATCH_WAIT_SECONDS)
        except asyncio.TimeoutError:
            self.authority.abandon(ticket_id, reason='DISPATCH_SLOT_BUSY')
            return await self.respond(send, 503, {'detail': 'The model server is busy; no inference dispatched.',
                                                  'code': 'QUEUE_BUSY_NOT_SENT'})
        try:
            if self.runtime.state != 'READY':
                self.authority.abandon(ticket_id, reason='MODEL_SERVER_NOT_READY')
                return await self.respond(send, 503, {'detail': 'The model server is not running now; '
                                                                'no inference dispatched.',
                                                      'code': 'MODEL_SERVER_NOT_READY'})
            self.current = self.authority.get(ticket_id, principal=self.principal)
            forward = asyncio.ensure_future(self.runtime.forward('POST', scope['path'], headers, body))
            # Answer the child's admission receipt while its call waits (the child allows 10 s).
            while not forward.done():
                self.service_receipts()
                await asyncio.wait({forward}, timeout=.02)
            try:
                status, content_type, data = forward.result()
            except Exception:
                status, content_type, data = None, b'application/json', b''
            state = self.authority.get(ticket_id, principal=self.principal)['state']
            if state == 'READY':
                # Only this service writes the child's admission; without it the child never dispatches.
                self.authority.abandon(ticket_id, reason='REFUSED_BEFORE_ADMISSION')
            # Reply at once: a PRISM client needs its 202 job ID within 2 s to poll and grant.
            if status is None:
                await self.respond(send, 502, {'detail': 'The model server connection was lost; '
                                                         'the outcome is unknown.', 'code': 'CHILD_CONNECTION_LOST'})
            else:
                await send({'type': 'http.response.start', 'status': status,
                            'headers': [(b'content-type', content_type), (b'cache-control', b'no-store')]})
                await send({'type': 'http.response.body', 'body': data})
            if state == 'ADMITTED':
                # The single running slot stays held until the child's terminal receipt.
                await self._await_terminal(ticket_id, PRISM_TERMINAL_SECONDS if ticket['kind'] == 'prism'
                                           else GLOBAL_TERMINAL_SECONDS)
        finally:
            self.current = None
            self.last_activity = self.monotonic()
            self.dispatch_lock.release()

    async def _await_terminal(self, ticket_id, seconds):
        deadline = self.monotonic() + seconds
        while self.monotonic() < deadline:
            self.service_receipts()
            if self.authority.get(ticket_id, principal=self.principal)['state'] != 'ADMITTED':
                return
            await asyncio.sleep(.05)
        # No terminal receipt in time: the call may still be running; never a failure or refund.
        self.authority.finish(ticket_id, outcome='UNKNOWN', reason='NO_TERMINAL_RECEIPT')
        self.last_reason = 'UNKNOWN_OUTCOME_QUARANTINED'
        for entry in self.receipts.values():
            if entry.get('ticket_id') == ticket_id and entry['state'] == 'ADMITTED':
                entry['state'] = 'UNKNOWN'

    # ------------------------------------------------------------------ child receipts

    def service_receipts(self):
        run = self.runtime.run
        if run is None:
            return
        for path in sorted(Path(run).glob('m1_*.request.json')):
            request_id = path.name[:-len('.request.json')]
            if request_id not in self.receipts:
                self._admit(request_id, path)
        for request_id, entry in list(self.receipts.items()):
            if entry['state'] == 'ADMITTED':
                self._observe(request_id, entry)

    def _write(self, name, value):
        try:
            new_json(Path(self.runtime.run) / name, value)
        except FileExistsError:
            pass
        return True

    def _admit(self, request_id, path):
        pid = self.runtime.pid
        try:
            value = read_json(path)
            facts = value['facts']
            valid = (REQUEST_ID.fullmatch(request_id) and value.get('request_id') == request_id
                     and value.get('pid') == pid and isinstance(facts, dict)
                     and facts == self.operations.facts(self.models, source_sha256=facts['source_sha256'],
                                                        model_id=facts['model_id'], modality=facts['modality']))
        except Exception:
            valid = False
        ticket = self.current
        if not valid or ticket is None:
            code = 'REQUEST_IDENTITY_OR_REVIEWED_PINS_CHANGED' if not valid else 'NO_SCHEDULED_TICKET_IN_FLIGHT'
            self._write(f'{request_id}.refused.json', {'request_id': request_id, 'pid': pid, 'code': code})
            self.receipts[request_id] = {'state': 'REFUSED'}
            return
        if not self.runtime.can_admit():
            self._write(f'{request_id}.refused.json', {'request_id': request_id, 'pid': pid,
                                                       'code': 'CHILD_NOT_IDLE_NO_ADMISSION'})
            self.receipts[request_id] = {'state': 'REFUSED'}
            return
        try:
            intent = self.authority.admit(ticket['ticket_id'], principal=self.principal,
                                          workstation=ticket['workstation'], model_id=facts['model_id'],
                                          modality=facts['modality'], source_sha256=facts['source_sha256'],
                                          request_digest=ticket['request_digest'])
        except ra.AuthorityError as error:
            self._write(f'{request_id}.refused.json', {'request_id': request_id, 'pid': pid, 'code': str(error)})
            self.receipts[request_id] = {'state': 'REFUSED'}
            return
        try:
            self.runtime.admit(intent['intent_id'])
        except Exception:
            # Charged but provably not dispatched (no admitted receipt): FAILED, never refunded.
            self.authority.finish(ticket['ticket_id'], outcome='FAILED', reason='SUPERVISOR_REFUSED_AFTER_INTENT')
            self._write(f'{request_id}.refused.json', {'request_id': request_id, 'pid': pid,
                                                       'code': 'SUPERVISOR_REFUSED'})
            self.receipts[request_id] = {'state': 'REFUSED'}
            return
        try:
            self._write(f'{request_id}.admitted.json', {'request_id': request_id, 'pid': pid,
                                                        'admission_id': intent['intent_id'],
                                                        'job_id': ticket['ticket_id'],
                                                        'operation_id': ticket['ticket_id']})
        except OSError:
            # Without the admitted receipt the child never dispatches: charged, never refunded, not unknown.
            self.authority.finish(ticket['ticket_id'], outcome='FAILED', reason='ADMISSION_RECEIPT_NOT_WRITTEN')
            self.receipts[request_id] = {'state': 'REFUSED'}
            return
        self.receipts[request_id] = {'state': 'ADMITTED', 'ticket_id': ticket['ticket_id'],
                                     'intent_id': intent['intent_id']}

    def _observe(self, request_id, entry):
        if self.authority.get(entry['ticket_id'], principal=self.principal)['state'] != 'ADMITTED':
            # Already settled (timed out to UNKNOWN or reconciled): a late receipt changes nothing.
            entry['state'] = 'SETTLED'
            return
        run = Path(self.runtime.run)
        finished = run / f'{request_id}.finished.json'
        if finished.is_file():
            try:
                value = read_json(finished)
                success = value['success'] if value.get('request_id') == request_id and type(value.get('success')) \
                    is bool and value.get('pid') == self.runtime.pid else None
            except Exception:
                success = None
            if success is None:
                self.authority.finish(entry['ticket_id'], outcome='UNKNOWN', reason='COMPLETION_IDENTITY_CHANGED')
            else:
                self.authority.finish(entry['ticket_id'], outcome='DONE' if success else 'FAILED',
                                      reason=None if success else 'MODEL_CALL_FAILED_NO_RETRY')
            self.runtime.finish(entry['intent_id'], success=bool(success))
            entry['state'] = 'FINISHED'
            return
        for name, reason in (('abandoned', 'ADMISSION_HANDOFF_UNCERTAIN'), ('uncertain', 'MODEL_OUTCOME_UNCERTAIN')):
            if (run / f'{request_id}.{name}.json').is_file():
                self.authority.finish(entry['ticket_id'], outcome='UNKNOWN', reason=reason)
                entry['state'] = 'UNKNOWN'
                self.last_reason = 'UNKNOWN_OUTCOME_QUARANTINED'
                return

    # ------------------------------------------------------------------ scheduler and lifecycle

    def step(self):
        """One scheduler pass; called about every 0.25 s by the service loop."""
        self.runtime.tick()
        self.service_receipts()
        now, mono = self.authority.clock.utc(), self.monotonic()
        status = self.authority.status()
        open_work = status['queued'] + status['ready'] + status['running']
        if open_work:
            self.last_activity = mono
        wanted = open_work > 0 or (self.warm_until is not None and mono < self.warm_until)
        state = self.runtime.state
        if state == 'STOPPED':
            self._after_stop(now)
            if wanted and status['ai_open'] and not status['quarantined'] and not status['revoked'] \
                    and (self.backoff_until is None or mono >= self.backoff_until):
                self._start(now)
            return
        if state in ('STARTING', 'READY'):
            left = (self.funded_until - now).total_seconds() if self.funded_until else 0
            if state == 'STARTING' and self.runtime.age() > LOAD_DEADLINE_SECONDS:
                return self._stop('LOAD_DEADLINE', backoff=True)
            failed = self.runtime.failed_reason()
            if failed:
                # A failed call drains the child by design (no retry); only load/runtime faults back off.
                return self._stop(failed, backoff=state == 'STARTING' or 'JOB_FAILED_NO_RETRY' not in failed)
            if state == 'READY' and self.discovery_epoch != self.epoch:
                self.discovery_epoch = self.epoch
                self.refresh = asyncio.get_running_loop().create_task(self._refresh_discovery()) \
                    if self._loop_running() else None
            if status['running'] == 0 and self.current is None and (
                    self.runtime.jobs() >= RETIRE_JOBS or self.runtime.age() >= RETIRE_SECONDS):
                return self._stop('HEALTHY_RETIREMENT')
            idle = self.last_activity is None or mono - self.last_activity >= self.authority.config.idle_seconds
            if left <= FUND_AHEAD_SECONDS and not idle:
                try:
                    segment = self.authority.fund_segment(epoch=self.epoch, gpu_uuid=self.authority.config.gpu_uuid)
                    self.funded_until = datetime.fromisoformat(segment['end_utc'])
                    left = (self.funded_until - now).total_seconds()
                except ra.AuthorityError as error:
                    self.last_reason = str(error)
            if left <= STOP_MARGIN_SECONDS or (idle and status['running'] == 0 and self.current is None):
                if status['running'] == 0 and self.current is None:
                    return self._stop('IDLE' if idle else 'FUNDED_TIME_ENDING')
            if state == 'READY' and left > PROMOTE_MIN_SECONDS and status['ready'] == 0 \
                    and status['running'] == 0 and self.current is None:
                self.authority.schedule(max_promote=1)
            elif status['ready'] or status['queued']:
                self.authority.schedule(max_promote=0)   # Still expire stale dispatch windows.
            return
        if state == 'STOPPING':
            return
        if state == 'UNCONFIRMED':
            # Unknown cleanup keeps its charge and stops new GPU work until owned proof.
            self.authority.quarantine('CHILD_CLEANUP_UNCONFIRMED')
            self.last_reason = 'CHILD_CLEANUP_UNCONFIRMED'

    def _start(self, now):
        epoch = 'rs_' + secrets.token_hex(12)
        refusal = self.runtime.preflight()
        if refusal:
            # Port busy or GPU not idle: nothing funded, nothing started.
            self.last_reason = refusal
            self.backoff_until = self.monotonic() + FAILURE_BACKOFF_SECONDS
            return
        try:
            segment = self.authority.fund_segment(epoch=epoch, gpu_uuid=self.authority.config.gpu_uuid)
        except ra.AuthorityError as error:
            self.last_reason = str(error)
            return
        self.epoch, self.funded_until = epoch, datetime.fromisoformat(segment['end_utc'])
        self.last_activity = self.monotonic()
        self.receipts.clear()
        try:
            self.runtime.start(epoch)
        except Exception as error:
            self.last_reason = 'CHILD_START_REFUSED_' + type(error).__name__
            self.backoff_until = self.monotonic() + FAILURE_BACKOFF_SECONDS

    def _stop(self, reason, *, backoff=False):
        self.last_reason = reason
        if backoff:
            self.backoff_until = self.monotonic() + FAILURE_BACKOFF_SECONDS
        self.runtime.stop(reason)

    def _after_stop(self, now):
        stopped = self.runtime.take_stop_record()
        if stopped is None:
            return
        if stopped.get('end_utc') and self.funded_until:
            over = (datetime.fromisoformat(stopped['end_utc']) - self.funded_until).total_seconds()
            if over > 0:
                self.authority.record_overrun(epoch=self.epoch or 'unknown', seconds=over)
                self.last_reason = 'GPU_OVERRUN_QUARANTINED'
        if not stopped.get('cleanup_confirmed'):
            self.authority.quarantine('CHILD_CLEANUP_UNCONFIRMED')
            self.last_reason = 'CHILD_CLEANUP_UNCONFIRMED'
        self.funded_until = self.epoch = None

    @staticmethod
    def _loop_running():
        try:
            asyncio.get_running_loop()
            return True
        except RuntimeError:
            return False

    async def _refresh_discovery(self):
        """Cache the loaded child's non-secret health and capability documents for when it is stopped."""
        for path in CACHED_GETS:
            try:
                status, _, data = await self.runtime.forward('GET', path, {}, b'')
                if status == 200:
                    self._store_discovery(path, json.loads(data))
            except Exception:
                pass

    async def loop(self, period=.25):
        while True:
            try:
                self.step()
            except ra.AuthorityError as error:
                self.last_reason = str(error)
            except Exception as error:
                # Never stop scheduling or lifecycle control; stop new GPU work until an operator checks.
                self.last_reason = 'SCHEDULER_ERROR_' + type(error).__name__
                try:
                    self.authority.quarantine('SCHEDULER_ERROR')
                except Exception:
                    pass
            await asyncio.sleep(period)

    def recover_after_restart(self):
        """At gateway start: settle work the previous gateway left open. Never refunds."""
        return self.authority.recover_open_tickets()


# ---------------------------------------------------------------------------
# Real host wiring (dr-train only; never run in tests)
# ---------------------------------------------------------------------------


class HostRuntime:
    """The reviewed m1_session worker as an owned child on 127.0.0.1:7861."""

    def __init__(self, *, deploy, models_path, prism_pins_path, runs, token):
        import m1_session
        self.m1 = m1_session
        self.deploy, self.models_path, self.prism_pins_path = Path(deploy), Path(models_path), Path(prism_pins_path)
        self.runs, self.token = Path(runs), token
        self.state, self.run, self.pid = 'STOPPED', None, None
        self.child = self.supervisor = self.gpu = self.disk = None
        self.started = None
        self.stop_record = None
        self._stopper = None
        self._failed = None
        import httpx
        self.client = httpx.AsyncClient(base_url=f'http://127.0.0.1:{CHILD_PORT}', timeout=httpx.Timeout(40, connect=2),
                                        trust_env=False, follow_redirects=False)

    def age(self):
        return time.monotonic() - self.started if self.started else 0

    def jobs(self):
        return self.supervisor.jobs_started if self.supervisor else 0

    def failed_reason(self):
        return self._failed

    def preflight(self):
        import socket
        import subprocess
        with socket.socket() as probe:
            try:
                probe.bind(('127.0.0.1', CHILD_PORT))
            except OSError:
                return 'CHILD_PORT_BUSY'
        try:
            used = subprocess.run(['nvidia-smi', '--id=' + self.m1.GPU, '--query-gpu=memory.used',
                                   '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=10)
            if used.returncode != 0 or int(used.stdout.strip()) > 64:
                return 'GPU0_NOT_IDLE_NO_ADOPTION'
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return 'GPU0_STATE_UNKNOWN'
        return None

    def start(self, epoch):
        import socket
        from scripts.qa.disk_monitor import ProjectDiskMonitor
        from scripts.qa.gpu_monitor import GPU0Monitor
        from scripts.qa.linux_owned_child import LinuxOwnedChild, LinuxResources, command_digest
        from scripts.qa.worker_supervisor import Policy, WorkerSupervisor
        m1 = self.m1
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', CHILD_PORT))
        self.run = self.runs / f'regular-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{epoch}'
        self.run.mkdir(mode=0o700)
        self.disk, self.gpu = ProjectDiskMonitor(m1.PROJECT), GPU0Monitor(m1.GPU)
        self.disk.start()
        self.gpu.start()
        if self.gpu.sample()['vram_mib'] > 64:
            self._cleanup_monitors()
            raise RuntimeError('GPU0_NOT_IDLE_NO_ADOPTION')
        argv = [str(m1.PROJECT / 'environments/prism-qa-torch213/bin/python'), '-I', '-B',
                str(Path(__file__).resolve()), '--child', '--deploy', str(self.deploy), '--run', str(self.run),
                '--models', str(self.models_path), '--prism-pins', str(self.prism_pins_path)]
        scope = 'regular_' + epoch
        self.child = LinuxOwnedChild.spawn(argv, model_id='prism-dr-5fold', owner_scope=scope,
                                           resource_provider=LinuxResources(m1.PROJECT, disk_monitor=self.disk,
                                                                            gpu_monitor=self.gpu),
                                           hard_seconds=m1.CHILD_HARD_SECONDS, env=m1.child_environment(self.run))
        self.supervisor = WorkerSupervisor(Policy('prism-dr-5fold', os.getpid(), scope, command_digest(argv), m1.GPU,
                                                  max_jobs=RETIRE_JOBS, max_seconds=2700, request_seconds=30,
                                                  drain_seconds=20, monitor_seconds=2), self.child)
        self.pid, self.started, self.state, self._failed = self.child.identity.pid, time.monotonic(), 'STARTING', None

    def tick(self):
        from scripts.qa.linux_owned_child import owned_loopback_listener
        if self.state in ('STARTING', 'READY') and self.supervisor is not None:
            state = self.supervisor.tick()
            if state not in ('IDLE', 'BUSY'):
                self._failed = 'SUPERVISOR_' + (self.supervisor.reason or state)
            elif self.state == 'STARTING' and (self.run / 'READY.json').is_file() \
                    and owned_loopback_listener(CHILD_PORT, self.pid):
                self.state = 'READY'
        if self.state == 'STOPPING' and self._stopper is not None and self._stopper.done():
            try:
                outcomes = self._stopper.result()
            except Exception as error:
                outcomes = {'cleanup': {'confirmed': False, 'error_class': type(error).__name__}}
            import socket
            with socket.socket() as sock:
                closed = sock.connect_ex(('127.0.0.1', CHILD_PORT)) != 0
            self.stop_record = {'cleanup_confirmed': closed and all(item['confirmed'] for item in outcomes.values()),
                                'end_utc': datetime.now(timezone.utc).isoformat(), 'components': outcomes}
            self.state = 'STOPPED' if self.stop_record['cleanup_confirmed'] else 'UNCONFIRMED'
            self.child = self.supervisor = None
            self._stopper = None

    def can_admit(self):
        return (self.state == 'READY' and self.supervisor is not None and self.supervisor.state == 'IDLE'
                and self.supervisor.jobs_started < RETIRE_JOBS)

    def admit(self, intent_id):
        self.supervisor.admit(intent_id)

    def finish(self, intent_id, *, success):
        if self.supervisor is not None and self.supervisor.state == 'BUSY':
            self.supervisor.finish(intent_id, success=success)

    def stop(self, reason):
        if self.state not in ('STARTING', 'READY'):
            return
        import concurrent.futures
        self.state = 'STOPPING'
        child, supervisor, gpu, disk = self.child, self.supervisor, self.gpu, self.disk
        self._stopper = concurrent.futures.ThreadPoolExecutor(1).submit(
            self.m1.cleanup_owned, child, supervisor, gpu, disk)

    def take_stop_record(self):
        record, self.stop_record = self.stop_record, None
        return record

    def _cleanup_monitors(self):
        for monitor in (self.gpu, self.disk):
            try:
                monitor.close()
            except Exception:
                pass

    async def forward(self, method, path, headers, body):
        keep = {key: values[0].decode('latin-1') for key, values in headers.items()
                if key in (b'content-type', b'x-prism-epoch', b'accept') and len(values) == 1}
        keep['authorization'] = 'Bearer ' + self.token
        async with self.client.stream(method, path, content=body or None, headers=keep) as response:
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > MAX_BODY:
                    raise RuntimeError('RESPONSE_LIMIT')
            content_type = response.headers.get('content-type', 'application/json').encode('latin-1')
            return response.status_code, content_type, bytes(data)


def child_main(args):
    """The reviewed worker, unchanged, on the regular child port."""
    import m1_session
    m1_session.PORT = CHILD_PORT
    return m1_session.worker(args)


def serve_main(args):
    import m1_operations as operations
    import m1_session
    import uvicorn
    m1_session.bindings(args.deploy)
    from approved_token_reader import read_private_token
    state = Path(args.state)
    if state.is_symlink() or not state.is_dir() or state.resolve().parent != (m1_session.PROJECT / 'regular').resolve():
        raise RuntimeError('PRIVATE_REGULAR_STATE_DIRECTORY_REQUIRED')
    token = read_private_token(m1_session.PROJECT / 'config/private/model-api.env')
    models = operations.reviewed_models(Path(args.models).read_bytes(), m1_session.read_json(args.prism_pins))
    lineage = m1_session.read_json(args.lineage)
    clock = ra.Clock(utc=lambda: datetime.now(timezone.utc), monotonic=time.monotonic,
                     boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    authority = ra.Authority(state / 'authority.sqlite3', config=ra.ServiceConfig(), clock=clock, lineage=lineage)
    runs = state / 'runs'
    runs.mkdir(mode=0o700, exist_ok=True)
    runtime = HostRuntime(deploy=args.deploy, models_path=args.models, prism_pins_path=args.prism_pins,
                          runs=runs, token=token)
    service = ControlService(authority, runtime, token=token, models=models, operations=operations,
                             discovery_path=state / 'discovery.json')
    recovered = service.recover_after_restart()

    class Lifespan:
        async def __call__(self, scope, receive, send):
            if scope['type'] == 'lifespan':
                message = await receive()
                if message['type'] == 'lifespan.startup':
                    self.task = asyncio.get_running_loop().create_task(service.loop())
                    await send({'type': 'lifespan.startup.complete'})
                    message = await receive()
                if message['type'] == 'lifespan.shutdown':
                    self.task.cancel()
                    runtime.stop('SERVICE_SHUTDOWN')
                    deadline = time.monotonic() + 40
                    while runtime.state == 'STOPPING' and time.monotonic() < deadline:
                        runtime.tick()
                        await asyncio.sleep(.25)
                    await send({'type': 'lifespan.shutdown.complete'})
                return
            await service(scope, receive, send)

    print(json.dumps({'phase': 'SERVING', 'url': f'http://127.0.0.1:{CONTROL_PORT}', 'child_port': CHILD_PORT,
                      'authority': str(state / 'authority.sqlite3'), 'recovered': recovered}), flush=True)
    uvicorn.run(Lifespan(), host='127.0.0.1', port=CONTROL_PORT, workers=1, access_log=False,
                log_level='warning', log_config=None, timeout_graceful_shutdown=45)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['serve'], nargs='?', default='serve')
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--deploy', type=Path)
    parser.add_argument('--run', type=Path)
    parser.add_argument('--models', type=Path)
    parser.add_argument('--prism-pins', type=Path)
    parser.add_argument('--state', type=Path)
    parser.add_argument('--lineage', type=Path)
    args = parser.parse_args()
    if sys.platform != 'linux':
        parser.error('Run on the approved GPU host through the existing SSH connection')
    if args.child:
        return child_main(args)
    return serve_main(args)


if __name__ == '__main__':
    raise SystemExit(main())
