"""Control races only; no app/database/native-entry qualification claim."""
from threading import Event, Thread

import pytest

from dr_support.services.source_mutation_gate import (
    MutationFenced, SourceMutationGate, guard_writes, guard_method_writes,
)


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


def test_whole_operation_and_direct_method_are_fenced_without_changing_signature():
    import inspect
    gate, effects = SourceMutationGate(), []
    @guard_writes(lambda: gate)
    def operation(image_id: str):
        effects.append(image_id)
        assert gate.snapshot().writers == 1
    class Store:
        source_mutation_gate = gate
        @guard_method_writes
        def put(self, value):
            effects.append(value)
    assert str(inspect.signature(operation)) == "(image_id: str)"
    operation("before")
    permit = gate.begin_entry(expected_generation=gate.snapshot().generation)
    for write in (lambda: operation("route"), lambda: Store().put("direct")):
        with pytest.raises(MutationFenced):
            write()
    assert effects == ["before"]
    permit._release_after_verified_authority()
    Store().put("after")
    assert effects == ["before", "after"]


def test_async_operation_has_no_thread_lock_held_across_await():
    import asyncio
    gate = SourceMutationGate()
    @guard_writes(lambda: gate)
    async def operation():
        # A different OS thread can enter the counters while this coroutine
        # owns its writer scope. No RLock spans the await/body.
        def other_thread():
            assert gate.snapshot().writers == 1
            with pytest.raises(MutationFenced):
                gate.begin_entry(expected_generation=gate.snapshot().generation)
        await asyncio.to_thread(other_thread)
    asyncio.run(operation())
    assert gate.snapshot().writers == 0


def test_legacy_none_and_wrong_injected_type_are_distinct():
    effects = []
    @guard_writes(lambda: None)
    def legacy():
        effects.append("legacy")
    @guard_writes(lambda: object())
    def invalid():
        effects.append("invalid")
    legacy()
    with pytest.raises(ValueError, match="EXPLICIT"):
        invalid()
    assert effects == ["legacy"]


def test_fastapi_keeps_original_future_annotation_types():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from pydantic import BaseModel
    class RequestBody(BaseModel):
        value: int
    namespace = {"RequestBody": RequestBody, "guard_writes": guard_writes}
    exec("from __future__ import annotations\n"
         "@guard_writes(lambda: None)\n"
         "def endpoint(body: RequestBody):\n"
         "    return {'value': body.value}\n", namespace)
    app = FastAPI()
    app.post("/write")(namespace["endpoint"])
    response = TestClient(app).post("/write", json={"value": 12})
    assert response.status_code == 200 and response.json() == {"value": 12}


def test_read_check_scope_blocks_entry_but_only_real_nested_writes_invalidate():
    gate = SourceMutationGate()
    original = gate.snapshot().generation
    with gate.writer(invalidate=False):
        assert gate.snapshot().generation == original
        with pytest.raises(MutationFenced):
            gate.begin_entry(expected_generation=original)
    assert gate.snapshot().generation == original
    with gate.writer(invalidate=False):
        with gate.writer():
            pass
    assert gate.snapshot().generation == original + 1
