"""PRISM window continuation: synthetic files/clocks only, no model, network, GPU or DB."""

import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from test_m1_accounting_continuation import funded, owned, rig, upstream_seed  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/model-server"))
ledger_module = importlib.import_module("batch_ledger")
proposal_tool = importlib.import_module("m1_proposal")
from batch_ledger import (BatchLedger, canonical, digest, M1_GPU0, M1_LOCAL, M1_PRISM_DECISION,  # noqa: E402
                          M1_PRISM_SERVER, M1_SERVER)
from batch_budget import BatchBudget, activate_continuation_window  # noqa: E402

DESTINATION = "9" * 64


def pass_job(ledger, budget, job):
    ledger.admit(job["job_id"], request_sha256="d" * 64, budget=budget)
    ledger.append(job["job_id"], "RESPONSE_RETAINED", artifact_sha256="a" * 64)
    ledger.append(job["job_id"], "PASS_READBACK", artifact_sha256="b" * 64)


def fence(rig):  # noqa: F811
    """Run the 2026-10-23 decision like the live session, then fence it."""
    ledger, budget = funded(rig)
    server = [job for job in rig.proposal["operations"] if job["purpose"] == "server_acceptance"]
    for job in server:
        if job["model_id"] != "prism-dr-5fold":
            pass_job(ledger, budget, job)
    budget.confirm_stop("synthetic-lifetime", cleanup_confirmed=True)
    ledger.close(cleanup_confirmed=True)
    source = owned(rig)
    return source.fence_handover(destination_installation_sha256=DESTINATION)


@pytest.fixture
def chain(rig, tmp_path):  # noqa: F811
    export = fence(rig)
    target = SimpleNamespace(directory=tmp_path / "prism-continuation", proposal_path=tmp_path / "prism.json",
                             approval_path=tmp_path / "prism-approval.json", upstream_path=tmp_path / "upstream.json",
                             export=export, rig=rig)
    proposal_tool.draft_prism(SimpleNamespace(source_accounting=rig.directory, accounting_directory=str(target.directory),
                                              installation_sha256=DESTINATION, output=target.proposal_path,
                                              upstream_output=target.upstream_path))
    target.proposal = json.loads(target.proposal_path.read_bytes())
    seal(target)
    return target


def seal(target):
    target.proposal_path.write_bytes(canonical(target.proposal))
    target.proposal_sha256 = digest(target.proposal_path.read_bytes())
    target.approval_path.write_bytes(canonical({"schema": "hospital-m1-owner-approval.v1",
        "decision_id": M1_PRISM_DECISION, "proposal_sha256": target.proposal_sha256,
        "status": "EXPLICIT_OWNER_APPROVED_NOT_ACTIVATED"}))


def options(target, **changes):
    value = dict(proposal_path=target.proposal_path, approval_path=target.approval_path,
                 proposal_sha256=target.proposal_sha256, approval_sha256=digest(target.approval_path.read_bytes()),
                 upstream_paths=json.loads(target.upstream_path.read_bytes()), installation_sha256=DESTINATION)
    value.update(changes)
    return value


def opened(target):
    ledger = BatchLedger.for_continuation(target.directory, **options(target))
    ledger.acquire()
    return ledger


def window(target, ledger):
    clocks = target.rig
    activate_continuation_window(ledger, window_id=M1_PRISM_SERVER, clock_origin=clocks.origin, gpu_uuid=M1_GPU0,
                                 clock=lambda: clocks.now[0], utc=lambda: clocks.utc[0])
    return BatchBudget(ledger, session_id=M1_PRISM_SERVER, clock_origin=clocks.origin,
                       clock=lambda: clocks.now[0], utc=lambda: clocks.utc[0])


