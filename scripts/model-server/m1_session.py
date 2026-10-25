"""Bounded Hospital M1 QA_SERVER acceptance runner on the approved GPU host.

This finite qualification session is not an installed persistent hospital model
service. Its lifetime, request budget and one-lease/no-renewal controls stay in
force; persistent operation and restart/reboot recovery remain separate M1 work.

Import is inert. One owned parent holds the approved continuation ledger, the
named Server window and its single lifetime lease, and admits each real model
request through M1AdmissionConsumer BEFORE the owned child may dispatch it.
The child serves USPEC/RETFound global grading (``/v1/predict/dr``) and PRISM
through the bound transport (``/v1/prism-bound/*``) on one authenticated
loopback port. No retry, renewal, public listener, credential creation or
second lease exists. Control RPCs (discovery, prepare, status, grant) are not
charged; every execute/predict is charged once before dispatch.

The window name and caps come from the verified decision (2026-10-23, the
PRISM continuation, or the MS-03 service window, which activates only after its
watchdog window is closed; see m1_watchdog.py). ``handover`` fences a closed source ledger for the next
approved decision; ``verify`` dry-runs a draft with a temporary approval.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import sys
import time
from uuid import uuid4

PROJECT = Path('/home/siripon/projects/dr-model-api-qa')
GPU = 'GPU-044a8b11-4729-458b-a07b-297e45439419'
PORT = 7860
BASE = '/v1/prism-bound'
GLOBAL_ROUTE = '/v1/predict/dr'
PRISM_ROUTE = BASE + '/execute'
CONTROL_POST = re.compile(re.escape(BASE) + r'/(?:prepare|jobs/[A-Za-z0-9_-]{8,80}/(?:grant|cancel))')
REQUEST_ID = re.compile(r'm1_[0-9]{4}_[a-f0-9]{16}')
MAX_BODY = 20_100_000
SESSION_SECONDS = 2640       # Inside WorkerSupervisor's 2700 s and the child's 2730 s hard cap.
CHILD_HARD_SECONDS = 2730
# The supervisor's 30 s request deadline starts at parent admission; the PRISM
# job deadline starts later at execute. 24 + 1 s grace + polling stays inside it
# (observed native PRISM time in the closed batch: p50 11.9 s, max 19.0 s).
PRISM_JOB_SECONDS = 24
WATCH_GRACE_SECONDS = 1
PRISM_PRINCIPAL = 'fixed-qa-backend'  # child_application's single trusted backend subject.
FINAL = {'COMPLETE', 'FAILED', 'ABORTED'}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def new_json(path, value):
    """Publish a complete receipt once; never replace an existing receipt."""
    path = Path(path)
    temporary = path.with_name(f'.{path.name}.{uuid4().hex}.pending')
    try:
        with temporary.open('xb') as stream:
            raw = canonical(value)
            if stream.write(raw) != len(raw):
                raise OSError('PARTIAL_RECEIPT_WRITE')
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def replace_json(path, value):
    """Atomically replace a mutable status view (never an accounting record)."""
    path = Path(path)
    temporary = path.with_name(f'.{path.name}.{uuid4().hex}.pending')
    with temporary.open('xb') as stream:
        stream.write(canonical(value))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def read_json(path, limit=65536):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError('BOUNDED_REGULAR_RECEIPT_REQUIRED')
    return json.loads(path.read_bytes())


def installation_digest(root):
    """Digest of every deployed file's relative path and bytes; no secrets here."""
    root = Path(root)
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('DEPLOYMENT_SYMLINK_REJECTED')
        if path.is_file() and '__pycache__' not in path.parts:
            files[path.relative_to(root).as_posix()] = sha(path.read_bytes())
    return sha(canonical(files))


def host_clock_origin():
    """Bind window clocks to this boot of this machine; never compared across hosts."""
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    machine = Path('/etc/machine-id').read_text().strip()
    return sha(canonical({'boot_id': boot, 'machine_id': machine}))


class Refused(Exception):
    """A request was refused before any dispatch; carries a fixed code only."""


# ---------------------------------------------------------------------------
# Child: charged-request admission in front of the model applications
# ---------------------------------------------------------------------------


