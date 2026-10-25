"""MS-03 phase A: bounded synthetic watchdog/OOM qualification on the approved GPU host.

Import is inert. No model weights, images, credentials, listener or inference
request. One owned parent holds the service decision's ledger, activates its
watchdog window (the first in the decision's order, with no operations) and
reserves that window's single lifetime lease. Each synthetic case then runs in a
fresh owned child under a WorkerSupervisor with low ceilings, wrapped in prlimit
and nice. GPU1 compute processes and the Ollama processes are recorded before
and after and must not change. Confirmed cleanup closes the window; the service
window can be activated only afterwards (batch_budget window order).

  start   run every case once inside the one lease and write WATCHDOG.json
  verify  print the cases and child commands; no ledger, window, GPU or child

The child side (``--child CASE``) uses only the standard library and torch, so
it runs with ``python -I`` without importing this repository.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from uuid import uuid4

PROJECT = Path('/home/siripon/projects/dr-model-api-qa')
GPU = 'GPU-044a8b11-4729-458b-a07b-297e45439419'
PYTHON = PROJECT / 'environments/prism-qa-torch213/bin/python'
PRLIMIT, NICE = '/usr/bin/prlimit', '/usr/bin/nice'
MIB, GIB = 1024**2, 1024**3
FRACTION_MIB = 1536          # torch per-process memory fraction for CUDA cases
IDLE_VRAM_MIB = 64
PHASE_SECONDS = 780          # Inside the 900 s lease with room for final cleanup.
ROLE = 'qa-watchdog-probe'
TERMINAL_STATES = {'STOPPED', 'UNCONFIRMED_STOP', 'UNVERIFIED'}
# Linux signal numbers (expected child return codes); this module also imports on Windows for tests.
SIGKILL, SIGALRM, SIGTERM = 9, 14, 15
# One synthetic child per case. `expect` is what a correct, safe stop looks like.
CASES = (
    {'case': 'oom-contained', 'cuda': True, 'max_vram_mib': 2048, 'max_rss_bytes': 4 * GIB,
     'request_seconds': 10, 'max_seconds': 90, 'hard_seconds': 120,
     'expect': {'state': 'STOPPED', 'reason': 'WORKER_EXITED', 'returncode': 0, 'oom_raised': True}},
    {'case': 'vram-limit', 'cuda': True, 'max_vram_mib': 768, 'max_rss_bytes': 4 * GIB,
     'request_seconds': 10, 'max_seconds': 90, 'hard_seconds': 120,
     'expect': {'state': 'STOPPED', 'reason': 'VRAM_LIMIT', 'returncode': -SIGKILL}},
    {'case': 'rss-limit', 'cuda': False, 'max_vram_mib': 2048, 'max_rss_bytes': 4 * GIB,
     'request_seconds': 10, 'max_seconds': 90, 'hard_seconds': 120, 'address_space': 6 * GIB,
     'expect': {'state': 'STOPPED', 'reason': 'RSS_LIMIT', 'returncode': -SIGTERM}},
    {'case': 'request-timeout', 'cuda': True, 'max_vram_mib': 2048, 'max_rss_bytes': 4 * GIB,
     'request_seconds': 10, 'max_seconds': 90, 'hard_seconds': 120, 'admit': True,
     'expect': {'state': 'STOPPED', 'reason': 'REQUEST_TIMEOUT', 'returncode': -SIGTERM}},
    {'case': 'hard-alarm', 'cuda': False, 'max_vram_mib': 2048, 'max_rss_bytes': 4 * GIB,
     'request_seconds': 10, 'max_seconds': 90, 'hard_seconds': 15,
     'expect': {'state': 'STOPPED', 'reason': 'WORKER_EXITED', 'returncode': -SIGALRM}},
)


# ---------------------------------------------------------------------------
# Child: synthetic behaviours only (stdlib + torch)
# ---------------------------------------------------------------------------


def _child_receipt(run, case, value):
    path = Path(run) / f'{case}.child.json'
    temporary = path.with_name(f'.{path.name}.{uuid4().hex}.pending')
    with temporary.open('xb') as stream:
        stream.write(json.dumps(value, sort_keys=True).encode())
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _cuda():
    import torch
    if torch.cuda.device_count() != 1:
        raise SystemExit(4)
    total = torch.cuda.get_device_properties(0).total_memory
    torch.cuda.set_per_process_memory_fraction(FRACTION_MIB * MIB / total, 0)
    return torch


def child(case, run):
    if case == 'oom-contained':
        torch = _cuda()
        blocks, raised = [], False
        try:
            while len(blocks) * 32 < 2 * FRACTION_MIB:  # Bounded even if the fraction were ignored.
                blocks.append(torch.empty(32 * MIB, dtype=torch.uint8, device='cuda'))
        except torch.cuda.OutOfMemoryError:
            raised = True
        allocated = len(blocks) * 32
        blocks.clear()
        torch.cuda.empty_cache()
        _child_receipt(run, case, {'oom_raised': raised, 'allocated_mib': allocated, 'fraction_mib': FRACTION_MIB})
        return 0 if raised else 3
    if case == 'vram-limit':
        signal.signal(signal.SIGTERM, signal.SIG_IGN)  # Only the supervisor's forced stop can end it.
        torch = _cuda()
        held = torch.empty(1024 * MIB, dtype=torch.uint8, device='cuda')
        held.fill_(1)
        torch.cuda.synchronize()
        time.sleep(60)
        return 5
    if case == 'rss-limit':
        held = []
        while len(held) < 40:  # At most 5 GiB, touched so it is resident; prlimit caps address space.
            held.append(bytearray(b'\x01') * (128 * MIB))
            time.sleep(.1)
        time.sleep(60)
        return 5
    if case == 'request-timeout':
        torch = _cuda()
        value = torch.ones((1024, 1024), device='cuda')
        _child_receipt(run, case, {'ready': True})
        until = time.monotonic() + 60
        while time.monotonic() < until:  # A slow "request" doing small real GPU work.
            value = (value @ value).clamp_(0, 1)
            torch.cuda.synchronize()
            time.sleep(.05)
        return 5
    if case == 'hard-alarm':
        signal.signal(signal.SIGTERM, signal.SIG_IGN)  # The bootstrap's hard alarm must end it.
        time.sleep(60)
        return 5
    return 2


# ---------------------------------------------------------------------------
# Parent: pure helpers (unit tested)
# ---------------------------------------------------------------------------


def child_argv(spec, run, *, python=PYTHON, script=None):
    """prlimit (no core, bounded files/descriptors, address space only without CUDA) then nice."""
    limits = ['--core=0', '--nofile=256', f'--fsize={64 * MIB}']
    if spec.get('address_space'):
        limits.append(f"--as={spec['address_space']}")
    return [PRLIMIT, *limits, '--', NICE, '-n', '10', str(python), '-I', '-B',
            str(script or Path(__file__).resolve()), '--child', spec['case'], '--run', str(run)]


def child_environment(spec):
    return {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1',
            'OMP_NUM_THREADS': '2', 'MKL_NUM_THREADS': '2',
            'CUDA_VISIBLE_DEVICES': GPU if spec['cuda'] else ''}


def evaluate(spec, observed):
    """Mismatches between one case's observation and its expected safe stop (empty = pass)."""
    expect = spec['expect']
    problems = [key for key in ('state', 'reason', 'returncode') if observed.get(key) != expect[key]]
    if 'oom_raised' in expect and (observed.get('child') or {}).get('oom_raised') is not expect['oom_raised']:
        problems.append('oom_raised')
    if observed.get('cleanup_confirmed') is not True:
        problems.append('cleanup_confirmed')
    peak = (observed.get('peaks') or {}).get('vram_mib')
    if spec['cuda'] and (type(peak) is not int or peak > 2048):
        problems.append('vram_peak')
    if spec.get('admit') and observed.get('admitted') is not True:
        problems.append('admitted')
    return problems


