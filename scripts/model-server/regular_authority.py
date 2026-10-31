"""Regular-service daily authority and fair scheduler (owner-approved 2026-10-31).

One SQLite database written only by the control service on dr-train. It holds the
daily model-invocation and GPU-reservation allowances, pair holds, durable
intents, tickets for the fair scheduler and a hash-chained audit trail. See
docs/milestone/m1/M1_REGULAR_SERVICE_DESIGN.md. It never reads an old finite
accounting directory for allowance and never writes one; the historical lineage
is recorded as evidence only.

Pure standard library: no model, network, GPU or credential access. Every
mutation runs in one ``BEGIN IMMEDIATE`` transaction with ``synchronous=FULL``,
so an intent is durable before its call is forwarded.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid

# Asia/Bangkok has been UTC+07:00 without daylight saving since 1920; a fixed offset avoids
# depending on a tz database on the host. Thai midnight is 17:00 UTC of the previous UTC day.
BANGKOK = timezone(timedelta(hours=7), "Asia/Bangkok")
SCHEMA = "dr-regular-authority.v1"
APPROVED_GPU = "GPU-044a8b11-4729-458b-a07b-297e45439419"
EXCLUDED_GPU = "GPU-277ccc57-c3e5-0731-cd49-f4f8695f7089"
TICKET_STATES = {"QUEUED", "READY", "ADMITTED", "DONE", "FAILED", "UNKNOWN", "CANCELLED", "EXPIRED"}
ACTIVE = ("READY", "ADMITTED")
OPEN = ("QUEUED", "READY", "ADMITTED")
KINDS = {"grader": {("retfound-aptos5", "CFP"), ("uspec-uwf-grading", "UWF")},
         "prism": {("prism-dr-5fold", "CFP"), ("prism-dr-5fold", "UWF")}}
SHA = re.compile(r"[a-f0-9]{64}")
NAME = re.compile(r"[A-Za-z0-9_.:-]{1,120}")


class AuthorityError(RuntimeError):
    """Fixed, secret-free refusal codes only."""


def require(condition, code):
    if not condition:
        raise AuthorityError(code)


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class ServiceConfig:
    """Approved, immutable policy. Never taken from a client request."""
    daily_invocations: int = 1500
    daily_gpu_seconds: int = 43200
    ai_open: str = "06:00"
    ai_close: str = "22:00"            # exclusive
    last_admission: str = "21:55"      # bounded drain margin before close
    gpu_uuid: str = APPROVED_GPU
    segment_seconds: int = 300
    idle_seconds: int = 300
    dispatch_window_seconds: int = 60
    max_active: int = 5
    max_running: int = 1
    max_per_workstation: int = 1
    clock_jump_tolerance_seconds: int = 300

    def __post_init__(self):
        require(self.daily_invocations == 1500 and self.daily_gpu_seconds == 43200
                and (self.ai_open, self.ai_close) == ("06:00", "22:00")
                and self.gpu_uuid == APPROVED_GPU and self.gpu_uuid != EXCLUDED_GPU
                and self.max_active == 5 and self.max_running == 1 and self.max_per_workstation == 1,
                "APPROVED_SERVICE_POLICY_ONLY")
        require(0 < self.segment_seconds <= 2700 and 0 < self.idle_seconds <= 2700
                and 0 < self.dispatch_window_seconds <= 300, "BOUNDED_INTERVALS_REQUIRED")

    def digest(self) -> str:
        return sha(canonical(asdict(self)))


def thai_day(moment: datetime) -> str:
    require(moment.tzinfo is not None, "AWARE_UTC_TIME_REQUIRED")
    return moment.astimezone(BANGKOK).date().isoformat()


def _at(day: str, hhmm: str) -> datetime:
    hour, minute = (int(part) for part in hhmm.split(":"))
    return datetime.fromisoformat(day).replace(hour=hour, minute=minute, tzinfo=BANGKOK)


def ai_window(moment: datetime, config: ServiceConfig) -> tuple[datetime, datetime, datetime]:
    """Opening, last-admission and closing instants for the Thai day containing ``moment``."""
    day = thai_day(moment)
    return _at(day, config.ai_open), _at(day, config.last_admission), _at(day, config.ai_close)


def next_ai_opening(moment: datetime, config: ServiceConfig) -> datetime:
    opening, _, _ = ai_window(moment, config)
    if moment < opening:
        return opening
    return _at((moment.astimezone(BANGKOK).date() + timedelta(days=1)).isoformat(), config.ai_open)


@dataclass
class Clock:
    """Injected clocks. ``boot_id`` identifies one host boot; monotonic values compare only within it."""
    utc: callable
    monotonic: callable
    boot_id: str = field(default="")


DDL = """
CREATE TABLE IF NOT EXISTS authority (
  id INTEGER PRIMARY KEY CHECK (id = 1), schema TEXT NOT NULL, config_json TEXT NOT NULL,
  config_digest TEXT NOT NULL, lineage_json TEXT NOT NULL, created_utc TEXT NOT NULL,
  revoked_utc TEXT, quarantine TEXT);