class ChildAdmission:
    """ASGI router that waits for the parent's durable admission before dispatch.

    Only one charged request is in flight. A request refused before admission
    is never dispatched. After admission every outcome is reported once as a
    finished receipt; PRISM finishes at its terminal job state, not its 202.
    """

    def __init__(self, *, model_app, prism_app, host, models, run, operations,
                 clock=time.monotonic, ack_seconds=10, upload_seconds=15, poll_seconds=.025):
        self.model_app, self.prism_app, self.host = model_app, prism_app, host
        self.models, self.run, self.operations = models, Path(run), operations
        self.clock, self.ack_seconds = clock, ack_seconds
        self.upload_seconds, self.poll_seconds = upload_seconds, poll_seconds
        self.sequence, self.busy, self.ready_callback = 0, False, None
        self.tasks = set()

    async def respond(self, send, code, value):
        await send({'type': 'http.response.start', 'status': code,
                    'headers': [(b'content-type', b'application/json'), (b'cache-control', b'no-store')]})
        await send({'type': 'http.response.body', 'body': canonical(value)})

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'lifespan':
            async def started(message):
                if message['type'] == 'lifespan.startup.complete' and self.ready_callback is not None:
                    self.ready_callback()
                await send(message)
            return await self.prism_app(scope, receive, started)
        if scope['type'] != 'http':
            return
        path, method = scope['path'], scope['method']
        target = self.prism_app if path.startswith(BASE) else self.model_app
        if method == 'GET' or (method == 'POST' and CONTROL_POST.fullmatch(path)):
            return await target(scope, receive, send)
        if method != 'POST' or path not in {GLOBAL_ROUTE, PRISM_ROUTE}:
            return await self.respond(send, 405, {'detail': 'Outside the M1 session scope'})
        if self.busy:
            return await self.respond(send, 429, {'detail': 'One model request is already in progress'})
        self.busy = True
        release = True
        try:
            body = await self._body(receive)
            if body is None:
                return await self.respond(send, 408, {'detail': 'Upload deadline exceeded; no inference dispatched'})
            if path == GLOBAL_ROUTE:
                return await self._global(scope, send, body)
            release = False
            return await self._prism(scope, send, body)
        except Refused as refusal:
            release = True
            return await self.respond(send, 409, {'detail': 'Request not admitted; no inference dispatched',
                                                  'code': str(refusal)})
        finally:
            if release:
                self.busy = False

    async def _body(self, receive):
        body, deadline = bytearray(), self.clock() + self.upload_seconds
        while True:
            remaining = deadline - self.clock()
            if remaining <= 0:
                return None
            try:
                message = await asyncio.wait_for(receive(), remaining)
            except asyncio.TimeoutError:
                return None
            if message['type'] == 'http.disconnect':
                raise Refused('CLIENT_DISCONNECTED_BEFORE_ADMISSION')
            body.extend(message.get('body', b''))
            if len(body) > MAX_BODY:
                raise Refused('BODY_LIMIT')
            if not message.get('more_body'):
                return bytes(body)

    def _global_facts(self, body):
        try:
            payload = json.loads(body)
            model_id, modality = payload['model_id'], payload['modality']
            declared = payload['image_sha256']
            decoded = base64.b64decode(payload['image_b64'], validate=True)
        except (ValueError, KeyError, TypeError):
            raise Refused('INVALID_PREDICTION_ENVELOPE') from None
        if (model_id not in self.operations.GLOBAL_MODELS or self.operations.GLOBAL_MODELS[model_id] != modality
                or sha(decoded) != declared):
            raise Refused('UNSUPPORTED_GLOBAL_REQUEST')
        # Global analysis bytes are the admitted source for supported JPEG/PNG input.
        return self.operations.facts(self.models, source_sha256=declared, model_id=model_id, modality=modality)

    def _prism_facts(self, body):
        try:
            value = json.loads(body)
            binding, plan, ticket_id = value['binding'], value['plan_sha256'], value['ticket_id']
            if set(value) != {'ticket_id', 'binding', 'plan_sha256'} or type(binding) is not dict:
                raise ValueError()
            with self.host.lock:
                ticket = self.host.tickets.get(ticket_id)
                if (ticket is None or ticket.owner != PRISM_PRINCIPAL
                        or any(job.state not in FINAL for job in self.host.jobs.values())):
                    raise Refused('PRISM_TICKET_OR_IDLE_HOST_REQUIRED')
                # The same replay refusals the host applies in _start, before any charge.
                if (ticket_id in self.host.consumed_tickets or plan in self.host.consumed_plans
                        or (binding['scope'], binding['image_id'], binding['plan_id']) in self.host.consumed_ids):
                    raise Refused('PRISM_PLAN_REPLAY')
                # Existing frozen-plan validation, before any charge.
                self.host._validate(ticket, binding, plan)
            pins = self.models[self.operations.PRISM]['pins']
            if canonical(binding['model_pins']) != canonical(pins):
                raise Refused('PRISM_REVIEWED_PINS_REQUIRED')
            return self.operations.facts(self.models, source_sha256=binding['source_sha256'],
                                         model_id=self.operations.PRISM, modality=binding['modality'])
        except Refused:
            raise
        except Exception:
            raise Refused('PRISM_FROZEN_PLAN_INVALID') from None

    async def _admit(self, facts, body, correlation=None):
        self.sequence += 1
        request_sha256 = sha(body)
        request_id = f'm1_{self.sequence:04d}_{request_sha256[:16]}'
        # Correlation lets the trusted readback bind persisted evidence to THIS
        # request (PRISM: its one-use plan). It is never an admission fact.
        record = {'request_id': request_id, 'pid': os.getpid(), 'request_sha256': request_sha256, 'facts': facts,
                  'correlation': correlation or {}}
        new_json(self.run / f'{request_id}.request.json', record)
        deadline = self.clock() + self.ack_seconds
        admitted, refused = self.run / f'{request_id}.admitted.json', self.run / f'{request_id}.refused.json'
        while self.clock() < deadline:
            if refused.is_file():
                raise Refused(str(read_json(refused).get('code', 'PARENT_REFUSED')))
            if admitted.is_file():
                value = read_json(admitted)
                if value.get('request_id') != request_id or value.get('pid') != os.getpid():
                    raise Refused('ADMISSION_IDENTITY_CHANGED')
                return request_id
            await asyncio.sleep(self.poll_seconds)
        # The parent may still admit; this marks the handoff uncertain so the
        # parent consumes the intent and closes admission. No dispatch occurs.
        new_json(self.run / f'{request_id}.abandoned.json', {'request_id': request_id, 'pid': os.getpid()})
        raise Refused('NO_PARENT_ADMISSION_NO_DISPATCH')

    def _finish(self, request_id, *, success, response_sha256, result_sha256=None):
        new_json(self.run / f'{request_id}.finished.json', {
            'request_id': request_id, 'pid': os.getpid(), 'success': success, 'response_sha256': response_sha256,
            'result_sha256': result_sha256})

    async def _dispatch(self, app, scope, send, body, *, forward=True):
        captured = {'status': 500, 'complete': False, 'body': bytearray()}
        digest = hashlib.sha256()

        async def replay():
            return {'type': 'http.request', 'body': body, 'more_body': False}

        async def observe(message):
            if message['type'] == 'http.response.start':
                captured['status'] = message['status']
            if message['type'] == 'http.response.body':
                chunk = message.get('body', b'')
                digest.update(chunk)
                if len(captured['body']) <= 65536:
                    captured['body'].extend(chunk)
                if not message.get('more_body'):
                    captured['complete'] = True
            if forward:
                await send(message)
        await app(scope, replay, observe)
        return captured, digest.hexdigest()

    async def _global(self, scope, send, body):
        request_id = await self._admit(self._global_facts(body), body)
        success, response, result = False, sha(b''), None
        try:
            captured, response = await self._dispatch(self.model_app, scope, send, body)
            success = captured['status'] == 200 and captured['complete']
            if success:
                try:
                    result = self.operations.global_result_digest(json.loads(bytes(captured['body'])))
                except Exception:
                    result = None  # The readback then cannot bind and will not pass.
        finally:
            self._finish(request_id, success=success, response_sha256=response, result_sha256=result)

    async def _prism(self, scope, send, body):
        try:
            facts = self._prism_facts(body)
            request_id = await self._admit(facts, body, {'plan_sha256': json.loads(body)['plan_sha256']})
        except BaseException:
            self.busy = False
            raise
        try:
            captured, _ = await self._dispatch(self.prism_app, scope, send, body)
            job_id = json.loads(bytes(captured['body'])).get('job_id') if captured['status'] == 202 else None
        except BaseException:
            self._finish(request_id, success=False, response_sha256=sha(b''))
            self.busy = False
            raise
        if job_id is None:
            self._finish(request_id, success=False, response_sha256=sha(bytes(captured['body'])))
            self.busy = False
            return
        task = asyncio.get_running_loop().create_task(self._watch(request_id, job_id))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _watch(self, request_id, job_id):
        """Report the authenticated terminal job state, never the execute 202.

        A job that is not terminal by its deadline may still be forwarding on the
        GPU: that is an uncertain outcome, not a model failure. It is reported as
        uncertain and this child stays busy, so no further work is admitted.
        """
        job = self.host.jobs.get(job_id)
        if job is None:
            self._finish(request_id, success=False, response_sha256=sha(b''))
            self.busy = False
            return
        while job.state not in FINAL and self.clock() < job.deadline + WATCH_GRACE_SECONDS:
            await asyncio.sleep(self.poll_seconds)
        if job.state not in FINAL:
            new_json(self.run / f'{request_id}.uncertain.json', {'request_id': request_id, 'pid': os.getpid()})
            return
        try:
            status = self.host._status(job)
            success = status['state'] == 'COMPLETE'
            evidence = status['result'] if success else {'state': status['state'], 'error': status['error']}
            response = sha(canonical(evidence))
        except Exception:
            success, response = False, sha(b'')
        self._finish(request_id, success=success, response_sha256=response)
        self.busy = False


