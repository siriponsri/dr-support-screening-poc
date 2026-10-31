"""Review-app side of the shared regular Model API queue (owner-approved 2026-10-31).

Every charged model call (``/v1/predict/dr`` grading, ``/v1/prism-bound/execute``)
first gets a scheduled ticket from the control service and is sent only once that
ticket is READY, with ``X-DR-Ticket`` and this app's ``X-DR-Workstation``. This is
done in an httpx transport so the existing providers, contracts and validation
stay unchanged. Waiting is bounded; a call that never got a READY ticket was
never sent. The backend token stays in this process; nothing here is exposed to
the browser beyond the plain status fields of :meth:`RegularGate.public_status`.
See docs/milestone/m1/M1_REGULAR_SERVICE_DESIGN.md.
"""
from __future__ import annotations

from contextvars import ContextVar
import hashlib
import json
import re
import threading
import time
from uuid import uuid4

import httpx

from ..providers.remote import RemoteModelError

# The image identity (content SHA-256 of the admitted source) for the current call,
# so an image's grader and PRISM stages share one pair hold on the host.
PAIR_KEY: ContextVar[str | None] = ContextVar("regular_pair_key", default=None)

WORKSTATION = re.compile(r"[A-Za-z0-9_.:-]{1,120}")
SHA = re.compile(r"[a-f0-9]{64}")
GLOBAL_ROUTE = "/v1/predict/dr"
PRISM_BASE = "/v1/prism-bound"
_NOTHING_SENT = " Nothing was sent. Manual review remains available."
WORDING = {
    "OUTSIDE_AI_HOURS": "AI analysis runs only from 06:00 to 22:00 (Thailand time)." + _NOTHING_SENT,
    "DAILY_INVOCATIONS_EXHAUSTED": "Today's AI analysis limit has been used." + _NOTHING_SENT,
    "DAILY_GPU_SECONDS_EXHAUSTED": "Today's AI server time has been used." + _NOTHING_SENT,
    "AUTHORITY_QUARANTINED_RECONCILE_FIRST": "AI analysis is paused until the operator checks the model server."
                                             + _NOTHING_SENT,
    "QUEUE_WAIT_TIMEOUT": "The AI queue did not reach this image in time. Try again later." + _NOTHING_SENT,
    "DISPATCH_WINDOW_EXPIRED": "The AI queue turn for this image expired. Try again." + _NOTHING_SENT,
    "QUEUE_UNREACHABLE": "The AI queue could not be reached." + _NOTHING_SENT,
    "QUEUE_BUSY_NOT_SENT": "The AI server was busy with another image. Try again." + _NOTHING_SENT,
    "MODEL_SERVER_NOT_READY": "The AI server is not running now. Try again shortly." + _NOTHING_SENT,
}
TERMINAL = {"DONE", "FAILED", "UNKNOWN", "CANCELLED", "EXPIRED"}


