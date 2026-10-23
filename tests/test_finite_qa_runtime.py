"""Portable finite-QA regressions; synthetic accounting, no private resources."""
from contextlib import nullcontext
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "scripts/qa/batch_runtime"
sys.path.insert(0, str(SOURCE))
budget_module = importlib.import_module("batch_budget")
from batch_budget import BatchBudget, activate_approved_session, original_session_deadline  # noqa: E402
from batch_ledger import BatchLedger, canonical, digest  # noqa: E402
from batch_plan import planned_leases  # noqa: E402
from batch_app_driver import BatchAppDriver  # noqa: E402


@pytest.fixture(scope="module")
def seed(tmp_path_factory):
    directory = tmp_path_factory.mktemp("synthetic-finite-accounting")
    jobs = [{"job_id": f"{n:064x}", "source_sha256": f"{n+10000:064x}",
             "model_id": "prism-dr-5fold", "modality": "UWF", "width": 16, "height": 12,
             "execution_surface_proposed": "ACTUAL_APP_ASGI_TESTCLIENT"} for n in range(480)]
    ledger = BatchLedger(directory, jobs=jobs, manifest_sha256="f" * 64)
    ledger.acquire()
    budget = BatchBudget(ledger, clock=lambda: 1000, utc=lambda: 100000)
    budget.body["charged_gpu_seconds"] = 4772.23
    budget.persist()
    for n, job in enumerate(jobs[:305]):
        key = job["job_id"]
        if n >= 302:
            ledger.append(key, "BLOCKED_PREMODEL", reason="APP_REJECTED")
            continue
        ledger.append(key, "ATTEMPT_INTENT")
        if n >= 294:
            ledger.append(key, "FAILED_NO_RETRY", reason="DISCONNECTED")
        else:
            ledger.append(key, "RESPONSE_RETAINED", artifact_sha256="a" * 64)
            ledger.append(key, "PASS_READBACK", artifact_sha256="b" * 64)
    ledger.close(cleanup_confirmed=True)
    return jobs, {name: (directory / name).read_bytes()
                  for name in ("LEDGER.jsonl", "BUDGET.json", "ACCOUNTING.json")}


@pytest.fixture
def rig(tmp_path, monkeypatch, seed):
    jobs, originals = seed
    directory = tmp_path / "accounting"
    directory.mkdir()
    for name, raw in originals.items():
        (directory / name).write_bytes(raw)
    model_raw = canonical({"synthetic_model_metadata": True})
    (tmp_path / "EXPECTED_BATCH_MODELS.json").write_bytes(model_raw)
    pending_dir = tmp_path / "demo-evidence-recovery03-20261023"
    pending_dir.mkdir()
    pending_raw = canonical({"synthetic_pending_receipt": True})
    (pending_dir / "UNSENT_ORIGINAL_JOBS.json").write_bytes(pending_raw)
    fields = ("job_id", "source_sha256", "model_id", "modality", "width", "height")
    proposal = {"decision_id": budget_module.APPROVED_SESSION,
        "anchor": {"ledger_sha256": digest(originals["LEDGER.jsonl"]),
            "budget_file_sha256": digest(originals["BUDGET.json"]),
            "manifest_sha256": "f" * 64, "expected_models_file_sha256": digest(model_raw),
            "pending_file_sha256": digest(pending_raw)},
        "old_session_preservation": {"budget_body": json.loads(originals["BUDGET.json"])["body"]},
        "pending_jobs": [{key: job[key] for key in fields} for job in jobs[305:]]}
    proposal_raw = canonical(proposal)
    approval_raw = canonical({"decision_id": budget_module.APPROVED_SESSION,
        "proposal_sha256": digest(proposal_raw), "status": "EXPLICIT_OWNER_APPROVED_NOT_ACTIVATED",
        "new_sessions_authorized": 1})
    (tmp_path / "CLI_NEXT_GPU_SESSION_PROPOSAL_20261023.json").write_bytes(proposal_raw)
    (tmp_path / "CLI_NEXT_GPU_SESSION_APPROVAL_20261023.json").write_bytes(approval_raw)
    monkeypatch.setattr(budget_module, "GRANT_ROOT", tmp_path)
    monkeypatch.setattr(budget_module, "PROPOSAL_SHA", digest(proposal_raw))
    monkeypatch.setattr(budget_module, "APPROVAL_SHA", digest(approval_raw))
    ledger = BatchLedger(directory, jobs=jobs, manifest_sha256="f" * 64)
    ledger.acquire()
    now = [20000.0]
    options = {"session_id": budget_module.APPROVED_SESSION,
               "clock": lambda: now[0], "utc": lambda: now[0] + 99000}
    return SimpleNamespace(ledger=ledger, now=now, options=options, root=tmp_path, originals=originals)


def activate(rig, **kwargs):
    return activate_approved_session(rig.ledger, package_root=rig.root, **rig.options, **kwargs)