# ---------------------------------------------------------------------------
# Parent: durable admission service over the owned consumer
# ---------------------------------------------------------------------------


class ParentAdmissions:
    """Turns child receipts into M1AdmissionConsumer calls; never dispatches itself."""

    def __init__(self, run, *, consumer, ledger, child, window_id, operations, readback_dir=None):
        self.run, self.consumer, self.ledger, self.child = Path(run), consumer, ledger, child
        self.window_id, self.operations = window_id, operations
        # Readback comes from the Windows PostgreSQL adapter over SSH into its
        # own directory; the child never writes there. Same-uid isolation is
        # not claimed: the child is our code behind authenticated loopback.
        self.readback_dir = Path(readback_dir) if readback_dir is not None else self.run / 'readback'
        self.requests, self.stop_reason = {}, None

    def _refuse(self, request_id, pid, code):
        new_json(self.run / f'{request_id}.refused.json', {'request_id': request_id, 'pid': pid, 'code': code})
        self.requests[request_id] = {'state': 'REFUSED', 'code': code}

    def service(self):
        for path in sorted(self.run.glob('m1_*.request.json')):
            request_id = path.name[:-len('.request.json')]
            if request_id in self.requests:
                continue
            value = read_json(path)
            pid = self.child.identity.pid
            correlation = value.get('correlation')
            if (not REQUEST_ID.fullmatch(request_id) or value.get('request_id') != request_id
                    or value.get('pid') != pid
                    or set(value) != {'request_id', 'pid', 'request_sha256', 'facts', 'correlation'}
                    or type(correlation) is not dict or set(correlation) - {'plan_sha256'}
                    or any(not re.fullmatch(r'[a-f0-9]{64}', str(item)) for item in correlation.values())):
                self.stop_reason = 'REQUEST_IDENTITY_CHANGED'
                self.requests[request_id] = {'state': 'INVALID'}
                continue
            self._admit(request_id, pid, value)
        for request_id, entry in self.requests.items():
            try:
                if entry['state'] == 'ADMITTED':
                    self._observe(request_id, entry)
                if entry['state'] == 'RESPONSE_OBSERVED':
                    self._readback(request_id, entry)
            except Exception:
                # A malformed receipt or consumer refusal stops admission; it is
                # never retried and never relabels an observed model result.
                entry['state'], self.stop_reason = 'RECEIPT_REFUSED', 'RECEIPT_OR_ACCOUNTING_REFUSED'

    def _admit(self, request_id, pid, value):
        if self.consumer.poisoned or self.consumer.active is not None:
            return self._refuse(request_id, pid, 'ADMISSION_BUSY_READBACK_PENDING_OR_CLOSED')
        try:
            job = self.operations.match_operation(self.ledger.jobs, value['facts'], window_id=self.window_id,
                                                  states=self.ledger.states)
        except Exception:
            job = None
        if job is None:
            return self._refuse(request_id, pid, 'UNAPPROVED_OR_CONSUMED_OPERATION')
        facts = {key: job[key] for key in ('operation_id', *self.operations.FACT_KEYS)}
        try:
            admission = self.consumer.admit(job['job_id'], request_id=request_id,
                                            request_sha256=value['request_sha256'], facts=facts,
                                            identity=self.child.identity)
        except Exception as error:
            code = str(error) if type(error) is RuntimeError and re.fullmatch(r'[A-Z0-9_]{3,80}', str(error)) else 'ADMISSION_REFUSED'
            if self.consumer.poisoned:
                self.stop_reason = 'ADMISSION_UNCERTAIN'
            return self._refuse(request_id, pid, code)
        new_json(self.run / f'{request_id}.admitted.json', {
            'request_id': request_id, 'pid': pid, 'admission_id': admission['admission_id'],
            'job_id': job['job_id'], 'operation_id': job['operation_id']})
        self.requests[request_id] = {'state': 'ADMITTED', 'admission_id': admission['admission_id'],
                                     'job_id': job['job_id'], 'operation_id': job['operation_id'],
                                     'admitted_utc': time.time(), 'correlation': dict(value['correlation']),
                                     **{key: job[key] for key in ('source_sha256', 'model_id', 'modality')}}

    def _observe(self, request_id, entry):
        finished = self.run / f'{request_id}.finished.json'
        if not finished.is_file():
            for name, state, reason in (('abandoned', 'UNCERTAIN_HANDOFF', 'ADMISSION_HANDOFF_UNCERTAIN'),
                                        ('uncertain', 'UNCERTAIN_OUTCOME', 'MODEL_OUTCOME_UNCERTAIN')):
                if (self.run / f'{request_id}.{name}.json').is_file():
                    # Sent or possibly still forwarding: consumed, never retried.
                    self.consumer.ack_failed(entry['admission_id'])
                    entry['state'], self.stop_reason = state, reason
                    return
            return
        value = read_json(finished)
        if (value.get('request_id') != request_id or value.get('pid') != self.child.identity.pid
                or type(value.get('success')) is not bool
                or not re.fullmatch(r'[a-f0-9]{64}', str(value.get('response_sha256')))
                or not (value.get('result_sha256') is None
                        or re.fullmatch(r'[a-f0-9]{64}', str(value['result_sha256'])))):
            self.stop_reason = 'COMPLETION_IDENTITY_CHANGED'
            entry['state'] = 'INVALID_COMPLETION'
            return
        outcome = self.consumer.record_response(entry['admission_id'], response_sha256=value['response_sha256'],
                                                success=value['success'])
        entry['outcome'] = outcome
        entry['result_sha256'] = value.get('result_sha256')
        entry['state'] = 'RESPONSE_OBSERVED' if value['success'] else 'FAILED_NO_RETRY'
        if not value['success']:
            self.stop_reason = 'REQUEST_FAILED_NO_RETRY'

    def _readback(self, request_id, entry):
        path = self.readback_dir / f'{request_id}.readback.json'
        if not path.is_file():
            return
        value = read_json(path)
        if (type(value) is not dict or set(value) != {'request_id', 'admission_id', 'readback_sha256', 'matches'}
                or value['request_id'] != request_id or value['admission_id'] != entry['admission_id']
                or type(value['matches']) is not bool
                or not re.fullmatch(r'[a-f0-9]{64}', str(value['readback_sha256']))):
            self.stop_reason = 'READBACK_IDENTITY_CHANGED'
            entry['state'] = 'INVALID_READBACK'
            return
        entry['readback'] = self.consumer.acknowledge_readback(
            entry['admission_id'], readback_sha256=value['readback_sha256'], matches=value['matches'])
        entry['state'] = 'PASS_READBACK' if value['matches'] else 'FAILED_PERSISTENCE'

    def status(self, *, budget, supervisor, started):
        return {'phase': 'SERVING', 'requests': self.requests, 'accounting': self.consumer.status(),
                'window': budget.summary(), 'supervisor_state': supervisor.state,
                'stop_reason': self.stop_reason, 'elapsed_seconds': round(time.monotonic() - started, 3),
                'session_seconds_cap': SESSION_SECONDS, 'automatic_retries': 0}


