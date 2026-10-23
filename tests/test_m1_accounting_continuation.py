"""Synthetic file/clock accounting only: no grants, models, network, GPU or DB."""

from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "scripts/qa/batch_runtime"
sys.path.insert(0, str(SOURCE))
ledger_module = importlib.import_module("batch_ledger")
budget_module = importlib.import_module("batch_budget")
from batch_ledger import (BatchLedger, canonical, digest, M1_SERVER, M1_LOCAL,  # noqa: E402
                          M1_WINDOWS, M1_ALLOCATIONS, M1_GPU0)
from batch_budget import BatchBudget, activate_continuation_window  # noqa: E402


def chain(rows, *, sequence="seq"):
    previous = "0" * 64
    result = []
    for index, entry in enumerate(rows, 1):
        row = {**entry, sequence: index, "previous": previous}
        row["hash"] = digest(canonical(row))
        result.append(canonical(row) + b"\n")
        previous = row["hash"]
    return b"".join(result)


@pytest.fixture(scope="module")
def upstream_seed():
    entries = []
    for number in range(480):
        job = {"manifest": "f" * 64, "job_id": f"{number + 1000:064x}", "reason": None,
               "artifact_sha256": None}
        states = ["BLOCKED_PREMODEL"] if number >= 476 else (
            ["ATTEMPT_INTENT", "FAILED_NO_RETRY"] if number >= 467 else
            ["ATTEMPT_INTENT", "RESPONSE_RETAINED", "PASS_READBACK"])
        entries += [{**job, "state": state,
                     "artifact_sha256": "a" * 64 if state in {"RESPONSE_RETAINED", "PASS_READBACK"} else None}
                    for state in states]
    raw = chain(entries)
    budgets = []
    for start, charge in [(1000, 4772.230), (2000, 9800.644)]:
        body = {"manifest": "f" * 64, "started_monotonic": start, "started_utc": start + 100000,
                "charged_gpu_seconds": charge, "lease_count": 1, "active": None, "quarantined": False}
        budgets.append(canonical({"body": body, "sha256": digest(canonical(body))}))
    return {
        "batch_ledger": raw, "original_budget": budgets[0], "second_budget": budgets[1],
        "demo_requests": chain([{"state": "ANCHOR", "prior_ledger_sha256": digest(raw),
                                  "base_used": 525, "cap": 529}], sequence="sequence"),
        "demo_activation": canonical({"run": "synthetic-closed-run", "prior_used": 525, "cap": 529,
                                      "prior_ledger_sha256": digest(raw)}),
        "demo_complete": canonical({"cleanup_confirmed": True, "listener_closed": True,
            "conservative_gpu_reserved_seconds": 2430,
            "cleanup_components": {name: {"confirmed": True} for name in
                ("supervisor_close", "child_terminal_reap", "gpu_monitor", "disk_monitor")}}),
        "demo_ready": canonical({"status": "LOADED_NOT_YET_INFERENCE_VALIDATED", "gpu_uuid": M1_GPU0,
            "prior_used": 525, "cap": 529, "models": [{"model_id": name, "forward_attempts_during_load": 0}
                for name in ("uspec-uwf-grading", "retfound-aptos5", "prism-dr-5fold")]}),
    }


def seal(rig):
    rig.proposal_path.write_bytes(canonical(rig.proposal))
    rig.options["proposal_sha256"] = digest(rig.proposal_path.read_bytes())
    rig.approval_path.write_bytes(canonical({"schema": "hospital-m1-owner-approval.v1",
        "decision_id": ledger_module.M1_DECISION, "proposal_sha256": rig.options["proposal_sha256"],
        "status": "EXPLICIT_OWNER_APPROVED_NOT_ACTIVATED"}))
    rig.options["approval_sha256"] = digest(rig.approval_path.read_bytes())


