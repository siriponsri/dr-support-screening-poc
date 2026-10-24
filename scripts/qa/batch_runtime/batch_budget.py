"""Conservative durable GPU reservation and whole-session budget; no launches.

Reservations are fsynced before a worker starts. Unknown cleanup never refunds
time or permits another lease. Runtime must additionally enforce native child
and parent deadlines; this is accounting, not a process-killing substitute.
"""

from datetime import datetime, timezone
import json
import math
import os
import re
from pathlib import Path
import time

from batch_ledger import (canonical, digest, require, M1_LOCAL,
                          M1_GPU0, _is_sha, _direct, _regular, _new_file)

APPROVED_RECOVERY_LEASE = "batch_retfound_aptos5_dbf5070ece3d72f24748"
APPROVED_RECOVERY_HASHES = {
    "LEDGER.jsonl": "c2786f2bc8c42d9b7f756e629ac961881f6ecb42c16267f1855783e5a53063fa",
    "BUDGET.json": "ae882ea35783fabd677cebe3d14254b700ca7f17a84d2087ffa6102e013f6ea9",
    "SESSION.lock": "b0811e9ce58cc4c8855d2edea4df0688b3fe41417b63606feb28660d7da33fc1",
}

# One further session authorized by the owner; no general session renewal API.
APPROVED_SESSION = "DR_B03_ORIGINAL_175_NEXT_SESSION_20261023"
PROPOSAL_SHA = "cea923cdd763c9419ef0b1eb615441ff08fa78466e7d0dc586a81d1b24d52603"
APPROVAL_SHA = "3dfb2c0ab01757aa2e69af39236d2dd836404098ad49c6e928eabc421fc62752"
GRANT_ROOT = Path(__file__).resolve().parent.parent


def _read_regular(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink()
            and not getattr(path.stat(), "st_file_attributes", 0) & 1024,
            "SESSION_DIRECT_REGULAR_FILE_REQUIRED")
    return path.read_bytes()


def _session_grant():
    proposal_raw = _read_regular(GRANT_ROOT / "CLI_NEXT_GPU_SESSION_PROPOSAL_20261023.json")
    approval_raw = _read_regular(GRANT_ROOT / "CLI_NEXT_GPU_SESSION_APPROVAL_20261023.json")
    require(digest(proposal_raw) == PROPOSAL_SHA and digest(approval_raw) == APPROVAL_SHA,
            "EXACT_OWNER_SESSION_APPROVAL_REQUIRED")
    proposal, approval = json.loads(proposal_raw), json.loads(approval_raw)
    require(approval["decision_id"] == proposal["decision_id"] == APPROVED_SESSION
            and approval["proposal_sha256"] == PROPOSAL_SHA
            and approval["status"] == "EXPLICIT_OWNER_APPROVED_NOT_ACTIVATED"
            and approval["new_sessions_authorized"] == 1,
            "EXACT_OWNER_SESSION_APPROVAL_REQUIRED")
    return proposal, proposal_raw, approval_raw


def _session_directory(directory, session_id):
    require(session_id == APPROVED_SESSION, "EXACT_APPROVED_NAMED_SESSION_REQUIRED")
    directory = Path(directory)
    for path in (directory, directory / "sessions", directory / "sessions" / session_id):
        if path.exists():
            require(not path.is_symlink()
                    and not getattr(path.stat(), "st_file_attributes", 0) & 1024
                    and path.resolve().is_relative_to(directory.resolve()),
                    "SESSION_REPARSE_PATH_REJECTED")
    return directory / "sessions" / session_id


def approved_session_context(directory, session_id):
    """Read the completed authorization; partial activation always fails closed."""
    directory = Path(directory)
    require(not (directory / "SESSION_ACTIVATION.lock").exists(),
            "INCOMPLETE_SESSION_ACTIVATION_PRESERVED")
    session = _session_directory(directory, session_id)
    proposal, proposal_raw, approval_raw = _session_grant()
    complete_raw = _read_regular(session / "COMPLETE.json")
    require((session / "ACTIVATION.lock.completed").is_file(), "SESSION_ACTIVATION_NOT_COMPLETED")
    complete = json.loads(complete_raw)
    old_budget = _read_regular(directory / "BUDGET.json")
    old_ledger = _read_regular(session / "LEDGER.jsonl.original")
    require(_read_regular(session / "BUDGET.json.original") == old_budget
            and digest(old_budget) == proposal["anchor"]["budget_file_sha256"]
            and digest(old_ledger) == proposal["anchor"]["ledger_sha256"]
            and _read_regular(directory / "LEDGER.jsonl").startswith(old_ledger)
            and _read_regular(session / "PROPOSAL.json") == proposal_raw
            and _read_regular(session / "APPROVAL.json") == approval_raw,
            "ORIGINAL_SESSION_HISTORY_CHANGED")
    ids = [job["job_id"] for job in proposal["pending_jobs"]]
    require(complete["session_id"] == session_id
            and complete["approval_sha256"] == APPROVAL_SHA
            and complete["proposal_sha256"] == PROPOSAL_SHA
            and complete["approved_job_ids"] == ids
            and complete["original_budget_sha256"] == digest(old_budget)
            and complete["original_ledger_sha256"] == digest(old_ledger),
            "SESSION_ACTIVATION_IDENTITY_CHANGED")
    return session / "BUDGET.json", complete, digest(complete_raw), json.loads(old_budget)["body"]


