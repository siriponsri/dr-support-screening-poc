"""Durable review API with optimistic concurrency and explicit human actions.

What lives here:
- module-level helpers that decide which stored AI result is current for the confirmed image
  (`_current_global_result`, `_spatial_ai_display`, ...) and the request contracts (`Review`,
  `ConfirmImage`, `HumanAnnotationSave`, ...);
- `install_workflow`: builds the shared per-app helpers (admission record, resolver refresh, the case
  `detail` view, annotation geometry checks) and then installs the route groups from
  `dr_support/workflow_routes/` in their original order.
"""
import math
from dataclasses import dataclass
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal
from fastapi import HTTPException
from pydantic import Field
from .contracts import Contract, GlobalResult
from .cvat import CVATOnline
from .presentation import annotation_set_hash, lesion_review_view, review_evidence_view
from .services.admission import clinician_view, legacy_admission
from .services.source_identity import record_source_identity_on_creation, source_identity_reason
from .services import artifact_roi_assist
from .services.source_mutation_gate import guard_writes, writer_scope
from .services.resolver import (
    apply_automatic_resolution,
    automatic_resolution_needs_refresh,
    resolver_clinician_view,
    resolve_authorized_hospital_record,
)
from .services.source_policy import HOSPITAL_ORIGIN, source_allowed_for_model
from .imaging.derivatives import (
    ANALYSIS_COORDINATE_SPACE,
    ANALYSIS_DICOM_PNG_TRANSFORM,
    ANALYSIS_REPRESENTATION_VERSION,
    ANALYSIS_SOURCE_TRANSFORM,
    ANALYSIS_TIFF_PNG_TRANSFORM,
    ANALYSIS_UWF_MASK_TRANSFORM,
    ANALYSIS_UWF_SOURCE_REPRESENTATION_VERSION,
    ANALYSIS_UWF_SOURCE_TRANSFORM,
    ORIGINAL_COORDINATE_SPACE,
)
from .grade import (
    GRADE_STATUS_NOT_REVIEWED,
    grade_label,
)
from .referral import current_referral
from .services.patient_presentation import (
    DISPLAY_INDICES, hospital_patient_label,
)


KNOWN_ANALYSIS_TRANSFORMS = frozenset({
    ANALYSIS_SOURCE_TRANSFORM,
    ANALYSIS_TIFF_PNG_TRANSFORM,
    ANALYSIS_DICOM_PNG_TRANSFORM,
    ANALYSIS_UWF_MASK_TRANSFORM,
    ANALYSIS_UWF_SOURCE_TRANSFORM,
})


def _source_origin(record, image):
    """Resolve origin from explicit admission/image facts without relabeling unknown data."""
    allowed = {'PUBLIC', 'SYNTHETIC', 'WORKSPACE', HOSPITAL_ORIGIN, 'UNKNOWN'}
    record_origin = (record or {}).get('source_origin')
    if record_origin in allowed:
        return record_origin
    image_origin = getattr(image, 'source_origin', None) if image is not None else None
    if image_origin in allowed and image_origin != 'UNKNOWN':
        return image_origin
    if image is not None and image.source_type in {'PUBLIC', 'SYNTHETIC'}:
        return image.source_type
    return 'UNKNOWN'


def _global_result_matches_modality(result, modality, source_origin):
    if not isinstance(result, dict) or result.get('modality') != modality:
        return False
    if not source_allowed_for_model(source_origin):
        return False
    model_id = result.get('model_id')
    if modality == 'CFP':
        return model_id == 'retfound-aptos5' or (
            model_id == 'mock-global' and source_origin == 'SYNTHETIC'
        )
    if modality == 'UWF':
        return model_id == 'uspec-uwf-grading'
    return False


def _lesion_result_matches_modality(result, modality, source_origin):
    return (
        isinstance(result, dict)
        and (
            result.get('model_id') == 'prism-dr-5fold'
            or (result.get('model_id') == 'mock-lesion' and source_origin == 'SYNTHETIC')
        )
        and result.get('modality') == modality
        and modality in {'CFP', 'UWF'}
        and source_allowed_for_model(source_origin)
    )


