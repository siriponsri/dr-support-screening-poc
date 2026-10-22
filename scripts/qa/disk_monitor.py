"""Full-project accounting off the live GPU/RSS sampling path. Import is inert."""
import math
import subprocess
import time
from threading import Event, Lock, Thread


class ProjectDiskMonitor:
    SCAN_SECONDS = 5.0
    FRESH_SECONDS = 10.0
    INTERVAL_SECONDS = 1.0
    QUOTA_BYTES = 40 * 1024**3

    def __init__(self, project, *, runner=subprocess.run, clock=time.monotonic,
                 thread_factory=Thread, event=None):
        self.project, self.runner, self.clock = project, runner, clock
        self.factory, self.stop = thread_factory, event if event is not None else Event()
        self.lock, self.thread = Lock(), None
        self.value = self.measured_at = self.failure = None
        self.failure_detail = None
        self.started = False

    def refresh_once(self):
        started = self.clock()
        stage = 'PROJECT_DU'
        try:
            result = self.runner(['du', '-sb', '--', str(self.project)],
                                 capture_output=True, text=True, check=True,
                                 timeout=self.SCAN_SECONDS)
            elapsed = self.clock() - started
            stage = 'PROJECT_PARSE'
            value = int(result.stdout.split()[0])
            if not math.isfinite(elapsed) or not 0 <= elapsed <= self.SCAN_SECONDS or value < 0:
                raise RuntimeError('PROJECT_SAMPLE_INVALID')
            with self.lock:
                self.value, self.measured_at = value, started
        except Exception as error:
            with self.lock:
                self.failure = 'PROJECT_SCAN_FAILED'
                kind = type(error).__name__
                self.failure_detail = {'stage': stage, 'exception_class': kind if kind in {'TimeoutExpired', 'CalledProcessError', 'PermissionError', 'FileNotFoundError', 'OSError', 'ValueError', 'IndexError', 'RuntimeError'} else 'OTHER'}
            raise

    def sample(self):
        with self.lock:
            age = self.clock() - self.measured_at if self.measured_at is not None else None
            if self.failure is not None:
                raise RuntimeError('PROJECT_SCAN_FAILED')
            if age is None or not math.isfinite(age) or not 0 <= age <= self.FRESH_SECONDS:
                raise RuntimeError('PROJECT_SAMPLE_STALE')
            return self.value

    def start(self):
        if self.started:
            raise RuntimeError('PROJECT_MONITOR_NO_RESTART')
        self.started = True
        # No child/model starts until a complete real full-project measurement.
        self.refresh_once()
        if self.sample() > self.QUOTA_BYTES:
            raise RuntimeError('PROJECT_DISK_LIMIT')
        def watch():
            while not self.stop.wait(self.INTERVAL_SECONDS):
                try:
                    self.refresh_once()
                except Exception:
                    return  # Invalidate cache, no silent retry/healthy fallback.
        self.thread = self.factory(target=watch, daemon=False)
        self.thread.start()
        return self

    def close(self):
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=self.SCAN_SECONDS + .5)
            if self.thread.is_alive():
                raise RuntimeError('PROJECT_MONITOR_STOP_UNCONFIRMED')