def activate_approved_session(ledger, *, session_id, package_root,
                              clock=time.monotonic, utc=time.time, write=None):
    """Single explicit activation under existing ledger ownership. No launches.

    Any partial write preserves both the activation gate and owner lock. The
    original budget/journal bytes are never replaced, truncated or refunded.
    """
    ledger.assert_owner()
    directory = ledger.directory
    session = _session_directory(directory, session_id)
    gate = directory / "SESSION_ACTIVATION.lock"
    require(not gate.exists() and not session.exists(), "SESSION_ACTIVATION_ONCE_OR_PARTIAL_PRESERVED")
    proposal, proposal_raw, approval_raw = _session_grant()
    anchor = proposal["anchor"]
    originals = {name: _read_regular(directory / name) for name in ("BUDGET.json", "LEDGER.jsonl")}
    require(digest(originals["BUDGET.json"]) == anchor["budget_file_sha256"]
            and digest(originals["LEDGER.jsonl"]) == anchor["ledger_sha256"]
            and ledger.manifest_sha256 == anchor["manifest_sha256"]
            and digest(_read_regular(Path(package_root) / "EXPECTED_BATCH_MODELS.json"))
            == anchor["expected_models_file_sha256"]
            and digest(_read_regular(GRANT_ROOT / "demo-evidence-recovery03-20261023/UNSENT_ORIGINAL_JOBS.json"))
            == anchor["pending_file_sha256"], "APPROVED_SESSION_ANCHORS_CHANGED")
    old = json.loads(originals["BUDGET.json"])
    require(old["sha256"] == digest(canonical(old["body"]))
            and old["body"] == proposal["old_session_preservation"]["budget_body"]
            and old["body"]["active"] is None and old["body"]["quarantined"] is False,
            "ORIGINAL_SESSION_MUST_BE_CLOSED_UNCHANGED")
    approved = proposal["pending_jobs"]
    fields = ("job_id", "source_sha256", "model_id", "modality", "width", "height")
    pending = [{key: row[key] for key in fields} for row in ledger.pending()]
    require(pending == approved and len(approved) == len({row["job_id"] for row in approved}) == 175
            and all(row["model_id"] == "prism-dr-5fold" for row in approved)
            and ledger.attempts == 302 and not ledger.uncertain(),
            "EXACT_175_ORIGINAL_UNSENT_PRISM_JOBS_REQUIRED")
    now, utc_now = clock(), utc()
    require(all(type(x) in (int, float) and math.isfinite(x) for x in (now, utc_now))
            and now >= old["body"]["started_monotonic"]
            and utc_now >= old["body"]["started_utc"] + BatchBudget.SESSION_SECONDS,
            "CLOSED_ORIGINAL_SESSION_AND_VALID_CLOCK_REQUIRED")

    def durable(path, raw):
        with path.open("xb") as output:
            require(output.write(raw) == len(raw), "SESSION_ACTIVATION_PARTIAL_WRITE")
            output.flush(); os.fsync(output.fileno())

    write = write or durable
    complete = {"session_id": session_id, "approval_sha256": APPROVAL_SHA,
        "proposal_sha256": PROPOSAL_SHA, "approved_job_ids": [row["job_id"] for row in approved],
        "original_budget_sha256": digest(originals["BUDGET.json"]),
        "original_ledger_sha256": digest(originals["LEDGER.jsonl"]),
        "started_monotonic": now, "started_utc": utc_now,
        "gpu_seconds_cap": 10800, "wall_seconds_cap": 14400,
        "status": "OWNER_APPROVED_SESSION_ACTIVATED_ONCE", "model_calls_at_activation": 0}
    complete_raw = canonical(complete)
    body = {"manifest": ledger.manifest_sha256, "started_monotonic": now, "started_utc": utc_now,
        "charged_gpu_seconds": 0, "lease_count": 0, "active": None, "quarantined": False,
        "session_id": session_id, "authorization_sha256": digest(complete_raw)}
    try:
        durable(gate, canonical({"session_id": session_id, "owner_lock_sha256": digest(ledger.owned_lock)}))
        ledger.assert_owner()
        session.mkdir(parents=True, exist_ok=False)
        write(session / "INTENT.json", canonical(complete))
        for name, raw in originals.items():
            write(session / (name + ".original"), raw)
        write(session / "PROPOSAL.json", proposal_raw)
        write(session / "APPROVAL.json", approval_raw)
        write(session / "BUDGET.json", canonical({"body": body, "sha256": digest(canonical(body))}))
        require(all(_read_regular(directory / name) == raw for name, raw in originals.items()),
                "SESSION_ACTIVATION_CONCURRENT_STATE_CHANGE")
        ledger.assert_owner()
        write(session / "COMPLETE.json", complete_raw)
        os.rename(gate, session / "ACTIVATION.lock.completed")
        approved_session_context(directory, session_id)
    except BaseException:
        ledger.poisoned = True
        raise
    return complete