class RegularQueueError(RemoteModelError):
    """Refused before any model call was sent. Carries a fixed code and plain wording only."""

    def __init__(self, code: str):
        self.code = code if isinstance(code, str) and re.fullmatch(r"[A-Z0-9_]{3,80}", code) else "QUEUE_REFUSED"
        self.message = WORDING.get(self.code, "The AI queue could not run this image now." + _NOTHING_SENT)
        super().__init__(self.message)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class RegularGate:
    """Ticket client for one review app (one workstation ID)."""

    def __init__(self, base_url: str, token: str, workstation: str, *, transport: httpx.BaseTransport,
                 clock=time.monotonic, sleep=time.sleep, ready_wait_seconds: float = 300, poll_seconds: float = 1.0):
        if not isinstance(workstation, str) or not WORKSTATION.fullmatch(workstation):
            raise ValueError("REGULAR_WORKSTATION_ID_REQUIRED")
        if not isinstance(token, str) or not 32 <= len(token) <= 1024:
            raise ValueError("REGULAR_BACKEND_TOKEN_REQUIRED")
        if not 0 < ready_wait_seconds <= 600 or not 0 < poll_seconds <= 5:
            raise ValueError("BOUNDED_QUEUE_WAIT_REQUIRED")
        self.workstation, self._token = workstation, token
        self.clock, self.sleep = clock, sleep
        self.ready_wait_seconds, self.poll_seconds = ready_wait_seconds, poll_seconds
        # 15 s rides out the gateway's brief pause while it spawns the GPU child.
        self.client = httpx.Client(base_url=base_url, transport=transport, timeout=httpx.Timeout(15),
                                   trust_env=False, follow_redirects=False)
        self.renegotiate = None   # Set to the PRISM provider's negotiate once composed.
        self.lock = threading.RLock()

    def _call(self, method: str, path: str, value=None) -> dict:
        try:
            response = self.client.request(method, "/v1/regular" + path, json=value, headers={
                "Authorization": "Bearer " + self._token, "X-DR-Workstation": self.workstation})
        except httpx.HTTPError:
            raise RegularQueueError("QUEUE_UNREACHABLE") from None
        try:
            body = response.json()
        except ValueError:
            raise RegularQueueError("QUEUE_UNREACHABLE") from None
        if response.status_code != 200 or not isinstance(body, dict):
            raise RegularQueueError(body.get("code") if isinstance(body, dict) else "QUEUE_REFUSED")
        return body

    def status(self) -> dict:
        return self._call("GET", "/status")

    def public_status(self) -> dict:
        """Plain fields only, for the review UI. No identifiers of other workstations."""
        value = self.status()
        own = value.get("own_open_tickets") or []
        return {key: value.get(key) for key in (
            "day", "ai_open", "ai_hours", "next_ai_opening_utc", "invocations_used", "invocations_cap",
            "invocations_available", "gpu_seconds_reserved", "gpu_seconds_cap", "gpu_seconds_available",
            "model_server", "quarantined", "revoked")} | {
            "own_waiting": sum(item.get("state") == "QUEUED" for item in own),
            "own_running": sum(item.get("state") in {"READY", "ADMITTED"} for item in own),
            "system_waiting": value.get("queued", 0), "system_running": value.get("running", 0)}

    def warm(self) -> None:
        self._call("POST", "/warm")

    def release(self, pair_key: str) -> int:
        """Give back today's unused slots of an image whose remaining stage will not run (never a used slot)."""
        if not isinstance(pair_key, str) or not SHA.fullmatch(pair_key):
            return 0
        return int(self._call("POST", "/images/release", {"pair_key": pair_key}).get("released", 0))

    def cancel(self, ticket_id: str) -> dict:
        return self._call("POST", f"/tickets/{ticket_id}/cancel")

    def cancel_stale(self) -> int:
        """At startup: cancel this workstation's open tickets left by a previous run (never forwarded)."""
        cancelled = 0
        for ticket in self.status().get("own_open_tickets") or []:
            if ticket.get("state") in {"QUEUED", "READY"}:
                try:
                    self.cancel(ticket["ticket_id"])
                    cancelled += 1
                except RegularQueueError:
                    pass
        return cancelled

    def acquire(self, *, kind: str, model_id: str, modality: str, source_sha256: str, pair_key: str | None) -> str:
        """Submit one ticket and wait, bounded, until READY. Any refusal means nothing was sent."""
        pair_key = pair_key if isinstance(pair_key, str) and SHA.fullmatch(pair_key) else source_sha256
        status = self.status()
        if status.get("quarantined") or status.get("revoked"):
            raise RegularQueueError("AUTHORITY_QUARANTINED_RECONCILE_FIRST")
        if not status.get("ai_open"):
            raise RegularQueueError("OUTSIDE_AI_HOURS")
        if status.get("invocations_available", 0) < 1:
            raise RegularQueueError("DAILY_INVOCATIONS_EXHAUSTED")
        key = "rq_" + uuid4().hex
        facts = {"kind": kind, "model_id": model_id, "modality": modality, "source_sha256": source_sha256,
                 "pair_key": pair_key, "workstation": self.workstation, "key": key}
        ticket = self._call("POST", "/tickets", {"idempotency_key": key, "request_digest": _sha(_canonical(facts)),
                                                 "kind": kind, "model_id": model_id, "modality": modality,
                                                 "source_sha256": source_sha256, "pair_key": pair_key})
        ticket_id = ticket["ticket_id"]
        deadline = self.clock() + self.ready_wait_seconds
        while True:
            state, reason = ticket.get("state"), ticket.get("last_reason")
            if state == "READY":
                return ticket_id
            if state in TERMINAL:
                raise RegularQueueError(reason or "QUEUE_REFUSED")
            if reason in {"DAILY_INVOCATIONS_EXHAUSTED"} or self.clock() >= deadline:
                try:
                    self.cancel(ticket_id)
                except RegularQueueError:
                    pass
                raise RegularQueueError(reason if reason == "DAILY_INVOCATIONS_EXHAUSTED" else "QUEUE_WAIT_TIMEOUT")
            self.sleep(self.poll_seconds)
            try:
                ticket = self._call("GET", f"/tickets/{ticket_id}")
            except RegularQueueError as error:
                if error.code != "QUEUE_UNREACHABLE":
                    raise
                # A brief gateway pause: keep the last known state and poll again within the same bound.

    def headers(self, ticket_id: str) -> dict:
        return {"X-DR-Ticket": ticket_id, "X-DR-Workstation": self.workstation}

    def close(self):
        self.client.close()


