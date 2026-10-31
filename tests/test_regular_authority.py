"""Regular-service daily authority and fair scheduler: offline, injected clocks, no model or network."""

from datetime import datetime, timedelta, timezone
import hashlib
import importlib
from pathlib import Path
import sqlite3
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/model-server"))
ra = importlib.import_module("regular_authority")

LINEAGE = {"service_ledger": "534->540/540 frozen", "restricted_slots": 9, "m1_gpu_seconds": "18900/21600",
           "pre_m1_gpu_seconds": 17002.874}
RTX = ra.APPROVED_GPU


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


class FakeClock:
    def __init__(self, utc):
        self.now, self.mono, self.boot = utc, 1000.0, "boot-1"

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)
        self.mono += seconds

    def clock(self):
        clock = ra.Clock(utc=lambda: self.now, monotonic=lambda: self.mono)
        clock.boot_id = self.boot
        return clock


def bangkok(day, hhmm):
    hour, minute = (int(part) for part in hhmm.split(":"))
    return datetime.fromisoformat(day).replace(hour=hour, minute=minute, tzinfo=ra.BANGKOK).astimezone(timezone.utc)


@pytest.fixture
def rig(tmp_path):
    fake = FakeClock(bangkok("2026-11-02", "09:00"))
    path = tmp_path / "authority.sqlite3"

    def open_authority():
        return ra.Authority(path, config=ra.ServiceConfig(), clock=fake.clock(), lineage=LINEAGE)
    return fake, path, open_authority


def submit(authority, workstation, image, *, kind="grader", key=None, model="retfound-aptos5", modality="CFP"):
    if kind == "prism":
        model = "prism-dr-5fold"
    return authority.submit(principal="shared", workstation=workstation, idempotency_key=key or f"{workstation}-{image}-{kind}",
                            request_digest=digest(f"{workstation}{image}{kind}"), kind=kind, model_id=model,
                            modality=modality, source_sha256=digest(image))


def admit(authority, ticket):
    return authority.admit(ticket["ticket_id"], principal="shared", workstation=ticket["workstation"],
                           model_id=ticket["model_id"], modality=ticket["modality"],
                           source_sha256=ticket["source_sha256"], request_digest=ticket["request_digest"])


def test_only_the_approved_policy_and_rtx_are_accepted():
    for change in ({"daily_invocations": 1501}, {"daily_gpu_seconds": 50000}, {"ai_close": "23:00"},
                   {"gpu_uuid": ra.EXCLUDED_GPU}, {"max_running": 2}, {"max_active": 6}):
        with pytest.raises(ra.AuthorityError, match="APPROVED_SERVICE_POLICY_ONLY"):
            ra.ServiceConfig(**change)


def test_thai_day_turns_at_17_utc():
    assert ra.thai_day(datetime(2026, 11, 2, 16, 59, 59, tzinfo=timezone.utc)) == "2026-11-02"
    assert ra.thai_day(datetime(2026, 11, 2, 17, 0, 0, tzinfo=timezone.utc)) == "2026-11-03"
    with pytest.raises(ra.AuthorityError):
        ra.thai_day(datetime(2026, 11, 2, 17, 0))


def test_a_new_authority_needs_lineage_and_a_changed_policy_needs_a_new_record(tmp_path):
    fake = FakeClock(bangkok("2026-11-02", "09:00"))
    clock = ra.Clock(lambda: fake.now, lambda: fake.mono, fake.boot)
    with pytest.raises(ra.AuthorityError, match="HISTORICAL_LINEAGE"):
        ra.Authority(tmp_path / "a.sqlite3", config=ra.ServiceConfig(), clock=clock)
    ra.Authority(tmp_path / "b.sqlite3", config=ra.ServiceConfig(), clock=clock, lineage=LINEAGE)
    with pytest.raises(ra.AuthorityError, match="CONFIGURATION_CHANGED"):
        ra.Authority(tmp_path / "b.sqlite3", config=ra.ServiceConfig(segment_seconds=600), clock=clock)