def test_named_session_preserves_original_bytes_charge_and_resume_clock(rig):
    activate(rig)
    budget = BatchBudget(rig.ledger, **rig.options)
    budget.reserve_worker("one")
    rig.now[0] += 7
    budget.confirm_stop("one", cleanup_confirmed=True)
    before = dict(budget.body)
    assert budget.summary()["aggregate_gpu_seconds"] == 4779.23
    assert all((rig.ledger.directory / name).read_bytes() == raw for name, raw in rig.originals.items())
    assert original_session_deadline(rig.ledger.directory / "BUDGET.json", "f" * 64,
                                     **rig.options) == 34400
    rig.ledger.close(cleanup_confirmed=True)
    resumed = BatchLedger(rig.ledger.directory, jobs=list(rig.ledger.jobs.values()), manifest_sha256="f" * 64)
    resumed.acquire()
    assert BatchBudget(resumed, **rig.options).body == before
    with pytest.raises(RuntimeError, match="NO_RETRY"):
        resumed.append(next(iter(resumed.states)), "ATTEMPT_INTENT")


def test_unapproved_and_repeated_activation_fail_before_calls(rig, monkeypatch):
    expected = budget_module.APPROVAL_SHA
    monkeypatch.setattr(budget_module, "APPROVAL_SHA", "0" * 64)
    with pytest.raises(RuntimeError, match="APPROVAL_REQUIRED"):
        activate(rig)
    assert not (rig.ledger.directory / "sessions").exists()
    monkeypatch.setattr(budget_module, "APPROVAL_SHA", expected)
    activate(rig)
    with pytest.raises(RuntimeError, match="ONCE_OR_PARTIAL"):
        activate(rig)


def test_concurrent_owner_cannot_activate(rig):
    other = BatchLedger(rig.ledger.directory, jobs=list(rig.ledger.jobs.values()), manifest_sha256="f" * 64)
    with pytest.raises(FileExistsError):
        other.acquire()
    with pytest.raises(RuntimeError, match="OWNER"):
        activate_approved_session(other, package_root=rig.root, **rig.options)


@pytest.mark.parametrize("failed_file", ["INTENT.json", "BUDGET.json", "COMPLETE.json"])
def test_partial_activation_preserves_exclusive_gates(rig, failed_file):
    def failing_write(path, raw):
        if path.name == failed_file:
            raise OSError("synthetic failure")
        path.write_bytes(raw)
    with pytest.raises(OSError):
        activate(rig, write=failing_write)
    assert rig.ledger.poisoned and (rig.ledger.directory / "SESSION_ACTIVATION.lock").is_file()
    assert (rig.ledger.directory / "SESSION.lock").is_file()
    with pytest.raises(RuntimeError):
        rig.ledger.close(cleanup_confirmed=True)


@pytest.mark.parametrize("limit", ["gpu", "wall", "rollback", "cleanup_margin"])
def test_each_new_session_limit_is_enforced(rig, limit):
    activate(rig)
    budget = BatchBudget(rig.ledger, **rig.options)
    if limit == "gpu":
        budget.body["charged_gpu_seconds"] = 10700
        budget.persist()
    elif limit == "wall":
        rig.now[0] += 14401
    elif limit == "rollback":
        rig.now[0] -= 1
    else:
        rig.now[0] += 14400 - 644
    with pytest.raises(RuntimeError):
        budget.reserve_worker("denied")
    assert budget.body["active"] is None


def test_unknown_stop_keeps_reservation_and_quarantine(rig):
    activate(rig)
    budget = BatchBudget(rig.ledger, **rig.options)
    budget.reserve_worker("unknown")
    with pytest.raises(RuntimeError, match="NO_REFUND"):
        budget.confirm_stop("unknown", cleanup_confirmed=False)
    assert budget.body["charged_gpu_seconds"] == 600 and budget.body["quarantined"]


def test_two_job_planner_preserves_order_parameters_and_excludes_terminal_jobs(seed):
    jobs, _ = seed
    expected = jobs[393:]
    groups = planned_leases(jobs, completed=[job["job_id"] for job in jobs[:393]])
    assert len(groups) == 44 and all(len(group["jobs"]) <= 2 for group in groups)
    assert [job for group in groups for job in group["jobs"]] == expected


def test_prepare_exception_is_terminal_without_inference_or_raw_text(tmp_path):
    job = {"job_id": "a" * 64, "source_sha256": "b" * 64, "model_id": "prism-dr-5fold",
           "execution_surface_proposed": "ACTUAL_APP_ASGI_TESTCLIENT"}
    ledger = BatchLedger(tmp_path / "accounting", jobs=[job], manifest_sha256="c" * 64)
    ledger.acquire()
    calls = []
    class Client:
        def post(self, path, **kwargs):
            calls.append(path)
            raise TimeoutError("SENSITIVE_ERROR_TEXT")
    provider = SimpleNamespace(last_failure={"stage": "PRISM_PREPARE", "code": "CONTROL_RPC_READ_TIMEOUT",
        "elapsed_ms": 20000, "raw_error_text": "SENSITIVE_ERROR_TEXT"})
    driver = BatchAppDriver(app=SimpleNamespace(state=SimpleNamespace(providers={job["model_id"]: provider})),
        client=Client(), readback=SimpleNamespace(get=lambda _: {"revision": 1}), ledger=ledger,
        output=tmp_path, expected_models={}, profile=SimpleNamespace(activate=lambda *args: nullcontext()))
    with pytest.raises(TimeoutError):
        driver.execute(job)
    raw = (tmp_path / "failures" / (job["job_id"] + "-preparation.json")).read_bytes()
    assert b"SENSITIVE_ERROR_TEXT" not in raw and json.loads(raw)["transport"]["elapsed_ms"] == 20000
    assert len(calls) == 1 and calls[0].endswith("prism-input-preview")
    assert ledger.attempts == 0 and ledger.states[job["job_id"]] == "BLOCKED_PREMODEL"