def test_fenced_source_continues_with_exactly_the_unsent_prism_operations(chain):
    assert chain.export["global_used"] == 531 and len(chain.export["remaining_job_ids"]) == 18
    proposal = chain.proposal
    assert proposal["base_used"] == 531 and proposal["cap"] == 534 and proposal["new_admissions_max"] == 3
    assert proposal["windows"] == {M1_PRISM_SERVER: {"profile": "QA_SERVER", "gpu_index": 0, "gpu_seconds_cap": 3600,
                                                    "wall_seconds_cap": 7200, "refund_unused": False, "renew": False}}
    origins = {job["operation_id"]: job for job in chain.rig.proposal["operations"]
               if job["job_id"] in chain.export["remaining_job_ids"] and job["model_id"] == "prism-dr-5fold"
               and job["purpose"] == "server_acceptance"}
    assert {job["operation_id"] for job in proposal["operations"]} == set(origins)
    for job in proposal["operations"]:
        same = {key for key in job if key not in {"job_id", "window_id"}}
        assert all(job[key] == origins[job["operation_id"]][key] for key in same)
        assert job["window_id"] == M1_PRISM_SERVER and job["job_id"] != origins[job["operation_id"]]["job_id"]


def test_new_window_reserves_3600_once_admits_only_its_operations_and_closes(chain):
    ledger = opened(chain)
    assert (ledger.base_used, ledger.cap) == (531, 534)
    origin = ledger.accounting()["continuation"]
    assert origin["base_used"] == 531 and origin["cap"] == 534 and origin["prior_gpu_seconds_preserved"] == 27802.874
    budget = window(chain, ledger)
    assert budget.GPU_SECONDS == budget.LEASE_SECONDS == 3600 and budget.SESSION_SECONDS == 7200
    budget.reserve_worker("prism-lifetime")
    assert budget.body["charged_gpu_seconds"] == 3600
    with pytest.raises(RuntimeError, match="M1_NO_WORKER_RENEWAL_OR_SECOND_LEASE"):
        budget.reserve_worker("second")
    old_job = chain.rig.proposal["operations"][0]["job_id"]
    with pytest.raises(RuntimeError, match="M1_OPERATION_OUTSIDE_ACTIVE_WINDOW"):
        ledger.admit(old_job, request_sha256="d" * 64, budget=budget)
    job = chain.proposal["operations"][0]
    receipt = ledger.admit(job["job_id"], request_sha256="d" * 64, budget=budget)
    assert receipt["window_id"] == M1_PRISM_SERVER and receipt["global_used"] == 532
    with pytest.raises(RuntimeError, match="M1_FUNDED_IDLE_ADMISSION_REQUIRED"):
        ledger.admit(chain.proposal["operations"][1]["job_id"], request_sha256="d" * 64, budget=budget)
    ledger.append(job["job_id"], "RESPONSE_RETAINED", artifact_sha256="a" * 64)
    ledger.append(job["job_id"], "PASS_READBACK", artifact_sha256="b" * 64)
    budget.confirm_stop("prism-lifetime", cleanup_confirmed=True)
    assert budget.body["window_closed"] is True
    ledger.close(cleanup_confirmed=True)
    reopened = opened(chain)
    with pytest.raises(RuntimeError, match="M1_UNCERTAIN_OR_CLOSED_WINDOW_NO_RESUME"):
        BatchBudget(reopened, session_id=M1_PRISM_SERVER, clock_origin=chain.rig.origin,
                    clock=lambda: chain.rig.now[0], utc=lambda: chain.rig.utc[0])


@pytest.mark.parametrize("window_id, code", [(M1_SERVER, "M1_EXACT_WINDOW_GPU0_AND_CLOCK_ORIGIN_REQUIRED"),
                                             (M1_LOCAL, "M1_LOCAL_ADOPTION_NOT_QUALIFIED")])
def test_only_the_prism_window_can_be_activated(chain, window_id, code):
    ledger = opened(chain)
    with pytest.raises(RuntimeError, match=code):
        activate_continuation_window(ledger, window_id=window_id, clock_origin=chain.rig.origin, gpu_uuid=M1_GPU0)