def test_submission_is_idempotent_and_a_reused_key_with_another_request_is_refused(rig):
    _, _, open_authority = rig
    authority = open_authority()
    first = submit(authority, "ws1", "img1")
    assert submit(authority, "ws1", "img1")["ticket_id"] == first["ticket_id"]
    with pytest.raises(ra.AuthorityError, match="IDEMPOTENCY_KEY_REUSED"):
        authority.submit(principal="shared", workstation="ws1", idempotency_key="ws1-img1-grader",
                         request_digest=digest("other"), kind="grader", model_id="retfound-aptos5",
                         modality="CFP", source_sha256=digest("img1"))
    with pytest.raises(ra.AuthorityError, match="UNSUPPORTED_STAGE"):
        submit(authority, "ws1", "img2", model="retfound-aptos5", modality="UWF")


def test_nothing_is_promoted_outside_ai_hours_or_after_the_last_admission_time(rig):
    fake, _, open_authority = rig
    fake.now = bangkok("2026-11-02", "05:59")
    authority = open_authority()
    submit(authority, "ws1", "img1")
    assert authority.schedule() == []
    status = authority.status()
    assert status["ai_open"] is False and status["next_ai_opening_utc"] == bangkok("2026-11-02", "06:00").isoformat()
    fake.advance(60)
    assert len(authority.schedule()) == 1
    fake.now = bangkok("2026-11-02", "21:55")
    fake.mono += 15 * 3600 + 55 * 60  # Same boot: monotonic follows the wall clock.
    submit(authority, "ws2", "img2")
    assert authority.schedule() == []


def test_fair_round_robin_one_stage_per_workstation_and_five_active(rig):
    _, _, open_authority = rig
    authority = open_authority()
    for image in range(3):
        submit(authority, "ws-a", f"a{image}")
    submit(authority, "ws-b", "b0")
    promoted = authority.schedule()
    assert len(promoted) == 2  # ws-a's second and third images wait for ws-a's first.
    for workstation in ("ws-c", "ws-d", "ws-e", "ws-f"):
        submit(authority, workstation, "x" + workstation)
    assert len(authority.schedule()) == 3  # Five active at most.
    assert authority.status()["ready"] == 5 and authority.status()["queued"] == 3


def test_admission_turns_the_hold_into_a_durable_intent_once_and_runs_one_at_a_time(rig):
    _, _, open_authority = rig
    authority = open_authority()
    a = submit(authority, "ws-a", "img-a")
    b = submit(authority, "ws-b", "img-b")
    authority.schedule()
    intent = admit(authority, a)
    with pytest.raises(ra.AuthorityError, match="NO_SECOND_DISPATCH"):
        admit(authority, a)
    with pytest.raises(ra.AuthorityError, match="ONE_MODEL_STAGE_RUNS_AT_A_TIME"):
        admit(authority, b)
    authority.db.close()
    reopened = open_authority()
    row = reopened.db.execute("SELECT * FROM intents WHERE intent_id = ?", (intent["intent_id"],)).fetchone()
    assert row is not None and row["outcome"] is None  # Durable before any forwarding.
    assert reopened.capacity()["invocations_used"] == 1 and reopened.capacity()["invocations_held"] == 3


def test_a_request_that_does_not_match_its_ticket_is_refused(rig):
    _, _, open_authority = rig
    authority = open_authority()
    ticket = submit(authority, "ws-a", "img-a")
    authority.schedule()
    with pytest.raises(ra.AuthorityError, match="REQUEST_DOES_NOT_MATCH_TICKET"):
        authority.admit(ticket["ticket_id"], principal="shared", workstation="ws-a", model_id="retfound-aptos5",
                        modality="CFP", source_sha256=digest("another image"),
                        request_digest=ticket["request_digest"])
    with pytest.raises(ra.AuthorityError, match="TICKET_NOT_FOUND"):
        authority.admit(ticket["ticket_id"], principal="shared", workstation="ws-b", model_id="retfound-aptos5",
                        modality="CFP", source_sha256=ticket["source_sha256"],
                        request_digest=ticket["request_digest"])