def original_session_deadline(path, manifest_sha256, *, clock=time.monotonic, utc=time.time, session_id=None):
    """Read-only absolute native deadline, including across driver invocations."""
    path = Path(path)
    if session_id is not None:
        path, complete, authorization_sha, _ = approved_session_context(path.parent, session_id)
    require(path.is_file() and not path.is_symlink(), "ORIGINAL_SESSION_BUDGET_REQUIRED")
    saved = json.loads(path.read_bytes())
    body = saved["body"]
    require(saved["sha256"] == digest(canonical(body)) and body["manifest"] == manifest_sha256,
            "ORIGINAL_SESSION_BUDGET_IDENTITY_CHANGED")
    if session_id is not None:
        require(body["session_id"] == session_id and body["authorization_sha256"] == authorization_sha
                and all(body[key] == complete[key] for key in ("started_monotonic", "started_utc")),
                "SESSION_CLOCK_OR_AUTHORIZATION_CHANGED")
    now, utc_now = clock(), utc()
    remaining = min(BatchBudget.SESSION_SECONDS-(now-body["started_monotonic"]),
                    BatchBudget.SESSION_SECONDS-(utc_now-body["started_utc"]))
    require(now >= body["started_monotonic"] and utc_now >= body["started_utc"]
            and 0 < remaining <= BatchBudget.SESSION_SECONDS, "ORIGINAL_SESSION_EXPIRED_OR_CLOCK_CHANGED")
    return now+remaining


