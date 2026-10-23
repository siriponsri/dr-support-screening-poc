"""Production-app request and PostgreSQL readback component; registration disabled.

Caller owns a separately qualified process/session and injected app/client. This
module neither loads models nor creates a listener, credential or database.
"""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import time

from batch_ledger import canonical, digest, require

CLINICAL = (
    "reviewed_grade", "grade_review_source", "grade_status", "grade_reviews",
    "grade_adjudication", "reviewed_grade_label", "clinician_review", "review_history",
    "human_annotations", "annotation_confirmation", "ai_annotation_reviews",
    "lesion_review_state", "annotation_completeness", "annotations", "admission",
    "admission_history", "patient_key", "laterality", "visit_context",
)
REGISTERED = False


def protected(case):
    return {key: deepcopy(case.get(key)) for key in CLINICAL}


def write_new(path, value):
    raw = canonical(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(raw)
        output.flush()
        import os
        os.fsync(output.fileno())
    require(path.read_bytes() == raw, "EVIDENCE_FILE_READBACK_FAILED")
    return digest(raw)


def app_failure(response):
    """Keep status/body identity and controlled local reasons, never raw errors."""
    reasons = {
        "This source is available for manual review only; model analysis is not approved for its origin.": "SOURCE_NOT_APPROVED_AT_APP_BOUNDARY",
        "Model unavailable; inspect Models readiness and runtime configuration": "MODEL_UNAVAILABLE_AT_APP_BOUNDARY",
        "Technical test excludes clinical or workspace mutations": "TECHNICAL_MUTATION_BLOCKED",
    }
    reason, body_sha = "UNCLASSIFIED_LOCAL_APP_FAILURE", None
    try:
        body = response.json()
        body_sha = digest(canonical(body))
        if isinstance(body, dict) and isinstance(body.get("detail"), str):
            reason = reasons.get(body["detail"], reason)
    except (ValueError, TypeError, UnicodeError):
        pass
    return {"stage": "LOCAL_APP_RESPONSE", "http_status": response.status_code,
            "reason": reason, "response_body_sha256": body_sha,
            "raw_error_text_retained": False, "automatic_retries": 0}


class PostgresReadback:
    """Use the actual production store, opening its normal new DB sessions."""

    def __init__(self, app, *, schema, workspace_id):
        from dr_support.persistence.cases import PostgresCaseStore
        store = app.state.store
        require(type(store) is PostgresCaseStore, "GENUINE_POSTGRES_CASE_STORE_REQUIRED")
        require(app.state.case_store_mode == "postgres", "POSTGRES_MODE_REQUIRED_NO_JSON_SUBSTITUTION")
        require(store.workspace_id == workspace_id and store.database.settings.schema == schema, "TEST_POSTGRES_TARGET_CHANGED")
        require(schema == "qa_model_api_20261022_batch01" and workspace_id.startswith("qa_batch_"), "EXACT_FRESH_BATCH_DATABASE_SCOPE_REQUIRED")
        from psycopg.conninfo import conninfo_to_dict
        configured = conninfo_to_dict(store.database.settings.dsn)
        require(configured.get("dbname") == "dr_support_model_api_test" and configured.get("host") in {"127.0.0.1", "localhost"} and configured.get("port") == "54805", "EXISTING_LOOPBACK_TEST_DATABASE_REQUIRED")
        self.app, self.original = app, store
        # Fresh store object avoids relying on a provider/app cached projection.
        self.reader = PostgresCaseStore(store.database, workspace_id)

    def get(self, image_id):
        require(self.app.state.store is self.original, "APP_POSTGRES_STORE_REPLACED")
        return self.reader.get(image_id)


class BatchAppDriver:
    def __init__(self, *, app, client, readback, ledger, output, expected_models, profile, clock=time.monotonic):
        self.app, self.client, self.readback = app, client, readback
        self.ledger, self.output = ledger, Path(output)
        self.models, self.profile, self.clock = expected_models, profile, clock

    def prepare(self, job, before):
        """Preparation never invokes a model and never consumes an attempt."""
        image_id = job["source_sha256"]
        if job["model_id"] == "prism-dr-5fold":
            response = self.client.post(f"/v1/cases/{image_id}/prism-input-preview", json={"revision": before["revision"]})
            if response.status_code != 200:
                failure = app_failure(response)
                failure["phase"] = "PRISM_PREPARATION_NO_INFERENCE_SENT"
                provider = self.app.state.providers.get(job["model_id"])
                diagnostic = getattr(provider, "last_failure", None)
                if type(diagnostic) is dict:
                    failure["transport"] = deepcopy(diagnostic)
                write_new(self.output/"failures"/(job["job_id"]+"-preparation.json"), failure)
            require(response.status_code == 200, "PRISM_PLAN_PREPARATION_FAILED")
            plan = response.json()
            require(plan["source_sha256"] == plan["wire_sha256"] == image_id, "ORIGINAL_WIRE_PLAN_CHANGED")
            require(plan["mask"]["sha256"] is None, "UNMASKED_BATCH_BASELINE_REQUIRED")
            require(plan["model_pins"] == self.models[job["model_id"]]["pins"], "MODEL_IDENTITY_CHANGED")
            payload = {"revision": plan["case_revision"], "source_sha256": image_id, "wire_sha256": image_id, "plan_sha256": plan["plan_sha256"], "mask_sha256": None, "transform_sha256": plan["transform"]["sha256"], "model_version": plan["model_version"]}
            return f"/v1/cases/{image_id}/prism-input-preview/{plan['plan_id']}/infer", payload, "preview-"+plan["plan_id"]
        model = self.models[job["model_id"]]
        payload = {"image_id": image_id, "modality": job["modality"], "model_id": job["model_id"], "invocation_id": "batch-"+job["job_id"][:40], "capability_id": model["capability_id"], "model_version": model["model_version"], "request_case_revision": before["revision"]}
        return "/v2/infer/global", payload, payload["invocation_id"]

    def execute(self, job, *, browser=None):
        """One planned request. Unknown/failed calls are never reissued."""
        from dr_support.contracts import GlobalResult, LesionResult
        key = job["job_id"]
        require(key not in self.ledger.states, "JOB_ALREADY_SENT_OR_TERMINAL")
        require((browser is not None) == (job["execution_surface_proposed"] == "ACTUAL_BROWSER_UI"), "BROWSER_ALLOCATION_MUST_NOT_BECOME_EXTRA_REQUEST")
        read_started = time.perf_counter()
        before = self.readback.get(job["source_sha256"])
        initial_readback_ms = (time.perf_counter()-read_started)*1000
        started = self.clock()
        stamp = datetime.now(timezone.utc).isoformat()
        # Profile is a manifest-scoped research authorization, not fake quality.
        with self.profile.activate(job, before):
            try:
                prepare_started = time.perf_counter()
                path, payload, invocation = (self.prepare(job, before) if browser is None
                                             else browser.prepare_once(job, before))
                preparation_ms = (time.perf_counter()-prepare_started)*1000
                require(not any(entry.get("invocation_id") == invocation
                                for entry in self.readback.get(job["source_sha256"]).get("inference_history", [])),
                        "EXISTING_INVOCATION_NOT_A_NEW_BATCH_ATTEMPT")
            except BaseException as error:
                self.ledger.append(key, "BLOCKED_PREMODEL", reason="APP_REJECTED")
                failure_path = self.output/"failures"/(key+"-preparation.json")
                if not failure_path.exists():
                    provider = self.app.state.providers.get(job["model_id"])
                    diagnostic = getattr(provider, "last_failure", None) or getattr(getattr(provider, "channel", None), "last_failure", None)
                    failure = {"phase": "PREPARATION_NO_INFERENCE_SENT",
                        "stage": "PREPARATION_EXCEPTION", "automatic_retries": 0,
                        "raw_error_text_retained": False,
                        "error_class": type(error).__name__ if type(error).__name__ in {
                            "TransportError", "TimeoutError", "RuntimeError", "ValueError", "KeyError",
                            "TypeError", "OSError", "PermissionError", "ConnectionError"} else "OTHER"}
                    if type(diagnostic) is dict:
                        failure["transport"] = {name: deepcopy(diagnostic[name]) for name in (
                            "stage", "code", "elapsed_ms", "payload_bytes", "http_status", "exception_class")
                            if name in diagnostic}
                    write_new(failure_path, failure)
                raise
            self.ledger.append(key, "ATTEMPT_INTENT")  # fsync before any send
            begin = self.clock()
            try:
                if browser is None:
                    response = self.client.post(path, json=payload)
                else:
                    # The browser adapter must drive this exact prepared route
                    # once through the real UI and return its captured response.
                    response = browser.execute_once(job, path=path, payload=payload)
            except BaseException:
                self.ledger.append(key, "SENT_OR_UNCERTAIN", reason="DISCONNECTED")
                raise
            elapsed = self.clock()-begin
            if response.status_code != 200:
                self.ledger.append(key, "FAILED_NO_RETRY", reason="APP_REJECTED")
                failure = app_failure(response)
                provider = self.app.state.providers.get(job["model_id"])
                diagnostic = getattr(provider, "last_failure", None) or getattr(getattr(provider, "channel", None), "last_failure", None)
                if type(diagnostic) is dict:
                    failure["transport"] = {name: deepcopy(diagnostic[name]) for name in (
                        "stage", "code", "elapsed_ms", "payload_bytes", "http_status", "exception_class")
                        if name in diagnostic}
                write_new(self.output/"failures"/(key+".json"), failure)
                raise RuntimeError("APP_REQUEST_FAILED_NO_RETRY")
            try:
                validation_started = time.perf_counter()
                body = response.json()
                if browser is not None and job["model_id"] != "prism-dr-5fold":
                    require(path == "/v1/infer/global", "REAL_REVIEW_GLOBAL_ROUTE_REQUIRED")
                    result = GlobalResult.model_validate(body)
                else:
                    require(body.get("status") == "APPLIED", "APP_RESULT_NOT_APPLIED")
                    result = (LesionResult if job["model_id"] == "prism-dr-5fold" else GlobalResult).model_validate(body["result"])
                require(result.model_id == job["model_id"] and result.modality == job["modality"], "RESULT_ROUTE_CHANGED")
                require(result.state == "AI_SUGGESTION", "NO_INFERENCE_SUGGESTION_RETURNED")
                require(result.provenance.image_sha256 == job["source_sha256"], "RESULT_SOURCE_CHANGED")
                require(result.provenance.source_type == before["admission"]["source_origin"]
                        and self.profile.claimed is True, "RESULT_ORIGIN_OR_NEW_ENTRY_CLAIM_MISMATCH")
                expected = self.models[job["model_id"]]
                require(result.model_version == expected["model_version"], "MODEL_VERSION_CHANGED")
                base_preprocessing = expected["pins"]["preprocessing"]
                accepted_preprocessing = {base_preprocessing}
                if job["model_id"] == "uspec-uwf-grading":
                    # Actual USPEC._result includes the observed existing mask
                    # branch in provenance; never discard it or permit an
                    # arbitrary suffix as though it matched the pinned code.
                    accepted_preprocessing.update(base_preprocessing + "; mask_status=" + status
                                                  for status in ("FOV_ONLY", "UNMASKED_FALLBACK"))
                require(result.provenance.checkpoint_sha256 == expected["pins"]["checkpoint_sha256"] and result.provenance.source_revision == expected["pins"]["source_revision"] and result.provenance.preprocessing in accepted_preprocessing, "RESULT_MODEL_PINS_CHANGED")
                response_sha = write_new(self.output/"responses"/(key+".json"), body)
                self.ledger.append(key, "RESPONSE_RETAINED", artifact_sha256=response_sha)
                validation_ms = (time.perf_counter()-validation_started)*1000
            except BaseException:
                if self.ledger.states[key] == "ATTEMPT_INTENT":
                    self.ledger.append(key, "FAILED_NO_RETRY", reason="INVALID_RESPONSE")
                else:
                    self.ledger.append(key, "FAILED_PERSISTENCE", reason="RESPONSE_IO_FAILED")
                raise
            try:
                read_started = time.perf_counter()
                saved = self.readback.get(job["source_sha256"])
                final_readback_ms = (time.perf_counter()-read_started)*1000
                entries = [entry for entry in saved.get("inference_history", []) if entry.get("invocation_id") == invocation]
                require(len(entries) == 1 and entries[0].get("status") == "APPLIED", "POSTGRES_INVOCATION_NOT_FOUND")
                require(entries[0]["result"] == result.model_dump(mode="json"), "POSTGRES_READBACK_MISMATCH")
                require(protected(saved) == protected(before), "CLINICAL_STATE_CHANGED")
                if job["model_id"] == "prism-dr-5fold":
                    require(entries[0].get("prism_processing") == body.get("processing_evidence"), "POSTGRES_PROCESSING_EVIDENCE_MISMATCH")
                record = {"status": "PASS_POSTGRES_READBACK", "job_id": key, "source_sha256": job["source_sha256"], "model_id": job["model_id"], "execution_surface": job["execution_surface_proposed"], "request_started_utc": stamp, "request_and_save_wall_ms": elapsed*1000, "whole_job_wall_ms": (self.clock()-started)*1000, "response_sha256": response_sha, "saved_entry_sha256": digest(canonical(entries[0])), "clinical_state_preserved": True, "persistence": "PRODUCTION_POSTGRES_CASE_STORE", "human_UX_timing": "NOT_MEASURED"}
                record["stage_timings"] = {
                    "clock": "PERF_COUNTER_SECONDS_CONVERTED_TO_MS",
                    "initial_fresh_readback_ms": initial_readback_ms,
                    "preparation_ms": preparation_ms,
                    "response_validation_and_durable_retention_ms": validation_ms,
                    "final_fresh_readback_ms": final_readback_ms,
                    "db_readback_scope": "APP_STORE_GET_WITH_NEW_SQL_SESSION; NOT_DATABASE_ENGINE_ONLY",
                    "db_write_only_ms": "NOT_RETAINED",
                }
                if browser is not None:
                    browser.capture_readback(job, record)
                    record["browser_screenshots"] = deepcopy(browser.screenshots)
                record_sha = write_new(self.output/"readbacks"/(key+".json"), record)
                self.ledger.append(key, "PASS_READBACK", artifact_sha256=record_sha)
                return record
            except BaseException as error:
                reason = "CLINICAL_STATE_CHANGED" if type(error) is RuntimeError and error.args == ("CLINICAL_STATE_CHANGED",) else "POSTGRES_READBACK_MISMATCH"
                self.ledger.append(key, "FAILED_PERSISTENCE", reason=reason)
                raise


def main():
    raise RuntimeError("BATCH_REGISTRATION_DISABLED_PENDING_OFFLINE_INTEGRATION_REVIEW")


if __name__ == "__main__":
    main()
