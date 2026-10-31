"""Referral list and an open connector for external systems (owner request, 31 October 2026).

No referral rule is derived here (owner decision D1): a referral exists only when a screening report is SIGNED
and the person who graded chose Refer (or the ungradable step). Each referral can be exported as an HL7 FHIR R4
``ServiceRequest`` bundle or CSV, and sent through one connector the administrator configures:

- ``none`` (default): nothing leaves the app.
- ``file_drop``: writes the FHIR JSON into a folder that a hospital integration engine reads.
- ``webhook``: POSTs the FHIR JSON to an HTTPS endpoint (plain HTTP only to this machine); the bearer token is
  read from an environment variable named in the setting, never stored or shown.

Every attempt is recorded on the case (``referral_delivery``); there is no automatic resend. Sending patient
data outside the hospital needs the hospital's approval before a connector is configured.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException, Request
from fastapi.responses import Response

CONNECTORS = {"none": "Off (nothing leaves the app)", "file_drop": "File drop folder", "webhook": "HTTPS webhook"}
SENDERS = {"physician", "expert", "admin"}
FILE_NAME = "referral-connector.json"
ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]{2,63}")
GRADE_NAMES = {0: "No apparent DR", 1: "Mild NPDR", 2: "Moderate NPDR", 3: "Severe NPDR", 4: "PDR"}
URGENCY_PRIORITY = {"URGENT": "urgent", "WITHIN_1_MONTH": "asap", "WITHIN_3_MONTHS": "routine", "OTHER": "routine"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def referral_of(case: dict) -> dict | None:
    """A referral only from a signed report whose grader chose Refer or the ungradable step."""
    report = case.get("screening_report") or {}
    form = report.get("form") or {}
    if report.get("status") != "SIGNED" or form.get("decision") not in {"REFER", "UNGRADABLE"}:
        return None
    signed = report.get("signed_by") or {}
    return {
        "image_id": case["image_id"], "decision": form["decision"], "refer_to": form.get("refer_to"),
        "urgency": form.get("urgency"), "patient_name": form.get("patient_name", ""), "hn": form.get("hn", ""),
        "right_grade": (form.get("right") or {}).get("grade"), "left_grade": (form.get("left") or {}).get("grade"),
        "signed_by": signed.get("name"), "signed_at": signed.get("timestamp"), "remarks": form.get("remarks", ""),
        "decision_source": "GRADER_SELECTED", "deliveries": case.get("referral_delivery") or [],
    }


def fhir_bundle(referral: dict) -> dict:
    """A small FHIR R4 collection Bundle: Patient, two Observations (ICDR grade per eye), ServiceRequest."""
    rid = referral["image_id"][:32]
    patient = {"resourceType": "Patient", "id": f"patient-{rid}",
               "identifier": [{"system": "urn:hospital:hn", "value": referral["hn"]}] if referral["hn"] else [],
               "name": [{"text": referral["patient_name"]}] if referral["patient_name"] else []}
    observations = []
    for side, code in (("right", "24028007"), ("left", "7771000")):   # SNOMED CT body sites: right eye, left eye
        grade = referral[f"{side}_grade"]
        if isinstance(grade, int):
            observations.append({
                "resourceType": "Observation", "id": f"dr-grade-{side}-{rid}", "status": "final",
                "code": {"text": "Diabetic retinopathy grade (ICDR 2003)"},
                "subject": {"reference": f"Patient/patient-{rid}"},
                "bodySite": {"coding": [{"system": "http://snomed.info/sct", "code": code, "display": f"{side.title()} eye"}]},
                "valueCodeableConcept": {"text": f"{grade} {GRADE_NAMES.get(grade, '')}".strip()},
                "note": [{"text": "Grade chosen by the reviewer; AI output is a suggestion only."}],
            })
    reason = "Ungradable retinal image: re-photograph or refer" if referral["decision"] == "UNGRADABLE" else "Diabetic retinopathy screening: refer"
    service = {
        "resourceType": "ServiceRequest", "id": f"referral-{rid}", "status": "active", "intent": "order",
        "priority": URGENCY_PRIORITY.get(referral["urgency"] or "", "routine"),
        "code": {"text": {"OPHTHALMOLOGIST": "Referral to ophthalmologist", "RETINA_SPECIALIST": "Referral to retina specialist"}
                 .get(referral["refer_to"] or "", "Referral to eye care")},
        "subject": {"reference": f"Patient/patient-{rid}"},
        "reasonCode": [{"text": reason}],
        "supportingInfo": [{"reference": f"Observation/{item['id']}"} for item in observations],
        "authoredOn": referral["signed_at"],
        "requester": {"display": referral["signed_by"] or ""},
        "note": [{"text": "Screening support only, not a diagnosis. The Refer decision was chosen by the grader."}]
                + ([{"text": referral["remarks"]}] if referral["remarks"] else []),
    }
    return {"resourceType": "Bundle", "type": "collection", "timestamp": _now(),
            "entry": [{"resource": resource} for resource in (patient, *observations, service)]}


def read_connector(config_dir: Path) -> dict:
    try:
        value = json.loads((Path(config_dir) / FILE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        value = {}
    kind = value.get("kind") if value.get("kind") in CONNECTORS else "none"
    return {"kind": kind, "folder": value.get("folder", ""), "url": value.get("url", ""),
            "token_env": value.get("token_env", ""), "updated_by": value.get("updated_by"), "updated_utc": value.get("updated_utc")}


def validate_connector(body: dict) -> dict:
    kind = body.get("kind")
    if kind not in CONNECTORS:
        raise HTTPException(422, "Choose off, file drop or webhook.")
    record = {"kind": kind, "folder": "", "url": "", "token_env": ""}
    if kind == "file_drop":
        folder = str(body.get("folder", "")).strip()
        if not folder or not Path(folder).is_absolute() or ".." in Path(folder).parts:
            raise HTTPException(422, "Give the full path of the drop folder.")
        record["folder"] = folder
    if kind == "webhook":
        url = str(body.get("url", "")).strip()
        parsed = urlparse(url)
        local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or (parsed.scheme == "http" and not local):
            raise HTTPException(422, "Use an https:// address (plain http only to this machine).")
        token_env = str(body.get("token_env", "")).strip()
        if token_env and not ENV_NAME.fullmatch(token_env):
            raise HTTPException(422, "The token setting is the NAME of an environment variable, such as REFERRAL_TOKEN.")
        record.update(url=url, token_env=token_env)
    return record


def deliver(connector: dict, referral: dict, *, post=None) -> dict:
    """One attempt, no retry. Returns the attempt record; never raises for a delivery failure."""
    body = json.dumps(fhir_bundle(referral), ensure_ascii=False).encode("utf-8")
    attempt = {"connector": connector["kind"], "at": _now()}
    try:
        if connector["kind"] == "file_drop":
            folder = Path(connector["folder"])
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / f"referral-{referral['image_id'][:32]}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
            with target.open("xb") as handle:
                handle.write(body)
            return {**attempt, "status": "WRITTEN", "detail": target.name}
        if connector["kind"] == "webhook":
            headers = {"Content-Type": "application/fhir+json"}
            token = os.environ.get(connector["token_env"], "") if connector["token_env"] else ""
            if token:
                headers["Authorization"] = "Bearer " + token
            if post is None:
                import httpx
                post = lambda url, content, headers: httpx.post(url, content=content, headers=headers, timeout=15)  # noqa: E731
            reply = post(connector["url"], body, headers)
            status = getattr(reply, "status_code", 0)
            return {**attempt, "status": "SENT" if 200 <= status < 300 else "FAILED", "http_status": status}
        return {**attempt, "status": "NOT_SENT", "detail": "No connector is configured."}
    except Exception as error:   # A failed attempt is recorded, not retried automatically.
        return {**attempt, "status": "FAILED", "detail": type(error).__name__}


def install_referral_routes(app):
    """Referral list, exports and send. The connector setting lives where the sign-in files live."""
    def store():
        value = getattr(app.state, "store", None)
        if value is None:
            raise HTTPException(503, "Open a Workspace first.")
        return value

    def settings_dir() -> Path:
        value = getattr(app.state, "referral_config_dir", None)
        if value is None:
            raise HTTPException(503, "Referral connectors need sign-in to be configured.")
        return value

    def referrals() -> list[dict]:
        cases = store()
        with cases.lock:
            return [item for item in (referral_of(case) for case in cases.all_cases()) if item]

    @app.get("/v1/referrals")
    def list_referrals():
        return {"items": referrals(), "decision_source": "GRADER_SELECTED",
                "note": "Only signed screening reports where the grader chose Refer or the ungradable step."}

    @app.get("/v1/referrals.csv")
    def referrals_csv():
        output = io.StringIO()
        fields = ["image_id", "decision", "refer_to", "urgency", "patient_name", "hn", "right_grade", "left_grade",
                  "signed_by", "signed_at", "remarks"]
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for item in referrals():
            writer.writerow({key: ("'" + value if isinstance(value, str) and value[:1] in "=+-@" else value)
                             for key, value in item.items()})   # Spreadsheet formula injection guard.
        return Response(output.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=referrals.csv", "Cache-Control": "no-store"})

    @app.get("/v1/referrals/{image_id}/fhir")
    def referral_fhir(image_id: str):
        try:
            case = store().get(image_id)
        except KeyError:
            raise HTTPException(404, "Image not found.") from None
        referral = referral_of(case)
        if referral is None:
            raise HTTPException(409, "This image has no signed Refer decision.")
        return Response(json.dumps(fhir_bundle(referral), ensure_ascii=False), media_type="application/fhir+json")

    @app.post("/v1/referrals/{image_id}/send")
    def send_referral(image_id: str, request: Request):
        session = getattr(request.state, "user", None)
        if session is not None and session.role not in SENDERS:
            raise HTTPException(403, "A physician or the administrator sends referrals.")
        connector = read_connector(settings_dir())
        if connector["kind"] == "none":
            raise HTTPException(409, "No referral connector is configured. The administrator sets one on the Admin page.")
        cases = store()
        with cases.lock:
            try:
                case = cases.get(image_id)
            except KeyError:
                raise HTTPException(404, "Image not found.") from None
            referral = referral_of(case)
            if referral is None:
                raise HTTPException(409, "This image has no signed Refer decision.")
            attempt = {**deliver(connector, referral), "by": getattr(session, "username", None)}
            case.setdefault("referral_delivery", []).append(attempt)
            case["revision"] += 1
            cases.put(case)
        return attempt



def install_referral_admin(app, require_admin, config_dir: Path):
    """Administrator setting for the connector, beside the accounts file."""
    config_dir = Path(config_dir)
    app.state.referral_config_dir = config_dir

    @app.get("/v1/admin/referral-connector")
    def get_connector(request: Request):
        require_admin(request)
        return {**read_connector(config_dir), "kinds": CONNECTORS}

    @app.put("/v1/admin/referral-connector")
    def set_connector(request: Request, body: dict):
        acting = require_admin(request)
        record = {**validate_connector(body), "updated_by": acting.username, "updated_utc": _now()}
        config_dir.mkdir(parents=True, exist_ok=True)
        temporary = config_dir / (FILE_NAME + ".tmp")
        temporary.write_text(json.dumps(record, indent=2), encoding="utf-8")
        os.replace(temporary, config_dir / FILE_NAME)
        return {**read_connector(config_dir), "kinds": CONNECTORS}