class RegularTransport(httpx.BaseTransport):
    """Adds a READY ticket to charged calls; keeps PRISM preparation on the live child epoch."""

    def __init__(self, gate: RegularGate, inner: httpx.BaseTransport):
        self.gate, self.inner = gate, inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        if method == "POST" and path == GLOBAL_ROUTE:
            body = json.loads(request.read())
            ticket = self.gate.acquire(kind="grader", model_id=body["model_id"], modality=body["modality"],
                                       source_sha256=body["image_sha256"], pair_key=PAIR_KEY.get())
            request.headers.update(self.gate.headers(ticket))
        elif method == "POST" and path == PRISM_BASE + "/execute":
            binding = json.loads(request.read())["binding"]
            ticket = self.gate.acquire(kind="prism", model_id=binding["model_id"], modality=binding["modality"],
                                       source_sha256=binding["source_sha256"], pair_key=binding["source_sha256"])
            request.headers.update(self.gate.headers(ticket))
        elif method == "POST" and path == PRISM_BASE + "/prepare":
            status = self.gate.status()
            if status.get("model_server") != "READY":
                if status.get("ai_open") and not status.get("quarantined"):
                    self.gate.warm()   # Start loading; the clinician prepares again shortly.
                return httpx.Response(503, json={"error": "PREPARE_UNAVAILABLE"}, request=request)
            epoch = status.get("model_epoch")
            if epoch and request.headers.get("x-prism-epoch") != epoch and callable(self.gate.renegotiate):
                # A newly started child has a new epoch: renegotiate its loaded identity first.
                with self.gate.lock:
                    self.gate.renegotiate()
                request.headers["X-Prism-Epoch"] = epoch
        response = self.inner.handle_request(request)
        if method == "POST" and path in {GLOBAL_ROUTE, PRISM_BASE + "/execute"} and response.status_code == 503:
            # The gateway refused before dispatch (busy or not loaded): nothing was sent.
            try:
                code = json.loads(response.read()).get("code")
            except (ValueError, AttributeError):
                code = None
            if code in {"QUEUE_BUSY_NOT_SENT", "MODEL_SERVER_NOT_READY"}:
                response.close()
                raise RegularQueueError(code)
        return response

    def close(self):
        self.inner.close()
