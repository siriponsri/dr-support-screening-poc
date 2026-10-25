"""MS-03 service decision: synthetic files/clocks only, no model, network, GPU or DB."""

import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from test_m1_accounting_continuation import funded, owned, rig, upstream_seed  # noqa: F401
from test_m1_prism_window import chain, opened as prism_opened, pass_job, window as prism_window  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/model-server"))
ledger_module = importlib.import_module("batch_ledger")
proposal_tool = importlib.import_module("m1_proposal")
from batch_ledger import (BatchLedger, canonical, digest, M1_GPU0, M1_PRISM_SERVER,  # noqa: E402
                          M1_SERVICE_DECISION, M1_SERVICE_SERVER, M1_SERVICE_WATCHDOG, M1_SERVICE_WINDOWS,
                          window_order)
from batch_budget import BatchBudget, activate_continuation_window  # noqa: E402

DESTINATION = "7" * 64


def fence_prism(chain):  # noqa: F811
    """Run the PRISM decision like the live session (all three pass), then fence it."""
    ledger = prism_opened(chain)
    budget = prism_window(chain, ledger)
    budget.reserve_worker("prism-lifetime")
    for job in chain.proposal["operations"]:
        pass_job(ledger, budget, job)
    budget.confirm_stop("prism-lifetime", cleanup_confirmed=True)
    ledger.close(cleanup_confirmed=True)
    return prism_opened(chain).fence_handover(destination_installation_sha256=DESTINATION)


@pytest.fixture
def service(chain, tmp_path):  # noqa: F811
    export = fence_prism(chain)
    target = SimpleNamespace(directory=tmp_path / "service-continuation", proposal_path=tmp_path / "service.json",
                             approval_path=tmp_path / "service-approval.json",
                             upstream_path=tmp_path / "service-upstream.json", export=export, chain=chain,
                             rig=chain.rig)
    proposal_tool.draft_service(SimpleNamespace(
        source_accounting=chain.directory, origin_accounting=chain.rig.directory,
        accounting_directory=str(target.directory), installation_sha256=DESTINATION,
        output=target.proposal_path, upstream_output=target.upstream_path))
    target.proposal = json.loads(target.proposal_path.read_bytes())
    seal(target)
    return target