def stop_child(child, supervisor, *, clock=time.monotonic, sleep=time.sleep):
    """Close the supervisor and confirm the owned child is reaped; never skips the reap attempt."""
    outcomes = {}
    try:
        if supervisor is not None:
            supervisor.close()
        outcomes['supervisor_close'] = True
    except BaseException:
        outcomes['supervisor_close'] = False
    try:
        if child.inspect():
            child.signal_verified(child.identity, force=False)
        until = clock() + 12
        while child.inspect() and clock() < until:
            sleep(.1)
        if child.inspect():
            child.signal_verified(child.identity, force=True)
        until = clock() + 5
        while child.inspect() and clock() < until:
            sleep(.1)
        child.close_confirmed()
        outcomes['child_reaped'] = True
    except BaseException:
        outcomes['child_reaped'] = False
    return outcomes


def run_case(spec, *, spawn, supervise, run, clock=time.monotonic, sleep=time.sleep):
    """One synthetic child under its own supervisor; returns the observation (never raises)."""
    observed = {'case': spec['case'], 'admitted': False}
    child = supervisor = resources = None
    started = clock()
    try:
        child, resources = spawn(spec)
        supervisor = supervise(spec, child)
        until = started + spec['max_seconds'] + 30
        while supervisor.state not in TERMINAL_STATES and clock() < until:
            supervisor.tick()
            if (spec.get('admit') and not observed['admitted'] and supervisor.state == 'IDLE'
                    and (Path(run) / f"{spec['case']}.child.json").is_file()):
                supervisor.admit(f"watchdog-{spec['case']}")
                observed['admitted'] = True
            sleep(.25)
    except BaseException as error:
        observed['error_class'] = type(error).__name__
    finally:
        if child is not None:
            observed['cleanup'] = stop_child(child, supervisor, clock=clock, sleep=sleep)
            observed['cleanup_confirmed'] = all(observed['cleanup'].values())
            try:
                observed['returncode'] = child.completion()['child_returncode']
            except BaseException:
                observed['returncode'] = None
        else:
            # LinuxOwnedChild.spawn kills and reaps its unreleased child before raising; only a
            # reap timeout leaves the outcome uncertain.
            observed['cleanup_confirmed'] = observed.get('error_class') != 'TimeoutExpired'
        if supervisor is not None:
            observed['state'], observed['reason'] = supervisor.state, supervisor.reason
        if resources is not None:
            observed['peaks'] = dict(resources.peaks)
        receipt = Path(run) / f"{spec['case']}.child.json"
        if receipt.is_file() and receipt.stat().st_size < 4096:
            observed['child'] = json.loads(receipt.read_bytes())
        observed['seconds'] = round(clock() - started, 3)
    observed['problems'] = evaluate(spec, observed)
    observed['passed'] = not observed['problems']
    return observed