# ---------------------------------------------------------------------------
# Real host wiring (dr-train only; never run in tests)
# ---------------------------------------------------------------------------


def bindings(deploy):
    deploy = Path(deploy)
    sys.path[:0] = [str(deploy / 'scripts/model-server'), str(deploy / 'scripts/qa/batch_runtime'),
                    str(deploy), str(deploy / 'base')]
    # Same Python/Torch/CUDA in both qualified environments; add only timm.
    extras = list((PROJECT / 'environments/uspec-qa-torch213/lib').glob('python*/site-packages'))
    if len(extras) != 1:
        raise RuntimeError('EXISTING_TIMM_ENVIRONMENT_REQUIRED')
    sys.path.append(str(extras[0]))


def child_environment(run):
    return {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1',
            'CUDA_VISIBLE_DEVICES': GPU, 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
            'YOLO_AUTOINSTALL': 'false', 'YOLO_OFFLINE': 'true', 'YOLO_CONFIG_DIR': str(run / 'ultralytics'),
            'APP_PROFILE': 'model_api', 'MODEL_RUNTIME': 'local', 'INFERENCE_DEVICE': 'cuda:0',
            'MODEL_API_PROVIDER_SET': 'grading', 'MODEL_REQUIRE_VERIFIED_ASSETS': '1',
            'MODEL_ALLOW_AUTHORIZED_HOSPITAL': '1', 'MODEL_HOSPITAL_SCOPE': 'PRIVATE_PROJECT_EVALUATION',
            'USPEC_ENABLE_CANDIDATE_LOAD': '1', 'USPEC_MODEL_DIR': str(PROJECT / 'artifact-staging-20261020/uspec'),
            'RETFOUND_SOURCE': str(PROJECT / 'upstream-sources/retfound-ae9a9ec'),
            'RETFOUND_WEIGHTS': str(PROJECT / 'artifacts/retfound/retfound-aptos.pth'),
            'PRISM_SOURCE': str(PROJECT / 'upstream-sources/prism-7963744'),
            'PRISM_WEIGHTS': str(PROJECT / 'artifact-staging-20261020/prism'), 'PRISM_THRESHOLDS': '{}',
            'MODEL_CPU_THREADS': '2', 'OMP_NUM_THREADS': '2', 'MKL_NUM_THREADS': '2'}


