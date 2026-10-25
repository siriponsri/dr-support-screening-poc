"""Unregistered transport client: mandatory trusted source fence, no model imports.

9488ab8's before_forward callback alone is insufficient. Authority.acquire must
run it under a fence covering source/admission/revision/Workspace/provider
mutations, retaining that fence until authentic ROI-entry/terminal proof. An
unknown grant outcome quarantines the fence; a timeout never releases authority.
"""
from copy import deepcopy
import base64
import time

import httpx

from dr_support.contracts import LesionResult, PrismProcessingEvidence
from dr_support.services.prism_remote_transport import BASE, PROTOCOL, TRANSPORT, TransportError, canonical, sha


class RemoteExecutionUncertain(TransportError):
    pass


# Prepare uploads the wire and the host builds the frozen CPU plan; it took longer
# than the 2 s client default right after a PRISM job (MS-03, 2026-10-25). Prepare
# is a control call that starts no model work, so a longer read is safe.
PREPARE_TIMEOUT = httpx.Timeout(20, connect=2)


class ExplicitHttpChannel:
    """No default transport/auth/environment; tests supply MockTransport only.

    Future private deployment must explicitly supply a no-retry transport and
    trusted-backend auth headers. Never expose forward-authority access to UI.
    """
    def __init__(self, base_url, *, transport, auth_headers):
        if transport is None or not callable(auth_headers):
            raise ValueError("EXPLICIT_TRANSPORT_AND_AUTH_REQUIRED")
        self.client = httpx.Client(base_url=base_url, transport=transport, timeout=2,
                                   follow_redirects=False, trust_env=False)
        self.auth_headers = auth_headers

    def request(self, method, path, value=None, *, epoch=None, authority=False):
        headers = dict(self.auth_headers(authority))
        if epoch:
            headers["X-Prism-Epoch"] = epoch
        timeout = PREPARE_TIMEOUT if path == BASE + "/prepare" else httpx.USE_CLIENT_DEFAULT
        with self.client.stream(method, path, json=value, headers=headers, timeout=timeout) as response:
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > 20_100_000:
                    raise TransportError("RESPONSE_LIMIT", 502)
            import json
            parsed = json.loads(data)
            if response.status_code not in {200, 202}:
                # Host refusals carry `error` (transport) or `code` (M1 session admission).
                code = parsed.get("error") or parsed.get("code")
                raise TransportError(code if isinstance(code, str) and code else "REMOTE_REJECTED",
                                     response.status_code)
            return parsed

    def close(self):
        self.client.close()