def _current_global_result(case, image, admission):
    """Project only source-bound, non-superseded grading evidence; never infer."""
    result = case.get('global')
    origin = _source_origin(admission, image)
    if source_identity_reason(case, image, admission) or not _global_result_matches_modality(
        result, (admission or {}).get('retinal_modality', 'UNKNOWN'), origin,
    ):
        return None
    try:
        GlobalResult.model_validate(result)
    except ValueError:
        return None
    provenance = result.get('provenance') or {}
    if (provenance.get('source_type') != origin
            or not result.get('model_version', '').strip()
            or not provenance.get('source_revision', '').strip()):
        return None
    derivative = case.get('analysis_derivative') or {}
    source_sha = image.sha256
    analysis_sha = source_sha
    transform = 'IDENTITY'
    representation = 'ORIGINAL'
    if derivative:
        analysis_sha = derivative.get('analysis_sha256')
        transform = derivative.get('transform_id')
        representation = derivative.get('representation_version')
        lineage = derivative.get('lineage') or {}
        if (derivative.get('source_sha256') != source_sha
                or derivative.get('source_origin') != origin
                or derivative.get('derivative_sha256') != analysis_sha
                or transform not in KNOWN_ANALYSIS_TRANSFORMS
                or representation not in {ANALYSIS_REPRESENTATION_VERSION, ANALYSIS_UWF_SOURCE_REPRESENTATION_VERSION}
                or lineage.get('purpose') != 'ANALYSIS'
                or lineage.get('source_sha256') != source_sha
                or lineage.get('derivative_sha256') != analysis_sha
                or lineage.get('transform_id') != transform):
            return None
    if provenance.get('image_sha256') != analysis_sha:
        return None
    # Legacy results lack run history: require explicit source/analysis binding.
    # Once global history exists, only its latest APPLIED result is authoritative.
    history = [entry for entry in case.get('inference_history', []) if entry.get('task') == 'global']
    if history:
        latest = next((entry for entry in reversed(history) if entry.get('status') == 'APPLIED'), None)
        if (latest is None or latest.get('result') != result
                or latest.get('model_id') != result.get('model_id')
                or latest.get('model_version') != result.get('model_version')
                or latest.get('source_sha256') != source_sha
                or latest.get('analysis_sha256') != analysis_sha
                or latest.get('transform_id') != transform
                or latest.get('representation_version') != representation
                or type(latest.get('case_revision')) is not int
                or not 0 <= latest['case_revision'] <= case['revision']):
            return None
    return result


