"""One serial GPU0 telemetry sampler, independent of RPC/watchdog polling.

No CUDA or model imports. Construction/import is inert; start is explicit.
A transient query failure never becomes a fabricated zero/fresh measurement.
"""
import math
import re
import subprocess
from threading import Event, Lock, Thread
import time


GPU_ARGV = ['nvidia-smi', '-i', '0', '--query-gpu=uuid,memory.used', '--format=csv,noheader,nounits']


class OwnedGPUQuery:
    """Retain only our Popen handle; no PID attachment/group signal or restart."""
    def __init__(self, *, process_factory=subprocess.Popen):
        self.factory, self.lock, self.process = process_factory, Lock(), None
        self.poisoned = False

    def __call__(self, argv, *, timeout, **options):
        if argv != GPU_ARGV or timeout != 1.0:
            raise ValueError('FIXED_GPU_QUERY_REQUIRED')
        with self.lock:
            if self.process is not None or self.poisoned:
                raise RuntimeError('GPU_QUERY_HANDLE_UNAVAILABLE')
            process = self.factory(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, close_fds=True, shell=False)
            self.process = process
        try:
            try:
                output, _ = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()  # Only this exact spawn-owned Popen handle.
                try:
                    process.communicate(timeout=.25)
                except Exception:
                    self.poisoned = True
                    raise RuntimeError('GPU_QUERY_CLEANUP_UNCONFIRMED') from None
                raise
            if process.returncode:
                raise subprocess.CalledProcessError(process.returncode, GPU_ARGV)
            return subprocess.CompletedProcess(GPU_ARGV, 0, stdout=output.decode('ascii'))
        finally:
            if process.poll() is not None:
                with self.lock:
                    if self.process is process:
                        self.process = None
            else:
                self.poisoned = True

    def cancel_owned(self):
        if not self.lock.acquire(blocking=False):
            raise RuntimeError('GPU_QUERY_HANDLE_BUSY')
        try:
            if self.process is not None and self.process.poll() is None:
                self.process.kill()
        finally:
            self.lock.release()

    def close_confirmed(self):
        # Called only after the sampling thread has joined. Never race its
        # communicate/reap; an unconfirmed handle remains available for proof.
        with self.lock:
            process = self.process
            if process is not None:
                process.wait(timeout=.25)
                if process.poll() is None:
                    raise RuntimeError('GPU_QUERY_CLEANUP_UNCONFIRMED')
                self.process = None