def global_identity(model_id):
    """CPU-only source/weight verification, exactly as the reviewed batch worker."""
    from dr_support.providers import assets
    if model_id == 'retfound-aptos5':
        from dr_support.providers.retfound import PREPROCESSING, RETFound, REVISION, WEIGHT_SHA256
        assets.verify_source(os.environ['RETFOUND_SOURCE'], REVISION)
        assets.verify_weight(os.environ['RETFOUND_WEIGHTS'], WEIGHT_SHA256)
        module, revision, checkpoints = RETFound.__module__, REVISION, {'aptos5': WEIGHT_SHA256}
    else:
        from dr_support.models.uspec_artifact import EXPECTED, PREPROCESSING, SOURCE_REVISION, verify_directory
        from dr_support.providers.uspec import USPEC
        verify_directory(os.environ['USPEC_MODEL_DIR'])
        module, revision, checkpoints = USPEC.__module__, SOURCE_REVISION, {'grading_state.pt': EXPECTED.sha256}
    return {'model_id': model_id, 'source_revision': revision, 'checkpoint_sha256': checkpoints,
            'preprocessing': PREPROCESSING,
            'provider_source_sha256': assets.sha256(Path(__import__(module, fromlist=['']).__file__))}


def identity_command(args):
    """CPU-only identity used to draft the proposal: no load, GPU, ledger or listener."""
    bindings(args.deploy)
    os.environ.update({key: value for key, value in child_environment(Path(args.deploy)).items()
                       if key.startswith(('RETFOUND_', 'PRISM_', 'USPEC_'))})
    from dr_support.providers.prism_bound import BoundLocalPRISM
    result = {'installation_sha256': installation_digest(args.deploy), 'clock_origin': host_clock_origin(),
              'prism_pins': BoundLocalPRISM(allow_cpu_fallback=False)._runtime_identity(),
              'global_pins': {model_id: global_identity(model_id)
                              for model_id in ('retfound-aptos5', 'uspec-uwf-grading')}}
    print(json.dumps(result, sort_keys=True))
    return 0