def _spatial_ai_display(case, image, *, source_origin='UNKNOWN'):
    """Return a safe projection for spatial AI evidence without mutating raw output."""
    lesion = case.get('lesion')
    if not lesion:
        return {
            'status': 'UNAVAILABLE',
            'reason': 'NO_SPATIAL_AI_RESULT',
            'note': 'No AI overlay is available. Review the Original image manually.',
        }
    if image is None:
        return {
            'status': 'BLOCKED',
            'reason': 'SOURCE_UNAVAILABLE',
            'note': 'AI overlay is hidden because the immutable source is unavailable. Review the Original image manually.',
        }
    if not source_allowed_for_model(source_origin):
        return {
            'status': 'BLOCKED',
            'reason': 'SOURCE_ORIGIN_UNSUPPORTED',
            'note': 'AI overlay is hidden because this source is outside the approved model boundary. Review the Original image manually.',
        }

    provenance = lesion.get('provenance') or {}
    derivative = case.get('analysis_derivative') or {}
    source_sha = image.sha256
    result_sha = provenance.get('image_sha256')
    if derivative:
        mapping = derivative.get('coordinate_mapping') or {}
        source_dimensions = derivative.get('source_dimensions') or {}
        analysis_dimensions = derivative.get('analysis_dimensions') or {}
        lineage = derivative.get('lineage') or {}
        canonical_width = image.size[0]
        canonical_height = image.size[1]
        analysis_width = analysis_dimensions.get('width')
        analysis_height = analysis_dimensions.get('height')
        expected_kind = 'IDENTITY' if (canonical_width, canonical_height) == (
            analysis_width, analysis_height,
        ) else 'SCALE'
        if derivative.get('source_sha256') != source_sha:
            reason = 'SOURCE_HASH_MISMATCH'
        elif result_sha != derivative.get('analysis_sha256'):
            reason = 'ANALYSIS_HASH_MISMATCH'
        elif derivative.get('derivative_sha256') != derivative.get('analysis_sha256'):
            reason = 'DERIVATIVE_HASH_MISMATCH'
        elif provenance.get('source_type') != source_origin:
            reason = 'SOURCE_ORIGIN_MISMATCH'
        elif derivative.get('source_origin') != source_origin:
            reason = 'SOURCE_ORIGIN_MISMATCH'
        elif derivative.get('representation_version') not in {
            ANALYSIS_REPRESENTATION_VERSION,
            ANALYSIS_UWF_SOURCE_REPRESENTATION_VERSION,
        }:
            reason = 'REPRESENTATION_VERSION_MISMATCH'
        elif derivative.get('transform_id') not in KNOWN_ANALYSIS_TRANSFORMS:
            reason = 'TRANSFORM_MISMATCH'
        elif (
            lineage.get('purpose') != 'ANALYSIS'
            or lineage.get('source_sha256') != source_sha
            or lineage.get('derivative_sha256') != derivative.get('analysis_sha256')
            or lineage.get('transform_id') != derivative.get('transform_id')
        ):
            reason = 'LINEAGE_MISMATCH'
        elif derivative.get('analysis_coordinate_space') != ANALYSIS_COORDINATE_SPACE:
            reason = 'ANALYSIS_COORDINATE_SPACE_MISMATCH'
        elif derivative.get('original_coordinate_space') != ORIGINAL_COORDINATE_SPACE:
            reason = 'COORDINATE_SPACE_MISMATCH'
        elif derivative.get('spatial_mapping_version') != 'analysis-to-original-v1':
            reason = 'SPATIAL_MAPPING_MISMATCH'
        elif lineage.get('coordinate_space') != ANALYSIS_COORDINATE_SPACE:
            reason = 'ANALYSIS_COORDINATE_SPACE_MISMATCH'
        elif (
            source_dimensions.get('width') != canonical_width
            or source_dimensions.get('height') != canonical_height
            or mapping.get('canonical_width') != canonical_width
            or mapping.get('canonical_height') != canonical_height
            or mapping.get('analysis_width') != analysis_width
            or mapping.get('analysis_height') != analysis_height
            or lineage.get('width') != analysis_width
            or lineage.get('height') != analysis_height
            or mapping.get('kind') != expected_kind
            or not isinstance(analysis_width, int)
            or isinstance(analysis_width, bool)
            or analysis_width <= 0
            or not isinstance(analysis_height, int)
            or isinstance(analysis_height, bool)
            or analysis_height <= 0
            or mapping.get('scale_x') != canonical_width / analysis_width
            or mapping.get('scale_y') != canonical_height / analysis_height
        ):
            reason = 'DIMENSION_MISMATCH'
        elif lesion.get('width') != image.size[0] or lesion.get('height') != image.size[1]:
            reason = 'RESULT_DIMENSION_MISMATCH'
        else:
            return {
                'status': 'AVAILABLE',
                'coordinate_space': ORIGINAL_COORDINATE_SPACE,
                'note': 'AI overlay geometry is mapped to original-image pixels; it remains optional model evidence.',
            }
    elif provenance.get('source_type') != source_origin:
        reason = 'SOURCE_ORIGIN_MISMATCH'
    elif result_sha != source_sha:
        reason = 'SOURCE_HASH_MISMATCH'
    elif lesion.get('width') != image.size[0] or lesion.get('height') != image.size[1]:
        reason = 'RESULT_DIMENSION_MISMATCH'
    else:
        return {
            'status': 'AVAILABLE',
            'coordinate_space': ORIGINAL_COORDINATE_SPACE,
            'note': 'AI overlay geometry is mapped to original-image pixels; it remains optional model evidence.',
        }
    return {
        'status': 'BLOCKED',
        'reason': reason,
        'note': 'AI overlay is hidden because its source or transform no longer matches the Original image. Review manually.',
    }


def _require_current_spatial_ai(case, image, admission):
    reason = source_identity_reason(case, image, admission)
    if reason:
        raise HTTPException(409, 'Source identity changed or is unavailable; reload before reviewing AI evidence')
    projection = _spatial_ai_display(case, image, source_origin=_source_origin(admission, image))
    if projection.get('status') != 'AVAILABLE':
        raise HTTPException(
            409, 'AI evidence no longer matches the source or transform; review the Original image manually'
        )