def recover_approved_lease(ledger, *, owner_approved_lease, observe, process_exited,
                           clock=time.monotonic, utc=time.time, write=None):
    """One explicit owner-approved transition; no refunds, ledger reset or calls.

    Ordinary acquire/resume cannot enter this path. Old bytes are hash pinned;
    every partial write leaves an exclusive recovery gate for manual review.
    """
    from collections import Counter
    from copy import deepcopy
    require(owner_approved_lease == APPROVED_RECOVERY_LEASE,
            "EXACT_USER_APPROVED_RECOVERY_LEASE_REQUIRED")
    require(ledger.owned_lock is None and not ledger.poisoned,
            "RECOVERY_REQUIRES_UNOWNED_LEDGER_HANDLE")
    directory = ledger.directory.resolve(strict=True)
    require(directory == ledger.directory.absolute(), "RECOVERY_DIRECT_ACCOUNTING_REQUIRED")
    gate = directory / "OWNER_RECOVERY.lock"
    receipt_dir = directory / "owner-recovery" / APPROVED_RECOVERY_LEASE
    require(not gate.exists() and not receipt_dir.exists(), "OWNER_RECOVERY_ONCE_OR_PARTIAL_PRESERVED")
    for path in (directory, receipt_dir.parent):
        if path.exists():
            require(not path.is_symlink() and not getattr(path.stat(), "st_file_attributes", 0) & 1024
                    and path.resolve().is_relative_to(directory), "RECOVERY_REPARSE_PATH_REJECTED")
    originals = {}
    for name, expected in APPROVED_RECOVERY_HASHES.items():
        path = directory / name
        require(path.is_file() and not path.is_symlink()
                and path.resolve().parent == directory, "RECOVERY_SOURCE_PATH_CHANGED")
        originals[name] = path.read_bytes()
        require(digest(originals[name]) == expected, "RECOVERY_OLD_BYTES_CHANGED")
    ledger._reload()
    require(ledger.accounting()["budget_required"] is True and ledger.attempts == 50
            and Counter(ledger.states.values()) == Counter({"PASS_READBACK": 49,
                "FAILED_NO_RETRY": 1, "BLOCKED_PREMODEL": 2}),
            "RECOVERY_REQUIRES_EXACT_TERMINAL_REQUEST_STATES")
    old = json.loads(originals["BUDGET.json"])
    body = old["body"]
    require(old["sha256"] == digest(canonical(body))
            and body["manifest"] == ledger.manifest_sha256
            and body["quarantined"] is True
            and body["active"]["lease_id"] == APPROVED_RECOVERY_LEASE,
            "RECOVERY_EXACT_QUARANTINE_REQUIRED")
    now, utc_now = clock(), utc()
    require(all(type(x) in (int, float) and math.isfinite(x) for x in (now, utc_now)), "RECOVERY_CLOCK_INVALID")
    require(0 <= now-body["started_monotonic"] < BatchBudget.SESSION_SECONDS
            and 0 <= utc_now-body["started_utc"] < BatchBudget.SESSION_SECONDS,
            "RECOVERY_ORIGINAL_SESSION_EXPIRED_OR_CLOCK_CHANGED")
    lock = json.loads(originals["SESSION.lock"])
    require(lock["manifest"] == ledger.manifest_sha256
            and type(lock["owner_pid"]) is int and lock["owner_pid"] > 0,
            "RECOVERY_ORIGINAL_OWNER_IDENTITY_CHANGED")
    exit_proof = process_exited(lock["owner_pid"])
    require(type(exit_proof) is dict and exit_proof.get("pid") == lock["owner_pid"]
            and exit_proof.get("exited") is True, "RECOVERY_ORIGINAL_PROCESS_NOT_PROVEN_EXITED")
    proof = observe()
    require(type(proof) is dict and proof.get("lease_id") == APPROVED_RECOVERY_LEASE
            and proof.get("original_server_final_sha256") == "e5f1a6fb3774d77722dd938ddc5f0d7fcf8996cbe9237055892283636896d6ad"
            and proof.get("remote_receipt_matches_original") is True
            and proof.get("original_ssh_exit_code") == 1
            and proof.get("original_worker_termination_confirmed") is True
            and proof.get("fixed_loopback_ports_closed") == {str(p): True for p in (7861,7862,7864,17860)}
            and proof.get("gpu0_uuid") == "GPU-044a8b11-4729-458b-a07b-297e45439419"
            and proof.get("gpu0_query_ok") is True and proof.get("gpu0_active_compute_entries") == 0
            and type(proof.get("gpu0_active_compute_entries")) is int
            and all(type(v) is bool for v in proof.get("fixed_loopback_ports_closed", {}).values())
            and 0 <= clock()-proof.get("observed_monotonic", -1e100) <= 30,
            "RECOVERY_FRESH_AUTHENTICATED_STOP_PROOF_REQUIRED")
    require(clock()-body["started_monotonic"] < BatchBudget.SESSION_SECONDS
            and utc()-body["started_utc"] < BatchBudget.SESSION_SECONDS,
            "RECOVERY_ORIGINAL_SESSION_EXPIRED_OR_CLOCK_CHANGED")
    def durable(path, data):
        with path.open("xb") as output:
            require(output.write(data) == len(data), "RECOVERY_PARTIAL_WRITE")
            output.flush(); os.fsync(output.fileno())
    write = write or durable
    # Exclusive gate precedes all data writes; never remove it after a failure.
    durable(gate, canonical({"lease_id": APPROVED_RECOVERY_LEASE, "recovery_pid": os.getpid()}))
    for name, data in originals.items():
        require((directory/name).read_bytes() == data, "RECOVERY_CONCURRENT_STATE_CHANGE")
    receipt_dir.mkdir(parents=True, exist_ok=False)
    require(receipt_dir.resolve().is_relative_to(directory), "RECOVERY_RECEIPT_PATH_CHANGED")
    intent = {"status": "EXPLICIT_OWNER_RECOVERY_INTENT", "lease_id": APPROVED_RECOVERY_LEASE,
        "owner_approval": "User answered: approve this exact recovery proposal; 2026-10-23 Asia/Bangkok",
        "old_file_sha256": {n: digest(v) for n,v in originals.items()},
        "process_exit_proof": exit_proof, "fresh_authenticated_stop_proof": proof,
        "original_cleanup_failure_replaced": False, "reservation_refunded": False,
        "request_replay": False, "new_session": False}
    write(receipt_dir/"INTENT.json", canonical(intent))
    for name, data in originals.items():
        write(receipt_dir/(name+".original"), data)
    reconciled = deepcopy(body)
    reconciled.update(active=None, quarantined=False)
    raw = canonical({"body": reconciled, "sha256": digest(canonical(reconciled))})
    pending = directory/"BUDGET.recovery.pending"
    write(pending, raw)
    require(all((directory/n).read_bytes() == data for n,data in originals.items()), "RECOVERY_CONCURRENT_STATE_CHANGE")
    os.replace(pending, directory/"BUDGET.json")
    require((directory/"BUDGET.json").read_bytes() == raw
            and (directory/"SESSION.lock").read_bytes() == originals["SESSION.lock"]
            and digest((directory/"LEDGER.jsonl").read_bytes()) == APPROVED_RECOVERY_HASHES["LEDGER.jsonl"],
            "RECOVERY_STATE_READBACK_FAILED")
    # Archive only the exact stale lock; its bytes and epoch remain available.
    os.rename(directory/"SESSION.lock", receipt_dir/"SESSION.lock.preserved")
    result = {**intent, "status": "OWNER_APPROVED_LEASE_RECONCILED_NO_REFUND",
        "new_budget_sha256": digest(raw), "charged_gpu_seconds": reconciled["charged_gpu_seconds"],
        "started_utc": reconciled["started_utc"], "started_monotonic": reconciled["started_monotonic"],
        "lease_count": reconciled["lease_count"], "attempts": ledger.attempts, "global_used": 49+ledger.attempts}
    write(receipt_dir/"COMPLETE.json", canonical(result))
    os.rename(gate, receipt_dir/"RECOVERY.lock.completed")
    return result


