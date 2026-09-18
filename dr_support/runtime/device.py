"""Single source of truth for runtime inference device resolution.

This module is imported by the local model providers (RETFound, PRISM) and by
the ``model_api`` service so that the entire stack agrees on a single
``torch.device``. It also exposes a runtime snapshot of what is actually
available on the host so ``/health`` and ``/v1/models`` can surface it without
the providers each having to re-check.

Failure semantics
-----------------

For the GPU deployment profile (``APP_PROFILE=model_api`` / ``full``), the
service refuses to silently fall back to CPU when the configured device is
``cuda*`` but no CUDA runtime is available. Instead the resolver raises
:class:`DeviceUnavailable` so the failure surfaces loudly in startup logs and
in the ``/health`` response. The CPU value is reserved for local development
of the review profile or contract tests.

The resolver never imports ``torch`` at module load; ``torch`` is imported
lazily so CPU-only CI and contract tests do not require GPU libraries. The
device check is therefore only performed when :func:`resolve_device` or
:func:`runtime_snapshot` is called.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Optional

_DEFAULT_DEVICE = 'cpu'


def _env_device() -> str:
    """Return the requested device string from the environment, normalised."""
    raw = (os.environ.get('INFERENCE_DEVICE') or _DEFAULT_DEVICE).strip()
    if not raw:
        return _DEFAULT_DEVICE
    return raw.lower()


def is_cuda_requested(device: str) -> bool:
    """Return True when the requested device string targets an Nvidia GPU."""
    return device.lower().startswith('cuda')


def _allowed_device(device: str) -> bool:
    """Return True when the device string is one we can resolve.

    Only ``cpu`` and ``cuda*`` are accepted; anything else (mps, xpu, etc.)
    is rejected so the deployment fails loudly on a misconfigured host
    instead of silently falling back.
    """
    return device == 'cpu' or device.startswith('cuda')


class DeviceUnavailable(RuntimeError):
    """Raised when CUDA is requested but no compatible runtime is available.

    The message is sanitised for inclusion in ``/health``; it never includes
    secrets or environment variables.
    """


@dataclass(frozen=True)
class DeviceSnapshot:
    """Immutable snapshot of the resolved device and the host capability.

    Surfaced through ``/health`` and ``/v1/models`` metadata so operators can
    verify GPU wiring without inspecting server logs.
    """

    requested_device: str
    effective_device: str
    cuda_available: bool
    cuda_device_count: int
    cuda_device_name: Optional[str]

    def as_dict(self) -> dict:
        return {
            'requested_device': self.requested_device,
            'effective_device': self.effective_device,
            'cuda_available': self.cuda_available,
            'cuda_device_count': self.cuda_device_count,
            'cuda_device_name': self.cuda_device_name,
        }


_snapshot_lock = threading.Lock()
_cached_snapshot: Optional[DeviceSnapshot] = None


def _probe_torch() -> tuple[bool, int, Optional[str]]:
    """Return ``(cuda_available, device_count, first_device_name)``.

    Returns ``(False, 0, None)`` if torch is unavailable or CUDA is not built.
    Never raises; the resolver turns the result into either a successful
    resolution or a :class:`DeviceUnavailable`.
    """
    try:
        import torch  # type: ignore
    except Exception:
        return False, 0, None
    available = bool(torch.cuda.is_available())
    if not available:
        return False, 0, None
    count = int(torch.cuda.device_count())
    name: Optional[str] = None
    try:
        if count > 0:
            name = torch.cuda.get_device_name(0)
    except Exception:
        name = None
    return True, count, name


def runtime_snapshot(*, force_refresh: bool = False) -> DeviceSnapshot:
    """Return the current device snapshot, probing torch on first use.

    The snapshot is cached for the lifetime of the process so the ``/health``
    endpoint does not repeatedly call into the CUDA runtime. Callers that need
    a fresh probe (e.g. after manual ``torch.cuda`` manipulation) can pass
    ``force_refresh=True``.
    """
    global _cached_snapshot
    with _snapshot_lock:
        if _cached_snapshot is not None and not force_refresh:
            return _cached_snapshot
        requested = _env_device()
        cuda_available, count, name = _probe_torch()
        if is_cuda_requested(requested):
            if not cuda_available:
                effective = 'cpu'
            else:
                effective = requested
        else:
            effective = 'cpu'
        snap = DeviceSnapshot(
            requested_device=requested,
            effective_device=effective,
            cuda_available=cuda_available,
            cuda_device_count=count,
            cuda_device_name=name,
        )
        _cached_snapshot = snap
        return snap


def resolve_device(*, allow_cpu_fallback: bool = False) -> str:
    """Resolve the runtime device as a plain string.

    Parameters
    ----------
    allow_cpu_fallback:
        When ``True`` (the default for local development / contract tests) a
        CUDA request that cannot be satisfied falls back to ``cpu`` and the
        snapshot reflects that mismatch. When ``False`` (the production model
        API behaviour) a CUDA request with no CUDA available raises
        :class:`DeviceUnavailable` instead.
    """
    snap = runtime_snapshot()
    requested = snap.requested_device
    if not _allowed_device(requested):
        raise DeviceUnavailable(
            f"INFERENCE_DEVICE={requested!r} is not supported; only 'cpu' and 'cuda*' are accepted. "
            'Set INFERENCE_DEVICE=cpu for local development, or cuda:0 for the GPU deployment.'
        )
    if is_cuda_requested(requested):
        if snap.cuda_available:
            return snap.effective_device
        if allow_cpu_fallback:
            return 'cpu'
        raise DeviceUnavailable(
            f"INFERENCE_DEVICE={requested!r} requested but no CUDA runtime is available. "
            'Set INFERENCE_DEVICE=cpu for local development, or run on a host with a CUDA GPU.'
        )
    return 'cpu'


def assert_cuda_ready() -> DeviceSnapshot:
    """Raise if the host cannot honour a CUDA request.

    Used by the ``model_api`` and ``full`` profile factories at startup so a
    misconfigured GPU host fails loudly instead of starting and silently
    regressing to CPU at the first inference call.
    """
    snap = runtime_snapshot(force_refresh=True)
    if snap.requested_device.startswith('cuda') and not snap.cuda_available:
        raise DeviceUnavailable(
            f"INFERENCE_DEVICE={snap.requested_device!r} requested but no CUDA runtime is available. "
            'Inspect the container GPU wiring and nvidia-container-toolkit configuration.'
        )
    return snap


def reset_cache() -> None:
    """Clear the cached snapshot. Intended for test isolation only."""
    global _cached_snapshot
    with _snapshot_lock:
        _cached_snapshot = None