class RemoteBoundTransportCandidate:
    # Deliberately NOT recognized by production v2 registration.
    prism_preview_protocol = TRANSPORT

    def __init__(self, channel, *, source_authority=None, wait_seconds=30, poll_seconds=.01):
        if not 0 < wait_seconds <= 120 or not .001 <= poll_seconds <= 1:
            raise ValueError("BOUNDED_WAIT_REQUIRED")
        self.channel, self.authority = channel, source_authority
        self.wait_seconds, self.poll_seconds = wait_seconds, poll_seconds
        self.capabilities = None
        self.tickets = {}

    def negotiate(self):
        value = self.channel.request("GET", BASE + "/capabilities")
        if value.get("transport") != TRANSPORT or value.get("binding_protocol") != PROTOCOL:
            raise TransportError("REMOTE_PROTOCOL_UNSUPPORTED", 503)
        self.capabilities = deepcopy(value)
        self.tickets.clear()

    def prism_preview_identity(self):
        if self.capabilities is None:
            raise TransportError("EXPLICIT_AUTHENTICATED_NEGOTIATION_REQUIRED", 503)
        pins = deepcopy(self.capabilities["pins"])
        return {"model_version": pins["source_revision"], "model_pins": pins,
                "descriptor": {"model_id": "prism-dr-5fold", "ready": False,
                               "status": "REMOTE_FENCE_CANDIDATE_NOT_QUALIFIED"}}

    def _request(self, method, path, value=None, *, authority=False):
        if self.capabilities is None:
            raise TransportError("NEGOTIATION_REQUIRED", 503)
        return self.channel.request(method, path, value, epoch=self.capabilities["epoch"], authority=authority)

    def _check_status_scope(self, status, binding, ticket, plan_hash, job_id):
        if (status["job_id"] != job_id or status["epoch"] != self.capabilities["epoch"] or status["plan_sha256"] != plan_hash
                or status["ticket_id"] != ticket["ticket_id"] or status["pins"] != binding["model_pins"]):
            raise TransportError("JOB_CHALLENGE_SCOPE_CHANGED")

    def prepare_prism_preview_candidate(self, wire):
        if self.authority is None or not callable(getattr(self.authority, "authorize_prepare", None)):
            raise TransportError("TRUSTED_PREPARATION_AUTHORITY_REQUIRED", 503)
        # Separate early transmission authorization; never replaces the final
        # after-load revalidation/fence. No bytes leave before this succeeds.
        self.authority.authorize_prepare(wire)
        if not isinstance(wire.data, bytes):
            raise TransportError("IMMUTABLE_WIRE_REQUIRED")
        try:
            value = self._request("POST", BASE + "/prepare", {
                "wire_b64": base64.b64encode(wire.data).decode(), "wire_sha256": sha(wire.data),
                "wire_media_type": wire.media_type, "modality": wire.modality})
        except httpx.TransportError:
            # A missed answer at prepare is a plain retry: no model work starts here.
            raise TransportError("PREPARE_UNAVAILABLE", 503) from None
        if value["pins"] != self.capabilities["pins"] or value["epoch"] != self.capabilities["epoch"]:
            raise TransportError("REMOTE_CONFIG_CHANGED")
        self.tickets[(wire.sha256, wire.modality)] = deepcopy(value)
        mask = base64.b64decode(value["mask_b64"], validate=True) if value["mask_b64"] else None
        return {"status": value["external_fov_status"], "reason_code": value["external_fov_reason_code"],
                "mask_png": mask, "mask_version": value["mask_version"]}

    def refresh_prism_preview_candidate(self, wire):
        value = self.tickets.get((wire.sha256, wire.modality))
        if value is None:
            raise TransportError("CACHE_ONLY_REFRESH_MISSING")
        mask = base64.b64decode(value["mask_b64"], validate=True) if value["mask_b64"] else None
        return {"status": value["external_fov_status"], "reason_code": value["external_fov_reason_code"],
                "mask_png": mask, "mask_version": value["mask_version"]}

    def get_prism_preview_candidate(self, wire):
        return self.refresh_prism_preview_candidate(wire)

    @staticmethod
    def _result(value, binding, plan_hash):
        if value.get("preview_receipt") != {"plan_sha256": plan_hash, "wire_sha256": binding["wire_sha256"],
                                             "mask_sha256": binding["mask_sha256"], "transform_sha256": binding["transform"]["sha256"]}:
            raise TransportError("EXECUTION_RECEIPT_MISMATCH", 502)
        result = LesionResult.model_validate(value["result"])
        pins = binding["model_pins"]
        if (result.model_id != binding["model_id"] or result.model_version != binding["model_version"]
                or result.state != "AI_SUGGESTION" or result.modality != binding["modality"]
                or (result.width, result.height) != (binding["wire_dimensions"]["width"], binding["wire_dimensions"]["height"])
                or result.provenance.image_sha256 != binding["wire_sha256"]
                or result.provenance.source_type != binding["admission"]["source_origin"]
                or result.provenance.source_revision != pins["source_revision"]
                or result.provenance.checkpoint_sha256 != pins["checkpoint_sha256"]
                or result.provenance.preprocessing != pins["preprocessing"]):
            raise TransportError("RESULT_PROVENANCE_MISMATCH", 502)
        if result.modality == "UWF":
            processing = PrismProcessingEvidence.model_validate(value["processing_evidence"])
            if (processing.input_image_sha256 != binding["wire_sha256"]
                    or processing.external_fov_status != binding["external_fov_status"]
                    or len(processing.raw_boundary_classes) != len(result.lesions)):
                raise TransportError("PROCESSING_MISMATCH", 502)
            if processing.native_roi_status == "FAILED" and (processing.processing_mode != "FALLBACK"
                    or processing.fov_used_for_model_input or processing.analysis_field is not None):
                raise TransportError("FALLBACK_MISMATCH", 502)
            if processing.native_roi_status == "SUCCEEDED" and binding["mask_sha256"]:
                field = processing.analysis_field
                if (field is None or not processing.fov_used_for_model_input
                        or field.mask_sha256 != binding["mask_sha256"] or field.source_rgb_sha256 != binding["wire_rgb_sha256"]):
                    raise TransportError("APPLIED_MASK_MISMATCH", 502)
        return value

    def infer_bound_prism(self, request, wire, *, mask_png, binding, plan_sha256, before_forward=None):
        # No old-style callback-only mode. No host job/load if the fence port is absent.
        if self.authority is None or not callable(getattr(self.authority, "acquire", None)) or not callable(before_forward):
            raise TransportError("SOURCE_MUTATION_FENCE_REQUIRED", 503)
        binding = deepcopy(binding)
        if sha(canonical(binding)) != plan_sha256:
            raise TransportError("PLAN_HASH_MISMATCH")
        ticket = self.tickets.pop((wire.sha256, wire.modality), None)
        if ticket is None:
            raise TransportError("PREPARE_ONCE_REQUIRED_NO_RETRY")
        if (request.image_id != binding["image_id"] or request.model_id != binding["model_id"]
                or request.modality != binding["modality"] or wire.image_id != request.image_id
                or wire.source_type != binding["admission"]["source_origin"] or wire.sha256 != binding["wire_sha256"]
                or mask_png != (base64.b64decode(ticket["mask_b64"], validate=True) if ticket["mask_b64"] else None)):
            raise TransportError("FROZEN_REQUEST_CHANGED")
        job_id = None;lease = None;released = False;grant_attempted = False
        try:
            started = self._request("POST", BASE + "/execute", {"ticket_id": ticket["ticket_id"],
                                    "binding": binding, "plan_sha256": plan_sha256})
            job_id = started["job_id"];until = time.monotonic() + self.wait_seconds
            while time.monotonic() < until:
                status = self._request("GET", BASE + "/jobs/" + job_id)
                self._check_status_scope(status, binding, ticket, plan_sha256, job_id)
                if status["state"] == "WAITING_SOURCE_FENCE" and lease is None:
                    # This is the first trusted local callback: remote load and
                    # queue wait have ALREADY completed. Authority must fence
                    # every relevant mutation atomically around this callback.
                    lease = self.authority.acquire(binding, status, before_forward)
                    if not callable(getattr(lease, "release", None)) or not callable(getattr(lease, "quarantine", None)):
                        raise TransportError("REAL_FENCE_LEASE_REQUIRED", 503)
                    grant_attempted = True
                    self._request("POST", BASE + "/jobs/" + job_id + "/grant", {
                        "challenge_id": status["challenge_id"], "fence_id": lease.fence_id,
                        "plan_sha256": plan_sha256}, authority=True)
                if status["forward_started"] and lease is not None and not released:
                    lease.release({"kind": "AUTHENTICATED_STATUS", "status": status});released = True
                if status["terminal"]:
                    if lease is not None and not released:
                        lease.release({"kind": "AUTHENTICATED_STATUS", "status": status});released = True
                    if status["state"] != "COMPLETE":
                        raise TransportError(status["error"] or "REMOTE_TERMINAL_FAILURE")
                    return self._result(status["result"], binding, plan_sha256)
                time.sleep(self.poll_seconds)
            raise RemoteExecutionUncertain("BOUNDED_WAIT_EXPIRED_NO_RETRY", 503)
        except BaseException as error:
            confirmed = False
            if job_id is not None:
                # Cancel is not a terminal receipt. Only a status proof permits
                # release; these calls never resubmit execution or model work.
                try:
                    self._request("POST", BASE + "/jobs/" + job_id + "/cancel")
                    end = time.monotonic() + min(.5, self.wait_seconds)
                    while time.monotonic() < end:
                        state = self._request("GET", BASE + "/jobs/" + job_id)
                        self._check_status_scope(state, binding, ticket, plan_sha256, job_id)
                        if state["terminal"] or state["forward_started"]:
                            confirmed = True;break
                        time.sleep(self.poll_seconds)
                except Exception:
                    pass
            if lease is not None and not released:
                if confirmed or not grant_attempted:
                    lease.release({"kind": "AUTHENTICATED_STATUS", "status": state} if confirmed
                                  else {"kind": "NO_GRANT_SENT"})
                else:
                    lease.quarantine("UNKNOWN_REMOTE_GRANT_OUTCOME_NO_TIMEOUT_RELEASE")
            if isinstance(error, httpx.TransportError):
                raise RemoteExecutionUncertain("TRANSPORT_LOST_NO_AUTOMATIC_RETRY", 503) from None
            raise

    def infer(self, *args, **kwargs):
        raise TransportError("BOUND_FENCED_EXECUTION_ONLY", 503)


class FixedSessionRemoteProvider(RemoteBoundTransportCandidate):
    """Internal offline app-injection port. Real transports cannot instantiate it."""
    prism_preview_protocol = PROTOCOL

    def __init__(self, channel, **kwargs):
        if not isinstance(channel.client._transport, httpx.MockTransport):
            raise TransportError('FIXED_QA_MOCK_TRANSPORT_ONLY', 503)
        super().__init__(channel, **kwargs)