@pytest.fixture
def rig(tmp_path, monkeypatch, upstream_seed):
    source = tmp_path / "prior"
    source.mkdir()
    paths = {}
    for name, raw in upstream_seed.items():
        paths[name] = source / name
        paths[name].write_bytes(raw)
    monkeypatch.setattr(ledger_module, "M1_UPSTREAM_LEDGER_SHA", digest(upstream_seed["batch_ledger"]))
    jobs = []
    for index in range(24):
        purpose = "server_acceptance" if index < 9 else "local_acceptance" if index < 15 else "post_fix_verification"
        model, modality = [("uspec-uwf-grading", "UWF"), ("retfound-aptos5", "CFP"),
                           ("prism-dr-5fold", "UWF")][index % 3]
        body = {"operation_id": f"synthetic-operation-{index}", "purpose": purpose,
            "window_id": M1_LOCAL if purpose == "local_acceptance" else M1_SERVER,
            "source_sha256": f"{index + 10000:064x}", "model_id": model, "modality": modality,
            "model_pins_sha256": "a" * 64, "parameters_sha256": "b" * 64,
            "preprocessing_id": "synthetic-pins-not-a-model"}
        jobs.append({**body, "job_id": digest(canonical(body))})
    proposal = {"schema": "hospital-m1-continuation.v1", "decision_id": ledger_module.M1_DECISION,
        "base_used": 525, "cap": 549, "new_admissions_max": 24, "allocations": deepcopy(M1_ALLOCATIONS),
        "windows": {key: {"profile": profile, "gpu_index": 0, "gpu_seconds_cap": 10800,
                         "wall_seconds_cap": 14400, "refund_unused": False, "renew": False}
                    for key, profile in M1_WINDOWS.items()},
        "accounting_directory": str(tmp_path / "continuation"), "installation_sha256": "e" * 64,
        "upstream": {key: digest(raw) for key, raw in upstream_seed.items()}, "operations": jobs}
    rig = SimpleNamespace(directory=tmp_path / "continuation", proposal=proposal, paths=paths,
        originals=upstream_seed, proposal_path=tmp_path / "proposal.json", approval_path=tmp_path / "approval.json",
        options={"installation_sha256": "e" * 64}, now=[3000.0], utc=[300000.0], origin="c" * 64)
    rig.options.update(proposal_path=rig.proposal_path, approval_path=rig.approval_path, upstream_paths=paths)
    seal(rig)
    return rig


def owned(rig):
    ledger = BatchLedger.for_continuation(rig.directory, **rig.options)
    ledger.acquire()
    return ledger


def activate(rig, ledger):
    return activate_continuation_window(ledger, window_id=M1_SERVER, clock_origin=rig.origin,
        gpu_uuid=M1_GPU0, clock=lambda: rig.now[0], utc=lambda: rig.utc[0])


def funded(rig):
    ledger = owned(rig)
    activate(rig, ledger)
    budget = BatchBudget(ledger, session_id=M1_SERVER, clock_origin=rig.origin,
                         clock=lambda: rig.now[0], utc=lambda: rig.utc[0])
    budget.reserve_worker("synthetic-lifetime")
    return ledger, budget


def pass_job(ledger, budget, job):
    receipt = ledger.admit(job["job_id"], request_sha256="d" * 64, budget=budget)
    ledger.append(job["job_id"], "RESPONSE_RETAINED", artifact_sha256="a" * 64)
    ledger.append(job["job_id"], "PASS_READBACK", artifact_sha256="b" * 64)
    return receipt


