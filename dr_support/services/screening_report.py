"""Screening report (phase 1, owner decision D1): the grader's Refer / Not refer on the approved A4 form.

Stored as one additive field ``screening_report`` on the case JSON. The app never pre-selects or derives the
referral; the person who grades chooses it. A nurse may prepare a report; only a physician, expert or admin signs.
The printable page is HTML laid out for A4; the browser's Print saves it as PDF (Thai names print as typed).
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Literal

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

SIGNING_ROLES = {"physician", "expert", "admin"}
GRADE_NAMES = {0: "0 No apparent DR", 1: "1 Mild NPDR", 2: "2 Moderate NPDR", 3: "3 Severe NPDR", 4: "4 PDR"}
SIGNS = ("Microaneurysms", "Haemorrhages", "Hard exudates", "Cotton wool spots", "Venous beading", "IRMA",
         "New vessels", "Vitreous haemorrhage")
Text = Field(default="", max_length=300)


class _Form(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EyeFindings(_Form):
    quality: Literal["GRADABLE", "UNGRADABLE"] | None = None
    grade: int | None = Field(default=None, ge=0, le=4)
    dme: Literal["NO", "SUSPECTED", "CANNOT_ASSESS"] | None = None
    signs: list[Literal[SIGNS]] = Field(default_factory=list, max_length=len(SIGNS))
    previous_laser: bool | None = None
    other: str = Text


class ReportForm(_Form):
    patient_name: str = Text
    hn: str = Field(default="", max_length=40)
    age_sex: str = Field(default="", max_length=40)
    diabetes_type: Literal["TYPE_1", "TYPE_2", "PREGNANCY"] | None = None
    diabetes_years: str = Field(default="", max_length=20)
    exam_date: str = Field(default="", max_length=40)
    referring_unit: str = Text
    screening_site: str = Text
    previous_screening: str = Field(default="", max_length=40)
    camera: Literal["UWF", "CFP"] | None = None
    dilated: bool | None = None
    va_right: str = Field(default="", max_length=20)
    va_left: str = Field(default="", max_length=20)
    right: EyeFindings = Field(default_factory=EyeFindings)
    left: EyeFindings = Field(default_factory=EyeFindings)
    ai_agreement: Literal["AGREED", "CHANGED"] | None = None
    decision: Literal["NOT_REFER", "REFER", "UNGRADABLE"] | None = None
    rescreen: Literal["ONE_YEAR", "SIX_TO_TWELVE_MONTHS"] | None = None
    refer_to: Literal["OPHTHALMOLOGIST", "RETINA_SPECIALIST"] | None = None
    urgency: Literal["URGENT", "WITHIN_1_MONTH", "WITHIN_3_MONTHS", "OTHER"] | None = None
    remarks: str = Field(default="", max_length=1000)


class ReportUpdate(_Form):
    revision: int = Field(ge=0)
    report: ReportForm
    sign: bool = False
    reviewer: str = Field(default="", max_length=120)   # Used only when sign-in is off.


def _signer(request: Request, update: ReportUpdate) -> tuple[str, str]:
    session = getattr(request.state, "user", None)
    if session is not None:
        return session.username, session.role
    name = update.reviewer.strip()
    if not name:
        raise HTTPException(422, "Enter your name before saving the report.")
    return name, "physician"


def install_screening_report_routes(app):
    def store():
        value = getattr(app.state, "store", None)
        if value is None:
            raise HTTPException(503, "Open a Workspace first.")
        return value

    def case_or_404(image_id: str) -> dict:
        try:
            return store().get(image_id)
        except KeyError:
            raise HTTPException(404, "Image not found.") from None

    @app.get("/v1/cases/{image_id}/screening-report")
    def get_report(image_id: str):
        case = case_or_404(image_id)
        return {"revision": case["revision"], "screening_report": case.get("screening_report")}

    @app.put("/v1/cases/{image_id}/screening-report")
    def save_report(image_id: str, update: ReportUpdate, request: Request):
        name, role = _signer(request, update)
        if update.sign and role not in SIGNING_ROLES:
            raise HTTPException(403, "A nurse prepares the report. A physician signs it.")
        if update.sign and update.report.decision is None:
            raise HTTPException(422, "Choose Refer, Not refer or the ungradable step before signing.")
        cases = store()
        with cases.lock:
            case = cases.get(image_id)
            if update.revision != case["revision"]:
                raise HTTPException(409, "Case changed; reload before saving the report.")
            now = datetime.now(timezone.utc).isoformat()
            previous = case.get("screening_report") or {}
            record = {
                "form": update.report.model_dump(mode="json"),
                "prepared_by": previous.get("prepared_by") or {"name": name, "role": role, "timestamp": now},
                "updated_by": {"name": name, "role": role, "timestamp": now},
                "status": "SIGNED" if update.sign else ("PRELIMINARY" if role == "nurse" else "DRAFT"),
                "signed_by": {"name": name, "role": role, "timestamp": now} if update.sign else None,
                "decision_source": "GRADER_SELECTED",   # Never derived by the software (owner decision D1).
            }
            case["screening_report"] = record
            case["revision"] += 1
            case.setdefault("events", []).append({"action": "SCREENING_REPORT_SAVED", "status": record["status"],
                                                  "by": record["updated_by"], "new_revision": case["revision"]})
            cases.put(case)
            return {"revision": case["revision"], "screening_report": record}

    @app.get("/v1/cases/{image_id}/screening-report/print", response_class=HTMLResponse)
    def print_report(image_id: str):
        case = case_or_404(image_id)
        record = case.get("screening_report") or {}
        return HTMLResponse(render_report(case, record), headers={"Cache-Control": "no-store"})


def _box(checked: bool) -> str:
    return '<span class="box">' + ("&#10003;" if checked else "") + "</span>"


def _choice(value, options: list[tuple[object, str]]) -> str:
    return " ".join(f'<span class="opt">{_box(value == key)}{escape(label)}</span>' for key, label in options)


def render_report(case: dict, record: dict) -> str:
    form = ReportForm.model_validate(record.get("form") or {})
    ai = case.get("global") or {}
    ai_grade = ai.get("grade") if isinstance(ai.get("grade"), int) else None
    status = record.get("status", "NOT STARTED")

    def eye_rows() -> str:
        rows = [
            ("Image quality", lambda eye: _choice(eye.quality, [("GRADABLE", "Gradable"), ("UNGRADABLE", "Ungradable")])),
            ("DR grade (ICDR)", lambda eye: "<br>".join(_choice(eye.grade, [(g, n)]) for g, n in GRADE_NAMES.items())),
            ("Suspected DME", lambda eye: _choice(eye.dme, [("NO", "No"), ("SUSPECTED", "Suspected"), ("CANNOT_ASSESS", "Cannot assess")])
             + '<div class="hint">Confirm with OCT</div>'),
            ("Signs seen", lambda eye: " ".join(f'<span class="opt">{_box(s in eye.signs)}{escape(s)}</span>' for s in SIGNS)),
            ("Previous laser", lambda eye: _choice(eye.previous_laser, [(True, "Yes"), (False, "No")])),
            ("Other findings", lambda eye: escape(eye.other) or "&nbsp;"),
        ]
        return "".join(f"<tr><th>{escape(label)}</th><td>{cell(form.right)}</td><td>{cell(form.left)}</td></tr>"
                       for label, cell in rows)

    def person(key: str) -> str:
        who = record.get(key) or {}
        return escape(f"{who.get('name', '')} ({who.get('role', '')}), {who.get('timestamp', '')[:16].replace('T', ' ')}") if who else "&nbsp;"

    fields = [("Patient name", form.patient_name), ("HN", form.hn), ("Age / Sex", form.age_sex),
              ("Diabetes duration (years)", form.diabetes_years), ("Exam date", form.exam_date),
              ("Referring clinic / unit", form.referring_unit), ("Screening site", form.screening_site),
              ("Previous screening date", form.previous_screening)]
    field_html = "".join(f'<div class="field"><div class="label">{escape(k)}</div><div class="value">{escape(v) or "&nbsp;"}</div></div>'
                         for k, v in fields)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>DR screening report</title>
<style>
@page {{ size: A4; margin: 12mm 14mm; }}
body {{ margin: 0; font-family: 'Sarabun', 'Tahoma', 'Segoe UI', Arial, sans-serif; font-size: 12px; color: #172018; }}
.page {{ max-width: 780px; margin: 0 auto; padding: 12px; }}
.head {{ display: flex; justify-content: space-between; gap: 16px; padding: 10px 14px; background: #F3F8F3;
  border-top: 1px solid #B9D6B9; border-bottom: 2px solid #016301; }}
h1 {{ margin: 0; font-size: 20px; font-weight: 600; color: #016301; }}
h2 {{ margin: 14px 0 6px; padding-bottom: 3px; border-bottom: 1px solid #B9D6B9; font-size: 13px; color: #016301;
  text-transform: uppercase; letter-spacing: .05em; }}
.muted, .hint {{ color: #52605A; }} .hint {{ font-size: 11px; }}
.grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px 12px; }}
.label {{ color: #52605A; }} .value {{ border-bottom: 1px solid #BFCABF; min-height: 16px; }}
table {{ width: 100%; border-collapse: collapse; }} th, td {{ border: 1px solid #BFCABF; padding: 4px 6px; text-align: left; vertical-align: top; }}
thead th {{ background: #E8F3E8; }} tbody th {{ width: 130px; }}
.box {{ display: inline-block; width: 11px; height: 11px; border: 1px solid #172018; margin-right: 4px; text-align: center;
  line-height: 11px; font-size: 10px; vertical-align: -1px; }}
.opt {{ margin-right: 10px; white-space: nowrap; }}
.ai {{ margin-top: 10px; padding: 8px 10px; background: #F1F4F1; border: 1px solid #D8DFD9; }}
.result {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }} .card {{ border: 1px solid #98A79B; padding: 8px 10px; }}
.refer {{ border: 1.5px solid #A73B24; }} .big {{ font-size: 14px; font-weight: 700; }}
.sign {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 10px; }}
.foot {{ margin-top: 14px; padding-top: 6px; border-top: 1px solid #D8DFD9; color: #52605A; font-size: 11px; }}
.toolbar {{ text-align: right; margin-bottom: 8px; }} @media print {{ .toolbar {{ display: none; }} }}
</style></head><body><div class="page">
<div class="toolbar"><button onclick="window.print()">Print / Save as PDF</button></div>
<div class="head"><div><div class="muted">Report status: {escape(status)}</div><h1>Diabetic Retinopathy Screening Report</h1>
<div class="muted">รายงานผลการคัดกรองเบาหวานขึ้นจอประสาทตา</div></div>
<div class="muted" style="text-align:right">Report ID: {escape(case.get("image_id", "")[:16])}<br>Case revision: {case.get("revision", "")}</div></div>
<h2>Patient and examination</h2><div class="grid">{field_html}</div>
<p>Diabetes: {_choice(form.diabetes_type, [("TYPE_1", "Type 1"), ("TYPE_2", "Type 2"), ("PREGNANCY", "Diabetes in pregnancy")])}
&nbsp; Camera: {_choice(form.camera, [("UWF", "UWF"), ("CFP", "CFP")])}
&nbsp; Pupils dilated: {_choice(form.dilated, [(True, "Yes"), (False, "No")])}
&nbsp; Visual acuity: RE 6/{escape(form.va_right) or "____"} LE 6/{escape(form.va_left) or "____"}</p>
<h2>Retinal findings (ICDR, per eye)</h2>
<table><thead><tr><th>Item</th><th>Right eye (RE)</th><th>Left eye (LE)</th></tr></thead><tbody>{eye_rows()}</tbody></table>
<div class="ai"><b>AI suggestion (optional)</b> Model: {escape(str(ai.get("model_id", "none")))} &nbsp;
AI grade: {escape(GRADE_NAMES.get(ai_grade, "no AI result"))} &nbsp;
Reviewer: {_choice(form.ai_agreement, [("AGREED", "Agreed"), ("CHANGED", "Changed the grade")])}
<div class="hint">The AI result is a suggestion, not a diagnosis. Its score is not a calibrated probability. The grade above is the reviewer's.</div></div>
<h2>Screening result (based on the worse eye)</h2>
<div class="result"><div class="card"><div class="big">{_box(form.decision == "NOT_REFER")}Not refer</div>
{_choice(form.rescreen, [("ONE_YEAR", "Rescreen in 1 year"), ("SIX_TO_TWELVE_MONTHS", "Rescreen in 6 to 12 months")])}</div>
<div class="card refer"><div class="big">{_box(form.decision == "REFER")}Refer</div>
{_choice(form.refer_to, [("OPHTHALMOLOGIST", "Ophthalmologist"), ("RETINA_SPECIALIST", "Retina specialist")])}<br>
{_choice(form.urgency, [("URGENT", "Urgent"), ("WITHIN_1_MONTH", "Within 1 month"), ("WITHIN_3_MONTHS", "Within 3 months"), ("OTHER", "Other")])}</div></div>
<p>{_box(form.decision == "UNGRADABLE")}Ungradable image: re-photograph with dilated pupils or refer. An ungradable image is never reported as normal.</p>
<div class="label">Main findings and remarks</div><div class="value">{escape(form.remarks) or "&nbsp;"}</div>
<div class="sign"><div><div class="label">Graded by</div><div class="value">{person("prepared_by")}</div></div>
<div><div class="label">Confirmed by physician</div><div class="value">{person("signed_by")}</div></div></div>
<div class="foot">Screening support only, not a diagnosis. Diabetic macular edema needs OCT or a clinical exam to confirm.
The Refer / Not refer choice is the grader's; the software does not derive it.
Grading: ICDR (2003). References: ICO Guidelines for Diabetic Eye Care (2017); Thai DMS DR screening and referral
recommendations (2026); MOH Singapore Advisory 04/2023.</div>
</div></body></html>"""
