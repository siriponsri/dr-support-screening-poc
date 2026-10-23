"""Finite interactive QA binding of the existing ordinary Model API.

Import is inert. No new model implementation, credentials, public listener,
clinical authority, inference retries, or persistent service registration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
from threading import RLock
import time

PROJECT = Path('/home/siripon/projects/dr-model-api-qa')
STAGE = PROJECT / 'deployments/demo-batch-20261022-b03r8'
GPU = 'GPU-044a8b11-4729-458b-a07b-297e45439419'
PRIOR_SHA = 'ebc4f23ac5b9d89f136ada7a36b08350ddacf186e338a50c0ea5ba6f5ba14d98'
PRIOR_USED, CAP = 525, 529
MODELS = {'uspec-uwf-grading', 'retfound-aptos5', 'prism-dr-5fold'}
PATHS = {'/v1/predict/dr', '/v1/predict/lesions', '/v2/predict/dr', '/v2/predict/lesions'}
SOFT_SECONDS, HARD_SECONDS = 2400, 2430


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def new_json(path, value):
    with Path(path).open('xb') as stream:
        stream.write(canonical(value))
        stream.flush()
        os.fsync(stream.fileno())


class RequestJournal:
    """Four new requests anchored to the immutable closed batch, never replayed.

    Intent is fsynced before ordinary API dispatch. A terminal logging failure
    quarantines further calls without turning a returned inference into failure.
    No constructor resumes/replaces an existing session or journal.
    """
    def __init__(self, path, *, prior_raw, expected_prior=PRIOR_SHA):
        if sha(prior_raw) != expected_prior or not prior_raw.endswith(b'\n'):
            raise ValueError('PRIOR_LEDGER_CHANGED')
        rows = [json.loads(line) for line in prior_raw.splitlines()]
        prior = '0' * 64
        attempts, states = set(), {}
        for seq, row in enumerate(rows, 1):
            body = {k: v for k, v in row.items() if k != 'hash'}
            if row['seq'] != seq or row['previous'] != prior or sha(canonical(body)) != row['hash']:
                raise ValueError('PRIOR_LEDGER_CHAIN_INVALID')
            prior = row['hash']
            states[row['job_id']] = row['state']
            if row['state'] == 'ATTEMPT_INTENT':
                if row['job_id'] in attempts:
                    raise ValueError('PRIOR_DUPLICATE_INTENT')
                attempts.add(row['job_id'])
        if any(s not in {'PASS_READBACK', 'FAILED_NO_RETRY', 'BLOCKED_PREMODEL'} for s in states.values()):
            raise ValueError('PRIOR_BATCH_NOT_CLOSED')
        self.base = 49 + len(attempts)
        if self.base != PRIOR_USED:
            raise ValueError('EXACT_REMAINING_FOUR_REQUIRED')
        self.path, self.lock = Path(path), RLock()
        self.used, self.seen, self.sequence = self.base, set(), 0
        self.previous, self.poisoned = '0' * 64, False
        self.log_failure = False
        with self.path.open('xb') as stream:
            self._write(stream, {'state': 'ANCHOR', 'prior_ledger_sha256': expected_prior,
                                 'base_used': self.base, 'cap': CAP})

    def _write(self, stream, value):
        body = {**value, 'sequence': self.sequence + 1, 'previous': self.previous}
        row = {**body, 'hash': sha(canonical(body))}
        raw = canonical(row) + b'\n'
        if stream.write(raw) != len(raw):
            raise OSError('PARTIAL_JOURNAL_WRITE')
        stream.flush()
        os.fsync(stream.fileno())
        self.sequence += 1
        self.previous = row['hash']

    def claim(self, model, image_sha, request_raw):
        with self.lock:
            identity = (model, image_sha)
            if self.poisoned or self.used >= CAP or model not in MODELS or identity in self.seen:
                return False
            try:
                with self.path.open('ab') as stream:
                    self._write(stream, {'state': 'ATTEMPT_INTENT', 'model_id': model,
                                         'image_sha256': image_sha, 'request_sha256': sha(request_raw),
                                         'global_used': self.used + 1})
            except OSError:
                self.poisoned = self.log_failure = True
                raise
            self.used += 1
            self.seen.add(identity)
            return True

    def terminal(self, status, response_sha):
        with self.lock:
            try:
                with self.path.open('ab') as stream:
                    self._write(stream, {'state': 'HTTP_RESPONSE', 'http_status': status,
                                         'response_sha256': response_sha, 'global_used': self.used})
            except OSError:
                self.poisoned = self.log_failure = True
                # Intent remains durable. Preserve the actual HTTP/model result.

    def status(self):
        return {'global_used': self.used, 'cap': CAP, 'remaining': CAP - self.used,
                'quarantined': self.poisoned, 'logging_blocked': self.log_failure,
                'automatic_retries': 0}


class QuotaApplication:
    def __init__(self, app, journal, *, stop, metadata):
        self.app, self.journal, self.stop, self.metadata = app, journal, stop, metadata

    async def respond(self, send, code, value):
        raw = canonical(value)
        await send({'type': 'http.response.start', 'status': code,
                    'headers': [(b'content-type', b'application/json'), (b'cache-control', b'no-store')]})
        await send({'type': 'http.response.body', 'body': raw})

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        path, method = scope['path'], scope['method']
        if method == 'GET' and path == '/__demo/status':
            return await self.respond(send, 200, {**self.metadata(), **self.journal.status()})
        if method == 'POST' and path == '/__demo/stop':
            await self.respond(send, 202, {'status': 'STOP_REQUESTED'})
            self.stop()
            return
        if method == 'GET':
            return await self.app(scope, receive, send)
        if method != 'POST' or path not in PATHS:
            return await self.respond(send, 405, {'detail': 'Outside demo session scope'})
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body.extend(message.get('body', b''))
            if len(body) > 20_100_000:
                return await self.respond(send, 413, {'detail': 'Request too large'})
            if not message.get('more_body'):
                break
        try:
            payload = json.loads(body)
            model, image_sha = payload['model_id'], payload['image_sha256']
            if not isinstance(image_sha, str) or len(image_sha) != 64:
                raise ValueError('INVALID_IMAGE_DIGEST')
            admitted = self.journal.claim(model, image_sha, bytes(body))
        except (ValueError, KeyError, TypeError):
            return await self.respond(send, 422, {'detail': 'Invalid prediction envelope'})
        except OSError:
            return await self.respond(send, 503, {'detail': 'Accounting unavailable; no inference dispatched'})
        if not admitted:
            return await self.respond(send, 409, {'detail': 'Demo allowance unavailable or request already consumed'})
        response_hash, status = hashlib.sha256(), 500
        async def replay():
            return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
        async def observe(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
            if message['type'] == 'http.response.body':
                response_hash.update(message.get('body', b''))
            await send(message)
        try:
            await self.app(scope, replay, observe)
        finally:
            self.journal.terminal(status, response_hash.hexdigest())


def bindings():
    # Existing reviewed source/control adapters only; no imports start a model.
    sys.path[:0] = [str(STAGE / 'source42'), str(STAGE / 'base-q06')]
    # Same Python/Torch/CUDA versions in both installed environments. Add only
    # fallback dependencies (timm); PRISM environment remains first on sys.path.
    extras = list((PROJECT / 'environments/uspec-qa-torch213/lib').glob('python*/site-packages'))
    if len(extras) != 1:
        raise RuntimeError('EXISTING_TIMM_ENVIRONMENT_REQUIRED')
    sys.path.append(str(extras[0]))


def worker(run):
    bindings()
    from approved_token_reader import read_private_token
    token = read_private_token(PROJECT / 'config/private/model-api.env')
    os.environ['REMOTE_MODEL_TOKEN'] = token
    from dr_support.run import configure
    configure()
    from dr_support.services.model_api import create_app
    from dr_support.services.prism_owned_runtime import torch_load_forward_guard
    from scripts.qa.private_gateway_auth import PrivateGatewayAuth
    import torch
    import uvicorn
    if torch.cuda.device_count() != 1 or os.environ.get('CUDA_VISIBLE_DEVICES') != GPU:
        raise RuntimeError('SOLE_APPROVED_GPU0_REQUIRED')
    torch.cuda.set_per_process_memory_fraction(10240 * 1024**2 / torch.cuda.get_device_properties(0).total_memory, 0)
    app = create_app()
    journal = RequestJournal(run / 'REQUESTS.jsonl', prior_raw=(run / 'PRIOR_LEDGER.jsonl').read_bytes())
    loads = []
    for model_id, provider in app.state.providers.items():
        started = time.monotonic()
        try:
            with torch_load_forward_guard() as guard:
                provider.load()
        except BaseException as error:
            new_json(run / 'LOAD_FAILURE.json', {'model_id': model_id,
                     'error_class': type(error).__name__, 'inference_requests': 0,
                     'loaded_models': [item['model_id'] for item in loads],
                     'forward_attempts_during_load': guard.forward_attempts})
            raise
        if guard.forward_attempts or provider.metadata()['status'] != 'LOADED':
            raise RuntimeError('REAL_LOAD_WITHOUT_FORWARD_REQUIRED')
        loads.append({'model_id': model_id, 'load_seconds': round(time.monotonic() - started, 3),
                      'forward_attempts_during_load': guard.forward_attempts, 'metadata': provider.metadata()})
    # One activation across run directories. Never clear this marker to obtain
    # four more requests while the old batch anchor remains unchanged.
    new_json(PROJECT / 'runs/INTERACTIVE_REMAINING_FOUR_20261023.json',
             {'run': str(run.resolve()), 'prior_used': PRIOR_USED,
              'prior_ledger_sha256': PRIOR_SHA, 'cap': CAP})
    ready = {'status': 'LOADED_NOT_YET_INFERENCE_VALIDATED', 'models': loads, 'gpu_uuid': GPU,
             'prior_used': PRIOR_USED, 'cap': CAP, 'session_soft_seconds': SOFT_SECONDS}
    new_json(run / 'READY.json', ready)
    def stop():
        if not (run / 'STOP_REQUESTED').exists():
            new_json(run / 'STOP_REQUESTED', {'requested': True})
    scoped = QuotaApplication(app, journal, stop=stop, metadata=lambda: ready)
    uvicorn.run(PrivateGatewayAuth(scoped, token), host='127.0.0.1', port=7860,
                workers=1, access_log=False, log_level='critical', log_config=None,
                timeout_graceful_shutdown=10)


def parent(run):
    bindings()
    from scripts.qa.linux_owned_child import LinuxOwnedChild, LinuxResources, command_digest, owned_loopback_listener
    from scripts.qa.disk_monitor import ProjectDiskMonitor
    from scripts.qa.gpu_monitor import GPU0Monitor
    from scripts.qa.worker_supervisor import Policy, WorkerSupervisor
    if not run.resolve().is_relative_to(PROJECT / 'runs') or run.is_symlink():
        raise RuntimeError('PROJECT_OWNED_FRESH_RUN_REQUIRED')
    new_json(run / 'STARTED_ONCE', {'started_utc': time.time(), 'hard_seconds': HARD_SECONDS})
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 7860))
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'LANG': 'C.UTF-8',
           'PYTHONDONTWRITEBYTECODE': '1', 'CUDA_VISIBLE_DEVICES': GPU,
           'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'YOLO_AUTOINSTALL': 'false',
           'YOLO_OFFLINE': 'true', 'YOLO_CONFIG_DIR': str(run / 'ultralytics'),
           'APP_PROFILE': 'model_api', 'MODEL_RUNTIME': 'local', 'INFERENCE_DEVICE': 'cuda:0',
           'MODEL_API_PROVIDER_SET': 'combined', 'MODEL_REQUIRE_VERIFIED_ASSETS': '1',
           'MODEL_ALLOW_AUTHORIZED_HOSPITAL': '1', 'MODEL_HOSPITAL_SCOPE': 'PRIVATE_PROJECT_EVALUATION',
           'USPEC_ENABLE_CANDIDATE_LOAD': '1', 'USPEC_MODEL_DIR': str(PROJECT / 'artifact-staging-20261020/uspec'),
           'RETFOUND_SOURCE': str(PROJECT / 'upstream-sources/retfound-ae9a9ec'),
           'RETFOUND_WEIGHTS': str(PROJECT / 'artifacts/retfound/retfound-aptos.pth'),
           'PRISM_SOURCE': str(PROJECT / 'upstream-sources/prism-7963744'),
           'PRISM_WEIGHTS': str(PROJECT / 'artifact-staging-20261020/prism'), 'PRISM_THRESHOLDS': '{}',
           'MODEL_CPU_THREADS': '2', 'OMP_NUM_THREADS': '2', 'MKL_NUM_THREADS': '2'}
    disk, gpu, child, supervisor = ProjectDiskMonitor(PROJECT), GPU0Monitor(GPU), None, None
    result = {'cleanup_confirmed': False, 'new_inference_scope': 4, 'prior_ledger_untouched': True}
    started = time.monotonic()
    try:
        disk.start()
        gpu.start()
        if gpu.sample()['vram_mib'] > 64:
            raise RuntimeError('GPU0_NOT_IDLE_NO_ADOPTION')
        argv = [str(PROJECT / 'environments/prism-qa-torch213/bin/python'), '-I', '-B',
                str(Path(__file__).resolve()), '--worker', '--run', str(run)]
        scope = 'interactive_main_demo_20261023'
        child = LinuxOwnedChild.spawn(argv, model_id='prism-dr-5fold', owner_scope=scope,
                                     resource_provider=LinuxResources(PROJECT, disk_monitor=disk, gpu_monitor=gpu),
                                     hard_seconds=HARD_SECONDS, env=env)
        supervisor = WorkerSupervisor(Policy('prism-dr-5fold', os.getpid(), scope, command_digest(argv),
                                            GPU, max_jobs=4, max_seconds=SOFT_SECONDS, drain_seconds=20,
                                            monitor_seconds=2), child)
        announced = False
        while child.inspect():
            supervisor.tick()
            if not announced and (run / 'READY.json').is_file() and owned_loopback_listener(7860, child.identity.pid):
                print(json.dumps({'phase': 'READY', 'remote_loopback_url': 'http://127.0.0.1:7860',
                                  'run': str(run), 'models_really_loaded': 3, 'forward_attempts': 0,
                                  'max_session_seconds': SOFT_SECONDS}), flush=True)
                announced = True
            if (run / 'STOP_REQUESTED').exists() or time.monotonic() - started >= SOFT_SECONDS:
                break
            if not announced and time.monotonic() - started > 180:
                raise RuntimeError('LOAD_READINESS_DEADLINE')
            if supervisor.state != 'IDLE':
                break
            time.sleep(.5)
    except BaseException as error:
        result['error_class'] = type(error).__name__
        result['raw_error_retained'] = False
    finally:
        if child is not None:
            if supervisor is not None:
                supervisor.close()
            elif child.inspect():
                child.signal_verified(child.identity, force=False)
            until = time.monotonic() + 22
            while child.inspect() and time.monotonic() < until:
                if supervisor is not None:
                    supervisor.tick()
                time.sleep(.1)
            if child.inspect():
                child.signal_verified(child.identity, force=True)
            until = time.monotonic() + 5
            while child.inspect() and time.monotonic() < until:
                time.sleep(.1)
            child.close_confirmed()
            result['completion'] = child.completion()
        gpu.close()
        disk.close()
        with socket.socket() as sock:
            result['cleanup_confirmed'] = sock.connect_ex(('127.0.0.1', 7860)) != 0
        result['observed_session_seconds'] = round(time.monotonic() - started, 3)
        result['conservative_gpu_reserved_seconds'] = HARD_SECONDS
        new_json(run / 'COMPLETE.json', result)
        print(json.dumps({'phase': 'STOPPED', **result}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'linux':
        parser.error('Start through the existing approved SSH connection on dr-train')
    (worker if args.worker else parent)(args.run)


if __name__ == '__main__':
    main()