def test_prism_uses_the_second_slot_of_the_grader_pair_hold(rig):
    _, _, open_authority = rig
    authority = open_authority()
    grader = submit(authority, "ws-a", "img-a")
    authority.schedule()
    admit(authority, grader)
    authority.finish(grader["ticket_id"], outcome="DONE")
    prism = submit(authority, "ws-a", "img-a", kind="prism")
    authority.schedule()
    assert authority.get(prism["ticket_id"], principal="shared")["hold_id"] == \
        authority.get(grader["ticket_id"], principal="shared")["hold_id"]
    admit(authority, prism)
    authority.finish(prism["ticket_id"], outcome="DONE")
    assert authority.capacity()["invocations_used"] == 2 and authority.capacity()["invocations_held"] == 0


def test_the_daily_invocation_cap_holds_with_pairs(rig):
    fake, _, open_authority = rig
    authority = open_authority()
    day = ra.thai_day(fake.now)
    rows = [(f"int_{n}", f"tkt_old_{n}", day, "hold_old", "shared", "ws-z", "retfound-aptos5", digest(str(n)),
             fake.now.isoformat(), "DONE", fake.now.isoformat()) for n in range(1499)]
    authority.db.executemany("INSERT INTO intents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    grader = submit(authority, "ws-a", "img-a")
    assert authority.schedule() == []
    assert authority.get(grader["ticket_id"], principal="shared")["last_reason"] == "DAILY_INVOCATIONS_EXHAUSTED"
    prism = submit(authority, "ws-b", "img-b", kind="prism")
    assert authority.schedule() == [prism["ticket_id"]]
    admit(authority, prism)
    assert authority.capacity()["invocations_available"] == 0
    # The next Thai day has its own allowance; nothing is borrowed or carried.
    fake.now = bangkok("2026-11-03", "06:00")
    fake.boot = "boot-2"
    authority.db.close()
    authority = open_authority()
    assert authority.capacity()["invocations_used"] == 0


def test_an_expired_dispatch_window_and_a_cancel_release_only_unused_slots(rig):
    fake, _, open_authority = rig
    authority = open_authority()
    a = submit(authority, "ws-a", "img-a")
    b = submit(authority, "ws-b", "img-b")
    authority.schedule()
    fake.advance(61)
    authority.schedule()
    assert authority.get(a["ticket_id"], principal="shared")["state"] == "EXPIRED"
    c = submit(authority, "ws-c", "img-c")
    authority.schedule()
    admit(authority, c)
    with pytest.raises(ra.AuthorityError, match="CANCEL_IS_NOT_PROOF"):
        authority.cancel(c["ticket_id"], principal="shared")
    assert authority.get(b["ticket_id"], principal="shared")["state"] == "EXPIRED"
    assert authority.capacity()["invocations_used"] == 1 and authority.capacity()["invocations_held"] == 1
    d = submit(authority, "ws-d", "img-d")
    assert authority.cancel(d["ticket_id"], principal="shared")["state"] == "CANCELLED"


def test_removing_an_image_releases_its_unused_prism_slot(rig):
    _, _, open_authority = rig
    authority = open_authority()
    grader = submit(authority, "ws-a", "img-a")
    authority.schedule()
    admit(authority, grader)
    with pytest.raises(ra.AuthorityError, match="CANCEL_FIRST"):
        authority.release_image(principal="shared", workstation="ws-a", pair_key=digest("img-a"))
    authority.finish(grader["ticket_id"], outcome="FAILED", reason="REMOTE_HTTP_ERROR")
    assert authority.release_image(principal="shared", workstation="ws-a", pair_key=digest("img-a")) == 1
    assert authority.capacity()["invocations_used"] == 1 and authority.capacity()["invocations_held"] == 0


def test_an_unknown_outcome_quarantines_until_an_operator_reconciles_with_evidence(rig):
    _, _, open_authority = rig
    authority = open_authority()
    ticket = submit(authority, "ws-a", "img-a")
    authority.schedule()
    admit(authority, ticket)
    authority.finish(ticket["ticket_id"], outcome="UNKNOWN", reason="REMOTE_TIMEOUT")
    assert authority.status()["quarantined"] is True
    with pytest.raises(ra.AuthorityError, match="QUARANTINED"):
        submit(authority, "ws-b", "img-b")
    with pytest.raises(ra.AuthorityError, match="QUARANTINED"):
        authority.fund_segment(epoch="e1", gpu_uuid=RTX)
    with pytest.raises(ra.AuthorityError, match="RECONCILIATION_EVIDENCE_REQUIRED"):
        authority.reconcile(reason="checked", evidence_sha256="not-a-hash")
    authority.reconcile(reason="host log shows no result was written", evidence_sha256=digest("evidence"))
    assert authority.status()["quarantined"] is False
    assert authority.capacity()["invocations_used"] == 1  # Never refunded.


def test_gpu_segments_do_not_overlap_stop_at_close_and_respect_the_daily_cap(rig):
    fake, _, open_authority = rig
    authority = open_authority()
    with pytest.raises(ra.AuthorityError, match="APPROVED_RTX_UUID_ONLY"):
        authority.fund_segment(epoch="e1", gpu_uuid=ra.EXCLUDED_GPU)
    first = authority.fund_segment(epoch="e1", gpu_uuid=RTX)
    second = authority.fund_segment(epoch="e1", gpu_uuid=RTX)
    assert first["seconds"] == 300 and second["start_utc"] == first["end_utc"]
    assert authority.capacity()["gpu_seconds_reserved"] == 600
    fake.now = bangkok("2026-11-02", "21:58")
    fake.mono += (fake.now - bangkok("2026-11-02", "09:00")).total_seconds()
    late = authority.fund_segment(epoch="e2", gpu_uuid=RTX)
    assert late["end_utc"] == bangkok("2026-11-02", "22:00").isoformat() and late["seconds"] == 120
    fake.now = bangkok("2026-11-03", "07:00")
    fake.boot = "boot-2"
    authority.db.close()
    authority = open_authority()
    authority.db.execute("INSERT INTO gpu_segments VALUES ('seg_old', '2026-11-03', 'e0', 'FUNDED', ?, ?, 43000, ?)",
                         (fake.now.isoformat(), fake.now.isoformat(), fake.now.isoformat()))
    with pytest.raises(ra.AuthorityError, match="DAILY_GPU_SECONDS_EXHAUSTED"):
        authority.fund_segment(epoch="e3", gpu_uuid=RTX)


def test_a_gpu_overrun_is_charged_and_quarantines(rig):
    _, _, open_authority = rig
    authority = open_authority()
    authority.record_overrun(epoch="e1", seconds=12.2)
    assert authority.capacity()["gpu_seconds_reserved"] == 13 and authority.status()["quarantined"] is True


def test_clock_rollback_quarantine_is_durable_and_survives_restart(rig):
    fake, _, open_authority = rig
    authority = open_authority()
    fake.now -= timedelta(minutes=10)
    with pytest.raises(ra.AuthorityError, match="CLOCK_ROLLBACK_QUARANTINED"):
        submit(authority, "ws-a", "img-a")
    authority.db.close()
    fake.boot = "boot-2"
    with pytest.raises(ra.AuthorityError, match="CLOCK_ROLLBACK"):
        open_authority()


def test_a_wall_clock_jump_within_one_boot_quarantines(rig):
    fake, _, open_authority = rig
    authority = open_authority()
    fake.now += timedelta(hours=2)  # Wall clock moved; monotonic did not.
    with pytest.raises(ra.AuthorityError, match="CLOCK_JUMP_QUARANTINED"):
        submit(authority, "ws-a", "img-a")
    assert authority.status()["quarantined"] is True
    authority.reconcile(reason="NTP correction confirmed", evidence_sha256=digest("ntp"))
    submit(authority, "ws-a", "img-a")


def test_a_damaged_audit_chain_fails_closed(rig):
    _, path, open_authority = rig
    authority = open_authority()
    submit(authority, "ws-a", "img-a")
    authority.db.close()
    with sqlite3.connect(path) as raw:
        raw.execute("UPDATE events SET body = '{\"edited\":true}' WHERE seq = 2")
    with pytest.raises(ra.AuthorityError, match="AUDIT_CHAIN_DAMAGED"):
        open_authority()


def test_status_shows_only_the_callers_own_tickets(rig):
    _, _, open_authority = rig
    authority = open_authority()
    submit(authority, "ws-a", "img-a")
    submit(authority, "ws-b", "img-b")
    own = authority.status(principal="shared", workstation="ws-a")["own_open_tickets"]
    assert len(own) == 1 and set(own[0]) == {"ticket_id", "kind", "model_id", "modality", "state", "last_reason",
                                              "ready_deadline_utc"}
    with pytest.raises(ra.AuthorityError, match="TICKET_NOT_FOUND"):
        authority.get(own[0]["ticket_id"], principal="someone-else")


def test_the_module_has_no_network_model_or_gpu_imports():
    source = (ROOT / "scripts/model-server/regular_authority.py").read_text(encoding="utf-8")
    for forbidden in ("import torch", "import httpx", "import requests", "import socket", "subprocess", "urllib"):
        assert forbidden not in source


def test_an_arrived_call_waits_its_turn_and_a_refused_one_gives_back_its_slot(rig):
    fake, _, open_authority = rig
    authority = open_authority()
    a = submit(authority, "ws-a", "img-a")
    b = submit(authority, "ws-b", "img-b")
    authority.schedule()
    admit(authority, a)
    authority.mark_arrived(b["ticket_id"], principal="shared", workstation="ws-b")
    fake.advance(90)  # Past b's dispatch window while a runs.
    authority.schedule()
    assert authority.get(b["ticket_id"], principal="shared")["state"] == "READY"
    authority.finish(a["ticket_id"], outcome="DONE")
    admit(authority, b)
    with pytest.raises(ra.AuthorityError, match="TICKET_ALREADY_ADMITTED"):
        authority.abandon(b["ticket_id"], reason="REFUSED_BEFORE_ADMISSION")
    authority.finish(b["ticket_id"], outcome="DONE")
    c = submit(authority, "ws-c", "img-c")
    authority.schedule()
    authority.mark_arrived(c["ticket_id"], principal="shared", workstation="ws-c")
    authority.abandon(c["ticket_id"], reason="REFUSED_BEFORE_ADMISSION")
    assert authority.get(c["ticket_id"], principal="shared")["state"] == "EXPIRED"
    assert authority.capacity()["invocations_used"] == 2 and authority.capacity()["invocations_held"] == 2


def test_grader_and_prism_with_different_stage_digests_share_the_image_pair_hold(rig):
    _, _, open_authority = rig
    authority = open_authority()
    image = digest("case-source")
    grader = authority.submit(principal="shared", workstation="ws-a", idempotency_key="g",
                              request_digest=digest("g"), kind="grader", model_id="uspec-uwf-grading",
                              modality="UWF", source_sha256=digest("analysis-bytes"), pair_key=image)
    authority.schedule()
    admit(authority, grader)
    authority.finish(grader["ticket_id"], outcome="DONE")
    prism = authority.submit(principal="shared", workstation="ws-a", idempotency_key="p",
                             request_digest=digest("p"), kind="prism", model_id="prism-dr-5fold",
                             modality="UWF", source_sha256=image, pair_key=image)
    authority.schedule()
    assert authority.get(prism["ticket_id"], principal="shared")["hold_id"] == \
        authority.get(grader["ticket_id"], principal="shared")["hold_id"]