def _legacy_grade_reviews(case):
    reviews = list(case.get('grade_reviews') or [])
    if reviews:
        return reviews
    prior = case.get('clinician_review') or {}
    if prior and prior.get('review_action') != 'CONFIRM_ANNOTATIONS':
        grade = prior.get('final_grade')
        return [{
            'reviewer': prior.get('reviewer'),
            'grade': grade,
            'grade_label': grade_label(grade),
            'review_action': prior.get('review_action'),
            'remark': prior.get('remark', ''),
            'timestamp': prior.get('timestamp'),
            'revision': prior.get('revision'),
            'legacy': True,
        }]
    return []


class Review(Contract):
    revision: int = Field(ge=0)
    action: Literal[
        'ACCEPT', 'MARK_INCORRECT', 'CORRECT_GRADE', 'ESCALATE',
        'CONFIRM_ANNOTATIONS', 'MARK_UNGRADABLE', 'REQUEST_SECOND_REVIEW',
        'ADJUDICATE_GRADE',
    ]
    reviewer: str = Field(min_length=1, max_length=80)
    grade: int | None = Field(default=None, ge=0, le=4, strict=True)
    comment: str = Field(default='', max_length=1000)


class ConfirmImage(Contract):
    revision: int = Field(ge=0)
    reviewer: str = Field(min_length=1, max_length=80)
    patient_key: str | None = Field(default=None, max_length=80)
    laterality: Literal['LEFT', 'RIGHT', 'UNKNOWN'] = 'UNKNOWN'
    retinal_modality: Literal['CFP', 'UWF', 'UNKNOWN'] | None = None
    visit_key: str | None = Field(default=None, max_length=120)
    captured_at: str | None = Field(default=None, max_length=80)
    capture_sequence: int | None = Field(default=None, ge=0)
    device: str | None = Field(default=None, max_length=120)
    note: str = Field(default='', max_length=1000)


class HumanAnnotationDraft(Contract):
    shape_id: str | None = Field(default=None, max_length=80)
    type: Literal['rectangle', 'polygon', 'point', 'circle']
    label: Literal['MICROANEURYSM', 'HEMORRHAGE', 'HARD_EXUDATE', 'SOFT_EXUDATE']
    geometry: dict[str, object]
    source_detection_id: str | None = Field(default=None, pattern=r'^ai-[a-f0-9]{20}$')
    # Omitted by older clients; saved legacy-style annotations stay protected by default.
    locked: bool = True


class HumanAnnotationSave(Contract):
    revision: int = Field(ge=0)
    reviewer: str = Field(min_length=1, max_length=80)
    annotations: list[HumanAnnotationDraft] = Field(default_factory=list, max_length=500)


class HumanAnnotationDerive(Contract):
    revision: int = Field(ge=0)
    reviewer: str = Field(min_length=1, max_length=80)
    detection_id: str = Field(pattern=r'^ai-[a-f0-9]{20}$')
    intent: Literal['USE_AS_HUMAN', 'CORRECT_AS_HUMAN']


class AnnotationCompletenessUpdate(Contract):
    revision: int = Field(ge=0)
    reviewer: str = Field(min_length=1, max_length=80)
    group: Literal['CORE', 'ADVANCED']
    state: Literal[
        'NOT_REVIEWED', 'PARTIALLY_REVIEWED',
        'REVIEWED_NONE_FOUND', 'REVIEWED_FINDINGS_RECORDED',
    ]
    taxonomy_version: str = Field(min_length=1, max_length=80)
    note: str = Field(default='', max_length=1000)


class ManualImport(Contract):
    revision: int = Field(ge=0)
    image_sha256: str
    annotations: dict
    label_ids: dict[str, int]


class QueueAction(Contract):
    revision: int = Field(ge=0)
    action: Literal['EXCLUDE', 'RESTORE']
    note: str = Field(default='', max_length=500)


class LesionReviewAction(Contract):
    revision: int = Field(ge=0)
    reviewer: str = Field(min_length=1, max_length=80)
    detection_id: str = Field(pattern=r'^ai-[a-f0-9]{20}$')
    action: Literal['CONFIRM', 'REJECT', 'CORRECT']
    label: Literal['MICROANEURYSM', 'HEMORRHAGE', 'HARD_EXUDATE', 'SOFT_EXUDATE'] | None = None
    rectangle: tuple[float, float, float, float] | None = None
    note: str = Field(default='', max_length=1000)