def handover_command(args):
    """Permanently fence a closed source ledger for the next owner-approved decision.

    The source decision is verified against its own deployment's installation;
    the destination is THIS deployment. Keeps the source owner lock and all data.
    """
    bindings(args.deploy)
    from batch_ledger import BatchLedger
    ledger = BatchLedger.for_continuation(
        args.accounting, proposal_path=args.proposal, approval_path=args.approval,
        proposal_sha256=args.proposal_sha256, approval_sha256=args.approval_sha256,
        upstream_paths=read_json(args.upstream_paths), installation_sha256=installation_digest(args.source_deploy))
    ledger.acquire()
    export = ledger.fence_handover(destination_installation_sha256=installation_digest(args.deploy))
    raw = (Path(args.accounting) / 'HANDOVER_EXPORT.json').read_bytes()
    print(json.dumps({'status': export['status'], 'handover_export_sha256': sha(raw),
                      'global_used': export['global_used'], 'remaining': len(export['remaining_job_ids']),
                      'destination_installation_sha256': export['destination_installation_sha256']}))
    return 0


def verify_command(args):
    """Dry-run the exact verifier on an unapproved draft with a temporary approval.

    Writes only that temporary file (removed afterwards); no ledger, window or GPU.
    """
    import tempfile
    bindings(args.deploy)
    from batch_ledger import _verify_decision, window_order
    raw = Path(args.proposal).read_bytes()
    proposal, digest_value = json.loads(raw), sha(raw)
    with tempfile.TemporaryDirectory() as temporary:
        approval = Path(temporary) / 'APPROVAL.dry-run.json'
        approval.write_bytes(canonical({'schema': 'hospital-m1-owner-approval.v1',
                                        'decision_id': proposal['decision_id'], 'proposal_sha256': digest_value,
                                        'status': 'EXPLICIT_OWNER_APPROVED_NOT_ACTIVATED'}))
        verified = _verify_decision(args.accounting, args.proposal, approval, digest_value,
                                    sha(approval.read_bytes()), read_json(args.upstream_paths),
                                    installation_digest(args.deploy))
    spec = verified['spec']
    print(json.dumps({'status': 'DRY_RUN_VERIFIED_NOT_APPROVED', 'proposal_sha256': digest_value,
                      'decision_id': spec['decision_id'], 'base_used': spec['base_used'], 'cap': spec['cap'],
                      'window': spec['server_window'], 'caps': spec['windows'][spec['server_window']],
                      'window_order': window_order(spec),
                      'all_caps': {key: spec['windows'][key] for key in window_order(spec)},
                      'prior_gpu_seconds': spec['prior_gpu_seconds'],
                      'operations': [{key: job[key] for key in ('operation_id', 'model_id', 'modality')}
                                     | {'source': job['source_sha256'][:12]} for job in proposal['operations']]}))
    return 0


def worker(args):
    bindings(args.deploy)
    run = Path(args.run)
    import m1_operations as operations
    from approved_token_reader import read_private_token
    token = read_private_token(PROJECT / 'config/private/model-api.env')
    os.environ['REMOTE_MODEL_TOKEN'] = token
    from dr_support.run import configure
    configure()
    import torch
    import uvicorn
    from dr_support.providers.prism_bound import BoundLocalPRISM
    from dr_support.services.model_api import create_app
    from dr_support.services.prism_owned_runtime import torch_load_forward_guard
    from dr_support.services.prism_workspace_executor import LoadedWorkspacePrismExecutor, workspace_child_application
    from scripts.qa.private_gateway_auth import PrivateGatewayAuth
    if torch.cuda.device_count() != 1 or os.environ.get('CUDA_VISIBLE_DEVICES') != GPU:
        raise RuntimeError('SOLE_APPROVED_GPU0_REQUIRED')
    torch.cuda.set_per_process_memory_fraction(10240 * 1024**2 / torch.cuda.get_device_properties(0).total_memory, 0)
    models = operations.reviewed_models(Path(args.models).read_bytes(), read_json(args.prism_pins))
    model_app = create_app()
    loads = []
    for model_id, provider in model_app.state.providers.items():
        if global_identity(model_id) != models[model_id]['pins']:
            raise RuntimeError('REVIEWED_GLOBAL_IDENTITY_CHANGED')
        started = time.monotonic()
        with torch_load_forward_guard() as guard:
            provider.load()
        if guard.forward_attempts or provider.metadata()['status'] != 'LOADED':
            raise RuntimeError('REAL_LOAD_WITHOUT_FORWARD_REQUIRED')
        loads.append({'model_id': model_id, 'load_seconds': round(time.monotonic() - started, 3),
                      'forward_attempts_during_load': 0})
    executor = LoadedWorkspacePrismExecutor(BoundLocalPRISM(allow_cpu_fallback=False),
                                            expected_pins=models[operations.PRISM]['pins'])
    epoch = 'm1_epoch_' + secrets.token_hex(16)
    prism_app, host = workspace_child_application(
        executor, token=token, issue_id=lambda: 'm1_' + secrets.token_hex(12), epoch=epoch,
        load_seconds=120, job_seconds=PRISM_JOB_SECONDS)
    admission = ChildAdmission(model_app=model_app, prism_app=prism_app, host=host, models=models,
                               run=run, operations=operations)

    def ready():
        new_json(run / 'READY.json', {'status': 'LOADED_NOT_YET_INFERENCE_VALIDATED', 'gpu_uuid': GPU,
                                      'epoch': epoch, 'global_models': loads, 'prism': 'LOADED',
                                      'forward_attempts_during_load': 0, 'url': f'http://127.0.0.1:{PORT}'})
    admission.ready_callback = ready
    uvicorn.run(PrivateGatewayAuth(admission, token), host='127.0.0.1', port=PORT, workers=1,
                access_log=False, log_level='critical', log_config=None, timeout_graceful_shutdown=10)


