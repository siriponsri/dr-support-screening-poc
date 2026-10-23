"""Inert writer/entry coordination primitive for the additive M1 authority.

No app registration, authentication, database fence or durable recovery here.
Only the authority that verifies existing native-entry proofs may release an
entry permit. This mechanism alone is not a qualified source authority.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
from inspect import iscoroutinefunction, signature
from threading import RLock


class MutationFenced(RuntimeError):
    """A writer or entry request cannot join the current authority scope."""


@dataclass(frozen=True)
class GateSnapshot:
    generation: int
    writers: int
    state: str


class SourceMutationGate:
    def __init__(self, *, quarantined: bool = False):
        self._lock = RLock()
        self._generation = self._writers = 0
        self._state = "QUARANTINED" if quarantined else "OPEN"
        self._entry = None

    def snapshot(self) -> GateSnapshot:
        with self._lock:
            return GateSnapshot(self._generation, self._writers, self._state)

    @contextmanager
    def writer(self, *, invalidate=True):
        # Only counters are protected. No lock survives the yield/ASGI await.
        with self._lock:
            if self._state != "OPEN":
                raise MutationFenced("SOURCE_WRITERS_FENCED")
            if invalidate:
                self._generation += 1
            self._writers += 1
            generation = self._generation
        try:
            yield generation
        finally:
            with self._lock:
                self._writers -= 1

    def begin_entry(self, *, expected_generation: int):
        with self._lock:
            if self._state != "OPEN" or self._writers:
                raise MutationFenced("SOURCE_WRITER_ACTIVE_OR_FENCED")
            if type(expected_generation) is not int or expected_generation != self._generation:
                raise MutationFenced("SOURCE_WRITER_GENERATION_CHANGED")
            permit = _EntryPermit(self)
            self._state, self._entry = "FENCED", permit
            return permit

    def _quarantine(self, permit):
        with self._lock:
            if permit is None or self._entry is None or self._entry is not permit:
                raise MutationFenced("ENTRY_PERMIT_NOT_CURRENT")
            self._state = "QUARANTINED"

    def _release_verified(self, permit):
        with self._lock:
            if (permit is None or self._entry is None or self._entry is not permit
                    or self._state not in {"FENCED", "QUARANTINED"}):
                raise MutationFenced("ENTRY_PERMIT_NOT_CURRENT")
            self._state, self._entry = "OPEN", None
            self._generation += 1


class _EntryPermit:
    # Deliberately no context manager/timeout/close: exception unwinding must
    # never release a possibly delivered grant. The composed authority owns it.
    def __init__(self, gate):
        self._gate = gate

    def quarantine(self):
        self._gate._quarantine(self)

    def _release_after_verified_authority(self):
        self._gate._release_verified(self)


@contextmanager
def writer_scope(gate, *, invalidate=True):
    """Legacy-compatible scope; an injected gate is never silently ignored."""
    if gate is None:
        yield
    else:
        if type(gate) is not SourceMutationGate:
            raise ValueError("EXPLICIT_SOURCE_MUTATION_GATE_REQUIRED")
        with gate.writer(invalidate=invalidate):
            yield


def _guard(function, resolver, *, invalidate=True):
    if iscoroutinefunction(function):
        @wraps(function)
        async def guarded(*args, **kwargs):
            with writer_scope(resolver(args, kwargs), invalidate=invalidate):
                return await function(*args, **kwargs)
    else:
        @wraps(function)
        def guarded(*args, **kwargs):
            with writer_scope(resolver(args, kwargs), invalidate=invalidate):
                return function(*args, **kwargs)
    guarded.__source_writer_scope__ = True
    # FastAPI may otherwise resolve copied future-annotation strings against
    # this helper's globals instead of the endpoint's original module globals.
    guarded.__signature__ = signature(function, eval_str=True)
    return guarded


def guard_writes(gate_getter, *, invalidate=True):
    """Cover a whole app operation, including its later scan/publication."""
    return lambda function: _guard(function, lambda args, kwargs: gate_getter(), invalidate=invalidate)


def guard_method_writes(function):
    """Cover direct service/store callers too, outside the HTTP route wrapper."""
    return _guard(function, lambda args, kwargs: getattr(args[0], "source_mutation_gate", None))
