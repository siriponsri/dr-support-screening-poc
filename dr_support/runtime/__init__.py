"""Runtime concerns shared by all deployment profiles.

Currently exposes the GPU/CPU device resolver in :mod:`.device`. Kept as a
package so future additions (e.g. memory accounting, deterministic seeding)
have an obvious home.
"""
from .device import (
    DeviceSnapshot,
    DeviceUnavailable,
    assert_cuda_ready,
    is_cuda_requested,
    resolve_device,
    runtime_snapshot,
)

__all__ = [
    'DeviceSnapshot',
    'DeviceUnavailable',
    'assert_cuda_ready',
    'is_cuda_requested',
    'resolve_device',
    'runtime_snapshot',
]