def cleanup_owned(child, supervisor, gpu, disk):
    """Attempt every owned cleanup; failures never skip unrelated finalizers."""
    outcomes = {}

    def attempt(name, callback):
        try:
            callback()
            outcomes[name] = {'confirmed': True}
        except BaseException as error:
            outcomes[name] = {'confirmed': False, 'error_class': type(error).__name__}
    if supervisor is not None:
        attempt('supervisor_close', supervisor.close)
    if child is not None:
        def drain():
            if child.inspect():
                child.signal_verified(child.identity, force=False)
            until = time.monotonic() + 22
            while child.inspect() and time.monotonic() < until:
                time.sleep(.1)
            if child.inspect():
                child.signal_verified(child.identity, force=True)
            until = time.monotonic() + 5
            while child.inspect() and time.monotonic() < until:
                time.sleep(.1)
            child.close_confirmed()
        attempt('child_terminal_reap', drain)
    attempt('gpu_monitor', gpu.close)
    attempt('disk_monitor', disk.close)
    return outcomes


def parent(args):
    bindings(args.deploy)
    import m1_operations as operations
    from batch_budget import BatchBudget, activate_continuation_window
    from batch_ledger import M1_GPU0, BatchLedger
    from m1_admission import M1AdmissionConsumer
    from scripts.qa.disk_monitor import ProjectDiskMonitor
    from scripts.qa.gpu_monitor import GPU0Monitor
    from scripts.qa.linux_owned_child import LinuxOwnedChild, LinuxResources, command_digest, owned_loopback_listener
    from scripts.qa.worker_supervisor import Policy, WorkerSupervisor
    run = Path(args.run)
    if run.exists() or run.is_symlink() or not run.parent.resolve() == (PROJECT / 'runs').resolve():
        raise RuntimeError('FRESH_PROJECT_RUN_REQUIRED')
    run.mkdir(mode=0o700)
    (run / 'readback').mkdir(mode=0o700)
    new_json(run / 'STARTED_ONCE', {'started_utc': time.time(), 'session_seconds': SESSION_SECONDS})
    result = {'window_id': None, 'automatic_retries': 0}
    disk, gpu, child, supervisor = ProjectDiskMonitor(PROJECT), GPU0Monitor(GPU), None, None
    ledger = budget = lease = service = None
    started = time.monotonic()
    try:
        # Every refusable preflight happens BEFORE the window/lease exists:
        # confirming a stop permanently closes the only Server window.
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', PORT))
        disk.start()
        gpu.start()
        if gpu.sample()['vram_mib'] > 64:
            raise RuntimeError('GPU0_NOT_IDLE_NO_ADOPTION')
        models = operations.reviewed_models(Path(args.models).read_bytes(), read_json(args.prism_pins))
        os.environ.update({key: value for key, value in child_environment(run).items()
                           if key.startswith(('RETFOUND_', 'PRISM_', 'USPEC_'))})
        from dr_support.providers.prism_bound import BoundLocalPRISM
        if (BoundLocalPRISM(allow_cpu_fallback=False)._runtime_identity() != models[operations.PRISM]['pins']
                or any(global_identity(model_id) != models[model_id]['pins'] for model_id in operations.GLOBAL_MODELS)):
            raise RuntimeError('REVIEWED_MODEL_IDENTITY_CHANGED_BEFORE_RESERVATION')
        ledger = BatchLedger.for_continuation(
            args.accounting, proposal_path=args.proposal, approval_path=args.approval,
            proposal_sha256=args.proposal_sha256, approval_sha256=args.approval_sha256,
            upstream_paths=read_json(args.upstream_paths), installation_sha256=installation_digest(args.deploy))
        ledger.acquire()
        # The verified decision names its only Server window and caps.
        window = result['window_id'] = ledger.spec['server_window']
        clock_origin = host_clock_origin()
        if not (Path(args.accounting) / 'windows' / window).exists():
            activate_continuation_window(ledger, window_id=window, clock_origin=clock_origin, gpu_uuid=M1_GPU0)
        budget = BatchBudget(ledger, session_id=window, clock_origin=clock_origin)
        candidate = 'm1_server_' + uuid4().hex[:16]
        budget.reserve_worker(candidate)
        lease = result['lease_id'] = candidate
        argv = [str(PROJECT / 'environments/prism-qa-torch213/bin/python'), '-I', '-B',
                str(Path(__file__).resolve()), '--worker', '--deploy', str(args.deploy), '--run', str(run),
                '--models', str(args.models), '--prism-pins', str(args.prism_pins)]
        scope = window.lower()
        child = LinuxOwnedChild.spawn(argv, model_id='prism-dr-5fold', owner_scope=scope,
                                     resource_provider=LinuxResources(PROJECT, disk_monitor=disk, gpu_monitor=gpu),
                                     hard_seconds=CHILD_HARD_SECONDS, env=child_environment(run))
        window_jobs = sum(job['window_id'] == window for job in ledger.jobs.values())
        supervisor = WorkerSupervisor(Policy('prism-dr-5fold', os.getpid(), scope, command_digest(argv), GPU,
                                             max_jobs=window_jobs, max_seconds=SESSION_SECONDS, request_seconds=30,
                                             drain_seconds=20, monitor_seconds=2), child)
        consumer = M1AdmissionConsumer(ledger, budget, supervisor, child=child, lease_id=lease)
        service = ParentAdmissions(run, consumer=consumer, ledger=ledger, child=child,
                                   window_id=window, operations=operations, readback_dir=run / 'readback')
        announced = False
        while child.inspect():
            supervisor.tick()
            if not announced and (run / 'READY.json').is_file() and owned_loopback_listener(PORT, child.identity.pid):
                print(json.dumps({'phase': 'READY', 'remote_loopback_url': f'http://127.0.0.1:{PORT}',
                                  'run': str(run), 'max_session_seconds': SESSION_SECONDS}), flush=True)
                announced = True
            if announced:
                service.service()
                replace_json(run / 'STATUS.json', service.status(budget=budget, supervisor=supervisor,
                                                                 started=started))
            if ((run / 'STOP_REQUESTED').exists() or time.monotonic() - started >= SESSION_SECONDS
                    or service.stop_reason is not None or supervisor.state not in {'IDLE', 'BUSY'}):
                break
            if not announced and time.monotonic() - started > 240:
                raise RuntimeError('LOAD_READINESS_DEADLINE')
            time.sleep(.25)
    except BaseException as error:
        result['error_class'] = type(error).__name__
    finally:
        result['cleanup_components'] = cleanup_owned(child, supervisor, gpu, disk)
        with socket.socket() as sock:
            result['listener_closed'] = sock.connect_ex(('127.0.0.1', PORT)) != 0
        result['cleanup_confirmed'] = (result['listener_closed']
                                       and all(item['confirmed'] for item in result['cleanup_components'].values()))
        if child is not None:
            result['completion'] = child.completion()
        result['supervisor_reason'] = supervisor.reason if supervisor is not None else None
        result['stop_reason'] = service.stop_reason if service is not None else None
        result['requests'] = service.requests if service is not None else {}
        result['observed_session_seconds'] = round(time.monotonic() - started, 3)
        actions = []
        if lease is not None:
            # Only a reserved lease is stopped; that confirmed stop closes the window.
            actions.append(('window_stop', lambda: budget.confirm_stop(lease, cleanup_confirmed=result['cleanup_confirmed'])))
        if ledger is not None and ledger.owned_lock is not None:
            actions.append(('ledger_close', lambda: ledger.close(cleanup_confirmed=result['cleanup_confirmed'])))
        for name, action in actions:
            try:
                action()
                result[name] = 'CONFIRMED'
            except BaseException as error:
                # Uncertain stop keeps its reservation/quarantine; no refund or unlock.
                result[name] = 'RETAINED_' + type(error).__name__
        result['window_stop'] = result.get('window_stop', 'NO_LEASE_RESERVED')
        result['ledger_close'] = result.get('ledger_close', 'NOT_OPENED')
        result['accounting'] = service.consumer.status() if service is not None else None
        try:
            new_json(run / 'COMPLETE.json', result)
        except OSError:
            result['logging_blocked'] = True
        print(json.dumps({'phase': 'STOPPED', **{key: result[key] for key in (
            'cleanup_confirmed', 'listener_closed', 'stop_reason', 'window_stop', 'ledger_close')}}), flush=True)
    return 0 if result['cleanup_confirmed'] and 'error_class' not in result else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['start', 'identity', 'status', 'stop', 'handover', 'verify'],
                        nargs='?', default='start')
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--deploy', type=Path)
    parser.add_argument('--run', type=Path)
    parser.add_argument('--models', type=Path)
    parser.add_argument('--prism-pins', type=Path)
    parser.add_argument('--accounting', type=Path)
    parser.add_argument('--proposal', type=Path)
    parser.add_argument('--approval', type=Path)
    parser.add_argument('--proposal-sha256')
    parser.add_argument('--approval-sha256')
    parser.add_argument('--upstream-paths', type=Path)
    parser.add_argument('--source-deploy', type=Path, help='handover: the source decision\'s own deployment')
    args = parser.parse_args()
    if sys.platform != 'linux':
        parser.error('Run on the approved GPU host through the existing SSH connection')
    if args.worker:
        return worker(args)
    if args.command == 'identity':
        return identity_command(args)
    if args.command == 'handover':
        return handover_command(args)
    if args.command == 'verify':
        return verify_command(args)
    if args.command == 'status':
        print((Path(args.run) / 'STATUS.json').read_text())
        return 0
    if args.command == 'stop':
        new_json(Path(args.run) / 'STOP_REQUESTED', {'requested': True})
        return 0
    return parent(args)


if __name__ == '__main__':
    raise SystemExit(main())