CREATE TABLE IF NOT EXISTS clock_highwater (
  id INTEGER PRIMARY KEY CHECK (id = 1), utc TEXT NOT NULL, boot_id TEXT NOT NULL, monotonic REAL NOT NULL);
CREATE TABLE IF NOT EXISTS holds (
  hold_id TEXT PRIMARY KEY, day TEXT NOT NULL, principal TEXT NOT NULL, workstation TEXT NOT NULL,
  source_sha256 TEXT NOT NULL, slots_total INTEGER NOT NULL CHECK (slots_total IN (1, 2)),
  slots_used INTEGER NOT NULL DEFAULT 0, slots_released INTEGER NOT NULL DEFAULT 0, created_utc TEXT NOT NULL,
  CHECK (slots_used + slots_released <= slots_total));
CREATE TABLE IF NOT EXISTS tickets (
  ticket_id TEXT PRIMARY KEY, principal TEXT NOT NULL, workstation TEXT NOT NULL,
  idempotency_key TEXT NOT NULL, request_digest TEXT NOT NULL, kind TEXT NOT NULL, model_id TEXT NOT NULL,
  modality TEXT NOT NULL, source_sha256 TEXT NOT NULL, state TEXT NOT NULL, hold_id TEXT,
  created_utc TEXT NOT NULL, updated_utc TEXT NOT NULL, ready_deadline_utc TEXT, last_reason TEXT,
  UNIQUE (principal, idempotency_key));
CREATE TABLE IF NOT EXISTS intents (
  intent_id TEXT PRIMARY KEY, ticket_id TEXT NOT NULL UNIQUE, day TEXT NOT NULL, hold_id TEXT NOT NULL,
  principal TEXT NOT NULL, workstation TEXT NOT NULL, model_id TEXT NOT NULL, request_digest TEXT NOT NULL,
  admitted_utc TEXT NOT NULL, outcome TEXT, finished_utc TEXT);