def _window_caps(ledger, window_id):
    """The verified decision's only Server window and its caps; Local stays fail-closed."""
    require(ledger.continuation is not None, "M1_VERIFIED_CONTINUATION_REQUIRED")
    require(window_id != M1_LOCAL, "M1_LOCAL_ADOPTION_NOT_QUALIFIED")
    require(window_id == ledger.spec["server_window"], "M1_EXACT_NAMED_WINDOW_REQUIRED")
    return ledger.spec["windows"][window_id]


def _m1_lifetime(body, caps):
    gpu_cap, wall_cap = caps["gpu_seconds_cap"], caps["wall_seconds_cap"]
    require(type(body["lease_count"]) is int and body["lease_count"] in {0, 1}
            and type(body["charged_gpu_seconds"]) in (int, float)
            and math.isfinite(body["charged_gpu_seconds"])
            and type(body["window_closed"]) is bool and type(body["quarantined"]) is bool,
            "M1_WINDOW_BUDGET_CHANGED")
    active = body["active"]
    if body["lease_count"] == 0:
        require(active is None and body["charged_gpu_seconds"] == 0 and not body["window_closed"],
                "M1_UNFUNDED_OR_REWRITTEN_LIFETIME_RESERVATION")
    else:
        require(body["charged_gpu_seconds"] >= gpu_cap
                and (active is not None or body["window_closed"] or body["quarantined"]),
                "M1_UNFUNDED_OR_REWRITTEN_LIFETIME_RESERVATION")
        if active is not None:
            require(type(active) is dict and set(active) == {"lease_id", "started", "deadline"}
                    and type(active["lease_id"]) is str
                    and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", active["lease_id"])
                    and all(type(active[key]) in (int, float) and math.isfinite(active[key])
                            for key in ("started", "deadline"))
                    and active["started"] >= body["started_monotonic"]
                    and active["deadline"] == active["started"] + gpu_cap
                    and active["deadline"] <= body["started_monotonic"] + wall_cap - 45
                    and not body["window_closed"], "M1_NATIVE_LIFETIME_DEADLINE_CHANGED")


def continuation_window_context(ledger, window_id):
    """Read verified M1 window state; never activates or adopts Local."""
    caps = _window_caps(ledger, window_id)
    ledger._check_continuation()
    require(not (ledger.directory / "M1_WINDOW_ACTIVATION.lock").exists(),
            "M1_PARTIAL_WINDOW_ACTIVATION_PRESERVED")
    directory = _direct(ledger.directory / "windows" / window_id)
    complete_raw = _regular(directory / "COMPLETE.json")
    complete = json.loads(complete_raw)
    require((directory / "ACTIVATION.lock.completed").is_file()
            and complete["window_id"] == window_id
            and complete["profile"] == caps["profile"]
            and complete["proposal_sha256"] == ledger.continuation["proposal_sha256"]
            and complete["approval_sha256"] == ledger.continuation["approval_sha256"]
            and complete["manifest"] == ledger.manifest_sha256
            and complete["gpu_uuid"] == M1_GPU0 and complete["gpu_index"] == 0
            and complete["gpu_seconds_cap"] == caps["gpu_seconds_cap"]
            and complete["wall_seconds_cap"] == caps["wall_seconds_cap"]
            and complete["refund_unused"] is False and complete["renew"] is False
            and _is_sha(complete["clock_origin"])
            and all(type(complete[key]) in (int, float) and math.isfinite(complete[key]) and complete[key] > 0
                    for key in ("started_monotonic", "started_utc")),
            "M1_WINDOW_AUTHORIZATION_CHANGED")
    path = directory / "BUDGET.json"
    saved = json.loads(_regular(path))
    body = saved["body"]
    require(saved["sha256"] == digest(canonical(body))
            and body["manifest"] == ledger.manifest_sha256
            and body["session_id"] == window_id and body["authorization_sha256"] == digest(complete_raw)
            and all(body[key] == complete[key] for key in ("started_monotonic", "started_utc", "clock_origin"))
            and type(body["window_closed"]) is bool and type(body["quarantined"]) is bool
            and type(body["lease_count"]) is int and 0 <= body["lease_count"] <= 1
            and type(body["charged_gpu_seconds"]) in (int, float)
            and math.isfinite(body["charged_gpu_seconds"]) and body["charged_gpu_seconds"] >= 0,
            "M1_WINDOW_BUDGET_CHANGED")
    _m1_lifetime(body, caps)
    return path, complete, body