def team_unchanged(before, after):
    """GPU1 compute processes and Ollama processes are identical (memory is reported only)."""
    return (before.get('ok') is True and after.get('ok') is True
            and before['gpu1_compute_pids'] == after['gpu1_compute_pids']
            and before['ollama_pids'] == after['ollama_pids'])


# ---------------------------------------------------------------------------
# Real host wiring (dr-train only; never run in tests)
# ---------------------------------------------------------------------------


def _query(argv):
    return subprocess.run(argv, capture_output=True, text=True, timeout=10, check=True).stdout


def team_snapshot():
    """Read-only view of other users' GPU1 and Ollama work; nothing is signalled or changed."""
    try:
        indexes = dict(line.split(', ') for line in _query(
            ['nvidia-smi', '--query-gpu=index,uuid', '--format=csv,noheader']).splitlines() if line.strip())
        gpu1 = indexes['1']
        apps = [line.split(', ') for line in _query(
            ['nvidia-smi', '--query-compute-apps=gpu_uuid,pid', '--format=csv,noheader']).splitlines() if line.strip()]
        memory = _query(['nvidia-smi', '-i', '1', '--query-gpu=memory.used', '--format=csv,noheader,nounits'])
        ollama = subprocess.run(['pgrep', '-x', 'ollama'], capture_output=True, text=True, timeout=10).stdout
        return {'ok': True, 'gpu1_compute_pids': sorted(int(pid) for uuid, pid in apps if uuid == gpu1),
                'gpu0_compute_pids': sorted(int(pid) for uuid, pid in apps if uuid == GPU),
                'gpu1_memory_mib': int(memory.strip()), 'ollama_pids': sorted(int(pid) for pid in ollama.split())}
    except Exception as error:
        return {'ok': False, 'error_class': type(error).__name__}


def cgroup_check():
    """Read-only: is a cgroup v2 memory controller delegated to this user? Nothing is configured."""
    uid = os.getuid()
    delegated = Path(f'/sys/fs/cgroup/user.slice/user-{uid}.slice/user@{uid}.service/cgroup.controllers')
    try:
        controllers = delegated.read_text().split() if delegated.is_file() else []
        return {'cgroup_v2': Path('/sys/fs/cgroup/cgroup.controllers').is_file(),
                'user_memory_controller_delegated': 'memory' in controllers, 'configured': False}
    except OSError as error:
        return {'cgroup_v2': None, 'error_class': type(error).__name__, 'configured': False}