CREATE TABLE IF NOT EXISTS gpu_segments (
  segment_id TEXT PRIMARY KEY, day TEXT NOT NULL, epoch TEXT NOT NULL, kind TEXT NOT NULL,
  start_utc TEXT NOT NULL, end_utc TEXT NOT NULL, seconds INTEGER NOT NULL CHECK (seconds > 0),
  created_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS served (workstation TEXT PRIMARY KEY, last_served_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY, utc TEXT NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL,
  previous TEXT NOT NULL, hash TEXT NOT NULL);
"""


class Authority:
    """The only writer of the regular-service accounting database."""

    def __init__(self, path, *, config: ServiceConfig, clock: Clock, lineage: dict | None = None):
        self.path, self.config, self.clock = Path(path), config, clock
        self.db = sqlite3.connect(self.path, isolation_level=None, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(DDL)  # Idempotent CREATE IF NOT EXISTS in autocommit mode.
        with self._tx() as now:
            row = self.db.execute("SELECT * FROM authority WHERE id = 1").fetchone()
            if row is None:
                require(isinstance(lineage, dict) and lineage, "HISTORICAL_LINEAGE_EVIDENCE_REQUIRED")
                self.db.execute("INSERT INTO authority VALUES (1, ?, ?, ?, ?, ?, NULL, NULL)",
                                (SCHEMA, canonical(asdict(config)).decode(), config.digest(),
                                 canonical(lineage).decode(), now.isoformat()))
                self._event(now, "AUTHORITY_CREATED", {"config_digest": config.digest(),
                                                       "lineage_sha256": sha(canonical(lineage))})
            else:
                require(row["schema"] == SCHEMA and row["config_digest"] == config.digest(),
                        "AUTHORITY_CONFIGURATION_CHANGED_NEW_RECORD_REQUIRED")
        self.verify_chain()

    # ------------------------------------------------------------------ plumbing

    class _Transaction:
        def __init__(self, authority, rebaseline):
            self.authority, self.rebaseline = authority, rebaseline

        def __enter__(self):
            self.authority.db.execute("BEGIN IMMEDIATE")
            try:
                return self.authority._observe_clock(self.rebaseline)
            except BaseException as error:
                self.__exit__(type(error), error, None)
                raise

        def __exit__(self, kind, value, trace):
            # A clock quarantine is itself durable even though the operation is refused.
            if kind is None or (kind is AuthorityError and str(value).startswith("CLOCK_")):
                self.authority.db.execute("COMMIT")
            else:
                self.authority.db.execute("ROLLBACK")
            return False

    def _tx(self, rebaseline=False):
        return Authority._Transaction(self, rebaseline)

    def _observe_clock(self, rebaseline=False) -> datetime:
        """High-water UTC plus same-boot monotonic agreement; violations quarantine durably.

        Only an explicit operator reconciliation re-baselines the high-water mark."""
        now = self.clock.utc()
        require(isinstance(now, datetime) and now.tzinfo is not None, "AWARE_UTC_TIME_REQUIRED")
        now = now.astimezone(timezone.utc)
        mono = float(self.clock.monotonic())
        last = self.db.execute("SELECT * FROM clock_highwater WHERE id = 1").fetchone()
        if last is None:
            self.db.execute("INSERT INTO clock_highwater VALUES (1, ?, ?, ?)",
                            (now.isoformat(), self.clock.boot_id, mono))
            return now
        if not rebaseline:
            previous = datetime.fromisoformat(last["utc"])
            if now < previous - timedelta(seconds=2):
                self._quarantine(now, "CLOCK_ROLLBACK")
                raise AuthorityError("CLOCK_ROLLBACK_QUARANTINED")
            if last["boot_id"] == self.clock.boot_id:
                drift = abs((now - previous).total_seconds() - (mono - last["monotonic"]))
                if drift > self.config.clock_jump_tolerance_seconds:
                    self._quarantine(now, "CLOCK_JUMP")
                    raise AuthorityError("CLOCK_JUMP_QUARANTINED")
            if now <= previous:
                return now
        self.db.execute("UPDATE clock_highwater SET utc = ?, boot_id = ?, monotonic = ? WHERE id = 1",
                        (now.isoformat(), self.clock.boot_id, mono))
        return now

    def _quarantine(self, now, reason):
        row = self.db.execute("SELECT quarantine FROM authority WHERE id = 1").fetchone()
        if row is not None and row["quarantine"] is None:  # The first reason is kept until reconciled.
            self.db.execute("UPDATE authority SET quarantine = ? WHERE id = 1", (reason,))
            self._event(now, "QUARANTINED", {"reason": reason})

    def _event(self, now, kind, body):
        last = self.db.execute("SELECT seq, hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        previous = last["hash"] if last else "0" * 64
        seq = (last["seq"] + 1) if last else 1
        row = {"seq": seq, "utc": now.isoformat(), "kind": kind, "body": body, "previous": previous}
        self.db.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)",
                        (seq, row["utc"], kind, canonical(body).decode(), previous, sha(canonical(row))))

    def verify_chain(self):
        previous = "0" * 64
        for seq, row in enumerate(self.db.execute("SELECT * FROM events ORDER BY seq"), 1):
            body = json.loads(row["body"])
            expected = sha(canonical({"seq": row["seq"], "utc": row["utc"], "kind": row["kind"],
                                      "body": body, "previous": previous}))
            require(row["seq"] == seq and row["previous"] == previous and row["hash"] == expected,
                    "AUDIT_CHAIN_DAMAGED_FAIL_CLOSED")
            previous = row["hash"]

    def _state(self):
        return self.db.execute("SELECT * FROM authority WHERE id = 1").fetchone()

    def _require_admissible(self, now):
        state = self._state()
        require(state["revoked_utc"] is None, "AUTHORITY_REVOKED")
        require(state["quarantine"] is None, "AUTHORITY_QUARANTINED_RECONCILE_FIRST")

    # ------------------------------------------------------------------ capacity

    def _usage(self, day):
        used = self.db.execute("SELECT COUNT(*) FROM intents WHERE day = ?", (day,)).fetchone()[0]
        held = self.db.execute("SELECT COALESCE(SUM(slots_total - slots_used - slots_released), 0) "
                               "FROM holds WHERE day = ?", (day,)).fetchone()[0]
        gpu = self.db.execute("SELECT COALESCE(SUM(seconds), 0) FROM gpu_segments WHERE day = ?",
                              (day,)).fetchone()[0]
        return used, held, gpu

    def capacity(self, now=None) -> dict:
        now = now or self.clock.utc()
        day = thai_day(now)
        used, held, gpu = self._usage(day)
        return {"day": day, "timezone": "Asia/Bangkok", "invocations_used": used, "invocations_held": held,
                "invocations_available": self.config.daily_invocations - used - held,
                "invocations_cap": self.config.daily_invocations, "gpu_seconds_reserved": gpu,
                "gpu_seconds_available": self.config.daily_gpu_seconds - gpu,
                "gpu_seconds_cap": self.config.daily_gpu_seconds}

    def _hold(self, now, ticket, slots):
        day = thai_day(now)
        used, held, _ = self._usage(day)
        if used + held + slots > self.config.daily_invocations:
            return None
        hold_id = "hold_" + uuid.uuid4().hex
        self.db.execute("INSERT INTO holds VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?)",
                        (hold_id, day, ticket["principal"], ticket["workstation"], ticket["source_sha256"],
                         slots, now.isoformat()))
        self._event(now, "HOLD", {"hold_id": hold_id, "day": day, "slots": slots, "ticket_id": ticket["ticket_id"]})
        return hold_id

    def _usable_hold(self, now, ticket):
        """Today's unconsumed slot for this image (a grader pair hold covers its PRISM stage)."""
        row = self.db.execute(
            "SELECT hold_id FROM holds WHERE day = ? AND principal = ? AND workstation = ? AND source_sha256 = ? "
            "AND slots_total - slots_used - slots_released > 0 AND hold_id NOT IN "
            "(SELECT hold_id FROM tickets WHERE state IN ('QUEUED','READY') AND hold_id IS NOT NULL "
            " AND ticket_id != ?) ORDER BY created_utc LIMIT 1",
            (thai_day(now), ticket["principal"], ticket["workstation"], ticket["source_sha256"],
             ticket["ticket_id"])).fetchone()
        return row["hold_id"] if row else None

    def _release(self, now, hold_id, slots, reason):
        if hold_id is None or slots <= 0:
            return
        row = self.db.execute("SELECT * FROM holds WHERE hold_id = ?", (hold_id,)).fetchone()
        free = row["slots_total"] - row["slots_used"] - row["slots_released"]
        slots = min(slots, free)
        if slots > 0:
            self.db.execute("UPDATE holds SET slots_released = slots_released + ? WHERE hold_id = ?", (slots, hold_id))
            self._event(now, "HOLD_RELEASED", {"hold_id": hold_id, "slots": slots, "reason": reason})

    # ------------------------------------------------------------------ tickets

    def submit(self, *, principal, workstation, idempotency_key, request_digest, kind, model_id, modality,
               source_sha256) -> dict:
        """Durable ticket. Same key and digest returns the existing ticket; a changed digest is refused."""
        require(all(isinstance(value, str) and NAME.fullmatch(value)
                    for value in (principal, workstation, idempotency_key)), "TICKET_IDENTITY_INVALID")
        require(SHA.fullmatch(str(request_digest)) and SHA.fullmatch(str(source_sha256)), "TICKET_DIGEST_INVALID")
        require(kind in KINDS and (model_id, modality) in KINDS[kind], "UNSUPPORTED_STAGE_MODEL_MODALITY")
        with self._tx() as now:
            existing = self.db.execute("SELECT * FROM tickets WHERE principal = ? AND idempotency_key = ?",
                                       (principal, idempotency_key)).fetchone()
            if existing is not None:
                require(existing["request_digest"] == request_digest and existing["kind"] == kind,
                        "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST")
                return dict(existing)
            self._require_admissible(now)
            ticket_id = "tkt_" + uuid.uuid4().hex
            self.db.execute("INSERT INTO tickets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'QUEUED', NULL, ?, ?, NULL, NULL)",
                            (ticket_id, principal, workstation, idempotency_key, request_digest, kind, model_id,
                             modality, source_sha256, now.isoformat(), now.isoformat()))
            self._event(now, "TICKET", {"ticket_id": ticket_id, "workstation": workstation, "kind": kind,
                                        "model_id": model_id})
            return dict(self.db.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone())

    def get(self, ticket_id, *, principal) -> dict:
        row = self.db.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
        require(row is not None and row["principal"] == principal, "TICKET_NOT_FOUND")
        return dict(row)

    def _set(self, now, ticket_id, state, reason=None, **fields):
        require(state in TICKET_STATES, "TICKET_STATE_INVALID")
        assignments = ", ".join(f"{name} = ?" for name in fields)
        values = list(fields.values())
        self.db.execute(f"UPDATE tickets SET state = ?, updated_utc = ?, last_reason = ?"
                        f"{', ' + assignments if assignments else ''} WHERE ticket_id = ?",
                        [state, now.isoformat(), reason, *values, ticket_id])
        self._event(now, "TICKET_" + state, {"ticket_id": ticket_id, "reason": reason})

    def schedule(self) -> list[str]:
        """Expire stale dispatch windows, then promote fairly. Returns newly READY ticket IDs."""
        promoted = []
        with self._tx() as now:
            for row in self.db.execute("SELECT ticket_id, hold_id, kind FROM tickets WHERE state = 'READY' "
                                       "AND ready_deadline_utc < ?", (now.isoformat(),)).fetchall():
                self._release(now, row["hold_id"], 2 if row["kind"] == "grader" else 1, "DISPATCH_WINDOW_EXPIRED")
                self._set(now, row["ticket_id"], "EXPIRED", "DISPATCH_WINDOW_EXPIRED")
            state = self._state()
            _, last_admission, _ = ai_window(now, self.config)
            opening, _, _ = ai_window(now, self.config)
            if state["revoked_utc"] or state["quarantine"] or not (opening <= now < last_admission):
                return promoted
            active = self.db.execute("SELECT workstation FROM tickets WHERE state IN ('READY','ADMITTED')").fetchall()
            busy = {row["workstation"] for row in active}
            slots = self.config.max_active - len(active)
            candidates = self.db.execute(
                "SELECT t.* FROM tickets t LEFT JOIN served s ON s.workstation = t.workstation "
                "WHERE t.state = 'QUEUED' ORDER BY COALESCE(s.last_served_utc, ''), t.created_utc").fetchall()
            for ticket in candidates:
                if slots <= 0:
                    break
                if ticket["workstation"] in busy:
                    continue  # At most one outstanding stage per workstation.
                hold_id = self._usable_hold(now, ticket) if ticket["kind"] == "prism" else None
                if hold_id is None:
                    hold_id = self._hold(now, ticket, 2 if ticket["kind"] == "grader" else 1)
                if hold_id is None:
                    if ticket["last_reason"] != "DAILY_INVOCATIONS_EXHAUSTED":
                        self._set(now, ticket["ticket_id"], "QUEUED", "DAILY_INVOCATIONS_EXHAUSTED")
                    continue
                deadline = now + timedelta(seconds=self.config.dispatch_window_seconds)
                self._set(now, ticket["ticket_id"], "READY", None, hold_id=hold_id,
                          ready_deadline_utc=deadline.isoformat())
                self.db.execute("INSERT INTO served VALUES (?, ?) ON CONFLICT(workstation) "
                                "DO UPDATE SET last_served_utc = excluded.last_served_utc",
                                (ticket["workstation"], now.isoformat()))
                busy.add(ticket["workstation"])
                slots -= 1
                promoted.append(ticket["ticket_id"])
        return promoted

    def admit(self, ticket_id, *, principal, workstation, model_id, modality, source_sha256, request_digest) -> dict:
        """Convert the ticket's hold slot into a durable intent BEFORE the call is forwarded."""
        with self._tx() as now:
            self._require_admissible(now)
            ticket = self.db.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
            require(ticket is not None and ticket["principal"] == principal
                    and ticket["workstation"] == workstation, "TICKET_NOT_FOUND")
            existing = self.db.execute("SELECT * FROM intents WHERE ticket_id = ?", (ticket_id,)).fetchone()
            if existing is not None:
                require(existing["request_digest"] == request_digest, "TICKET_ALREADY_USED_FOR_ANOTHER_REQUEST")
                raise AuthorityError("TICKET_ALREADY_ADMITTED_NO_SECOND_DISPATCH")
            require(ticket["state"] == "READY", "TICKET_NOT_READY")
            require(datetime.fromisoformat(ticket["ready_deadline_utc"]) >= now, "DISPATCH_WINDOW_EXPIRED")
            require((ticket["model_id"], ticket["modality"], ticket["source_sha256"])
                    == (model_id, modality, source_sha256), "REQUEST_DOES_NOT_MATCH_TICKET")
            _, last_admission, _ = ai_window(now, self.config)
            opening, _, _ = ai_window(now, self.config)
            require(opening <= now < last_admission, "OUTSIDE_AI_HOURS")
            running = self.db.execute("SELECT COUNT(*) FROM tickets WHERE state = 'ADMITTED'").fetchone()[0]
            require(running < self.config.max_running, "ONE_MODEL_STAGE_RUNS_AT_A_TIME")
            hold = self.db.execute("SELECT * FROM holds WHERE hold_id = ?", (ticket["hold_id"],)).fetchone()
            day = thai_day(now)
            if hold is None or hold["day"] != day or hold["slots_total"] - hold["slots_used"] - hold["slots_released"] < 1:
                # Midnight passed or the slot was released: a new day needs a new hold, never borrowing.
                require(False, "HOLD_NOT_VALID_TODAY_REQUEUE")
            used, held, _ = self._usage(day)
            require(used + 1 <= self.config.daily_invocations, "DAILY_INVOCATIONS_EXHAUSTED")
            intent_id = "int_" + uuid.uuid4().hex
            self.db.execute("UPDATE holds SET slots_used = slots_used + 1 WHERE hold_id = ?", (hold["hold_id"],))
            self.db.execute("INSERT INTO intents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
                            (intent_id, ticket_id, day, hold["hold_id"], principal, workstation, model_id,
                             request_digest, now.isoformat()))
            self._set(now, ticket_id, "ADMITTED", None)
            self._event(now, "INTENT", {"intent_id": intent_id, "ticket_id": ticket_id, "day": day,
                                        "model_id": model_id, "request_digest": request_digest})
            return {"intent_id": intent_id, "ticket_id": ticket_id, "day": day}

    def finish(self, ticket_id, *, outcome, reason=None) -> None:
        """Record the forwarded call's outcome. Never refunds; UNKNOWN quarantines new GPU work."""
        require(outcome in {"DONE", "FAILED", "UNKNOWN"}, "OUTCOME_INVALID")
        with self._tx() as now:
            ticket = self.db.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
            require(ticket is not None and ticket["state"] == "ADMITTED", "TICKET_NOT_ADMITTED")
            self.db.execute("UPDATE intents SET outcome = ?, finished_utc = ? WHERE ticket_id = ?",
                            (outcome, now.isoformat(), ticket_id))
            self._set(now, ticket_id, outcome, reason)
            if outcome == "UNKNOWN":
                self._quarantine(now, "UNKNOWN_MODEL_OUTCOME")

    def cancel(self, ticket_id, *, principal) -> dict:
        """Cancel before admission releases this ticket's unused slots; after admission nothing changes."""
        with self._tx() as now:
            ticket = self.db.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
            require(ticket is not None and ticket["principal"] == principal, "TICKET_NOT_FOUND")
            if ticket["state"] in ("QUEUED", "READY"):
                self._release(now, ticket["hold_id"], 2 if ticket["kind"] == "grader" else 1, "CANCELLED_BEFORE_ADMISSION")
                self._set(now, ticket_id, "CANCELLED", "CANCELLED_BEFORE_ADMISSION")
            elif ticket["state"] == "ADMITTED":
                raise AuthorityError("ALREADY_ADMITTED_CANCEL_IS_NOT_PROOF")
        return self.get(ticket_id, principal=principal)

    def release_image(self, *, principal, workstation, source_sha256) -> int:
        """Release today's unconsumed slots for an image the clinician removed. Never touches used slots."""
        released = 0
        with self._tx() as now:
            require(not self.db.execute(
                "SELECT 1 FROM tickets WHERE principal = ? AND workstation = ? AND source_sha256 = ? "
                "AND state IN ('QUEUED','READY','ADMITTED')", (principal, workstation, source_sha256)).fetchone(),
                "IMAGE_HAS_OPEN_STAGE_CANCEL_FIRST")
            for row in self.db.execute(
                    "SELECT hold_id, slots_total - slots_used - slots_released AS free FROM holds WHERE day = ? "
                    "AND principal = ? AND workstation = ? AND source_sha256 = ?",
                    (thai_day(now), principal, workstation, source_sha256)).fetchall():
                self._release(now, row["hold_id"], row["free"], "IMAGE_REMOVED")
                released += max(0, row["free"])
        return released

    # ------------------------------------------------------------------ GPU segments

    def fund_segment(self, *, epoch, gpu_uuid) -> dict:
        """Fund the next non-overlapping segment before the child runs into it. Full charge, no refund."""
        require(gpu_uuid == self.config.gpu_uuid, "APPROVED_RTX_UUID_ONLY")
        require(NAME.fullmatch(str(epoch)), "EPOCH_INVALID")
        with self._tx() as now:
            self._require_admissible(now)
            opening, last_admission, closing = ai_window(now, self.config)
            require(opening <= now < closing, "OUTSIDE_AI_HOURS")
            last_end = self.db.execute("SELECT MAX(end_utc) FROM gpu_segments").fetchone()[0]
            start = max(now, datetime.fromisoformat(last_end)) if last_end else now
            # Stored instants are always UTC so text ordering matches time ordering.
            end = min(start + timedelta(seconds=self.config.segment_seconds), closing).astimezone(timezone.utc)
            require(end > start, "NO_FUNDABLE_TIME_BEFORE_CLOSE")
            pieces, cursor = [], start
            while cursor < end:  # Split at Thai midnight so each day pays its own part.
                midnight = datetime.fromisoformat(thai_day(cursor)).replace(tzinfo=BANGKOK) + timedelta(days=1)
                piece_end = min(end, midnight.astimezone(timezone.utc))
                pieces.append((thai_day(cursor), cursor, piece_end))
                cursor = piece_end
            for day, piece_start, piece_end in pieces:
                seconds = int(round((piece_end - piece_start).total_seconds()))
                _, _, gpu = self._usage(day)
                require(gpu + seconds <= self.config.daily_gpu_seconds, "DAILY_GPU_SECONDS_EXHAUSTED")
            segment_ids = []
            for day, piece_start, piece_end in pieces:
                seconds = int(round((piece_end - piece_start).total_seconds()))
                segment_id = "seg_" + uuid.uuid4().hex
                self.db.execute("INSERT INTO gpu_segments VALUES (?, ?, ?, 'FUNDED', ?, ?, ?, ?)",
                                (segment_id, day, epoch, piece_start.isoformat(), piece_end.isoformat(), seconds,
                                 now.isoformat()))
                segment_ids.append(segment_id)
            self._event(now, "GPU_SEGMENT", {"epoch": epoch, "start": start.isoformat(), "end": end.isoformat(),
                                             "segments": segment_ids})
            return {"epoch": epoch, "start_utc": start.isoformat(), "end_utc": end.isoformat(),
                    "seconds": int(round((end - start).total_seconds()))}

    def record_overrun(self, *, epoch, seconds) -> None:
        """Observed use beyond funding is charged once and quarantines new GPU work."""
        require(isinstance(seconds, (int, float)) and seconds > 0, "OVERRUN_SECONDS_INVALID")
        with self._tx() as now:
            segment_id = "seg_" + uuid.uuid4().hex
            self.db.execute("INSERT INTO gpu_segments VALUES (?, ?, ?, 'OVERRUN', ?, ?, ?, ?)",
                            (segment_id, thai_day(now), epoch, now.isoformat(), now.isoformat(),
                             max(1, int(-(-seconds // 1))), now.isoformat()))
            self._quarantine(now, "GPU_OVERRUN")

    # ------------------------------------------------------------------ operator

    def reconcile(self, *, reason, evidence_sha256) -> None:
        """Explicit operator release of a quarantine after reviewing evidence. Never automatic."""
        require(isinstance(reason, str) and reason.strip() and SHA.fullmatch(str(evidence_sha256)),
                "RECONCILIATION_EVIDENCE_REQUIRED")
        with self._tx(rebaseline=True) as now:
            for row in self.db.execute("SELECT ticket_id FROM tickets WHERE state = 'ADMITTED'").fetchall():
                # A call that may have run is never refunded; its outcome stays unknown.
                self.db.execute("UPDATE intents SET outcome = 'UNKNOWN', finished_utc = ? WHERE ticket_id = ?",
                                (now.isoformat(), row["ticket_id"]))
                self._set(now, row["ticket_id"], "UNKNOWN", "RECONCILED_OUTCOME_UNKNOWN")
            previous = self._state()["quarantine"]
            self.db.execute("UPDATE authority SET quarantine = NULL WHERE id = 1")
            self._event(now, "RECONCILED", {"previous": previous, "reason": reason,
                                            "evidence_sha256": evidence_sha256})

    def revoke(self, *, reason) -> None:
        with self._tx() as now:
            self.db.execute("UPDATE authority SET revoked_utc = ? WHERE id = 1", (now.isoformat(),))
            self._event(now, "REVOKED", {"reason": reason})

    def status(self, *, principal=None, workstation=None) -> dict:
        now = self.clock.utc()
        opening, last_admission, closing = ai_window(now, self.config)
        state = self._state()
        counts = {row["state"]: row["n"] for row in self.db.execute(
            "SELECT state, COUNT(*) AS n FROM tickets WHERE state IN ('QUEUED','READY','ADMITTED') GROUP BY state")}
        result = {**self.capacity(now), "ai_open": opening <= now < last_admission,
                  "ai_hours": f"{self.config.ai_open}-{self.config.ai_close} Asia/Bangkok",
                  "next_ai_opening_utc": None if opening <= now < last_admission
                  else next_ai_opening(now, self.config).astimezone(timezone.utc).isoformat(),
                  "queued": counts.get("QUEUED", 0), "ready": counts.get("READY", 0),
                  "running": counts.get("ADMITTED", 0), "revoked": state["revoked_utc"] is not None,
                  "quarantined": state["quarantine"] is not None}
        if principal is not None and workstation is not None:
            # Own tickets only: never another workstation's work.
            result["own_open_tickets"] = [dict(row) for row in self.db.execute(
                "SELECT ticket_id, kind, model_id, modality, state, last_reason FROM tickets "
                "WHERE principal = ? AND workstation = ? AND state IN ('QUEUED','READY','ADMITTED')",
                (principal, workstation))]
        return result