def test_preserves_all_old_bytes_and_accounts_server_plus_local_from_one_lineage(rig):
    ledger, budget = funded(rig)
    assert ledger.summary()["global_used"] == 525 and ledger.summary()["cap"] == 549
    assert ledger_module.CAP == 529 and ledger_module.BASE_USED == 49
    assert budget.body["charged_gpu_seconds"] == 10800
    assert budget.summary()["prior_gpu_seconds_preserved"] == 17002.874
    for job in rig.proposal["operations"]:
        if job["window_id"] == M1_SERVER:
            pass_job(ledger, budget, job)
    assert ledger.summary()["global_used"] == 543
    assert len(ledger.pending()) == 6 and all(job["window_id"] == M1_LOCAL for job in ledger.pending())
    rig.now[0] += 5
    rig.utc[0] += 5
    budget.confirm_stop("synthetic-lifetime", cleanup_confirmed=True)
    assert budget.body["charged_gpu_seconds"] == 10800 and budget.body["window_closed"]
    assert budget.summary()["aggregate_gpu_seconds"] == 27802.874
    ledger.close(cleanup_confirmed=True)
    reopened = BatchLedger.for_continuation(rig.directory, **rig.options)
    assert reopened.summary()["global_used"] == 543
    assert all(path.read_bytes() == rig.originals[name] for name, path in rig.paths.items())


@pytest.mark.parametrize("change", ["base", "cap", "slots", "allocation", "window", "old_job", "job_hash"])
def test_forged_authorization_scope_fails_before_accounting_creation(rig, change):
    if change == "base": rig.proposal["base_used"] = 0
    elif change == "cap": rig.proposal["cap"] = 550
    elif change == "slots": rig.proposal["new_admissions_max"] = 25
    elif change == "allocation": rig.proposal["allocations"]["server_acceptance"] = 10
    elif change == "window": rig.proposal["windows"][M1_SERVER]["gpu_seconds_cap"] = 10801
    elif change == "old_job": rig.proposal["operations"][0]["job_id"] = f"{1000:064x}"
    else: rig.proposal["operations"][0]["parameters_sha256"] = "0" * 64
    seal(rig)
    with pytest.raises(RuntimeError): owned(rig)
    assert not rig.directory.exists()