class GPU0Monitor:
    QUERY_SECONDS = 1.0
    INTERVAL_SECONDS = .25
    FRESH_SECONDS = 2.5
    MAX_CONSECUTIVE_TRANSIENTS = 1
    MAX_VRAM_MIB = 10240
    SAFE_CLASSES = frozenset({'TimeoutExpired', 'CalledProcessError', 'PermissionError',
                              'FileNotFoundError', 'OSError', 'ValueError', 'RuntimeError'})

    def __init__(self, expected_uuid, *, runner=None, clock=time.monotonic,
                 thread_factory=Thread, event=None):
        if not isinstance(expected_uuid, str) or not re.fullmatch(r'GPU-[A-Za-z0-9-]{8,80}', expected_uuid):
            raise ValueError('EXACT_GPU0_UUID_REQUIRED')
        self.owned_query = OwnedGPUQuery() if runner is None else None
        self.expected_uuid, self.runner, self.clock = expected_uuid, self.owned_query if runner is None else runner, clock
        self.factory, self.stop = thread_factory, event if event is not None else Event()
        self.lock, self.query_lock = Lock(), Lock()
        self.thread = None
        self.started = self.closed = False
        self.value = self.measured_at = self.last_now = self.next_query_at = None
        self.failure = self.failure_detail = None
        self.query_attempts = self.query_successes = self.transient_failures = self.cache_reads = 0
        self.max_sample_age_seconds = 0.
        self.consecutive_failures = 0
        self.max_query_seconds = 0.
        self.over_limit = False

    def _now(self):
        now = self.clock()
        if (type(now) not in (int, float) or not math.isfinite(now)
                or self.last_now is not None and now < self.last_now):
            raise RuntimeError('GPU_CLOCK_INVALID')
        self.last_now = now
        return now

    def _fail(self, reason, stage, error):
        self.failure = reason
        kind = type(error).__name__
        self.failure_detail = {'stage': stage, 'exception_class': kind if kind in self.SAFE_CLASSES else 'OTHER', 'reason': reason}

    def refresh_once(self):
        # Start plus the one watch thread use this port. A programming error
        # cannot spawn a second overlapping nvidia-smi process.
        if not self.query_lock.acquire(blocking=False):
            raise RuntimeError('GPU_QUERY_ALREADY_ACTIVE')
        attempted = False
        try:
            with self.lock:
                if not self.started or self.closed or self.stop.is_set() or self.failure:
                    raise RuntimeError('GPU_MONITOR_NOT_ACTIVE')
                started = self._now()
                if self.next_query_at is not None and started < self.next_query_at:
                    return False  # Coalesce eager/manual polling; no extra process.
                attempted = True
                self.query_attempts += 1
            stage = 'GPU_QUERY'
            try:
                result = self.runner(['nvidia-smi', '-i', '0', '--query-gpu=uuid,memory.used',
                                      '--format=csv,noheader,nounits'], capture_output=True,
                                     text=True, check=True, timeout=self.QUERY_SECONDS)
                with self.lock:
                    elapsed = self._now() - started
                if not 0 <= elapsed < self.QUERY_SECONDS:
                    raise RuntimeError('GPU_QUERY_INVALID_DURATION')
                stage = 'GPU_PARSE'
                if not isinstance(result.stdout, str) or len(result.stdout) > 4096:
                    raise ValueError('GPU_SAMPLE_INVALID')
                fields = result.stdout.strip().split(',')
                if len(fields) != 2 or fields[0].strip() != self.expected_uuid:
                    raise ValueError('GPU_IDENTITY_MISMATCH')
                memory = int(fields[1].strip())
                if memory < 0:
                    raise ValueError('GPU_SAMPLE_INVALID')
                with self.lock:
                    self.max_query_seconds = max(self.max_query_seconds, elapsed)
                    # Latch any measured over-limit value until teardown. A
                    # later low sample must not erase a missed resource spike.
                    self.over_limit = self.over_limit or memory > self.MAX_VRAM_MIB
                    if self.over_limit:
                        memory = max(memory, self.value or 0)
                    self.value, self.measured_at = memory, started
                    self.query_successes += 1
                    self.consecutive_failures = 0
                    self.failure_detail = None
                return True
            except Exception as error:
                with self.lock:
                    self.consecutive_failures += 1
                    age = self._now() - self.measured_at if self.measured_at is not None else None
                    transient = isinstance(error, (subprocess.TimeoutExpired, subprocess.CalledProcessError))
                    allowed = (transient and self.value is not None and age is not None
                               and 0 <= age <= self.FRESH_SECONDS
                               and self.consecutive_failures <= self.MAX_CONSECUTIVE_TRANSIENTS)
                    if allowed:
                        self.transient_failures += 1
                        self.failure_detail = {'stage': stage, 'exception_class': type(error).__name__, 'reason': 'GPU_QUERY_TRANSIENT'}
                        return False  # One scheduled future poll, never immediate retry.
                    reason = 'GPU_QUERY_FAILED'
                    if type(error) in (ValueError, RuntimeError) and error.args and error.args[0] in {
                            'GPU_CLOCK_INVALID', 'GPU_QUERY_INVALID_DURATION', 'GPU_SAMPLE_INVALID', 'GPU_IDENTITY_MISMATCH'}:
                        reason = error.args[0]
                    self._fail(reason, stage, error)
                raise
        finally:
            try:
                if attempted:
                    with self.lock:
                        try:
                            self.next_query_at = self._now() + self.INTERVAL_SECONDS
                        except Exception as error:
                            self._fail('GPU_CLOCK_INVALID', 'GPU_SAMPLE', error)
                            raise
            finally:
                self.query_lock.release()

    def sample(self):
        with self.lock:
            if not self.started or self.closed:
                raise RuntimeError('GPU_MONITOR_NOT_ACTIVE')
            if self.failure is not None:
                raise RuntimeError(self.failure)
            try:
                age = self._now() - self.measured_at if self.measured_at is not None else None
            except Exception as error:
                self._fail('GPU_CLOCK_INVALID', 'GPU_SAMPLE', error)
                raise
            if age is None or not math.isfinite(age) or not 0 <= age <= self.FRESH_SECONDS:
                error = RuntimeError('GPU_SAMPLE_STALE')
                self._fail('GPU_SAMPLE_STALE', 'GPU_SAMPLE', error)
                raise error
            self.cache_reads += 1
            self.max_sample_age_seconds = max(self.max_sample_age_seconds, age)
            return {'gpu_index': 0, 'gpu_uuid': self.expected_uuid, 'vram_mib': self.value,
                    'gpu_observed_at': self.measured_at}

    def start(self):
        if self.started:
            raise RuntimeError('GPU_MONITOR_NO_RESTART')
        self.started = True
        # A successful real, correctly identified measurement is required
        # before the worker is spawned. There is no healthy-zero default.
        self.refresh_once()
        if self.sample()['vram_mib'] > self.MAX_VRAM_MIB:
            raise RuntimeError('VRAM_LIMIT')
        def watch():
            while not self.stop.wait(self.INTERVAL_SECONDS):
                try:
                    self.refresh_once()
                except Exception:
                    return
        self.thread = self.factory(target=watch, daemon=False)
        self.thread.start()
        return self

    def stats(self):
        with self.lock:
            state = ('STOPPED' if self.closed else 'FAILED' if self.failure else
                     'NOT_STARTED' if not self.started else 'DEGRADED' if self.consecutive_failures else 'HEALTHY')
            return {'state': state, 'query_attempts': self.query_attempts,
                    'query_successes': self.query_successes, 'transient_failures': self.transient_failures,
                    'cache_reads': self.cache_reads, 'max_sample_age_seconds': self.max_sample_age_seconds,
                    'consecutive_failures': self.consecutive_failures,
                    'max_query_seconds': self.max_query_seconds,
                    'query_timeout_seconds': self.QUERY_SECONDS, 'fresh_seconds': self.FRESH_SECONDS,
                    'interval_seconds': self.INTERVAL_SECONDS,
                    'failure_reason': self.failure, 'over_limit_latched': self.over_limit}

    def close(self):
        self.stop.set()
        first_error = None
        if self.owned_query is not None:
            try:
                self.owned_query.cancel_owned()
            except BaseException as error:
                first_error = error
        thread_stopped = self.thread is None
        if self.thread is not None:
            try:
                self.thread.join(timeout=self.QUERY_SECONDS + .5)
                thread_stopped = not self.thread.is_alive()
                if not thread_stopped:
                    raise RuntimeError('GPU_MONITOR_STOP_UNCONFIRMED')
            except BaseException as error:
                if first_error is None:
                    first_error = error
        if thread_stopped and self.owned_query is not None:
            try:
                self.owned_query.close_confirmed()
            except BaseException as error:
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error
        self.closed = True