def seal(target):
    target.proposal_path.write_bytes(canonical(target.proposal))
    target.proposal_sha256 = digest(target.proposal_path.read_bytes())
    target.approval_path.write_bytes(canonical({"schema": "hospital-m1-owner-approval.v1",
        "decision_id": M1_SERVICE_DECISION, "proposal_sha256": target.proposal_sha256,
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


def activate(target, ledger, window_id):
    clocks = target.rig
    return activate_continuation_window(ledger, window_id=window_id, clock_origin=clocks.origin, gpu_uuid=M1_GPU0,
                                        clock=lambda: clocks.now[0], utc=lambda: clocks.utc[0])


def budget_for(target, ledger, window_id):
    clocks = target.rig
    return BatchBudget(ledger, session_id=window_id, clock_origin=clocks.origin,
                       clock=lambda: clocks.now[0], utc=lambda: clocks.utc[0])


def test_service_proposal_continues_six_unsent_post_fix_operations(service):
    assert service.export["global_used"] == 534 and service.export["remaining_job_ids"] == []
    proposal = service.proposal
    assert proposal["base_used"] == 534 and proposal["cap"] == 540 and proposal["new_admissions_max"] == 6
    assert proposal["allocations"] == {"post_fix_verification": 6}
    assert proposal["windows"] == M1_SERVICE_WINDOWS
    origin_export = json.loads((service.rig.directory / "HANDOVER_EXPORT.json").read_bytes())
    origins = {job["operation_id"]: job for job in service.rig.proposal["operations"]
               if job["job_id"] in origin_export["remaining_job_ids"] and job["purpose"] == "post_fix_verification"}
    assert len(proposal["operations"]) == 6 and {job["operation_id"] for job in proposal["operations"]} <= set(origins)
    for job in proposal["operations"]:
        assert job["window_id"] == M1_SERVICE_SERVER and job["job_id"] != origins[job["operation_id"]]["job_id"]
        assert all(job[key] == origins[job["operation_id"]][key] for key in job if key not in {"job_id", "window_id"})


def test_selection_prefers_non_prism_then_prism_in_register_order():
    jobs = [{"operation_id": f"op-{index}", "job_id": str(index), "purpose": "post_fix_verification",
             "window_id": proposal_tool.SERVER, "model_id": model}
            for index, model in enumerate(["retfound-aptos5", "uspec-uwf-grading", "uspec-uwf-grading",
                                           *["prism-dr-5fold"] * 6])]
    chosen = proposal_tool.service_selection(jobs, {job["job_id"] for job in jobs})
    assert [job["operation_id"] for job in chosen] == ["op-0", "op-1", "op-2", "op-3", "op-4", "op-5"]
    with pytest.raises(Exception, match="SIX_UNSENT_POST_FIX_OPERATIONS_REQUIRED"):
        proposal_tool.service_selection(jobs, {"0", "1", "3"})


def test_windows_run_in_order_and_only_the_service_window_admits(service):
    ledger = opened(service)
    assert (ledger.base_used, ledger.cap) == (534, 540)
    assert ledger.spec["prior_gpu_seconds"] == 31402.874
    assert window_order(ledger.spec) == [M1_SERVICE_WATCHDOG, M1_SERVICE_SERVER]
    with pytest.raises(RuntimeError, match="M1_EARLIER_WINDOW_MUST_RUN_FIRST"):
        activate(service, ledger, M1_SERVICE_SERVER)
    activate(service, ledger, M1_SERVICE_WATCHDOG)
    watchdog = budget_for(service, ledger, M1_SERVICE_WATCHDOG)
    assert watchdog.GPU_SECONDS == watchdog.LEASE_SECONDS == 900 and watchdog.SESSION_SECONDS == 1800
    watchdog.reserve_worker("watchdog-lifetime")
    job = service.proposal["operations"][0]
    with pytest.raises(RuntimeError, match="M1_OPERATION_OUTSIDE_ACTIVE_WINDOW"):
        ledger.admit(job["job_id"], request_sha256="d" * 64, budget=watchdog)
    with pytest.raises(RuntimeError, match="M1_EARLIER_WINDOW_MUST_BE_CLOSED"):
        activate(service, ledger, M1_SERVICE_SERVER)
    watchdog.confirm_stop("watchdog-lifetime", cleanup_confirmed=True)
    assert watchdog.body["window_closed"] is True and watchdog.body["charged_gpu_seconds"] == 900
    assert not ledger.rows and not ledger.poisoned
    activate(service, ledger, M1_SERVICE_SERVER)
    with pytest.raises(RuntimeError, match="M1_WINDOW_ACTIVATION_ONCE_OR_PARTIAL_PRESERVED"):
        activate(service, ledger, M1_SERVICE_WATCHDOG)
    budget = budget_for(service, ledger, M1_SERVICE_SERVER)
    assert budget.GPU_SECONDS == 3600 and budget.SESSION_SECONDS == 7200
    assert budget.prior_gpu_seconds == 32302.874  # The closed watchdog window's 900 s counts as prior use.
    budget.reserve_worker("service-lifetime")
    receipt = ledger.admit(job["job_id"], request_sha256="d" * 64, budget=budget)
    assert receipt["window_id"] == M1_SERVICE_SERVER and receipt["global_used"] == 535
    ledger.append(job["job_id"], "RESPONSE_RETAINED", artifact_sha256="a" * 64)
    ledger.append(job["job_id"], "PASS_READBACK", artifact_sha256="b" * 64)
    budget.confirm_stop("service-lifetime", cleanup_confirmed=True)
    ledger.close(cleanup_confirmed=True)
    reopened = opened(service)
    for window_id in (M1_SERVICE_WATCHDOG, M1_SERVICE_SERVER):
        with pytest.raises(RuntimeError, match="M1_UNCERTAIN_OR_CLOSED_WINDOW_NO_RESUME"):
            budget_for(service, reopened, window_id)
    export = reopened.fence_handover(destination_installation_sha256="6" * 64)
    assert export["global_used"] == 535 and len(export["remaining_job_ids"]) == 5
    assert {key: value["charged_gpu_seconds"] for key, value in export["windows"].items()} == {
        M1_SERVICE_WATCHDOG: 900, M1_SERVICE_SERVER: 3600}


def test_an_open_watchdog_window_keeps_the_ledger_owned(service):
    ledger = opened(service)
    activate(service, ledger, M1_SERVICE_WATCHDOG)
    with pytest.raises(RuntimeError, match="M1_WINDOW_MUST_BE_CLOSED"):
        ledger.close(cleanup_confirmed=True)


def test_a_quarantined_watchdog_window_blocks_the_service_window(service):
    ledger = opened(service)
    activate(service, ledger, M1_SERVICE_WATCHDOG)
    watchdog = budget_for(service, ledger, M1_SERVICE_WATCHDOG)
    watchdog.reserve_worker("watchdog-lifetime")
    with pytest.raises(RuntimeError, match="OWNED_WORKER_STOP_UNCONFIRMED_NO_REFUND"):
        watchdog.confirm_stop("watchdog-lifetime", cleanup_confirmed=False)
    with pytest.raises(RuntimeError, match="M1_EARLIER_WINDOW_MUST_BE_CLOSED"):
        activate(service, ledger, M1_SERVICE_SERVER)


@pytest.mark.parametrize("change, code", [
    (lambda p: p.update(cap=541), "M1_SERVICE_SOURCE_USAGE_INVALID"),
    (lambda p: p.update(base_used=533, cap=539), "M1_SERVICE_SOURCE_USAGE_INVALID"),
    (lambda p: p["operations"].pop(), "M1_SERVICE_EXACT_POST_FIX_OPERATIONS_REQUIRED"),
    (lambda p: p["windows"][M1_SERVICE_WATCHDOG].update(gpu_seconds_cap=900.0), "M1_SERVICE_AUTHORIZATION_SCOPE_INVALID"),
    (lambda p: p["windows"][M1_SERVICE_SERVER].update(gpu_seconds_cap=7200), "M1_SERVICE_AUTHORIZATION_SCOPE_INVALID"),
    (lambda p: p["windows"].pop(M1_SERVICE_WATCHDOG), "M1_SERVICE_AUTHORIZATION_SCOPE_INVALID"),
    (lambda p: p.update(new_admissions_max=7), "M1_SERVICE_AUTHORIZATION_SCOPE_INVALID"),
    (lambda p: p["allocations"].update(post_fix_verification=6.0), "M1_SERVICE_AUTHORIZATION_SCOPE_INVALID"),
])
def test_changed_service_proposals_are_refused(service, change, code):
    change(service.proposal)
    seal(service)
    with pytest.raises(RuntimeError, match=code):
        opened(service)


def test_a_changed_operation_is_refused(service):
    job = service.proposal["operations"][0]
    job["source_sha256"] = "f" * 64
    job["job_id"] = digest(canonical({k: v for k, v in job.items() if k != "job_id"}))
    seal(service)
    with pytest.raises(RuntimeError, match="M1_SERVICE_OPERATION_CHANGED"):
        opened(service)


def test_an_operation_keeping_its_old_window_is_refused(service):
    origin = next(job for job in service.rig.proposal["operations"]
                  if job["operation_id"] == service.proposal["operations"][0]["operation_id"])
    service.proposal["operations"][0] = dict(origin)
    seal(service)
    with pytest.raises(RuntimeError, match="M1_SERVICE_OPERATION_CHANGED"):
        opened(service)


def test_non_post_fix_or_already_sent_operations_are_refused(service):
    used = next(job for job in service.rig.proposal["operations"] if job["purpose"] == "server_acceptance")
    local = next(job for job in service.rig.proposal["operations"] if job["purpose"] == "local_acceptance")
    for origin in (used, local):
        body = {k: v for k, v in origin.items() if k != "job_id"} | {"window_id": M1_SERVICE_SERVER}
        service.proposal["operations"][0] = {**body, "job_id": digest(canonical(body))}
        seal(service)
        with pytest.raises(RuntimeError, match="M1_SERVICE_EXACT_POST_FIX_OPERATIONS_REQUIRED"):
            opened(service)


def test_new_seconds_above_the_approved_total_are_refused(service, monkeypatch):
    monkeypatch.setattr(ledger_module, "M1_NEW_GPU_SECONDS_MAX", 18899)
    with pytest.raises(RuntimeError, match="M1_SERVICE_SOURCE_WINDOW_NOT_CLOSED_OR_OVER_BUDGET"):
        opened(service)


@pytest.mark.parametrize("key", ["handover_export", "origin_export"])
def test_both_sources_must_still_be_fenced(service, key):
    lock = Path(json.loads(service.upstream_path.read_bytes())[key]).parent / "HANDOVER.lock"
    lock.unlink()
    with pytest.raises(RuntimeError, match="M1_SERVICE_SOURCE_NOT_FENCED"):
        opened(service)


def test_origin_bytes_changed_after_drafting_are_refused(service):
    path = Path(json.loads(service.upstream_path.read_bytes())["origin_proposal"])
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(RuntimeError, match="M1_PINNED_UPSTREAM_BYTES_CHANGED"):
        opened(service)


def test_anchors_come_from_the_two_named_sources(service, tmp_path):
    paths = json.loads(service.upstream_path.read_bytes())
    copy = tmp_path / "elsewhere" / "ACCOUNTING.json"
    copy.parent.mkdir()
    copy.write_bytes(Path(paths["source_accounting"]).read_bytes())
    paths["source_accounting"] = str(copy)
    service.upstream_path.write_bytes(canonical(paths))
    with pytest.raises(RuntimeError, match="M1_SERVICE_ANCHORS_FROM_TWO_SOURCES_REQUIRED"):
        opened(service)


def test_destination_installation_must_match_the_fenced_prism_export(service):
    service.proposal["installation_sha256"] = "8" * 64
    seal(service)
    with pytest.raises(RuntimeError, match="M1_SERVICE_HANDOVER_ANCHOR_INVALID"):
        BatchLedger.for_continuation(service.directory, **options(service, installation_sha256="8" * 64))


def test_neither_source_directory_is_reused(service):
    for directory in (service.chain.directory, service.rig.directory):
        service.proposal["accounting_directory"] = str(directory)
        seal(service)
        with pytest.raises(RuntimeError, match="M1_OLD_ACCOUNTING_DIRECTORY_MUST_NOT_BE_REUSED"):
            BatchLedger.for_continuation(directory, **options(service))


def test_a_fenced_prism_source_never_admits_again(service):
    source = BatchLedger.for_continuation(service.chain.directory, **{
        key: value for key, value in __import__("test_m1_prism_window").options(service.chain).items()})
    with pytest.raises(RuntimeError, match="M1_SOURCE_PERMANENTLY_FENCED"):
        source.acquire()


def test_earlier_decisions_keep_one_server_window(chain):  # noqa: F811
    ledger = prism_opened(chain)
    assert window_order(ledger.spec) == [M1_PRISM_SERVER] and "window_order" not in ledger.spec


def test_earlier_single_window_exports_keep_their_shape(chain):  # noqa: F811
    assert "windows" not in fence_prism(chain)


def test_preserved_seconds_are_rederived_from_the_origin_window(service):
    paths = {name: Path(value) for name, value in json.loads(service.upstream_path.read_bytes()).items()}
    accounting = json.loads(paths["source_accounting"].read_bytes())
    accounting["continuation"]["prior_gpu_seconds_preserved"] = 17002.874  # Would hide the 10800 s window.
    paths["source_accounting"].write_bytes(canonical(accounting))
    service.proposal["upstream"] = {name: digest(path.read_bytes()) for name, path in paths.items()}
    seal(service)
    with pytest.raises(RuntimeError, match="M1_SERVICE_PRESERVED_GPU_SECONDS_INVALID"):
        opened(service)
