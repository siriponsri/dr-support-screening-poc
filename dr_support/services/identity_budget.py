"""Thread-context CPU verification budget; no cache/stat identity substitution."""
from contextlib import contextmanager
from contextvars import ContextVar
import time
import math
from .prism_remote_transport import TransportError

_CURRENT = ContextVar('prism_identity_budget', default=None)


@contextmanager
def identity_budget(deadline, *, cancelled=lambda:False, clock=time.monotonic):
    token = _CURRENT.set((deadline, cancelled, clock))
    try:
        check_identity_budget()
        yield
    finally:
        _CURRENT.reset(token)


def check_identity_budget():
    value = _CURRENT.get()
    if value is None:
        return None
    deadline, cancelled, clock = value
    if cancelled():
        raise TransportError('IDENTITY_VERIFICATION_CANCELLED', 409)
    remaining = deadline - clock()
    if not math.isfinite(remaining) or remaining <= 0:
        raise TransportError('IDENTITY_VERIFICATION_DEADLINE', 408)
    return remaining