@pytest.mark.parametrize("change, code", [
    (lambda p: p.update(cap=535), "M1_PRISM_SOURCE_USAGE_INVALID"),
    (lambda p: p.update(base_used=530, cap=533), "M1_PRISM_SOURCE_USAGE_INVALID"),
    (lambda p: p["operations"][0].update(source_sha256="f" * 64), "M1_PRISM_OPERATION_CHANGED"),
    (lambda p: p["operations"].pop(), "M1_PRISM_EXACT_UNSENT_OPERATIONS_REQUIRED"),
    (lambda p: p["windows"][M1_PRISM_SERVER].update(gpu_seconds_cap=3600.0), "M1_PRISM_AUTHORIZATION_SCOPE_INVALID"),
    (lambda p: p["windows"][M1_PRISM_SERVER].update(gpu_seconds_cap=10800), "M1_PRISM_AUTHORIZATION_SCOPE_INVALID"),
    (lambda p: p.update(new_admissions_max=4), "M1_PRISM_AUTHORIZATION_SCOPE_INVALID"),
])
def test_changed_proposals_are_refused(chain, change, code):
    if code == "M1_PRISM_OPERATION_CHANGED":
        job = chain.proposal["operations"][0]
        change(chain.proposal)
        job["job_id"] = digest(canonical({k: v for k, v in job.items() if k != "job_id"}))
    else:
        change(chain.proposal)
    seal(chain)
    with pytest.raises(RuntimeError, match=code):
        opened(chain)


EXPORT_FIELD = {"source_approval": "approval_sha256", "source_journal_head": "journal_head_sha256",
                "source_server_budget": "server_budget_sha256"}


def tamper(chain, key, mutate):
    """Rewrite one source receipt, then keep export, HANDOVER.lock and pins consistent with it."""
    paths = {name: Path(value) for name, value in json.loads(chain.upstream_path.read_bytes()).items()}
    value = json.loads(paths[key].read_bytes())
    mutate(value)
    paths[key].write_bytes(canonical(value))
    export = json.loads(paths["handover_export"].read_bytes())
    if key in EXPORT_FIELD:
        export[EXPORT_FIELD[key]] = digest(paths[key].read_bytes())
    raw = canonical(export)
    paths["handover_export"].write_bytes(raw)
    (paths["handover_export"].parent / "HANDOVER.lock").write_bytes(raw)
    chain.proposal["upstream"] = {name: digest(path.read_bytes()) for name, path in paths.items()}
    seal(chain)


def reopen(saved):
    saved["body"]["window_closed"] = False
    saved["sha256"] = digest(canonical(saved["body"]))


@pytest.mark.parametrize("key, mutate, code", [
    ("handover_export", lambda e: e.update(global_used=e["global_used"] + 1), "M1_PRISM_SOURCE_USAGE_INVALID"),
    ("handover_export", lambda e: e["remaining_job_ids"].reverse(), "M1_PRISM_SOURCE_USAGE_INVALID"),
    ("handover_export", lambda e: e.update(seq=float(e["seq"])), "M1_PRISM_SOURCE_USAGE_INVALID"),
    ("source_journal_head", lambda h: h.update(seq=h["seq"] - 1), "M1_PRISM_SOURCE_USAGE_INVALID"),
    ("source_server_budget", reopen, "M1_PRISM_SOURCE_WINDOW_NOT_CLOSED_OR_OVER_BUDGET"),
    ("source_approval", lambda a: a.update(decision_id=M1_PRISM_DECISION), "M1_PRISM_SOURCE_DECISION_INVALID"),
])
def test_consistently_rewritten_source_receipts_are_refused(chain, key, mutate, code):
    tamper(chain, key, mutate)
    with pytest.raises(RuntimeError, match=code):
        opened(chain)


def test_the_source_must_still_be_fenced(chain):
    lock = Path(json.loads(chain.upstream_path.read_bytes())["handover_export"]).parent / "HANDOVER.lock"
    lock.unlink()
    with pytest.raises(RuntimeError, match="M1_PRISM_SOURCE_NOT_FENCED"):
        opened(chain)


