"""Admin database view for the physician UX pilot: read-only, administrators only.

Shows what the app has stored for the open workspace: a summary, a paged case
list and one case's stored record. Nothing here writes, deletes or exports. The
view can contain patient data, so it is limited to the signed-in administrator
on this workstation and is never part of a public report.
"""
from __future__ import annotations

import json

from fastapi import HTTPException, Request

MAX_PAGE = 100
MAX_RECORD_BYTES = 2_000_000


def _latest(history, task):
    items = [item for item in history or [] if item.get("task") == task and isinstance(item.get("result"), dict)]
    return items[-1] if items else None


def _row(case: dict) -> dict:
    history = case.get("inference_history") or []
    grade = _latest(history, "global")
    prism = _latest(history, "lesion-roi")
    admission = case.get("admission") or {}
    return {
        "image_id": case.get("image_id"),
        "revision": case.get("revision"),
        "modality": admission.get("retinal_modality") or case.get("modality"),
        "source_origin": admission.get("source_origin"),
        "ai_grade": (grade or {}).get("result", {}).get("grade"),
        "ai_model": (grade or {}).get("model_id"),
        "prism_saved": prism is not None,
        "clinician_grade": case.get("reviewed_grade"),
        "grade_status": case.get("grade_status"),
        "grade_source": case.get("grade_review_source"),
        "lesion_review": (case.get("lesion_review_state") or {}).get("state")
        if isinstance(case.get("lesion_review_state"), dict) else case.get("lesion_review_state"),
        "annotations": len(case.get("annotations") or []),
        "ai_runs": len(history),
    }


def install_pilot_admin(app, require_admin):
    """``require_admin(request)`` raises unless the signed-in user is an administrator."""

    def store_kind():
        name = type(app.state.store).__name__
        return "PostgreSQL" if "Postgres" in name else "SQLite" if name == "Store" else name

    def cases():
        try:
            return [case for case in app.state.store.all_cases() if isinstance(case, dict)]
        except Exception:
            raise HTTPException(503, "The database could not be read right now.") from None

    @app.get("/v1/admin/db/summary")
    def summary(request: Request):
        require_admin(request)
        rows = [_row(case) for case in cases()]
        manager = getattr(app.state, "workspace_manager", None)
        workspace = getattr(manager, "active_workspace", None)
        batches = getattr(app.state, "regular_batches", None)
        return {
            "storage": store_kind(),
            "workspace": {"id": workspace.id, "name": workspace.name} if workspace is not None else None,
            "cases": len(rows),
            "with_ai_grade": sum(row["ai_grade"] is not None for row in rows),
            "with_prism": sum(row["prism_saved"] for row in rows),
            "grade_confirmed": sum(row["grade_status"] == "CONFIRMED" for row in rows),
            "grade_corrected": sum(row["grade_source"] == "AI_CORRECTED" for row in rows),
            "annotations": sum(row["annotations"] for row in rows),
            "batches": len(batches.list()) if batches is not None else 0,
        }

    @app.get("/v1/admin/db/cases")
    def case_list(request: Request, offset: int = 0, limit: int = 25, search: str = ""):
        require_admin(request)
        limit = max(1, min(int(limit), MAX_PAGE))
        offset = max(0, int(offset))
        rows = sorted((_row(case) for case in cases()), key=lambda row: str(row["image_id"]))
        if search.strip():
            needle = search.strip().lower()
            rows = [row for row in rows if needle in str(row["image_id"]).lower()]
        return {"total": len(rows), "offset": offset, "limit": limit, "rows": rows[offset:offset + limit]}

    @app.get("/v1/admin/db/cases/{image_id}")
    def case_record(request: Request, image_id: str):
        require_admin(request)
        try:
            record = app.state.store.get(image_id)
        except Exception:
            raise HTTPException(404, "No stored record for this image.") from None
        raw = json.dumps(record, default=str)
        if len(raw) > MAX_RECORD_BYTES:
            raise HTTPException(413, "This record is too large to show here.")
        return {"image_id": image_id, "record": json.loads(raw)}