def watchdog(args):
    from m1_session import bindings, host_clock_origin, installation_digest, new_json, read_json
    bindings(args.deploy)
    from batch_budget import BatchBudget, activate_continuation_window
    from batch_ledger import M1_GPU0, BatchLedger, window_order
    from scripts.qa.disk_monitor import ProjectDiskMonitor
    from scripts.qa.gpu_monitor import GPU0Monitor
    from scripts.qa.linux_owned_child import LinuxOwnedChild, LinuxResources, command_digest
    from scripts.qa.worker_supervisor import Policy, WorkerSupervisor
    run = Path(args.run)
    if (run.exists() or run.is_symlink() or not run.parent.resolve() == (PROJECT / 'runs').resolve()
            or not re.fullmatch(r'm1-watchdog-[A-Za-z0-9_-]{1,80}', run.name)):
        raise RuntimeError('FRESH_PROJECT_WATCHDOG_RUN_REQUIRED')
    run.mkdir(mode=0o700)
    new_json(run / 'STARTED_ONCE', {'started_utc': time.time(), 'phase_seconds': PHASE_SECONDS})
    result = {'window_id': None, 'inference_requests': 0, 'automatic_retries': 0, 'cases': []}
    disk, gpu = ProjectDiskMonitor(PROJECT), GPU0Monitor(GPU)
    ledger = budget = lease = None
    started = time.monotonic()
    try:
        # Every refusable preflight happens BEFORE the window/lease exists.
        if not all(Path(item).is_file() for item in (PRLIMIT, NICE, PYTHON)):
            raise RuntimeError('PRLIMIT_NICE_AND_TORCH_PYTHON_REQUIRED')
        result['cgroup'] = cgroup_check()
        result['team_before'] = team_snapshot()
        if not result['team_before']['ok'] or result['team_before']['gpu0_compute_pids']:
            raise RuntimeError('TEAM_SNAPSHOT_OR_IDLE_GPU0_REQUIRED')
        disk.start()
        gpu.start()
        time.sleep(1)
        if gpu.sample()['vram_mib'] > IDLE_VRAM_MIB:
            raise RuntimeError('GPU0_NOT_IDLE_NO_ADOPTION')
        ledger = BatchLedger.for_continuation(
            args.accounting, proposal_path=args.proposal, approval_path=args.approval,
            proposal_sha256=args.proposal_sha256, approval_sha256=args.approval_sha256,
            upstream_paths=read_json(args.upstream_paths), installation_sha256=installation_digest(args.deploy))
        order = window_order(ledger.spec)
        # Only a decision whose first window carries no operations has a watchdog window.
        if len(order) < 2 or any(job['window_id'] == order[0] for job in ledger.jobs.values()):
            raise RuntimeError('SERVICE_DECISION_WATCHDOG_WINDOW_REQUIRED')
        ledger.acquire()
        window = result['window_id'] = order[0]
        clock_origin = host_clock_origin()
        if not (Path(args.accounting) / 'windows' / window).exists():
            activate_continuation_window(ledger, window_id=window, clock_origin=clock_origin, gpu_uuid=M1_GPU0)
        budget = BatchBudget(ledger, session_id=window, clock_origin=clock_origin)
        candidate = 'm1_watchdog_' + uuid4().hex[:16]
        budget.reserve_worker(candidate)
        lease = result['lease_id'] = candidate

        def spawn(spec):
            argv = child_argv(spec, run)
            resources = LinuxResources(PROJECT, disk_monitor=disk, gpu_monitor=gpu)
            scope = f"{window.lower()}-{spec['case']}"
            owned = LinuxOwnedChild.spawn(argv, model_id=ROLE, owner_scope=scope, resource_provider=resources,
                                          hard_seconds=spec['hard_seconds'], env=child_environment(spec))
            return owned, resources

        def supervise(spec, owned):
            argv = child_argv(spec, run)
            return WorkerSupervisor(Policy(ROLE, os.getpid(), owned.identity.owner_scope, command_digest(argv), GPU,
                                           max_jobs=1, max_seconds=spec['max_seconds'],
                                           request_seconds=spec['request_seconds'], drain_seconds=10,
                                           monitor_seconds=2, max_vram_mib=spec['max_vram_mib'],
                                           max_rss_bytes=spec['max_rss_bytes']), owned)

        for spec in CASES:
            if time.monotonic() - started + spec['max_seconds'] + 60 > PHASE_SECONDS or (run / 'STOP_REQUESTED').exists():
                result['cases'].append({'case': spec['case'], 'passed': False, 'problems': ['NOT_RUN']})
                continue
            result['cases'].append(run_case(spec, spawn=spawn, supervise=supervise, run=run))
            new_json(run / f"{spec['case']}.observed.json", result['cases'][-1])
        time.sleep(3)
        result['gpu0_vram_after_mib'] = gpu.sample()['vram_mib']
        result['team_after'] = team_snapshot()
    except BaseException as error:
        result['error_class'] = type(error).__name__
    finally:
        monitors = {}
        for name, monitor in (('gpu_monitor', gpu), ('disk_monitor', disk)):
            try:
                monitor.close()
                monitors[name] = True
            except BaseException:
                monitors[name] = False
        result['monitors_closed'] = monitors
        # A case that never ran has nothing to clean; every spawned child must be confirmed reaped.
        result['cleanup_confirmed'] = all(monitors.values()) and all(
            case.get('problems') == ['NOT_RUN'] or case.get('cleanup_confirmed') is True for case in result['cases'])
        actions = []
        if lease is not None:
            # Confirmed stop closes the watchdog window permanently (no refund, no renewal).
            actions.append(('window_stop', lambda: budget.confirm_stop(lease, cleanup_confirmed=result['cleanup_confirmed'])))
        if ledger is not None and ledger.owned_lock is not None:
            actions.append(('ledger_close', lambda: ledger.close(cleanup_confirmed=result['cleanup_confirmed'])))
        for name, action in actions:
            try:
                action()
                result[name] = 'CONFIRMED'
            except BaseException as error:
                result[name] = 'RETAINED_' + type(error).__name__
        result['window_stop'] = result.get('window_stop', 'NO_LEASE_RESERVED')
        result['ledger_close'] = result.get('ledger_close', 'NOT_OPENED')
        result['observed_seconds'] = round(time.monotonic() - started, 3)
        result['gpu0_idle_after'] = type(result.get('gpu0_vram_after_mib')) is int and result['gpu0_vram_after_mib'] <= IDLE_VRAM_MIB
        result['team_unchanged'] = team_unchanged(result.get('team_before', {}), result.get('team_after', {}))
        result['status'] = ('PASS' if (result['cases'] and all(case['passed'] for case in result['cases'])
                                       and result['gpu0_idle_after'] and result['team_unchanged']
                                       and result['cleanup_confirmed'] and 'error_class' not in result
                                       and result['window_stop'] == 'CONFIRMED'
                                       and result['ledger_close'] == 'CONFIRMED') else 'FAIL')
        try:
            new_json(run / 'WATCHDOG.json', result)
        except OSError:
            result['logging_blocked'] = True
        print(json.dumps({'phase': 'STOPPED', 'status': result['status'],
                          'cases': {case['case']: case['passed'] for case in result['cases']},
                          **{key: result.get(key) for key in ('window_stop', 'ledger_close', 'gpu0_idle_after',
                                                              'team_unchanged', 'error_class')}}), flush=True)
    return 0 if result['status'] == 'PASS' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['start', 'verify'], nargs='?', default='start')
    parser.add_argument('--child')
    parser.add_argument('--run', type=Path)
    parser.add_argument('--deploy', type=Path)
    parser.add_argument('--accounting', type=Path)
    parser.add_argument('--proposal', type=Path)
    parser.add_argument('--approval', type=Path)
    parser.add_argument('--proposal-sha256')
    parser.add_argument('--approval-sha256')
    parser.add_argument('--upstream-paths', type=Path)
    args = parser.parse_args()
    if args.child:
        return child(args.child, args.run)
    if args.command == 'verify':
        print(json.dumps({'cases': [{key: spec[key] for key in ('case', 'cuda', 'max_vram_mib', 'max_rss_bytes',
                                                                 'request_seconds', 'hard_seconds', 'expect')}
                                    | {'argv': child_argv(spec, Path('/run-placeholder'))} for spec in CASES],
                          'fraction_mib': FRACTION_MIB, 'phase_seconds': PHASE_SECONDS}, indent=1))
        return 0
    if sys.platform != 'linux':
        parser.error('Run on the approved GPU host through the existing SSH connection')
    return watchdog(args)


if __name__ == '__main__':
    raise SystemExit(main())
