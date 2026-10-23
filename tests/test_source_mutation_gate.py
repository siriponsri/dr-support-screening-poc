"""Control races only; no app/database/native-entry qualification claim."""
from threading import Event, Thread

import pytest

from dr_support.services.source_mutation_gate import MutationFenced, SourceMutationGate


def test_writer_blocks_entry_without_waiting_and_invalidates_previous_generation():
    gate = SourceMutationGate()
    original = gate.snapshot().generation
    with gate.writer():
        with pytest.raises(MutationFenced, match="ACTIVE_OR_FENCED"):
            gate.begin_entry(expected_generation=original)
    with pytest.raises(MutationFenced, match="GENERATION_CHANGED"):
        gate.begin_entry(expected_generation=original)
    permit = gate.begin_entry(expected_generation=gate.snapshot().generation)
    with pytest.raises(MutationFenced):
        with gate.writer():
            pytest.fail("Writer crossed the grant-to-entry fence")
    permit.quarantine()
    assert gate.snapshot().state == "QUARANTINED"
    with pytest.raises(MutationFenced):
        with gate.writer():
            pytest.fail("Timeout/exception must not unlock a source")
    permit._release_after_verified_authority()
    with gate.writer():
        pass
    with pytest.raises(MutationFenced, match="NOT_CURRENT"):
        permit._release_after_verified_authority()


def test_writer_scope_releases_after_failure_but_keeps_invalidation():
    gate = SourceMutationGate()
    with pytest.raises(ValueError):
        with gate.writer():
            raise ValueError("Synthetic writer failure")
    assert gate.snapshot().writers == 0
    assert gate.snapshot().generation == 1


def test_writer_does_not_hold_a_thread_lock_across_its_body():
    gate, entered, release = SourceMutationGate(), Event(), Event()
    def writer():
        with gate.writer():
            entered.set()
            assert release.wait(5)
    thread = Thread(target=writer)
    thread.start()
    try:
        assert entered.wait(5)
        # Would deadlock if writer retained its thread lock across an await.
        with pytest.raises(MutationFenced, match="ACTIVE_OR_FENCED"):
            gate.begin_entry(expected_generation=gate.snapshot().generation)
        with gate.writer():
            assert gate.snapshot().writers == 2
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive() and gate.snapshot().writers == 0


def test_restart_quarantine_has_no_local_reset_or_implicit_recovery():
    gate = SourceMutationGate(quarantined=True)
    before = gate.snapshot()
    for operation in (gate._release_verified, gate._quarantine):
        with pytest.raises(MutationFenced, match="NOT_CURRENT"):
            operation(None)
        assert gate.snapshot() == before
    with pytest.raises(MutationFenced):
        gate.begin_entry(expected_generation=0)
    with pytest.raises(MutationFenced):
        with gate.writer():
            pytest.fail("Recovery needs the composed durable authority")