def test_all_anchors_come_from_one_source_directory(chain, tmp_path):
    paths = json.loads(chain.upstream_path.read_bytes())
    copy = tmp_path / "elsewhere" / "LEDGER.jsonl"
    copy.parent.mkdir()
    copy.write_bytes(Path(paths["source_journal"]).read_bytes())
    paths["source_journal"] = str(copy)
    chain.upstream_path.write_bytes(canonical(paths))
    with pytest.raises(RuntimeError, match="M1_PRISM_ANCHORS_FROM_ONE_SOURCE_REQUIRED"):
        opened(chain)


def test_allocation_must_be_an_exact_integer(chain):
    chain.proposal["allocations"]["server_acceptance"] = 3.0
    seal(chain)
    with pytest.raises(RuntimeError, match="M1_PRISM_AUTHORIZATION_SCOPE_INVALID"):
        opened(chain)


def test_an_operation_keeping_its_old_window_is_refused(chain):
    origin = next(job for job in chain.rig.proposal["operations"]
                  if job["operation_id"] == chain.proposal["operations"][0]["operation_id"])
    chain.proposal["operations"][0] = dict(origin)
    seal(chain)
    with pytest.raises(RuntimeError, match="M1_PRISM_OPERATION_CHANGED"):
        opened(chain)


def test_wrong_window_activation_keeps_its_original_code_for_2026_10_23(rig):  # noqa: F811
    ledger = owned(rig)
    with pytest.raises(RuntimeError, match="M1_EXACT_WINDOW_GPU0_AND_CLOCK_ORIGIN_REQUIRED"):
        activate_continuation_window(ledger, window_id=M1_PRISM_SERVER, clock_origin=rig.origin, gpu_uuid=M1_GPU0)


def test_destination_installation_must_match_the_fenced_export(chain):
    chain.proposal["installation_sha256"] = "8" * 64
    seal(chain)
    with pytest.raises(RuntimeError, match="M1_PRISM_HANDOVER_ANCHOR_INVALID"):
        BatchLedger.for_continuation(chain.directory, **options(chain, installation_sha256="8" * 64))


def test_source_bytes_changed_after_fencing_are_refused(chain):
    journal = Path(json.loads(chain.upstream_path.read_bytes())["source_journal"])
    journal.write_bytes(journal.read_bytes() + b"\n")
    with pytest.raises(RuntimeError, match="M1_PINNED_UPSTREAM_BYTES_CHANGED"):
        opened(chain)


def test_the_source_accounting_directory_is_never_reused(chain):
    chain.proposal["accounting_directory"] = str(chain.rig.directory)
    seal(chain)
    with pytest.raises(RuntimeError, match="M1_OLD_ACCOUNTING_DIRECTORY_MUST_NOT_BE_REUSED"):
        BatchLedger.for_continuation(chain.rig.directory, **options(chain))


def test_an_unfenced_source_cannot_be_drafted(rig, tmp_path):  # noqa: F811
    ledger, budget = funded(rig)
    budget.confirm_stop("synthetic-lifetime", cleanup_confirmed=True)
    ledger.close(cleanup_confirmed=True)
    with pytest.raises(FileNotFoundError):
        proposal_tool.draft_prism(SimpleNamespace(source_accounting=rig.directory,
            accounting_directory=str(tmp_path / "x"), installation_sha256=DESTINATION,
            output=tmp_path / "p.json", upstream_output=tmp_path / "u.json"))


def test_a_fenced_source_never_admits_again(chain):
    source = BatchLedger.for_continuation(chain.rig.directory, **chain.rig.options)
    with pytest.raises(RuntimeError, match="M1_SOURCE_PERMANENTLY_FENCED"):
        source.acquire()


def test_the_2026_10_23_origin_is_unchanged(rig):  # noqa: F811
    ledger = owned(rig)
    origin = ledger.accounting()["continuation"]
    assert origin["base_used"] == 525 and origin["cap"] == 549 and origin["prior_gpu_seconds_preserved"] == 17002.874
    assert ledger.spec["server_window"] == M1_SERVER and ledger.spec["local_window"] == M1_LOCAL
