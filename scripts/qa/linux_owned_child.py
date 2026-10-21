"""Linux-only owned-spawn/pidfd adapter. Importing this module starts nothing."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time
from threading import Thread

from scripts.qa.worker_supervisor import ChildIdentity, Observation, TerminalObservation


# The new child cannot exec until its parent has pinned a pidfd. EOF/timeout
# causes self-exit; parent death kills only this owned child, including after exec.
BOOTSTRAP = """
import ctypes,json,os,select,signal,sys
fd,parent,seconds=int(sys.argv[1]),int(sys.argv[2]),int(sys.argv[3])
libc=ctypes.CDLL(None,use_errno=True)
if libc.prctl(1,signal.SIGKILL,0,0,0)!=0 or os.getppid()!=parent: sys.exit(91)
signal.alarm(seconds)
if not select.select([fd],[],[],5)[0] or os.read(fd,1)!=b'G': sys.exit(92)
os.close(fd)
argv=json.loads(sys.argv[4])
os.execv(argv[0],argv)
"""


def command_digest(argv: list[str]) -> str:
    return hashlib.sha256(json.dumps(argv, separators=(",", ":")).encode()).hexdigest()


def proc_identity(pid: int) -> tuple[int, str]:
    info = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    return int(info[1]), boot + ":" + info[19]


def owned_loopback_listener(port: int, pid: int) -> bool:
    """Read-only listener inode qualification, tolerating closed transient FDs."""
    if type(port) is not int or not 1 <= port <= 65535 or type(pid) is not int or pid <= 1:
        raise ValueError("INVALID_LISTENER_TARGET")
    rows = []
    for table in ('tcp', 'tcp6'):
        for row in Path('/proc/net', table).read_text().splitlines()[1:]:
            fields = row.split()
            address, encoded_port = fields[1].split(':')
            if fields[3] == '0A' and int(encoded_port, 16) == port:
                rows.append((table, address, fields[9]))
    if not rows:
        return False
    sockets = set()
    for node in Path(f'/proc/{pid}/fd').iterdir():
        try:
            sockets.add(os.readlink(node))
        except (FileNotFoundError, ProcessLookupError):
            # /proc/self/fd enumeration itself creates a transient descriptor.
            # Missing descriptors do not prove ownership; the listener's exact
            # inode must still be found below or qualification fails closed.
            continue
    if (len(rows) != 1 or rows[0][:2] != ('tcp', '0100007F')
            or 'socket:[' + rows[0][2] + ']' not in sockets):
        raise RuntimeError("LISTENER_IDENTITY_OR_LOOPBACK_MISMATCH")
    return True


class LinuxOwnedChild:
    """No PID-attach constructor. Spawn owns the Popen AND pinned kernel pidfd.

    The resource provider is called only after identity/liveness checks. Signals
    use the pinned fd, never os.kill/PID groups. Only the parent may reap this
    child; SIGCHLD handlers/reapers are prohibited for this dedicated watchdog.
    """
    atomic_identity_signals = True

    @classmethod
    def spawn(cls, argv, *, model_id, owner_scope, resource_provider, hard_seconds=2730, env=None):
        if (sys.platform != "linux" or not hasattr(os, "pidfd_open")
                or not hasattr(signal, "pidfd_send_signal") or signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL):
            raise RuntimeError("LINUX_PIDFD_SPAWN_NOT_QUALIFIED")
        if (not isinstance(argv, list) or not argv or not all(isinstance(arg, str) and "\0" not in arg for arg in argv)
                or not Path(argv[0]).is_absolute() or type(hard_seconds) is not int or not 1 <= hard_seconds <= 2730):
            raise ValueError("INVALID_BOUNDED_CHILD_COMMAND")
        # Prove this kernel permits pidfds before creating a child.
        probe = os.pidfd_open(os.getpid(), 0)
        os.close(probe)
        read_fd, write_fd = os.pipe()
        process = None
        pinned = None
        released = False
        try:
            process = subprocess.Popen(
                [sys.executable, "-I", "-c", BOOTSTRAP, str(read_fd), str(os.getpid()), str(hard_seconds), json.dumps(argv)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                close_fds=True, pass_fds=(read_fd,), env=env,
            )
            pinned = os.pidfd_open(process.pid, 0)
            parent, birth = proc_identity(process.pid)
            if parent != os.getpid() or Path(f"/proc/{process.pid}").stat().st_uid != os.getuid():
                raise RuntimeError("SPAWN_CHILD_IDENTITY_UNVERIFIED")
            instance = object.__new__(cls)
            instance._process, instance._pidfd, instance._resources = process, pinned, resource_provider
            instance.identity = ChildIdentity(process.pid, parent, birth, owner_scope, command_digest(argv), model_id)
            instance._closed = False
            instance._stderr_bytes = 0
            instance._stderr_hash = hashlib.sha256()
            # Drain continuously without retaining or publishing secret-bearing text.
            # Memory is bounded to one 4096-byte chunk regardless of output size.
            def drain_stderr():
                while chunk := process.stderr.read(4096):
                    instance._stderr_bytes += len(chunk)
                    instance._stderr_hash.update(chunk)
                process.stderr.close()
            instance._stderr_thread = Thread(target=drain_stderr, daemon=True)
            instance._stderr_thread.start()
            instance._poll = select.poll()
            instance._poll.register(pinned, select.POLLIN)
            os.write(write_fd, b"G")
            released = True
            return instance
        except Exception:
            # Before release the child can only exit, never run model code.
            if pinned is not None:
                signal.pidfd_send_signal(pinned, signal.SIGKILL, None, 0)
            if process is not None:
                process.wait(timeout=6)
            raise RuntimeError("OWNED_SPAWN_FAILED") from None
        finally:
            os.close(read_fd)
            os.close(write_fd)
            if not released and pinned is not None:
                os.close(pinned)

    def _observation_error(self, stage, error):
        kind = type(error).__name__
        self.observation_failure = {
            "stage": stage,
            "exception_class": kind if kind in {"PermissionError", "ProcessLookupError", "FileNotFoundError", "OSError",
                                               "RuntimeError", "IndexError", "ValueError", "StopIteration"} else "OTHER",
            "errno": error.errno if isinstance(error, OSError) and type(error.errno) is int and 0 <= error.errno <= 4095 else None,
        }

    def _pidfd_terminal(self):
        try:
            if self._closed:
                raise RuntimeError("OWNED_HANDLE_CLOSED")
            events = self._poll.poll(0)
            if not events:
                return False
            # Linux poll ABI values also let Windows unit tests inject fake
            # events without enabling the Linux-only spawn implementation.
            invalid = getattr(select, "POLLNVAL", 0x020) | getattr(select, "POLLERR", 0x008)
            readable = getattr(select, "POLLIN", 0x001)
            # Invalid/foreign descriptors and errors are never terminal proof.
            if any(fd != self._pidfd or mask & invalid or not mask & readable
                   for fd, mask in events):
                raise RuntimeError("OWNED_PIDFD_EVENT_INVALID")
            return True
        except Exception as error:
            self._observation_error("PIDFD_POLL", error)
            raise

    def inspect(self):
        if self._closed:
            raise RuntimeError("OWNED_HANDLE_CLOSED")
        exited = self._pidfd_terminal()
        if not exited:
            try:
                parent, birth = proc_identity(self.identity.pid)
            except PermissionError as error:
                self._observation_error("PROC_IDENTITY", error)
                raise  # A denied observation is not a route to terminal proof.
            except (OSError, RuntimeError, IndexError, ValueError) as error:
                self._observation_error("PROC_IDENTITY", error)
                # The OWNED kernel handle can become terminal after the poll
                # and before /proc is read. Never interpret a missing /proc
                # entry as proof of exit without this pinned-handle recheck.
                # An exit-racing /proc read can also be empty/partial: its
                # parser failure needs the SAME kernel-terminal proof. If the
                # pidfd is not terminal, preserve the original inspection error.
                if self._pidfd_terminal():
                    return False
                raise
            if (parent, birth) != (self.identity.parent_pid, self.identity.birth_marker):
                if self._pidfd_terminal():
                    return False
                error = RuntimeError("OWNED_CHILD_IDENTITY_CHANGED")
                self._observation_error("PROC_IDENTITY", error)
                raise error
        return not exited

    def observe_terminal(self):
        """Nonblocking pinned-handle wait; caller retains the existing drain deadline.

        No /proc/resource inference, no signal/reap, no healthy/zero resource
        values for a live child. Nonterminal means keep waiting, never STOPPED.
        """
        return TerminalObservation(self.identity, not self._pidfd_terminal(), time.monotonic())

    def observe(self):
        alive = self.inspect()
        if alive:
            try:
                values = self._resources(self.identity.pid)
            except PermissionError as error:
                self._observation_error("RESOURCE_SAMPLE", error)
                raise
            except Exception as error:
                self._observation_error("RESOURCE_SAMPLE", error)
                if self.inspect():
                    raise
                alive = False
            else:
                alive = self.inspect()
        if not alive:
            values = dict(gpu_index=0, gpu_uuid="", vram_mib=0, rss_bytes=0, project_bytes=0)
        return Observation(self.identity, alive, time.monotonic(), **values)

    def signal_verified(self, expected, *, force):
        if expected != self.identity or type(force) is not bool:
            raise RuntimeError("UNRECOGNIZED_SIGNAL_TARGET")
        if not self.inspect():
            return
        # pidfd remains pinned even if the child exits between inspect and signal.
        try:
            signal.pidfd_send_signal(self._pidfd, signal.SIGKILL if force else signal.SIGTERM, None, 0)
        except ProcessLookupError:
            if self.inspect():
                raise

    def close_confirmed(self):
        if self.inspect():
            raise RuntimeError("LIVE_CHILD_HANDLE_PRESERVED")
        try:
            self._process.wait(timeout=1)
        except Exception as error:
            self._observation_error("REAP", error)
            raise
        try:
            self._stderr_thread.join(timeout=1)
            if self._stderr_thread.is_alive():
                raise RuntimeError("STDERR_DRAIN_UNCONFIRMED")
        except Exception as error:
            self._observation_error("STDERR_DRAIN", error)
            raise
        os.close(self._pidfd)
        self._closed = True

    def completion(self):
        """Only after confirmed reap; no raw stderr or exception messages."""
        if not self._closed:
            raise RuntimeError("COMPLETION_NOT_CONFIRMED")
        return dict(child_returncode=self._process.returncode,
                    stderr_bytes=self._stderr_bytes,
                    stderr_sha256=self._stderr_hash.hexdigest(),
                    stderr_text_retained=False)


class LinuxResources:
    """Bounded read-only GPU0/RSS/project sampling; no CUDA/model imports."""
    def __init__(self, project: Path, *, clock=time.monotonic, sample_seconds=.5):
        if type(sample_seconds) not in (int, float) or not 0 < sample_seconds <= .5:
            raise ValueError('RESOURCE_SAMPLE_BUDGET_REQUIRED')
        self.project = project.resolve(strict=True)
        self.clock, self.sample_seconds = clock, sample_seconds

    def __call__(self, pid):
        deadline = self.clock() + self.sample_seconds
        def remaining():
            value = deadline - self.clock()
            if value <= 0:
                raise RuntimeError('RESOURCE_SAMPLE_DEADLINE')
            return value
        measured = subprocess.run(["nvidia-smi", "-i", "0", "--query-gpu=uuid,memory.used", "--format=csv,noheader,nounits"],
                                  capture_output=True, text=True, timeout=min(.2, remaining()), check=True)
        remaining()
        uuid, memory = measured.stdout.strip().split(",")
        size = subprocess.run(["du", "-sb", "--", str(self.project)], capture_output=True, text=True, timeout=min(.2, remaining()), check=True)
        remaining()
        status = Path(f"/proc/{pid}/status").read_text()
        remaining()
        rss = next(int(row.split()[1]) * 1024 for row in status.splitlines() if row.startswith("VmRSS:"))
        return dict(gpu_index=0, gpu_uuid=uuid.strip(), vram_mib=int(memory.strip()), rss_bytes=rss,
                    project_bytes=int(size.stdout.split()[0]))
