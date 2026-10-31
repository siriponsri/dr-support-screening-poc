"""Gold-100 research labelling (phase 1 spec 3.5): the expert grades before seeing any AI suggestion.

Flow per image: save the blind label -> reveal the AI suggestion (the blind label is then locked) -> save the
final grade (the same or changed). Both grades are kept with provenance. Stored as the additive case field
``gold_label``, apart from screening grades; nothing here changes the clinical review. Writes are for the expert
(or the administrator account); the research export is for experts, researchers and the administrator.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

WRITERS = {"expert", "admin"}
READERS = {"expert", "researcher", "admin"}
QUADRANTS = ("superior", "inferior", "nasal", "temporal")
QuadrantSign = Literal["HAEMORRHAGES", "VENOUS_BEADING", "IRMA", "NEW_VESSELS", "HARD_EXUDATES_NEAR_FOVEA"]


class _Form(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BlindLabel(_Form):
    gradable: bool
    grade: int | None = Field(default=None, ge=0, le=4)
    quality_issue: Literal["NONE", "BLUR", "EYELID_OR_LASHES", "SMALL_PUPIL", "MEDIA_OPACITY", "ARTIFACT", "OTHER"] = "NONE"
    laterality: Literal["RIGHT", "LEFT", "UNKNOWN"] = "UNKNOWN"
    confidence: Literal["SURE", "UNSURE"] | None = None
    quadrant_signs: dict[Literal[QUADRANTS], list[QuadrantSign]] = Field(default_factory=dict)
    dme_suspected: bool | None = None
    selection_reason: Literal["TYPICAL", "HARD", "SEVERE", "RARE", "OTHER"] | None = None
    note: str = Field(default="", max_length=500)


class BlindUpdate(_Form):
    revision: int = Field(ge=0)
    label: BlindLabel
    seconds_spent: int = Field(default=0, ge=0, le=86_400)
    reviewer: str = Field(default="", max_length=120)


class RevealRequest(_Form):
    revision: int = Field(ge=0)
    reviewer: str = Field(default="", max_length=120)


class FinalUpdate(_Form):
    revision: int = Field(ge=0)
    grade: int | None = Field(default=None, ge=0, le=4)
    note: str = Field(default="", max_length=500)
    seconds_spent: int = Field(default=0, ge=0, le=86_400)
    reviewer: str = Field(default="", max_length=120)


def _who(request: Request, reviewer: str, allowed: set[str]) -> dict:
    session = getattr(request.state, "user", None)
    if session is not None:
        if session.role not in allowed:
            raise HTTPException(403, "Gold labels are for the ophthalmologist (expert) account.")
        return {"name": session.username, "role": session.role}
    if not reviewer.strip():
        raise HTTPException(422, "Enter your name first.")
    return {"name": reviewer.strip(), "role": "expert"}


def install_gold_label_routes(app):
    def store():
        value = getattr(app.state, "store", None)
        if value is None:
            raise HTTPException(503, "Open a Workspace first.")
        return value

    def mutate(image_id: str, revision: int, change):
        cases = store()
        with cases.lock:
            try:
                case = cases.get(image_id)
            except KeyError:
                raise HTTPException(404, "Image not found.") from None
            if revision != case["revision"]:
                raise HTTPException(409, "Case changed; reload before saving.")
            record = dict(case.get("gold_label") or {})
            result = change(case, record)
            case["gold_label"] = record
            case["revision"] += 1
            cases.put(case)
            return {"revision": case["revision"], "gold_label": record, **(result or {})}

    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @app.get("/v1/cases/{image_id}/gold-label")
    def get_gold(image_id: str):
        try:
            case = store().get(image_id)
        except KeyError:
            raise HTTPException(404, "Image not found.") from None
        record = case.get("gold_label") or {}
        reveal = {"ai_grade": record.get("ai_at_reveal")} if record.get("ai_revealed_at") else {}
        return {"revision": case["revision"], "gold_label": record or None, **reveal}

    @app.put("/v1/cases/{image_id}/gold-label/blind")
    def save_blind(image_id: str, update: BlindUpdate, request: Request):
        who = _who(request, update.reviewer, WRITERS)
        if update.label.gradable and update.label.grade is None:
            raise HTTPException(422, "Choose a grade, or mark the image ungradable.")

        def change(case, record):
            if record.get("ai_revealed_at"):
                raise HTTPException(409, "The AI suggestion has been shown; your blind grade is kept as saved.")
            record["blind"] = {**update.label.model_dump(mode="json"), "grade": update.label.grade if update.label.gradable else None,
                               "by": who, "timestamp": now(), "seconds_spent": update.seconds_spent}
            record["provenance"] = "clinician_verified"
        return mutate(image_id, update.revision, change)

    @app.post("/v1/cases/{image_id}/gold-label/reveal-ai")
    def reveal_ai(image_id: str, update: RevealRequest, request: Request):
        who = _who(request, update.reviewer, WRITERS)

        def change(case, record):
            if not record.get("blind"):
                raise HTTPException(409, "Save your own grade first; the AI suggestion stays hidden until then.")
            if not record.get("ai_revealed_at"):
                ai = case.get("global") or {}
                grade = ai.get("grade") if isinstance(ai.get("grade"), int) else None
                record["ai_at_reveal"] = {"grade": grade, "model_id": ai.get("model_id"), "provenance": "model_suggestion"}
                record["ai_revealed_at"] = now()
                record["ai_revealed_by"] = who
            return {"ai_grade": record["ai_at_reveal"]}
        return mutate(image_id, update.revision, change)

    @app.put("/v1/cases/{image_id}/gold-label/final")
    def save_final(image_id: str, update: FinalUpdate, request: Request):
        who = _who(request, update.reviewer, WRITERS)

        def change(case, record):
            if not record.get("blind"):
                raise HTTPException(409, "Save your own grade first.")
            blind = record["blind"].get("grade")
            record["after_ai"] = {"grade": update.grade, "changed": update.grade != blind, "note": update.note,
                                  "ai_seen": bool(record.get("ai_revealed_at")), "by": who, "timestamp": now(),
                                  "seconds_spent": update.seconds_spent}
        return mutate(image_id, update.revision, change)

    @app.get("/v1/research/gold-labels")
    def export_gold(request: Request):
        session = getattr(request.state, "user", None)
        if session is not None and session.role not in READERS:
            raise HTTPException(403, "The Gold-100 export is for experts, researchers and the administrator.")
        cases = store()
        rows = []
        with cases.lock:
            for case in cases.all_cases():
                record = case.get("gold_label")
                if record and record.get("blind"):
                    rows.append({"image_id": case["image_id"], "modality": case.get("modality"),
                                 "source_sha256": (case.get("admission") or {}).get("source_sha256"), **record})
        return {"schema": "dr-gold-labels.v1", "count": len(rows), "items": rows,
                "note": "Gold labels are clinician_verified; AI values are model_suggestion and never Gold."}
