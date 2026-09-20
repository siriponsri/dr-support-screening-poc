"""Conservative patient and eye resolution for admitted local images.

The resolver deliberately keeps identity separate from the image and from model
inference. Filename parsing is explicit and anchored; OCR is an injectable,
optional fallback that returns candidates and outcome metadata rather than raw
text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol


Laterality = Literal["LEFT", "RIGHT", "UNKNOWN"]
ResolutionState = Literal["RESOLVED", "NEEDS_CONFIRMATION", "UNLINKED", "CONFLICT"]
OCRStatus = Literal[
    "USABLE_CANDIDATE",
    "NO_TEXT_DETECTED",
    "TEXT_UNUSABLE",
    "OCR_UNAVAILABLE",
    "OCR_REQUEST_FAILED",
]


_PATIENT_TOKEN = r"[A-Za-z]{1,12}\d{2,12}"
_FILENAME_WITH_EYE = re.compile(
    rf"^(?P<patient>{_PATIENT_TOKEN})[_-](?P<eye>LEFT|RIGHT|L|R)"
    rf"(?:[_-]?(?P<capture>\d{{1,4}}))?(?:[_-][A-Za-z0-9]+)*$",
    re.IGNORECASE,
)
_PATIENT_ONLY = re.compile(
    rf"^(?P<patient>{_PATIENT_TOKEN})(?:[_-](?:CAPTURE|IMAGE|IMG)[_-]?\d{{1,4}})?$",
    re.IGNORECASE,
)
_AMBIGUOUS_PATIENT = re.compile(
    rf"^(?P<patient>{_PATIENT_TOKEN})[_-][A-Za-z0-9][A-Za-z0-9_-]*$",
    re.IGNORECASE,
)
_PATIENT_KEY = re.compile(r"^(?=[A-Z0-9_-]{3,32}$)(?=.*\d)[A-Z][A-Z0-9_-]*$")


@dataclass(frozen=True)
class FilenameEvidence:
    patient_candidate: str | None
    laterality: Laterality
    parser_status: Literal["MATCHED", "AMBIGUOUS", "NO_MATCH"]
    pattern: str | None


@dataclass(frozen=True)
class OCREvidence:
    status: OCRStatus
    patient_candidate: str | None = None
    laterality: Laterality = "UNKNOWN"
    strength: str | None = None


class OCRAdapter(Protocol):
    """Optional OCR boundary; implementations must not log or expose raw text."""

    def extract(self, image, *, filename: str) -> OCREvidence:
        ...


class DisabledOCRAdapter:
    """Default adapter used when OCR is off or no provider is configured."""

    def __init__(self, status: OCRStatus = "OCR_UNAVAILABLE"):
        self.status = status

    def extract(self, image, *, filename: str) -> OCREvidence:
        return OCREvidence(status=self.status)


def _normalize_patient(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip().upper()
    return candidate if re.fullmatch(_PATIENT_TOKEN, candidate) else None


def normalize_patient_key(value: str) -> str:
    """Validate a short pseudonymous key; names and whitespace are rejected."""
    candidate = value.strip().upper()
    if not _PATIENT_KEY.fullmatch(candidate):
        raise ValueError("Patient key must be a short pseudonymous identifier")
    return candidate


def _normalize_eye(value: str | None) -> Laterality:
    if not value:
        return "UNKNOWN"
    normalized = value.strip().upper()
    return {"L": "LEFT", "LEFT": "LEFT", "R": "RIGHT", "RIGHT": "RIGHT"}.get(
        normalized, "UNKNOWN"
    )  # type: ignore[return-value]


def parse_filename(filename: str) -> FilenameEvidence:
    """Parse only the frozen, explicit filename patterns from the S2A2 spec."""
    stem = Path(filename).stem
    match = _FILENAME_WITH_EYE.fullmatch(stem)
    if match:
        return FilenameEvidence(
            patient_candidate=_normalize_patient(match.group("patient")),
            laterality=_normalize_eye(match.group("eye")),
            parser_status="MATCHED",
            pattern="PATIENT_EYE_CAPTURE",
        )

    match = _PATIENT_ONLY.fullmatch(stem)
    if match:
        return FilenameEvidence(
            patient_candidate=_normalize_patient(match.group("patient")),
            laterality="UNKNOWN",
            parser_status="MATCHED",
            pattern="PATIENT_ONLY",
        )

    match = _AMBIGUOUS_PATIENT.fullmatch(stem)
    if match:
        return FilenameEvidence(
            patient_candidate=_normalize_patient(match.group("patient")),
            laterality="UNKNOWN",
            parser_status="AMBIGUOUS",
            pattern="PATIENT_PREFIX_AMBIGUOUS_SUFFIX",
        )

    return FilenameEvidence(None, "UNKNOWN", "NO_MATCH", None)


def _usable_ocr(ocr: OCREvidence | None) -> OCREvidence | None:
    if ocr is None or ocr.status != "USABLE_CANDIDATE":
        return None
    patient = _normalize_patient(ocr.patient_candidate)
    laterality = _normalize_eye(ocr.laterality)
    if patient is None and laterality == "UNKNOWN":
        return None
    return OCREvidence(ocr.status, patient, laterality, ocr.strength)


def reconcile(filename: FilenameEvidence, ocr: OCREvidence | None = None) -> dict:
    """Reconcile filename and OCR evidence without silently resolving conflicts."""
    usable_ocr = _usable_ocr(ocr)
    file_patient = filename.patient_candidate
    ocr_patient = usable_ocr.patient_candidate if usable_ocr else None
    file_eye = filename.laterality
    ocr_eye = usable_ocr.laterality if usable_ocr else "UNKNOWN"

    patient_conflict = bool(file_patient and ocr_patient and file_patient != ocr_patient)
    if patient_conflict:
        patient_state: ResolutionState = "CONFLICT"
        patient_key = None
        patient_reason = "FILENAME_OCR_CONFLICT"
        patient_method = "FILENAME_AND_OCR"
        patient_candidate = file_patient
    elif file_patient:
        patient_candidate = file_patient
        if filename.parser_status == "AMBIGUOUS":
            patient_state = "NEEDS_CONFIRMATION"
            patient_key = None
            patient_reason = "AMBIGUOUS_FILENAME"
        else:
            patient_state = "RESOLVED"
            patient_key = file_patient
            patient_reason = "FILENAME_MATCH" if not ocr_patient else "FILENAME_OCR_AGREE"
        patient_method = "FILENAME_AND_OCR" if ocr_patient else "FILENAME"
    elif ocr_patient:
        patient_state = "NEEDS_CONFIRMATION"
        patient_key = None
        patient_candidate = ocr_patient
        patient_method = "OCR"
        patient_reason = "OCR_CANDIDATE"
    else:
        patient_state = "UNLINKED"
        patient_key = None
        patient_candidate = None
        patient_method = "NONE"
        patient_reason = "NO_PATIENT_EVIDENCE"

    laterality_conflict = bool(file_eye != "UNKNOWN" and ocr_eye != "UNKNOWN" and file_eye != ocr_eye)
    if laterality_conflict:
        laterality_state: ResolutionState = "CONFLICT"
        laterality = "UNKNOWN"
        laterality_candidate = file_eye
        laterality_method = "FILENAME_AND_OCR"
        laterality_reason = "FILENAME_OCR_LATERALITY_CONFLICT"
    elif file_eye != "UNKNOWN":
        laterality_state = "RESOLVED"
        laterality = file_eye
        laterality_candidate = file_eye
        laterality_method = "FILENAME_AND_OCR" if ocr_eye != "UNKNOWN" else "FILENAME"
        laterality_reason = "FILENAME_OCR_AGREE" if ocr_eye != "UNKNOWN" else "FILENAME_MATCH"
    elif ocr_eye != "UNKNOWN":
        laterality_state = "NEEDS_CONFIRMATION"
        laterality = "UNKNOWN"
        laterality_candidate = ocr_eye
        laterality_method = "OCR"
        laterality_reason = "OCR_LATERALITY_CANDIDATE"
    else:
        laterality_state = "UNLINKED"
        laterality = "UNKNOWN"
        laterality_candidate = None
        laterality_method = "NONE"
        laterality_reason = "NO_LATERALITY_EVIDENCE"

    if patient_state == "CONFLICT" or laterality_state == "CONFLICT":
        overall_state: ResolutionState = "CONFLICT"
    elif patient_state == "NEEDS_CONFIRMATION" or laterality_state == "NEEDS_CONFIRMATION":
        overall_state = "NEEDS_CONFIRMATION"
    elif patient_state == "UNLINKED":
        overall_state = "UNLINKED"
    else:
        overall_state = "RESOLVED"

    ocr_snapshot = {
        "status": ocr.status if ocr else "NOT_RUN",
        "patient_candidate": ocr_patient,
        "laterality": ocr_eye,
        "strength": usable_ocr.strength if usable_ocr else None,
    }
    return {
        "patient_key": patient_key,
        "patient_resolution_state": patient_state,
        "patient_resolution_method": patient_method,
        "patient_reason_code": patient_reason,
        "patient_candidate": patient_candidate,
        "patient_confidence_or_strength": usable_ocr.strength if ocr_patient else None,
        "laterality": laterality,
        "laterality_resolution_state": laterality_state,
        "laterality_resolution_method": laterality_method,
        "laterality_reason_code": laterality_reason,
        "laterality_candidate": laterality_candidate,
        "resolver_state": overall_state,
        "resolver_evidence": {
            "filename": {
                "patient_candidate": filename.patient_candidate,
                "laterality": filename.laterality,
                "parser_status": filename.parser_status,
                "pattern": filename.pattern,
            },
            "ocr": ocr_snapshot,
        },
    }


def combined_resolution_state(patient_state: str, laterality_state: str) -> ResolutionState:
    if patient_state == "CONFLICT" or laterality_state == "CONFLICT":
        return "CONFLICT"
    if patient_state == "NEEDS_CONFIRMATION" or laterality_state == "NEEDS_CONFIRMATION":
        return "NEEDS_CONFIRMATION"
    if patient_state == "UNLINKED":
        return "UNLINKED"
    return "RESOLVED"


class ResolverService:
    """Filename-first resolver with an injectable optional OCR adapter."""

    def __init__(self, ocr_adapter: OCRAdapter | None = None):
        self.ocr_adapter = ocr_adapter or DisabledOCRAdapter()

    def resolve(self, image, filename: str) -> dict:
        parsed = parse_filename(filename)
        needs_fallback = parsed.parser_status != "MATCHED" or parsed.laterality == "UNKNOWN"
        ocr = None
        if needs_fallback and image is not None:
            try:
                ocr = self.ocr_adapter.extract(image, filename=filename)
            except Exception:
                # OCR is an optional enhancement; failure must leave the image usable.
                ocr = OCREvidence(status="OCR_REQUEST_FAILED")
        return reconcile(parsed, ocr)


def apply_automatic_resolution(case: dict, decision: dict, *, timestamp: str) -> dict:
    """Persist first-pass evidence while keeping the audit event compact."""
    fields = (
        "patient_key",
        "patient_resolution_state",
        "patient_resolution_method",
        "patient_reason_code",
        "patient_candidate",
        "patient_confidence_or_strength",
        "laterality",
        "laterality_resolution_state",
        "laterality_resolution_method",
        "laterality_reason_code",
        "laterality_candidate",
        "resolver_state",
        "resolver_evidence",
    )
    for field in fields:
        case[field] = decision[field]
    case.setdefault("resolution_history", []).append(
        {
            "action": "AUTOMATIC_RESOLUTION",
            "method": decision["patient_resolution_method"],
            "timestamp": timestamp,
            "patient": {
                "new": decision["patient_key"],
                "state": decision["patient_resolution_state"],
            },
            "laterality": {
                "new": decision["laterality"],
                "state": decision["laterality_resolution_state"],
            },
        }
    )
    return case


def resolver_clinician_view(case: dict) -> dict:
    """Translate internal resolver state into short clinician-facing copy."""
    patient_state = case.get("patient_resolution_state", "UNLINKED")
    if patient_state == "RESOLVED" and case.get("patient_key"):
        patient = {
            "label": "Patient matched",
            "note": "Patient information was matched for this image.",
            "tone": "success",
            "action_required": False,
        }
    elif patient_state == "CONFLICT":
        patient = {
            "label": "Patient information needs review",
            "note": "The available patient information does not match.",
            "tone": "warning",
            "action_required": True,
        }
    elif patient_state == "NEEDS_CONFIRMATION":
        patient = {
            "label": "Please confirm patient",
            "note": "Patient information was found but needs confirmation.",
            "tone": "warning",
            "action_required": True,
        }
    else:
        patient = {
            "label": "Patient not linked",
            "note": "Choose a patient to continue.",
            "tone": "neutral",
            "action_required": True,
        }

    eye_state = case.get("laterality_resolution_state", "UNLINKED")
    eye = case.get("laterality", "UNKNOWN")
    if eye_state == "RESOLVED" and eye in {"LEFT", "RIGHT"}:
        laterality = {
            "label": f"{eye.title()} eye",
            "note": "Eye side is set for this image.",
            "tone": "success",
            "action_required": False,
        }
    elif eye_state == "RESOLVED" and eye == "UNKNOWN":
        laterality = {
            "label": "Eye side not specified",
            "note": "This image is not assigned to Left or Right.",
            "tone": "neutral",
            "action_required": False,
        }
    else:
        laterality = {
            "label": "Eye side needs confirmation",
            "note": "Choose Left or Right, or leave it as Unknown.",
            "tone": "warning",
            "action_required": True,
        }
    primary = patient if patient["action_required"] else laterality if laterality["action_required"] else patient
    return {
        "label": primary["label"],
        "note": primary["note"],
        "tone": "warning" if patient["action_required"] or laterality["action_required"] else "success",
        "action_required": patient["action_required"] or laterality["action_required"],
        "patient": {**patient, "patient_key": case.get("patient_key"), "candidate": case.get("patient_candidate")},
        "laterality": {**laterality, "value": eye, "candidate": case.get("laterality_candidate")},
    }