def activate_continuation_window(ledger, *, window_id, clock_origin, gpu_uuid,
                                 clock=time.monotonic, utc=time.time, write=None):
    """One explicit Server window, no launches; Local remains fail-closed.

    A host/boot clock-origin digest must be supplied by the qualified runtime.
    This function does not observe hardware or grant access to a machine.
    """
    with ledger.lock:
        ledger.assert_owner()
        caps = _window_caps(ledger, window_id)
        require(_is_sha(clock_origin) and gpu_uuid == M1_GPU0,
                "M1_EXACT_WINDOW_GPU0_AND_CLOCK_ORIGIN_REQUIRED")
        directory = _direct(ledger.directory / "windows" / window_id)
        gate = ledger.directory / "M1_WINDOW_ACTIVATION.lock"
        require(not gate.exists() and not directory.exists() and not ledger.rows and not ledger.uncertain(),
                "M1_WINDOW_ACTIVATION_ONCE_OR_PARTIAL_PRESERVED")
        now, utc_now = clock(), utc()
        require(all(type(value) in (int, float) and math.isfinite(value) and value > 0 for value in (now, utc_now)),
                "M1_WINDOW_CLOCK_INVALID")
        complete = {"window_id": window_id, "profile": caps["profile"],
            "manifest": ledger.manifest_sha256, "proposal_sha256": ledger.continuation["proposal_sha256"],
            "approval_sha256": ledger.continuation["approval_sha256"], "gpu_uuid": gpu_uuid, "gpu_index": 0,
            "started_monotonic": now, "started_utc": utc_now, "clock_origin": clock_origin,
            "gpu_seconds_cap": caps["gpu_seconds_cap"], "wall_seconds_cap": caps["wall_seconds_cap"],
            "refund_unused": False, "renew": False}
        body = {"manifest": ledger.manifest_sha256, "session_id": window_id,
            "authorization_sha256": digest(canonical(complete)),
            "started_monotonic": now, "started_utc": utc_now, "clock_origin": clock_origin,
            "charged_gpu_seconds": 0, "lease_count": 0, "active": None,
            "quarantined": False, "window_closed": False}
        write = write or _new_file
        try:
            _new_file(gate, canonical({"window_id": window_id, "owner_sha256": digest(ledger.owned_lock)}))
            directory.mkdir(parents=True, exist_ok=False)
            write(directory / "INTENT.json", canonical(complete))
            write(directory / "BUDGET.json", canonical({"body": body, "sha256": digest(canonical(body))}))
            ledger.assert_owner()
            write(directory / "COMPLETE.json", canonical(complete))
            os.rename(gate, directory / "ACTIVATION.lock.completed")
            continuation_window_context(ledger, window_id)
        except BaseException:
            ledger.poisoned = True
            raise
        return complete