def test_unpinned_approval_and_different_directory_cannot_create_a_second_counter(rig):
    rig.options["approval_sha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="EXACT_EXTERNAL_OWNER_APPROVAL"):
        owned(rig)
    seal(rig)
    with pytest.raises(RuntimeError, match="SINGLE_AUTHORIZED_ACCOUNTING_DIRECTORY"):
        BatchLedger.for_continuation(rig.directory.with_name("other-counter"), **rig.options)
    assert not rig.directory.exists()


def test_independent_replay_rejects_forged525_even_with_rehashed_input_documents(rig, monkeypatch):
    raw = b"\n".join(rig.paths["batch_ledger"].read_bytes().splitlines()[:-4]) + b"\n"
    rig.paths["batch_ledger"].write_bytes(raw)
    rig.proposal["upstream"]["batch_ledger"] = digest(raw)
    monkeypatch.setattr(ledger_module, "M1_UPSTREAM_LEDGER_SHA", digest(raw))
    seal(rig)
    with pytest.raises(RuntimeError, match="EXACT_CLOSED_480_BATCH"):
        owned(rig)
    assert not rig.directory.exists()


@pytest.mark.parametrize("anchor", ["original_budget", "second_budget", "demo_requests", "demo_complete", "demo_ready"])
def test_rehashed_but_unclosed_or_nonzero_upstream_evidence_is_rejected(rig, anchor):
    value = json.loads(rig.paths[anchor].read_bytes())
    if anchor in {"original_budget", "second_budget"}:
        value["body"]["active"] = {"lease_id": "not-stopped"}
        value["sha256"] = digest(canonical(value["body"]))
    elif anchor == "demo_requests":
        value["state"] = "ATTEMPT_INTENT"
        value["hash"] = digest(canonical({key: item for key, item in value.items() if key != "hash"}))
    elif anchor == "demo_complete": value["cleanup_confirmed"] = False
    else: value["models"][0]["forward_attempts_during_load"] = 1
    raw = canonical(value) + (b"\n" if anchor == "demo_requests" else b"")
    rig.paths[anchor].write_bytes(raw)
    rig.proposal["upstream"][anchor] = digest(raw)
    seal(rig)
    with pytest.raises(RuntimeError): owned(rig)
    assert not rig.directory.exists()


def test_one_exclusive_owner_and_immutable_operation_manifest(rig):
    ledger = owned(rig)
    other = BatchLedger.for_continuation(rig.directory, **rig.options)
    with pytest.raises(FileExistsError): other.acquire()
    ledger.assert_owner()
    next(iter(ledger.jobs.values()))["parameters_sha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="CONTEXT_CHANGED"): ledger.assert_owner()


@pytest.mark.parametrize("anchor", ["approval", "original_budget", "preserved_copy"])
def test_changed_authority_or_closure_blocks_before_new_dispatch(rig, anchor):
    ledger, budget = funded(rig)
    path = (rig.approval_path if anchor == "approval" else rig.paths[anchor]
            if anchor == "original_budget" else rig.directory / "upstream" / "batch_ledger.original")
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(RuntimeError, match="CHANGED"):
        ledger.admit(rig.proposal["operations"][0]["job_id"], request_sha256="d" * 64, budget=budget)
    assert ledger.attempts == 0 and (rig.directory / "LEDGER.jsonl").read_bytes() == b""
    assert (rig.directory / "SESSION.lock").exists()


@pytest.mark.parametrize("damage", ["truncate", "missing_head", "old_head"])
def test_durable_high_water_refuses_journal_loss_without_replaying_a_request(rig, damage):
    ledger, budget = funded(rig)
    original_head = (rig.directory / "JOURNAL_HEAD.json").read_bytes()
    pass_job(ledger, budget, rig.proposal["operations"][0])
    if damage == "truncate": (rig.directory / "LEDGER.jsonl").write_bytes(b"")
    elif damage == "missing_head": (rig.directory / "JOURNAL_HEAD.json").unlink()
    else: (rig.directory / "JOURNAL_HEAD.json").write_bytes(original_head)
    with pytest.raises(RuntimeError):
        BatchLedger.for_continuation(rig.directory, **rig.options)
    assert (rig.directory / "SESSION.lock").exists()


def test_intent_is_durable_before_dispatch_and_terminal_operation_cannot_retry(rig):
    ledger, budget = funded(rig)
    job = rig.proposal["operations"][0]
    receipt = ledger.admit(job["job_id"], request_sha256="d" * 64, budget=budget)
    rows = [json.loads(line) for line in (rig.directory / "LEDGER.jsonl").read_bytes().splitlines()]
    assert rows[-1]["state"] == "ATTEMPT_INTENT" and rows[-1]["artifact_sha256"] == "d" * 64
    assert rows[-1]["hash"] == receipt["admission_id"] and receipt["global_used"] == 526
    ledger.append(job["job_id"], "FAILED_NO_RETRY", reason="APP_REJECTED")
    with pytest.raises(RuntimeError, match="NO_RETRY"):
        ledger.admit(job["job_id"], request_sha256="e" * 64, budget=budget)
    assert ledger.attempts == 1


def test_unfunded_wrong_window_direct_append_and_uncertain_admission_are_refused(rig):
    ledger = owned(rig)
    activate(rig, ledger)
    budget = BatchBudget(ledger, session_id=M1_SERVER, clock_origin=rig.origin,
                         clock=lambda: rig.now[0], utc=lambda: rig.utc[0])
    job = rig.proposal["operations"][0]
    with pytest.raises(RuntimeError, match="FUNDED_IDLE"):
        ledger.admit(job["job_id"], request_sha256="d" * 64, budget=budget)
    budget.reserve_worker("synthetic-lifetime")
    with pytest.raises(RuntimeError, match="ADMISSION_GATE"):
        ledger.append(job["job_id"], "ATTEMPT_INTENT", artifact_sha256="d" * 64)
    local = next(job for job in ledger.pending() if job["window_id"] == M1_LOCAL)
    with pytest.raises(RuntimeError, match="OUTSIDE_ACTIVE_WINDOW"):
        ledger.admit(local["job_id"], request_sha256="d" * 64, budget=budget)
    ledger.admit(job["job_id"], request_sha256="d" * 64, budget=budget)
    ledger.append(job["job_id"], "SENT_OR_UNCERTAIN", reason="DISCONNECTED")
    with pytest.raises(RuntimeError, match="FUNDED_IDLE"):
        ledger.admit(rig.proposal["operations"][1]["job_id"], request_sha256="d" * 64, budget=budget)
    with pytest.raises(RuntimeError, match="UNCERTAIN_INTENT"):
        ledger.close(cleanup_confirmed=True)
    assert ledger.attempts == 1


@pytest.mark.parametrize("failure", ["intent", "terminal"])
def test_head_publication_failure_blocks_dispatch_or_preserves_returned_result(rig, monkeypatch, failure):
    ledger, budget = funded(rig)
    job = rig.proposal["operations"][0]
    if failure == "terminal":
        ledger.admit(job["job_id"], request_sha256="d" * 64, budget=budget)
    def fail(_): raise OSError("synthetic accounting I/O failure")
    monkeypatch.setattr(ledger, "_write_head", fail)
    returned_model_result = {"status": "synthetic-response-already-returned"}
    dispatched = []
    with pytest.raises(OSError):
        if failure == "intent":
            receipt = ledger.admit(job["job_id"], request_sha256="d" * 64, budget=budget)
            dispatched.append(receipt)
        else:
            ledger.append(job["job_id"], "RESPONSE_RETAINED", artifact_sha256="a" * 64)
    assert dispatched == [] and returned_model_result["status"] == "synthetic-response-already-returned"
    assert ledger.poisoned
    durable = [json.loads(line) for line in (rig.directory / "LEDGER.jsonl").read_bytes().splitlines()]
    assert sum(row["state"] == "ATTEMPT_INTENT" for row in durable) == 1
    assert (rig.directory / "SESSION.lock").exists()
    with pytest.raises(RuntimeError): ledger.assert_owner()
    with pytest.raises(RuntimeError, match="HIGH_WATER"):
        BatchLedger.for_continuation(rig.directory, **rig.options)


@pytest.mark.parametrize("file", ["INTENT.json", "BUDGET.json", "COMPLETE.json"])
def test_partial_window_activation_retains_owner_and_gate(rig, file):
    ledger = owned(rig)
    def write(path, raw):
        if path.name == file: raise OSError("synthetic partial activation")
        ledger_module._new_file(path, raw)
    with pytest.raises(OSError):
        activate_continuation_window(ledger, window_id=M1_SERVER, clock_origin=rig.origin,
            gpu_uuid=M1_GPU0, clock=lambda: rig.now[0], utc=lambda: rig.utc[0], write=write)
    assert ledger.poisoned and (rig.directory / "M1_WINDOW_ACTIVATION.lock").exists()
    assert (rig.directory / "SESSION.lock").exists()
    with pytest.raises(RuntimeError): ledger.close(cleanup_confirmed=True)


@pytest.mark.parametrize("limit", ["wall", "rollback", "clock_origin", "lease_deadline"])
def test_window_clocks_and_deadlines_never_reset_or_resume(rig, limit):
    ledger, budget = funded(rig)
    if limit == "wall": rig.utc[0] += 14401
    elif limit == "rollback": rig.now[0] -= 1
    elif limit == "lease_deadline": rig.now[0] += 10801
    else:
        with pytest.raises(RuntimeError, match="CLOCK_ORIGIN"):
            BatchBudget(ledger, session_id=M1_SERVER, clock_origin="0" * 64,
                        clock=lambda: rig.now[0], utc=lambda: rig.utc[0])
        return
    with pytest.raises(RuntimeError): budget.check()
    assert budget.body["charged_gpu_seconds"] == 10800
    if limit == "rollback": assert budget.body["quarantined"]


def test_no_refund_renewal_or_second_window_and_local_remains_unqualified(rig):
    ledger, budget = funded(rig)
    budget.confirm_stop("synthetic-lifetime", cleanup_confirmed=True)
    assert budget.body["charged_gpu_seconds"] == 10800
    with pytest.raises(RuntimeError): budget.reserve_worker("second")
    with pytest.raises(RuntimeError, match="ONCE_OR_PARTIAL"): activate(rig, ledger)
    with pytest.raises(RuntimeError, match="LOCAL_ADOPTION_NOT_QUALIFIED"):
        activate_continuation_window(ledger, window_id=M1_LOCAL, clock_origin=rig.origin,
                                     gpu_uuid=M1_GPU0)
    assert not (rig.directory / "windows" / M1_LOCAL).exists()
    with pytest.raises(RuntimeError, match="LOCAL_ADOPTION_NOT_QUALIFIED"):
        BatchBudget(ledger, session_id=M1_LOCAL, clock_origin=rig.origin)


def test_in_memory_refund_or_extended_lifetime_cannot_be_persisted(rig):
    ledger, budget = funded(rig)
    original = budget.path.read_bytes()
    budget.body["charged_gpu_seconds"] = 1
    with pytest.raises(RuntimeError, match="LIFETIME_RESERVATION"): budget.persist()
    budget.body["charged_gpu_seconds"] = 10800
    budget.body["active"]["deadline"] += 1
    with pytest.raises(RuntimeError, match="LIFETIME_DEADLINE_CHANGED"): budget.persist()
    assert budget.path.read_bytes() == original and ledger.attempts == 0


def test_unknown_cleanup_keeps_full_reservation_and_prevents_handover(rig):
    ledger, budget = funded(rig)
    with pytest.raises(RuntimeError, match="NO_REFUND"):
        budget.confirm_stop("synthetic-lifetime", cleanup_confirmed=False)
    assert budget.body["charged_gpu_seconds"] == 10800 and budget.body["quarantined"]
    assert budget.body["active"] is not None
    with pytest.raises(RuntimeError): ledger.fence_handover(destination_installation_sha256="1" * 64)


@pytest.mark.parametrize("partial", [False, True])
def test_source_handover_is_permanent_and_never_creates_a_local_counter(rig, monkeypatch, partial):
    ledger, budget = funded(rig)
    budget.confirm_stop("synthetic-lifetime", cleanup_confirmed=True)
    lock = (rig.directory / "SESSION.lock").read_bytes()
    if partial:
        original = ledger_module._new_file
        def fail_export(path, raw):
            if path.name == "HANDOVER_EXPORT.json": raise OSError("synthetic export failure")
            return original(path, raw)
        monkeypatch.setattr(ledger_module, "_new_file", fail_export)
        with pytest.raises(OSError): ledger.fence_handover(destination_installation_sha256="1" * 64)
    else:
        value = ledger.fence_handover(destination_installation_sha256="1" * 64)
        assert value["global_used"] == 525 and value["local_activation_available"] is False
        assert value["status"] == "SOURCE_FENCED_LOCAL_ADOPTION_NOT_QUALIFIED"
        assert value["server_budget_sha256"] == digest(budget.path.read_bytes())
        assert value["journal_head_sha256"] == digest((rig.directory / "JOURNAL_HEAD.json").read_bytes())
        assert value["upstream"] == rig.proposal["upstream"]
    assert (rig.directory / "HANDOVER.lock").exists()
    assert (rig.directory / "SESSION.lock").read_bytes() == lock
    reopened = BatchLedger.for_continuation(rig.directory, **rig.options)
    with pytest.raises(RuntimeError, match="SOURCE_PERMANENTLY_FENCED"): reopened.acquire()
    assert not (rig.directory / "windows" / M1_LOCAL).exists()
