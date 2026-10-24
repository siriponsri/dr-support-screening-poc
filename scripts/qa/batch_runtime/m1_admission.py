"""Parent-side consumer of the existing M1 ledger/budget and owned supervisor.

No new counter, process, service, credentials, model, database or retry loop.
The real child/HTTP/readback adapters still require separate qualification.
"""
from copy import deepcopy
import re

from batch_budget import BatchBudget
from batch_ledger import BatchLedger, M1_GPU0, require
from scripts.qa.worker_supervisor import ChildIdentity, WorkerSupervisor


FACTS = {"operation_id", "source_sha256", "model_id", "modality", "model_pins_sha256",
         "parameters_sha256", "preprocessing_id"}


def _sha(value):
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


class M1AdmissionConsumer:
    """One parent-owned native admission at a time, never an inference driver.

    Child observations must come from the existing independently qualified owned
    spawn adapter. HTTP completion and genuine PostgreSQL readback are distinct
    trusted ports, not claims accepted from an unauthenticated browser request.
    """
    def __init__(self, ledger, budget, supervisor, *, child, lease_id):
        require(type(ledger) is BatchLedger and ledger.continuation is not None
                and ledger.base_used == ledger.spec["base_used"] and ledger.cap == ledger.spec["cap"],
                "M1_EXISTING_CONTINUATION_LEDGER_REQUIRED")
        require(type(budget) is BatchBudget and budget.ledger is ledger
                and ledger._window_budget is budget and budget.session_id == ledger.spec["server_window"],
                "M1_EXACT_SERVER_WINDOW_BUDGET_REQUIRED")
        require(type(supervisor) is WorkerSupervisor and supervisor._child is child
                and type(child.identity) is ChildIdentity and supervisor._identity == child.identity
                and supervisor.policy.gpu_uuid == M1_GPU0,
                "M1_EXACT_OWNED_SUPERVISOR_CHILD_REQUIRED")
        self.ledger, self.budget, self.supervisor, self.child = ledger, budget, supervisor, child
        self.identity, self.lease_id = child.identity, lease_id
        self.poisoned, self.active = False, None
        self._ready()

    def _ready(self):
        require(not self.poisoned and self.child.identity == self.identity,
                "M1_NATIVE_ADMISSION_POISONED_OR_CHILD_CHANGED")
        self.budget.check()
        active = self.budget.body["active"]
        require(active is not None and active["lease_id"] == self.lease_id,
                "M1_FUNDED_OWNED_LIFETIME_REQUIRED")
        self.supervisor.tick()
        require(self.supervisor.state in {"IDLE", "BUSY"}, "M1_SUPERVISOR_ADMISSION_CLOSED")

    def admit(self, job_id, *, request_id, request_sha256, facts, identity):
        """Fsync the existing intent BEFORE authorizing the owned child ACK."""
        with self.ledger.lock:
            self._ready()
            require(self.active is None and self.supervisor.state == "IDLE",
                    "M1_SERIAL_NATIVE_ADMISSION_REQUIRED")
            require(type(request_id) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,96}", request_id)
                    and _sha(request_sha256) and type(identity) is ChildIdentity and identity == self.identity,
                    "M1_REQUEST_AND_OWNED_CHILD_IDENTITY_REQUIRED")
            job = self.ledger.jobs.get(job_id)
            require(job is not None and job["window_id"] == self.budget.session_id
                    and type(facts) is dict and set(facts) == FACTS
                    and all(facts[key] == job[key] for key in FACTS),
                    "M1_PREPARED_REQUEST_OUTSIDE_FROZEN_OPERATION")
            admission = self.ledger.admit(job_id, request_sha256=request_sha256, budget=self.budget)
            self.active = {**admission, "request_id": request_id,
                           "response_observed": False, "response_retained": False}
            try:
                self.supervisor.admit(admission["admission_id"])
            except Exception:
                # Durable intent is already consumed. No ACK/dispatch is safe,
                # and an uncertain native handoff never becomes pending again.
                self.poisoned = True
                try:
                    self.ledger.append(job_id, "SENT_OR_UNCERTAIN", reason="RESOURCE_LIMIT")
                except Exception:
                    pass
                raise
            return deepcopy(admission | {"request_id": request_id})

    def _matching(self, admission_id):
        require(self.active is not None and self.active["admission_id"] == admission_id,
                "M1_MATCHING_ACTIVE_ADMISSION_REQUIRED")
        return self.active

    def ack_failed(self, admission_id):
        """An uncertain ACK consumes its intent and closes further admission."""
        with self.ledger.lock:
            active = self._matching(admission_id)
            self.poisoned = True
            self.ledger.append(active["job_id"], "SENT_OR_UNCERTAIN", reason="DISCONNECTED")

    def record_response(self, admission_id, *, response_sha256, success):
        """Actual terminal model/HTTP response, not PRISM's execute HTTP202.

        Call only after the authenticated old job is terminal (bound PRISM) or
        the ordinary prediction response is complete. An I/O failure must not
        relabel a returned valid model result as failed inference.
        """
        with self.ledger.lock:
            active = self._matching(admission_id)
            require(not active["response_observed"] and _sha(response_sha256) and type(success) is bool,
                    "M1_EXACT_TERMINAL_RESPONSE_REQUIRED")
            accounting, supervision = "PASS", "PASS"
            try:
                self.ledger.append(active["job_id"], "RESPONSE_RETAINED" if success else "FAILED_NO_RETRY",
                    reason=None if success else "APP_REJECTED", artifact_sha256=response_sha256)
            except Exception:
                self.poisoned, accounting = True, "BLOCKED"
            try:
                self.supervisor.finish(admission_id, success=success)
            except Exception:
                self.poisoned, supervision = True, "BLOCKED"
            active["response_observed"] = success
            active["response_retained"] = success and accounting == "PASS"
            if not success:
                self.active = None
            return {"inference": "MODEL_COMPLETE" if success else "MODEL_FAILED_NO_RETRY",
                    "accounting": accounting, "supervision": supervision,
                    "persistence": "PENDING" if success else "NOT_RUN"}

    def acknowledge_readback(self, admission_id, *, readback_sha256, matches):
        """Trusted app's independent PostgreSQL readback, not HTTP/model success.

        The composed adapter must actually read its fixed test DB and verify
        invocation/provenance plus protected physician fields before this call.
        A hash or this method's existence does not itself qualify that adapter.
        """
        with self.ledger.lock:
            active = self._matching(admission_id)
            require(active["response_observed"] and _sha(readback_sha256) and type(matches) is bool,
                    "M1_OBSERVED_RESPONSE_AND_ACTUAL_READBACK_REQUIRED")
            if not active["response_retained"]:
                # Actual inference and DB readback can both succeed while the
                # earlier journal/head write is uncertain. Do not manufacture
                # a missing RESPONSE_RETAINED transition or discard DB proof.
                self.poisoned, self.active = True, None
                return {"inference": "MODEL_COMPLETE", "persistence": "PASS" if matches else "FAILED",
                        "accounting": "BLOCKED", "automatic_retries": 0}
            accounting = "PASS"
            try:
                self.ledger.append(active["job_id"], "PASS_READBACK" if matches else "FAILED_PERSISTENCE",
                    reason=None if matches else "POSTGRES_READBACK_MISMATCH", artifact_sha256=readback_sha256)
            except Exception:
                self.poisoned, accounting = True, "BLOCKED"
            self.active = None
            return {"inference": "MODEL_COMPLETE", "persistence": "PASS" if matches else "FAILED",
                    "accounting": accounting, "automatic_retries": 0}

    def status(self):
        observed = self.ledger.base_used + self.ledger.attempts
        return {"global_used": None if self.ledger.poisoned else observed,
                "global_used_at_least": observed,
                "usage_status": "UNCERTAIN" if self.ledger.poisoned else "EXACT", "cap": self.ledger.cap,
                "poisoned": self.poisoned or self.ledger.poisoned,
                "active_admission": self.active is not None, "supervisor_state": self.supervisor.state,
                "automatic_retries": 0, "counter_source": "EXISTING_BATCH_LEDGER"}
