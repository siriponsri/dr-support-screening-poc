"""Inert writer/entry coordination primitive for the additive M1 authority.

No app registration, authentication, database fence or durable recovery here.
Only the authority that verifies existing native-entry proofs may release an
entry permit. This mechanism alone is not a qualified source authority.
"""
from contextlib import contextmanager
from dataclasses import dataclass
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
    def writer(self):
        # Only counters are protected. No lock survives the yield/ASGI await.
        with self._lock:
            if self._state != "OPEN":
                raise MutationFenced("SOURCE_WRITERS_FENCED")
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
