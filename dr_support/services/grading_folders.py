"""Copy plans for optional canonical-snapshot folders; no paths from filenames."""
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json

from .source_identity import source_identity_reason

POLICY = "grading-folders.v1"
GROUPS = ("Grade0", "Grade1", "Grade2", "Grade3", "Grade4", "UNREVIEWED", "UNGRADABLE", "UNDETERMINED")
FORMATS = {"image/png": ".png", "image/jpeg": ".jpg", "image/tiff": ".tif", "application/dicom": ".dcm"}
AUTHORIZATIONS = {"PUBLIC": "ALLOWED_ENGINEERING_PUBLIC", "SYNTHETIC": "ALLOWED_ENGINEERING_SYNTHETIC"}


class GradingFolderError(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _opaque(value):
    return digest(str(value).encode()) if value else None


def _copy_path(group, full_hash, extension, data, files):
    for length in (24, 40, 64):
        relative = f"grading_folders/{group}/image_{full_hash[:length]}{extension}"
        if relative not in files or files[relative] == data:
            return relative
    raise GradingFolderError("Output content collision; existing bytes cannot be overwritten.")


def _group(case, row, image, admission):
    if (case.get("grade_status") == "UNGRADABLE" or admission.get("quality_state") == "UNGRADABLE"):
        return "UNGRADABLE", None, "UNGRADABLE"
    if (case.get("grade_status") == "NEEDS_SECOND_REVIEW" or admission.get("quality_state") == "NEEDS_REVIEW"):
        return "UNDETERMINED", None, "REVIEW_REQUIRED"
    review = case.get("clinician_review") or {}
    if case.get("grade_status") != "CONFIRMED":
        return "UNREVIEWED", None, "NO_CURRENT_CONFIRMED_GRADE"
    grade = review.get("final_grade")
    try:
        stamp = datetime.fromisoformat(str(review.get("timestamp")))
        timestamp_valid = stamp.utcoffset() is not None
    except ValueError:
        timestamp_valid = False
    if (row.get("dr_grade_training_ready") is not True or type(grade) is not int or grade not in range(5)
            or grade != row.get("clinician_grade") or grade != case.get("reviewed_grade")
            or review.get("review_action") not in {"ACCEPT", "CORRECT_GRADE", "ADJUDICATE_GRADE"}
            or not review.get("reviewer") or not timestamp_valid
            or type(review.get("revision")) is not int or type(case.get("revision")) is not int
            or not 1 <= review["revision"] <= case["revision"]
            or review.get("source_sha256") != image.sha256):
        return "UNDETERMINED", None, "CURRENT_REVIEW_PROVENANCE_REQUIRED"
    return f"Grade{grade}", grade, "CURRENT_RECORDED_CLINICIAN_CONFIRMATION"


@dataclass(frozen=True)
class GradingFolderPlan:
    manifest: dict
    files: dict[str, bytes]

    def summary(self):
        return {key: value for key, value in self.manifest.items() if key != "items"}


def plan_grading_folders(cases, rows, sources, admissions) -> GradingFolderPlan:
    """Freeze source bytes against the same rows/cases as the canonical snapshot.

    Numeric groups use a stricter explicit-source review requirement than legacy
    label exports. Organization never grants clinical roles or training approval.
    """
    row_by_id = {row["image_id"]: row for row in rows}
    if len(row_by_id) != len(rows):
        raise GradingFolderError("Duplicate record identities prevent folder planning.")
    items = []
    payloads = {}
    for case in cases:
        image_id = str(case["image_id"])
        row = row_by_id[image_id]
        image = sources.get(image_id)
        admission = case.get("admission") or admissions.get(image_id) or {}
        live_admission = admissions.get(image_id)
        origin = row.get("source_origin")
        if (origin not in AUTHORIZATIONS or row.get("export_authorization") != AUTHORIZATIONS[origin]
                or admission.get("source_origin") != origin
                or (live_admission is not None and live_admission.get("source_origin") != origin)
                or (image is not None and image.source_origin not in {origin, "UNKNOWN"})):
            raise GradingFolderError("Grading-folder export requires existing public/synthetic engineering authorization; hospital export remains disabled.")
        review = case.get("clinician_review") or {}
        item = dict(record_key=_opaque(image_id), source_sha256=row.get("source_sha256"),
                    case_revision=case.get("revision"), group="UNDETERMINED", confirmed_grade=None,
                    review_revision=review.get("revision"), annotator_key=_opaque(review.get("reviewer")),
                    patient_group_digest=_opaque(row.get("training_group_key")), laterality=row.get("laterality"),
                    exam_group_digest=_opaque(row.get("visit_key")), grade_source=row.get("grade_provenance"),
                    output_path=None, output_sha256=None, duplicate_of=None, status="SKIPPED", reason=None)
        reason = source_identity_reason(case, image, admission)
        for proof in (admission, live_admission):
            if proof is None:
                continue
            reason = reason or source_identity_reason(case, image, proof)
            metadata = proof.get("source_metadata") or {}
            if not isinstance(metadata, dict) or metadata.get("integrity_status") not in {None, "OK", "DUPLICATE_CONTENT"}:
                reason = reason or "SOURCE_INTEGRITY_FAILED"
            elif image is not None and metadata.get("source_sha256") not in {None, image.sha256}:
                reason = reason or "SOURCE_HASH_MISMATCH"
        if live_admission is not None and live_admission != admission:
            reason = reason or "ADMISSION_PROJECTIONS_DISAGREE"
        if reason is None:
            for recorded in (case.get("image_sha256"), case.get("source_sha256"), row.get("source_sha256")):
                if recorded is not None and recorded != image.sha256:
                    reason = "SOURCE_HASH_MISMATCH"
        if reason is None and (case.get("queue_state", "INCLUDED") != "INCLUDED"
                               or admission.get("modality_admission") != "FUNDUS_ACCEPTED"):
            reason = "EXCLUDED_OR_UNSUPPORTED_ADMISSION"
        if reason is None and image.media_type not in FORMATS:
            reason = "UNSUPPORTED_COPY_FORMAT"
        if reason is not None:
            item["reason"] = reason
        else:
            item["group"], item["confirmed_grade"], item["reason"] = _group(case, row, image, admission)
            item["source_sha256"] = image.sha256
            item["status"] = "PLANNED_COPY"
            payloads[item["record_key"]] = (bytes(image.data), FORMATS[image.media_type])
        items.append(item)
    if len(items) != len(rows) or len({item["record_key"] for item in items}) != len(items):
        raise GradingFolderError("Snapshot rows and folder record identities disagree.")

    aliases = defaultdict(list)
    for item in items:
        if item["status"] == "PLANNED_COPY":
            aliases[item["source_sha256"]].append(item)
    for records in aliases.values():
        grades = {item["confirmed_grade"] for item in records if item["confirmed_grade"] is not None}
        patients = {item["patient_group_digest"] for item in records if item["patient_group_digest"]}
        if len(grades) > 1 or len(patients) > 1:
            for item in records:
                item.update(group="UNDETERMINED", confirmed_grade=None, reason="DUPLICATE_CONTENT_LABEL_OR_IDENTITY_CONFLICT")

    files, first = {}, {}
    for item in sorted(items, key=lambda entry: entry["record_key"]):
        if item["status"] != "PLANNED_COPY":
            continue
        data, extension = payloads[item["record_key"]]
        full_hash = digest(data)
        relative = _copy_path(item["group"], full_hash, extension, data, files)
        if relative in first:
            item["duplicate_of"] = first[relative]
        else:
            first[relative] = item["record_key"]
            files[relative] = data
        item.update(output_path=relative, output_sha256=digest(data))
    counts = Counter(item["group"] for item in items if item["output_path"])
    skipped = Counter(item["reason"] for item in items if not item["output_path"])
    manifest = dict(schema_version=POLICY, policy_version=POLICY,
                    status="READY" if files else "NO_COPYABLE_SOURCES", source_immutability="COPY_ONLY_ORIGINAL_BYTES",
                    record_count=len(items), file_count=len(files), copy_bytes=sum(map(len, files.values())),
                    group_counts={group: counts[group] for group in GROUPS}, skipped_count=sum(skipped.values()),
                    skipped_reasons=dict(sorted(skipped.items())),
                    duplicate_record_count=sum(item["duplicate_of"] is not None for item in items),
                    training_readiness="ORGANIZATION_ONLY; see canonical task-specific labels/completeness",
                    role_verification="NOT_ESTABLISHED_BY_FOLDER_ORGANIZATION", items=sorted(items, key=lambda item: item["record_key"]))
    manifest["plan_sha256"] = digest(encoded(manifest))
    return GradingFolderPlan(manifest=manifest, files=files)