@dataclass(frozen=True)
class WorkflowContext:
    """Per-app helpers that install_workflow builds once and every route group shares."""

    mutation_gate: Callable
    current_store: Callable
    admission_record: Callable
    case_with_admission: Callable
    ensure_resolution: Callable
    get_image: Callable
    detail: Callable
    clean_geometry: Callable


def install_workflow(app, store, *, persist_automatic_updates=True):
    app.state.store = store
    if artifact_roi_assist.enabled() and not getattr(app.state, 'qa_fixed_session', None):
        # Image-only CPU annotation assist; model wire remains Original.
        from .services.artifact_roi_generic_adapter import GenericUwfArtifactProvider
        from .services.artifact_roi_replay import CONFIG, CachedArtifactReplayProvider
        replay_path = os.environ.get(CONFIG)
        app.state.artifact_roi_provider = (CachedArtifactReplayProvider.from_path(replay_path)
                                           if replay_path else GenericUwfArtifactProvider())
    app.state.remote = CVATOnline()
    app.state.admissions = getattr(app.state, 'admissions', {})
    mutation_gate = lambda: getattr(app.state, "source_mutation_gate", None)

    def current_store():
        return app.state.store

    @guard_writes(mutation_gate, invalidate=False)
    def admission_record(image_id):
        case = current_store().get(image_id)
        if case.get('admission') is not None:
            if mutation_gate() is None or app.state.admissions.get(image_id) != case['admission']:
                with writer_scope(mutation_gate()):
                    app.state.admissions[image_id] = case['admission']
            return case['admission']
        record = app.state.admissions.get(image_id)
        if record is None and image_id in app.state.images:
            record = legacy_admission(app.state.images[image_id])
            with writer_scope(mutation_gate()):
                app.state.admissions[image_id] = record
        return record

    @guard_writes(mutation_gate, invalidate=False)
    def case_with_admission(image_id):
        case = current_store().get(image_id)
        record = admission_record(image_id)
        if persist_automatic_updates and record is not None and case.get('admission') is None:
            record_source_identity_on_creation(case, record)
            case['admission'] = record
            case.setdefault('admission_history', []).append({
                'action': 'AUTOMATIC_ADMISSION',
                'method': record['admission_method'],
                'reason_code': record['admission_reason_code'],
                'quality_reason_code': record.get('quality_reason_code'),
                'new': {
                    'modality_admission': record['modality_admission'],
                    'quality_state': record['quality_state'],
                },
                'timestamp': record['created_at'],
            })
            current_store().put(case)
        return case, record

    @guard_writes(mutation_gate, invalidate=False)
    def ensure_resolution(image_id, case, record):
        """Resolve local evidence, refreshing only unresolved automatic state."""
        if not persist_automatic_updates:
            return case
        authorized = resolve_authorized_hospital_record(record)
        if authorized is not None and (
            case.get('patient_resolution_method') == 'MANUAL'
            or case.get('laterality_resolution_method') == 'MANUAL'
            or any(event.get('action') == 'CONFIRM_IMAGE' for event in case.get('events', []))
        ):
            return case
        if authorized is not None and not any(
            event.get('action') == 'CONFIRM_IMAGE'
            for history in (case.get('resolution_history', []), case.get('events', []))
            for event in history
            if isinstance(event, dict)
        ):
            changed = any(case.get(key) != value for key, value in authorized.items())
            if changed:
                case.update(authorized)
                visit_context = dict(case.get('visit_context') or {})
                visit_context.update({
                    'capture_sequence': record.get('trusted_capture_sequence'),
                    'evidence_state': 'PROVIDED',
                })
                case['visit_context'] = visit_context
                case.setdefault('resolution_history', []).append({
                    'action': 'AUTHORIZED_SOURCE_RESOLUTION',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'method': 'AUTHORIZED_FILENAME_SEMANTICS',
                })
                current_store().put(case)
            return case
        image = app.state.images.get(image_id)
        filename = (image.filename if image is not None else None) or (record or {}).get('filename') or image_id
        decision = app.state.resolver.resolve(image, filename)
        if case.get('resolver_evidence') is None or automatic_resolution_needs_refresh(case, decision):
            changed = apply_automatic_resolution(
                case,
                decision,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            if changed:
                current_store().put(case)
        return case

    def get_image(image_id):
        if image_id not in app.state.images:
            raise HTTPException(404, 'Image not admitted')
        return app.state.images[image_id]

    @guard_writes(mutation_gate, invalidate=False)
    def detail(image_id):
        image = app.state.images.get(image_id)
        record = admission_record(image_id)
        if image is None and record is None:
            raise HTTPException(404, 'Image not admitted')
        case, record = case_with_admission(image_id)
        case = ensure_resolution(image_id, case, record)
        filename = image.filename if image is not None else record.get('filename')
        width = image.size[0] if image is not None else record.get('width')
        height = image.size[1] if image is not None else record.get('height')
        current_annotation_hash = annotation_set_hash(case)
        annotation_confirmed = bool(
            case.get('confirmed_annotation_hash')
            and case.get('confirmed_annotation_hash') == current_annotation_hash
            and case.get('lesion_review_state') == 'REVIEWED'
        )
        source_modality = (record or {}).get('retinal_modality', 'UNKNOWN')
        source_origin = _source_origin(record, image)
        case, patient_display_label = hospital_patient_label(
            current_store(), case, source_origin=source_origin,
            allocate=persist_automatic_updates,
        )
        visible_global = _current_global_result(case, image, record)
        modality_matched_lesion = (
            case.get('lesion')
            if _lesion_result_matches_modality(case.get('lesion'), source_modality, source_origin)
            else None
        )
        spatial_ai = _spatial_ai_display(
            {**case, 'lesion': modality_matched_lesion}, image,
            source_origin=source_origin,
        )
        visible_lesion = modality_matched_lesion if spatial_ai['status'] == 'AVAILABLE' else None
        evidence_case = {
            **case,
            'global': visible_global,
            'lesion': visible_lesion,
            'ai_annotation_reviews': case.get('ai_annotation_reviews', []) if visible_lesion else [],
        }
        explanation = case.get('explainability')
        if not isinstance(explanation, dict):
            explanation = {
                'status': 'UNAVAILABLE',
                'note': 'Explainability evidence is unavailable for this result. It is not lesion localization or a clinical probability.',
            }
        return {**{key: value for key, value in case.items() if key != DISPLAY_INDICES},
                'patient_display_label': patient_display_label, 'global': visible_global,
                'lesion': visible_lesion,
                'source_type': image.source_type if image is not None else None,
                'source_origin': source_origin,
                'source': image.source if image is not None else 'WORKSPACE_INPUT',
                'filename': filename or None,
                'display_name': Path(filename).stem if filename else image_id,
                'image_sha256': image.sha256 if image is not None else None,
                'source_sha256': image.sha256 if image is not None else None,
                'width': width, 'height': height,
                'image_url': f'/v1/images/{image_id}/display' if image is not None else None,
                'source_image_url': f'/v1/images/{image_id}' if image is not None else None,
                'analysis_derivative': case.get('analysis_derivative'),
                'analysis_preparation': case.get('analysis_preparation'),
                'spatial_ai_display': spatial_ai,
                'explainability': explanation,
                'grade_status': case.get('grade_status', GRADE_STATUS_NOT_REVIEWED),
                'reviewed_grade_label': case.get('reviewed_grade_label') or grade_label(case.get('reviewed_grade')),
                'grade_reviews': _legacy_grade_reviews(case),
                'grade_adjudication': case.get('grade_adjudication'),
                'referral': current_referral(case),
                'visit_context': case.get('visit_context'),
                'modality': source_modality,
                'admission': record,
                'admission_ui': clinician_view(record) if record is not None else None,
                'admission_history': case.get('admission_history', []),
                'resolver_ui': resolver_clinician_view(case),
                'resolution_history': case.get('resolution_history', []),
                'lesion_review': lesion_review_view(evidence_case.get('lesion')),
                'artifact_roi_assist': artifact_roi_assist.project(
                    evidence_case, image, getattr(app.state, 'artifact_roi_provider', None),
                    scope=artifact_roi_assist.scope_for_app(app, current_store()), admission=record),
                'human_annotations': case.get('human_annotations', []),
                'clinician_review': case.get('clinician_review'),
                'review_history': case.get('review_history', []),
                'review_evidence': review_evidence_view(evidence_case),
                'annotation_completeness': case.get('annotation_completeness', {}),
                'annotation_hash': current_annotation_hash,
                'annotation_set_hash': current_annotation_hash,
                'annotation_confirmation_status': 'CONFIRMED' if annotation_confirmed else 'DRAFT',
                'annotation_confirmation': {
                    'status': 'CONFIRMED' if annotation_confirmed else 'DRAFT',
                    'reviewer': (case.get('annotation_confirmation') or {}).get('reviewer'),
                    'timestamp': (case.get('annotation_confirmation') or {}).get('timestamp'),
                    'annotation_set_hash': case.get('confirmed_annotation_hash') if annotation_confirmed else None,
                },
                'ai_annotation_reviews': evidence_case.get('ai_annotation_reviews', []),
                'queue_state': case.get('queue_state', 'INCLUDED'),
                'queue_history': case.get('queue_history', [])}

    artifact_roi_assist.install(app, detail, current_store, get_image, _require_current_spatial_ai)

    def finite_number(value, name):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f'{name} must be a finite number')
        return float(value)

    def clean_geometry(annotation, width, height):
        geometry = annotation.geometry
        if annotation.type == 'rectangle':
            keys = ('x', 'y', 'width', 'height')
            if set(geometry) != set(keys):
                raise ValueError('Rectangle geometry must contain x, y, width, and height')
            x, y = finite_number(geometry['x'], 'x'), finite_number(geometry['y'], 'y')
            w, h = finite_number(geometry['width'], 'width'), finite_number(geometry['height'], 'height')
            if not (0 <= x < x + w <= width and 0 <= y < y + h <= height and w > 0 and h > 0):
                raise ValueError('Rectangle geometry must be inside the original image')
            return {'x': x, 'y': y, 'width': w, 'height': h}
        if annotation.type == 'polygon':
            points = geometry.get('points')
            if set(geometry) != {'points'} or not isinstance(points, list) or len(points) < 3:
                raise ValueError('Polygon geometry needs at least three points')
            clean_points = []
            for point in points:
                if not isinstance(point, list) or len(point) != 2:
                    raise ValueError('Polygon points must be [x, y] pairs')
                x, y = finite_number(point[0], 'x'), finite_number(point[1], 'y')
                if not (0 <= x <= width and 0 <= y <= height):
                    raise ValueError('Polygon points must be inside the original image')
                clean_points.append([x, y])
            return {'points': clean_points}
        if annotation.type == 'point':
            if set(geometry) != {'x', 'y'}:
                raise ValueError('Point geometry must contain x and y')
            x, y = finite_number(geometry['x'], 'x'), finite_number(geometry['y'], 'y')
            if not (0 <= x <= width and 0 <= y <= height):
                raise ValueError('Point geometry must be inside the original image')
            return {'x': x, 'y': y}
        if set(geometry) != {'cx', 'cy', 'radius'}:
            raise ValueError('Circle geometry must contain cx, cy, and radius')
        cx = finite_number(geometry['cx'], 'cx')
        cy = finite_number(geometry['cy'], 'cy')
        radius = finite_number(geometry['radius'], 'radius')
        if not (radius > 0 and radius <= cx <= width - radius and radius <= cy <= height - radius):
            raise ValueError('Circle geometry must be inside the original image')
        return {'cx': cx, 'cy': cy, 'radius': radius}

    # Route groups live in dr_support/workflow_routes/. They are installed in this order because FastAPI
    # matches routes in registration order (the same order the routes had in this file).
    from .workflow_routes import annotations, cases, confirm, cvat, images, review
    ctx = WorkflowContext(
        mutation_gate=mutation_gate,
        current_store=current_store,
        admission_record=admission_record,
        case_with_admission=case_with_admission,
        ensure_resolution=ensure_resolution,
        get_image=get_image,
        detail=detail,
        clean_geometry=clean_geometry,
    )
    cases.install_cases_routes(app, ctx)
    images.install_images_routes(app, ctx)
    review.install_review_routes(app, ctx)
    confirm.install_confirm_routes(app, ctx)
    annotations.install_annotations_routes(app, ctx)
    cvat.install_cvat_routes(app, ctx)