class BatchBudget:
    GPU_SECONDS, SESSION_SECONDS, LEASE_SECONDS = 10800, 14400, 600

    def __init__(self, ledger, *, clock=time.monotonic, utc=lambda: datetime.now(timezone.utc).timestamp(), session_id=None,
                 clock_origin=None):
        require(ledger.owned_lock is not None, "OWNED_LEDGER_REQUIRED_FOR_BUDGET")
        self.ledger, self.clock, self.utc = ledger, clock, utc
        self.epoch, self.file_sha = ledger.owned_lock, None
        self.poisoned = False
        self.path = Path(ledger.directory)/"BUDGET.json"
        self.session_id, self.prior_gpu_seconds = session_id, 0
        self.authorization_sha = self.complete = None
        self.m1 = ledger.continuation is not None
        if self.m1:
            self.path, self.complete, self.body = continuation_window_context(ledger, session_id)
            require(clock_origin == self.complete["clock_origin"], "M1_CLOCK_ORIGIN_CHANGED_NO_RESUME")
            require(self.body["active"] is None and not self.body["quarantined"]
                    and not self.body["window_closed"], "M1_UNCERTAIN_OR_CLOSED_WINDOW_NO_RESUME")
            self.authorization_sha = digest(_regular(self.path.parent / "COMPLETE.json"))
            self.file_sha = digest(_regular(self.path))
            self.prior_gpu_seconds = ledger.spec["prior_gpu_seconds"]
            caps = ledger.spec["windows"][session_id]
            # Whole owned lifetime (load + idle + inference) inside the window's wall horizon.
            self.GPU_SECONDS = self.LEASE_SECONDS = caps["gpu_seconds_cap"]
            self.SESSION_SECONDS = caps["wall_seconds_cap"]
            self.check()
            ledger._window_budget = self
            return
        if session_id is not None:
            self.path, self.complete, self.authorization_sha, old = approved_session_context(ledger.directory, session_id)
            self.prior_gpu_seconds = old["charged_gpu_seconds"]
            ledger.restrict_to_jobs(self.complete["approved_job_ids"])
        ledger.assert_owner()
        if self.path.exists():
            require(not self.path.is_symlink() and self.path.stat().st_size <= 1024**2, "BUDGET_FILE_INVALID")
            saved = json.loads(self.path.read_bytes())
            body = saved["body"]
            require(saved["sha256"] == digest(canonical(body)) and body["manifest"] == ledger.manifest_sha256, "BUDGET_IDENTITY_CHANGED")
            self.body = body
            self.file_sha = digest(self.path.read_bytes())
            require(body["active"] is None and not body["quarantined"], "UNCERTAIN_WORKER_BUDGET_QUARANTINED")
        else:
            require(session_id is None, "ACTIVATED_SESSION_BUDGET_REQUIRED_NO_RESET")
            require(not ledger.rows and not ledger.accounting()["budget_required"], "MISSING_PRIOR_BUDGET_NO_RESET")
            ledger.require_budget_file()
            self.body = {"manifest": ledger.manifest_sha256, "started_monotonic": self.clock(), "started_utc": self.utc(), "charged_gpu_seconds": 0, "lease_count": 0, "active": None, "quarantined": False}
            self.persist()
        self.check()

    def persist(self):
        self.assert_current()
        if self.m1:
            _m1_lifetime(self.body, self.ledger.spec["windows"][self.session_id])
            previous = json.loads(_regular(self.path))["body"]
            require(self.body["charged_gpu_seconds"] >= previous["charged_gpu_seconds"]
                    and self.body["lease_count"] >= previous["lease_count"], "M1_NO_REFUND_OR_LEASE_RESET")
        raw = canonical({"body":self.body,"sha256":digest(canonical(self.body))})
        pending = self.path.with_suffix(".pending")
        require(not pending.exists() and not pending.is_symlink(), "UNCERTAIN_BUDGET_WRITE_PRESERVED")
        try:
            with pending.open("xb") as out:
                require(out.write(raw) == len(raw), "PARTIAL_BUDGET_WRITE")
                out.flush()
                os.fsync(out.fileno())
            os.replace(pending, self.path)
            self.file_sha = digest(raw)
        except BaseException:
            self.poisoned = self.ledger.poisoned = True
            raise

    def assert_current(self):
        self.ledger.assert_owner()
        require(not self.poisoned and self.ledger.owned_lock == self.epoch, "STALE_OR_RELEASED_BUDGET_HANDLE")
        if self.file_sha is None:
            require(not self.path.exists(), "STALE_BUDGET_HANDLE")
        else:
            require(self.path.is_file() and not self.path.is_symlink()
                    and digest(self.path.read_bytes()) == self.file_sha, "STALE_BUDGET_HANDLE")
        if self.m1:
            _, complete, _ = continuation_window_context(self.ledger, self.session_id)
            require(digest(_regular(self.path.parent / "COMPLETE.json")) == self.authorization_sha
                    and all(self.body[key] == complete[key] for key in
                            ("started_monotonic", "started_utc", "clock_origin")),
                    "M1_WINDOW_OR_CLOCK_CHANGED")
        elif self.session_id is not None:
            require(not (self.ledger.directory / "SESSION_ACTIVATION.lock").exists()
                    and digest(_read_regular(self.path.parent / "COMPLETE.json")) == self.authorization_sha
                    and digest(_read_regular(self.ledger.directory / "BUDGET.json")) == self.complete["original_budget_sha256"]
                    and self.body["session_id"] == self.session_id
                    and self.body["authorization_sha256"] == self.authorization_sha
                    and all(self.body[key] == self.complete[key] for key in ("started_monotonic", "started_utc")),
                    "SESSION_ORIGINAL_HISTORY_OR_AUTHORIZATION_CHANGED")

    def check(self):
        self.assert_current()
        now, utc_now = self.clock(), self.utc()
        if self.m1:
            require(not self.body["window_closed"], "M1_WINDOW_CLOSED_NO_RENEWAL")
            if not (all(type(x) in (int, float) and math.isfinite(x) for x in (now, utc_now))
                    and now >= self.body["started_monotonic"] and utc_now >= self.body["started_utc"]):
                self.body["quarantined"] = True
                self.persist()
                raise RuntimeError("M1_CLOCK_ROLLBACK_OR_INVALID_QUARANTINED")
        require(all(type(x) in (int,float) and math.isfinite(x) for x in (now,utc_now)), "BUDGET_CLOCK_INVALID")
        require(now >= self.body["started_monotonic"] and utc_now >= self.body["started_utc"], "CLOCK_ROLLBACK_NO_AUTOMATIC_RESUME")
        require(now-self.body["started_monotonic"] < self.SESSION_SECONDS and utc_now-self.body["started_utc"] < self.SESSION_SECONDS, "WHOLE_BATCH_DEADLINE")
        require(not self.body["quarantined"] and self.body["charged_gpu_seconds"] <= self.GPU_SECONDS, "GPU_BUDGET_OR_CLEANUP_BLOCKED")
        active = self.body["active"]
        if active is not None:
            require(now <= active["deadline"], "OWNED_WORKER_LEASE_DEADLINE")
        return now

    def reserve_worker(self, lease_id):
        with self.ledger.lock:
            return self._reserve_worker(lease_id)

    def _reserve_worker(self, lease_id):
        now = self.check()
        if self.m1:
            require(self.body["lease_count"] == 0, "M1_NO_WORKER_RENEWAL_OR_SECOND_LEASE")
        require(self.body["active"] is None and self.body["charged_gpu_seconds"] + self.LEASE_SECONDS <= self.GPU_SECONDS, "NO_CONCURRENT_OR_UNFUNDED_GPU_WORKER")
        require(type(lease_id) is str and 1 <= len(lease_id) <= 100 and lease_id.isascii() and all(x.isalnum() or x in "_-" for x in lease_id), "BOUNDED_LEASE_ID_REQUIRED")
        # Keep45s within whole-session horizon for final parent/tunnel cleanup.
        remaining = min(self.SESSION_SECONDS-(now-self.body["started_monotonic"]),self.SESSION_SECONDS-(self.utc()-self.body["started_utc"]))-45
        require(remaining >= self.LEASE_SECONDS, "INSUFFICIENT_WHOLE_SESSION_CLEANUP_MARGIN")
        self.body["charged_gpu_seconds"] += self.LEASE_SECONDS
        self.body["lease_count"] += 1
        self.body["active"] = {"lease_id":lease_id,"started":now,"deadline":now+self.LEASE_SECONDS}
        self.persist()
        return self.body["active"]["deadline"]

    def confirm_stop(self, lease_id, *, cleanup_confirmed):
        with self.ledger.lock:
            self.assert_current()
            return self._confirm_stop(lease_id, cleanup_confirmed=cleanup_confirmed)

    def _confirm_stop(self, lease_id, *, cleanup_confirmed):
        active = self.body["active"]
        require(active is not None and active["lease_id"] == lease_id, "EXACT_OWNED_LEASE_REQUIRED")
        elapsed = self.clock()-active["started"]
        if cleanup_confirmed is not True or not 0 <= elapsed <= self.LEASE_SECONDS:
            if type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed > self.LEASE_SECONDS:
                self.body["charged_gpu_seconds"] += elapsed-self.LEASE_SECONDS
            self.body["quarantined"] = True
            self.persist()  # keep full conservative reservation and active ID
            raise RuntimeError("OWNED_WORKER_STOP_UNCONFIRMED_NO_REFUND")
        if self.m1:
            self.body["window_closed"] = True
        else:
            self.body["charged_gpu_seconds"] -= self.LEASE_SECONDS-elapsed
        self.body["active"] = None
        self.persist()

    def summary(self):
        result = {"gpu_seconds_conservatively_charged":self.body["charged_gpu_seconds"],"gpu_seconds_cap":self.GPU_SECONDS,"session_seconds_cap":self.SESSION_SECONDS,"active_lease":self.body["active"] is not None,"quarantined":self.body["quarantined"]}
        if self.session_id is not None:
            result.update(session_id=self.session_id, prior_gpu_seconds_preserved=self.prior_gpu_seconds,
                          aggregate_gpu_seconds=self.prior_gpu_seconds+self.body["charged_gpu_seconds"],
                          started_utc=self.body["started_utc"], started_monotonic=self.body["started_monotonic"])
        if self.m1:
            result.update(window_closed=self.body["window_closed"], refund_unused=False,
                          local_adoption_available=False, automatic_renewal=False)
        return result
