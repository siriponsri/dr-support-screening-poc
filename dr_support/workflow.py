"""Durable review API with optimistic concurrency and explicit human actions."""
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4
from fastapi import HTTPException
from fastapi.responses import Response
from pydantic import Field
from .contracts import AdmissionMetadata, AdmissionReview, Contract, ResolverReview
from .sync import Sync, digest
from .cvat import CVATOnline, OnlineError
from .presentation import annotation_set_hash, lesion_review_view, review_evidence_view
from .services.admission import clinician_view, legacy_admission
from .services.resolver import (
    apply_automatic_resolution,
    combined_resolution_state,
    normalize_patient_key,
    resolver_clinician_view,
)
from .imaging import DerivativeError
from .imaging.derivatives import (
    ANALYSIS_COORDINATE_SPACE,
    ANALYSIS_DICOM_PNG_TRANSFORM,
    ANALYSIS_REPRESENTATION_VERSION,
    ANALYSIS_SOURCE_TRANSFORM,
    ANALYSIS_TIFF_PNG_TRANSFORM,
    ANALYSIS_UWF_MASK_TRANSFORM,
    MASK_OVERLAY_REPRESENTATION_VERSION,
    ORIGINAL_COORDINATE_SPACE,
    render_mask_overlay,
)
from .imaging.retinal_field import RetinalFieldNeedsReview
from .grade import (
    GRADE_STATUS_CONFIRMED,
    GRADE_STATUS_NEEDS_SECOND_REVIEW,
    GRADE_STATUS_NOT_REVIEWED,
    GRADE_STATUS_UNGRADABLE,
    grade_label,
)


KNOWN_ANALYSIS_TRANSFORMS = frozenset({
    ANALYSIS_SOURCE_TRANSFORM,
    ANALYSIS_TIFF_PNG_TRANSFORM,
    ANALYSIS_DICOM_PNG_TRANSFORM,
    ANALYSIS_UWF_MASK_TRANSFORM,
})


def _source_origin(record, image):
    """Resolve origin from explicit admission/image facts without relabeling unknown data."""
    allowed = {'PUBLIC', 'SYNTHETIC', 'WORKSPACE', 'UNKNOWN'}
    record_origin = (record or {}).get('source_origin')
    if record_origin in allowed:
        return record_origin
    image_origin = getattr(image, 'source_origin', None) if image is not None else None
    if image_origin in allowed and image_origin != 'UNKNOWN':
        return image_origin
    if image is not None and image.source_type in {'PUBLIC', 'SYNTHETIC'}:
        return image.source_type
    return 'UNKNOWN'


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
    if source_origin not in {'PUBLIC', 'SYNTHETIC'}:
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
        elif derivative.get('representation_version') != ANALYSIS_REPRESENTATION_VERSION:
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


def install_workflow(app, store):
    app.state.store = store
    app.state.remote = CVATOnline()
    app.state.admissions = getattr(app.state, 'admissions', {})

    def current_store():
        return app.state.store

    def admission_record(image_id):
        case = current_store().get(image_id)
        if case.get('admission') is not None:
            app.state.admissions[image_id] = case['admission']
            return case['admission']
        record = app.state.admissions.get(image_id)
        if record is None and image_id in app.state.images:
            record = legacy_admission(app.state.images[image_id])
            app.state.admissions[image_id] = record
        return record

    def case_with_admission(image_id):
        case = current_store().get(image_id)
        record = admission_record(image_id)
        if record is not None and case.get('admission') is None:
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

    def ensure_resolution(image_id, case, record):
        """Resolve once from local evidence, preserving later manual decisions."""
        if case.get('resolver_evidence') is not None:
            return case
        if any(event.get('action') == 'MANUAL_RESOLUTION'
               for event in case.get('resolution_history', [])):
            return case
        image = app.state.images.get(image_id)
        filename = (image.filename if image is not None else None) or (record or {}).get('filename') or image_id
        decision = app.state.resolver.resolve(image, filename)
        apply_automatic_resolution(
            case,
            decision,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        current_store().put(case)
        return case

    def get_image(image_id):
        if image_id not in app.state.images:
            raise HTTPException(404, 'Image not admitted')
        return app.state.images[image_id]

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
        spatial_ai = _spatial_ai_display(case, image, source_origin=source_origin)
        # CFP evidence from a legacy case is not current evidence for UWF.
        visible_ai = source_modality == 'CFP' and source_origin in {'PUBLIC', 'SYNTHETIC'}
        visible_lesion = case.get('lesion') if spatial_ai['status'] == 'AVAILABLE' else None
        evidence_case = (case if visible_ai else {
            **case, 'global': None, 'lesion': None, 'ai_annotation_reviews': []
        })
        if visible_ai and visible_lesion is None:
            evidence_case = {**evidence_case, 'lesion': None, 'ai_annotation_reviews': []}
        explanation = case.get('explainability')
        if not isinstance(explanation, dict):
            explanation = {
                'status': 'UNAVAILABLE',
                'note': 'Explainability evidence is unavailable for this result. It is not lesion localization or a clinical probability.',
            }
        return {**case, 'global': case.get('global') if visible_ai else None,
                'lesion': visible_lesion if visible_ai else None,
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
                'visit_context': case.get('visit_context'),
                'modality': source_modality,
                'admission': record,
                'admission_ui': clinician_view(record) if record is not None else None,
                'admission_history': case.get('admission_history', []),
                'resolver_ui': resolver_clinician_view(case),
                'resolution_history': case.get('resolution_history', []),
                'lesion_review': lesion_review_view(evidence_case.get('lesion')),
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

    @app.get('/v1/cases')
    def cases():
        image_ids = list(app.state.admissions)
        image_ids.extend(image_id for image_id in app.state.images if image_id not in app.state.admissions)
        return [detail(image_id) for image_id in image_ids]

    @app.get('/v1/cases/{image_id}')
    def case(image_id: str):
        return detail(image_id)

    @app.get('/v1/images/{image_id}')
    def image_bytes(image_id: str):
        image = get_image(image_id)
        return Response(image.data, media_type=image.media_type,
                        headers={'Cache-Control': 'private, max-age=3600'})

    @app.get('/v1/images/{image_id}/display')
    def display_image_bytes(image_id: str):
        image = app.state.images.get(image_id)
        if image is None:
            record = admission_record(image_id)
            status = (record or {}).get('integrity_status')
            if (record or {}).get('admission_reason_code') == 'DICOM_UNSUPPORTED_MODALITY':
                raise HTTPException(
                    409,
                    'This DICOM has an unsupported modality; it is not an ophthalmic retinal image for DR analysis.',
                )
            messages = {
                'DICOM_CODEC_REQUIRED': 'This DICOM image needs a supported pixel codec before it can be displayed.',
                'DICOM_MULTIFRAME_UNSUPPORTED': 'Multi-frame DICOM images require explicit frame selection before display.',
                'DECODE_FAILED': 'This DICOM image could not be decoded for display.',
                'UNSUPPORTED_FORMAT': 'This DICOM image is outside the supported display scope.',
            }
            if status in messages:
                raise HTTPException(409, messages[status])
            raise HTTPException(404, 'Image not admitted')
        try:
            derivative = app.state.derivatives.prepare_display(image)
        except DerivativeError as exc:
            record = admission_record(image_id)
            if (record or {}).get('admission_reason_code') == 'DICOM_UNSUPPORTED_MODALITY':
                raise HTTPException(
                    409,
                    'This DICOM has an unsupported modality; it is not an ophthalmic retinal image for DR analysis.',
                ) from None
            messages = {
                'DICOM_CODEC_REQUIRED': 'This DICOM image needs a supported pixel codec before it can be displayed.',
                'DICOM_MULTIFRAME_UNSUPPORTED': 'Multi-frame DICOM images require explicit frame selection before display.',
                'DECODE_FAILED': 'This DICOM image could not be decoded for display.',
                'UNSUPPORTED_FORMAT': 'This DICOM image is outside the supported display scope.',
            }
            raise HTTPException(
                409,
                messages.get(getattr(exc, 'status', None),
                             'This image cannot be displayed in the browser. Review the source format or use a supported copy.'),
            ) from None
        return Response(
            derivative.data,
            media_type=derivative.media_type,
            headers={
                'Cache-Control': 'private, max-age=3600',
                'ETag': f'"{derivative.lineage.derivative_sha256}"',
                'X-Source-SHA256': derivative.lineage.source_sha256,
                'X-Derivative-SHA256': derivative.lineage.derivative_sha256,
            },
        )

    @app.get('/v1/images/{image_id}/analysis-area')
    def analysis_area_bytes(image_id: str):
        """Inspect a confirmed UWF mask; never fall back to full source bytes."""
        image = get_image(image_id)
        record = admission_record(image_id) or {}
        preparation = current_store().get(image_id).get('analysis_preparation') or {}
        if record.get('retinal_modality') != 'UWF' or preparation.get('status') != 'READY':
            raise HTTPException(409, 'Analysis area is not available for this image.')
        try:
            derivative = app.state.derivatives.prepare_analysis(image, source_modality='UWF')
        except (DerivativeError, RetinalFieldNeedsReview):
            raise HTTPException(409, 'Analysis area could not be prepared.') from None
        expected = preparation.get('derivative') or {}
        audit = derivative.audit_record()
        if (expected.get('source_sha256') != audit['source_sha256']
                or expected.get('analysis_sha256') != audit['analysis_sha256']
                or expected.get('valid_retina_mask_sha256') != audit['valid_retina_mask_sha256']
                or expected.get('transform_id') != audit['transform_id']
                or (expected.get('representation_version') is not None
                    and expected.get('representation_version') != audit['representation_version'])
                or (expected.get('original_coordinate_space') is not None
                    and expected.get('original_coordinate_space') != audit['original_coordinate_space'])):
            raise HTTPException(409, 'Analysis area no longer matches its recorded source.')
        return Response(derivative.data, media_type=derivative.media_type,
                        headers={'Cache-Control': 'private, no-store',
                                 'X-Source-SHA256': image.sha256,
                                 'X-Analysis-SHA256': audit['analysis_sha256']})

    @app.get('/v1/images/{image_id}/mask-overlay')
    def mask_overlay_bytes(image_id: str):
        """Inspect the deterministic UWF mask over the immutable source image."""
        image = get_image(image_id)
        record = admission_record(image_id) or {}
        preparation = current_store().get(image_id).get('analysis_preparation') or {}
        status = preparation.get('status')
        if record.get('retinal_modality') != 'UWF' or status not in {'READY', 'NEEDS_REVIEW'}:
            raise HTTPException(409, 'Mask overlay is not available for this image.')
        expected_source = preparation.get('source_sha256') or (preparation.get('derivative') or {}).get('source_sha256')
        if expected_source != image.sha256:
            raise HTTPException(409, 'Mask overlay no longer matches its recorded source.')
        try:
            inspection = app.state.derivatives.inspect_analysis_mask(image, source_modality='UWF')
        except DerivativeError:
            raise HTTPException(409, 'Mask overlay could not be prepared.') from None
        if inspection.mask is None or inspection.mask_sha256 is None:
            raise HTTPException(409, 'No candidate mask is available for inspection.')
        if status == 'READY':
            expected = preparation.get('derivative') or {}
            try:
                regenerated = app.state.derivatives.prepare_analysis(image, source_modality='UWF')
            except (DerivativeError, RetinalFieldNeedsReview):
                raise HTTPException(409, 'Mask overlay could not be prepared.') from None
            audit = regenerated.audit_record()
            if (inspection.reason_code is not None
                    or expected.get('source_sha256') != image.sha256
                    or expected.get('analysis_sha256') != audit['analysis_sha256']
                    or expected.get('valid_retina_mask_sha256') != inspection.mask_sha256
                    or expected.get('transform_id') != ANALYSIS_UWF_MASK_TRANSFORM
                    or expected.get('representation_version') != ANALYSIS_REPRESENTATION_VERSION):
                raise HTTPException(409, 'Mask overlay no longer matches its recorded preparation.')
        else:
            if (preparation.get('reason_code') != inspection.reason_code
                    or preparation.get('candidate_mask_sha256') != inspection.mask_sha256
                    or preparation.get('candidate_mask_representation_version') != MASK_OVERLAY_REPRESENTATION_VERSION):
                raise HTTPException(409, 'Mask overlay no longer matches its recorded candidate.')
        return Response(
            render_mask_overlay(inspection.mask),
            media_type='image/png',
            headers={
                'Cache-Control': 'private, no-store',
                'X-Source-SHA256': image.sha256,
                'X-Mask-SHA256': inspection.mask_sha256,
                'X-Mask-Status': status,
                'X-Mask-Representation': MASK_OVERLAY_REPRESENTATION_VERSION,
            },
        )

    @app.post('/v1/cases/{image_id}/review')
    def review(image_id: str, request: Review):
        get_image(image_id)
        store = current_store()
        with store.lock:
            case = store.get(image_id)
            # Historical CFP evidence cannot authorize AI provenance on a
            # source whose image type is now UWF or still unknown.
            current_admission = admission_record(image_id) or {}
            current_source_origin = _source_origin(current_admission, app.state.images.get(image_id))
            current_ai = (case.get('global') if current_admission.get('retinal_modality') == 'CFP'
                          and current_source_origin in {'PUBLIC', 'SYNTHETIC'}
                          else None)
            if request.revision != case['revision']:
                raise HTTPException(409, 'Case changed; reload before reviewing')
            if not request.reviewer.strip():
                raise HTTPException(422, 'Reviewer name required')
            if (request.action == 'ESCALATE'
                    and case.get('grade_status') == GRADE_STATUS_NEEDS_SECOND_REVIEW):
                raise HTTPException(
                    409,
                    'Resolve the outstanding grade disagreement before escalating the case',
                )
            if (request.action == 'MARK_INCORRECT'
                    and case.get('grade_status') == GRADE_STATUS_NEEDS_SECOND_REVIEW):
                raise HTTPException(
                    409,
                    'Resolve the outstanding grade disagreement before marking the AI suggestion incorrect',
                )
            grade_action = request.action in {
                'ACCEPT', 'CORRECT_GRADE', 'MARK_UNGRADABLE',
                'REQUEST_SECOND_REVIEW', 'ADJUDICATE_GRADE',
            }
            if request.action == 'ACCEPT':
                if not current_ai or current_ai['grade'] is None:
                    raise HTTPException(409, 'No grade suggestion to accept')
                requested_grade = current_ai['grade']
                requested_source = 'AI_ACCEPTED'
            elif request.action in {'CORRECT_GRADE', 'ADJUDICATE_GRADE'}:
                if request.grade is None:
                    raise HTTPException(422, 'Corrected/manual grade required')
                if request.action == 'ADJUDICATE_GRADE' and case.get('grade_status') != GRADE_STATUS_NEEDS_SECOND_REVIEW:
                    raise HTTPException(409, 'This case does not have an unresolved grade disagreement')
                requested_grade = request.grade
                requested_source = ('AI_CORRECTED' if current_ai and
                                    current_ai.get('grade') is not None else 'MANUAL')
            elif request.action == 'MARK_UNGRADABLE':
                if case.get('grade_status') == GRADE_STATUS_NEEDS_SECOND_REVIEW:
                    raise HTTPException(
                        409,
                        'Resolve the outstanding grade disagreement before marking the image ungradable',
                    )
                requested_grade = None
                requested_source = None
            elif request.action == 'REQUEST_SECOND_REVIEW':
                requested_grade = None
                requested_source = None
            elif request.action == 'CONFIRM_ANNOTATIONS':
                case['annotation_hash'] = annotation_set_hash(case)
                case['lesion_review_state'] = 'REVIEWED'
                case['confirmed_annotation_hash'] = case['annotation_hash']
            else:
                if request.action == 'MARK_INCORRECT' and (not current_ai or
                                                            current_ai.get('grade') is None):
                    raise HTTPException(409, 'No AI grade suggestion to mark incorrect')
                case['state'] = 'NEEDS_CORRECTION' if request.action == 'MARK_INCORRECT' else 'ESCALATED'
                case['reviewed_grade'] = None
                case['grade_review_source'] = None
                case['grade_status'] = GRADE_STATUS_NOT_REVIEWED
                case['reviewed_grade_label'] = None

            if grade_action:
                previous_reviews = _legacy_grade_reviews(case)
                prior_grade_reviews = [
                    item for item in previous_reviews
                    if isinstance(item.get('grade'), int) and not isinstance(item.get('grade'), bool)
                ]
                independent_disagreement = (
                    requested_grade is not None
                    and request.action != 'ADJUDICATE_GRADE'
                    and any(
                        item.get('reviewer', '').strip().casefold() != request.reviewer.strip().casefold()
                        and item.get('grade') != requested_grade
                        for item in prior_grade_reviews
                    )
                )
                unresolved = (
                    request.action == 'REQUEST_SECOND_REVIEW'
                    or independent_disagreement
                    or (
                        case.get('grade_status') == GRADE_STATUS_NEEDS_SECOND_REVIEW
                        and request.action != 'ADJUDICATE_GRADE'
                    )
                )
                if request.action == 'MARK_UNGRADABLE':
                    case['grade_status'] = GRADE_STATUS_UNGRADABLE
                    case['reviewed_grade'] = None
                    case['grade_review_source'] = None
                    case['reviewed_grade_label'] = None
                    case['state'] = 'REVIEWED'
                    case['grade_adjudication'] = None
                elif unresolved:
                    case['grade_status'] = GRADE_STATUS_NEEDS_SECOND_REVIEW
                    case['reviewed_grade'] = None
                    case['grade_review_source'] = None
                    case['reviewed_grade_label'] = None
                    case['state'] = 'NEEDS_SECOND_REVIEW'
                    case['grade_adjudication'] = {
                        'status': 'UNRESOLVED',
                        'opened_by': request.reviewer.strip(),
                        'opened_at': datetime.now(timezone.utc).isoformat(),
                    }
                else:
                    case['reviewed_grade'] = requested_grade
                    case['reviewed_grade_label'] = grade_label(requested_grade)
                    case['grade_review_source'] = requested_source
                    case['grade_status'] = GRADE_STATUS_CONFIRMED
                    case['state'] = 'REVIEWED'
                    if request.action == 'ADJUDICATE_GRADE':
                        case['grade_adjudication'] = {
                            'status': 'RESOLVED',
                            'resolved_by': request.reviewer.strip(),
                            'resolved_at': datetime.now(timezone.utc).isoformat(),
                            'grade': requested_grade,
                        }
            case['revision'] += 1
            timestamp = datetime.now(timezone.utc).isoformat()
            event = {**request.model_dump(), 'timestamp': timestamp,
                     'new_revision': case['revision'], 'identity_assurance': 'LOCAL_POC_SELF_DECLARED'}
            case.setdefault('events', []).append(event)
            review_record = {
                'reviewer': request.reviewer.strip(),
                'final_grade': case.get('reviewed_grade'),
                'final_grade_label': grade_label(case.get('reviewed_grade')),
                'review_action': request.action,
                'remark': request.comment,
                'timestamp': timestamp,
                'revision': case['revision'],
            }
            # Annotation finality is a separate milestone. Keep the recorded
            # DR-grade reviewer/decision intact when an annotation reviewer
            # confirms the current active set later.
            if request.action != 'CONFIRM_ANNOTATIONS':
                case['clinician_review'] = review_record
            case.setdefault('review_history', []).append(review_record)
            if grade_action:
                case['grade_reviews'] = [
                    *previous_reviews,
                    {
                        'reviewer': request.reviewer.strip(),
                        'grade': requested_grade,
                        'grade_label': grade_label(requested_grade),
                        'review_action': request.action,
                        'remark': request.comment,
                        'timestamp': timestamp,
                        'revision': case['revision'],
                    },
                ]
            if request.action == 'CONFIRM_ANNOTATIONS':
                case['annotation_confirmation'] = {
                    'reviewer': request.reviewer.strip(),
                    'timestamp': timestamp,
                    'annotation_set_hash': case['confirmed_annotation_hash'],
                }
            store.put(case)
            return detail(image_id)

    @app.post('/v1/cases/{image_id}/queue')
    def queue_action(image_id: str, request: QueueAction):
        store = current_store()
        with store.lock:
            case, record = case_with_admission(image_id)
            image = app.state.images.get(image_id)
            if image is None and record is None:
                raise HTTPException(404, 'Image not admitted')
            if request.revision != case['revision']:
                raise HTTPException(409, 'Case changed; reload before updating the queue')
            next_state = 'EXCLUDED' if request.action == 'EXCLUDE' else 'INCLUDED'
            timestamp = datetime.now(timezone.utc).isoformat()
            previous_state = case.get('queue_state', 'INCLUDED')
            case['queue_state'] = next_state
            event = {
                'action': f'QUEUE_{request.action}',
                'note': request.note.strip(),
                'timestamp': timestamp,
                'previous_state': previous_state,
                'new_state': next_state,
            }
            case.setdefault('queue_history', []).append(event)
            case.setdefault('events', []).append(event)
            case['revision'] += 1
            store.put(case)
            return detail(image_id)

    @app.post('/v1/cases/{image_id}/lesion-review')
    def lesion_review(image_id: str, request: LesionReviewAction):
        image = get_image(image_id)
        reviewer = request.reviewer.strip()
        if not reviewer:
            raise HTTPException(422, 'Reviewer name required')
        store = current_store()
        with store.lock:
            case = store.get(image_id)
            if request.revision != case['revision']:
                raise HTTPException(409, 'Case changed; reload before reviewing lesion evidence')
            raw_result = case.get('lesion')
            view = lesion_review_view(raw_result) if raw_result else None
            target = next((item for item in (view or {}).get('lesions', [])
                           if item.get('detection_id') == request.detection_id), None)
            if target is None:
                raise HTTPException(404, 'AI lesion suggestion is no longer available')

            corrected_label = request.label
            corrected_rectangle = list(request.rectangle) if request.rectangle is not None else None
            if request.action == 'CORRECT':
                if corrected_label is None and corrected_rectangle is None:
                    raise HTTPException(422, 'A corrected label or geometry is required')
                if corrected_rectangle is not None:
                    x1, y1, x2, y2 = corrected_rectangle
                    if not (0 <= x1 < x2 <= image.size[0] and 0 <= y1 < y2 <= image.size[1]):
                        raise HTTPException(422, 'Corrected lesion geometry must be inside the original image')
                corrected_label = corrected_label or target['canonical_label']
            elif request.label is not None or request.rectangle is not None:
                raise HTTPException(422, 'Label and geometry are only accepted for a correction')

            timestamp = datetime.now(timezone.utc).isoformat()
            decision = {
                'detection_id': request.detection_id,
                'action': request.action,
                'reviewer': reviewer,
                'timestamp': timestamp,
                'note': request.note.strip(),
                'original_label': target['canonical_label'],
                'original_rectangle': target['rectangle'],
                'original_score': target['score'],
                'corrected_label': corrected_label,
                'corrected_rectangle': corrected_rectangle,
                'model_id': (raw_result or {}).get('model_id'),
                'model_version': (raw_result or {}).get('model_version'),
            }
            case.setdefault('ai_annotation_reviews', []).append(decision)
            case['annotation_hash'] = annotation_set_hash(case)
            if case.get('confirmed_annotation_hash') != case['annotation_hash']:
                case['lesion_review_state'] = 'REQUIRES_CONFIRMATION'
            case['revision'] += 1
            case.setdefault('events', []).append({
                'action': 'AI_ANNOTATION_REVIEWED',
                'review_action': request.action,
                'detection_id': request.detection_id,
                'reviewer': reviewer,
                'timestamp': timestamp,
                'original_score': target['score'],
                'new_label': corrected_label,
                'new_rectangle': corrected_rectangle,
                'new_revision': case['revision'],
            })
            store.put(case)
            return detail(image_id)

    @app.post('/v1/cases/{image_id}/admission')
    def review_admission(image_id: str, request: AdmissionReview):
        image = get_image(image_id)
        reviewer = request.reviewer.strip()
        if not reviewer:
            raise HTTPException(422, 'Reviewer name required')
        store = current_store()
        with store.lock:
            case, current = case_with_admission(image_id)
            if current is None:
                current = legacy_admission(image)
            if request.revision != case['revision']:
                raise HTTPException(409, 'Case changed; reload before reviewing admission')
            previous = {
                'modality_admission': current['modality_admission'],
                'quality_state': current['quality_state'],
                'admission_reason_code': current['admission_reason_code'],
                'quality_reason_code': current.get('quality_reason_code'),
            }
            updated = dict(current)
            timestamp = datetime.now(timezone.utc).isoformat()
            if request.action == 'ACCEPT_RETINAL':
                updated['modality_admission'] = 'FUNDUS_ACCEPTED'
                updated['admission_reason_code'] = 'MANUAL_ACCEPT'
                updated['admission_method'] = 'MANUAL'
            elif request.action == 'MARK_NON_FUNDUS':
                updated['modality_admission'] = 'REJECTED_NON_FUNDUS'
                updated['admission_reason_code'] = 'MANUAL_NON_FUNDUS'
                updated['admission_method'] = 'MANUAL'
            elif request.action == 'QUALITY_ACCEPTABLE':
                updated['quality_state'] = 'GRADABLE'
                updated['quality_reason_code'] = 'MANUAL_QUALITY_ACCEPTED'
                updated['admission_method'] = 'MANUAL'
            elif request.action == 'QUALITY_INADEQUATE':
                updated['quality_state'] = 'UNGRADABLE'
                updated['quality_reason_code'] = 'MANUAL_QUALITY_INADEQUATE'
                updated['admission_method'] = 'MANUAL'
            updated['updated_at'] = timestamp
            updated['reviewed_by'] = reviewer
            updated['reviewed_at'] = timestamp
            updated['review_note'] = request.note.strip() or None
            updated = AdmissionMetadata.model_validate(updated).model_dump(mode='json')
            current = updated
            case['admission'] = updated
            event = {
                'action': 'ADMISSION_OVERRIDE',
                'review_action': request.action,
                'method': 'MANUAL' if request.action != 'LEAVE_UNRESOLVED' else updated['admission_method'],
                'reviewer': reviewer,
                'note': request.note.strip(),
                'timestamp': timestamp,
                'previous': previous,
                'new': {
                    'modality_admission': updated['modality_admission'],
                    'quality_state': updated['quality_state'],
                    'admission_reason_code': updated['admission_reason_code'],
                    'quality_reason_code': updated.get('quality_reason_code'),
                },
            }
            case.setdefault('admission_history', []).append(event)
            case.setdefault('events', []).append(event)
            case['revision'] += 1
            store.put(case)
            app.state.admissions[image_id] = updated
            return detail(image_id)

    @app.post('/v1/cases/{image_id}/resolver')
    def review_resolver(image_id: str, request: ResolverReview):
        store = current_store()
        with store.lock:
            case, record = case_with_admission(image_id)
            image = app.state.images.get(image_id)
            if image is None and record is None:
                raise HTTPException(404, 'Image not admitted')
            case = ensure_resolution(image_id, case, record)
            if request.revision != case['revision']:
                raise HTTPException(409, 'Case changed; reload before confirming patient or eye')
            reviewer = request.reviewer.strip()
            if not reviewer:
                raise HTTPException(422, 'Reviewer name required')
            if request.patient_action == 'KEEP' and request.laterality_action == 'KEEP':
                raise HTTPException(422, 'Choose a patient or eye action')

            previous = {
                'patient_key': case.get('patient_key'),
                'patient_resolution_state': case.get('patient_resolution_state'),
                'laterality': case.get('laterality'),
                'laterality_resolution_state': case.get('laterality_resolution_state'),
            }
            timestamp = datetime.now(timezone.utc).isoformat()
            if request.patient_action == 'CONFIRM':
                key = request.patient_key or case.get('patient_candidate')
                if not key:
                    raise HTTPException(422, 'A proposed patient key is not available')
                try:
                    key = normalize_patient_key(key)
                except ValueError as error:
                    raise HTTPException(422, str(error)) from None
                case['patient_key'] = key
                case['patient_resolution_state'] = 'RESOLVED'
                case['patient_resolution_method'] = 'MANUAL'
                case['patient_reason_code'] = 'MANUAL_CONFIRMED'
                case['patient_confidence_or_strength'] = 'HIGH'
            elif request.patient_action == 'SET':
                if not request.patient_key:
                    raise HTTPException(422, 'Patient key is required')
                try:
                    case['patient_key'] = normalize_patient_key(request.patient_key)
                except ValueError as error:
                    raise HTTPException(422, str(error)) from None
                case['patient_resolution_state'] = 'RESOLVED'
                case['patient_resolution_method'] = 'MANUAL'
                case['patient_reason_code'] = 'MANUAL_ASSIGNED'
                case['patient_confidence_or_strength'] = 'HIGH'
            elif request.patient_action == 'LEAVE_UNLINKED':
                case['patient_key'] = None
                case['patient_resolution_state'] = 'UNLINKED'
                case['patient_resolution_method'] = 'MANUAL'
                case['patient_reason_code'] = 'MANUAL_LEFT_UNLINKED'
                case['patient_confidence_or_strength'] = None

            if request.laterality_action == 'SET':
                if request.laterality is None:
                    raise HTTPException(422, 'Choose Left, Right, or Unknown')
                case['laterality'] = request.laterality
                case['laterality_resolution_state'] = 'RESOLVED'
                case['laterality_resolution_method'] = 'MANUAL'
                case['laterality_reason_code'] = (
                    'MANUAL_UNKNOWN' if request.laterality == 'UNKNOWN' else 'MANUAL_SET'
                )
                case['laterality_candidate'] = request.laterality

            case['resolver_state'] = combined_resolution_state(
                case.get('patient_resolution_state', 'UNLINKED'),
                case.get('laterality_resolution_state', 'UNLINKED'),
            )
            new = {
                'patient_key': case.get('patient_key'),
                'patient_resolution_state': case.get('patient_resolution_state'),
                'laterality': case.get('laterality'),
                'laterality_resolution_state': case.get('laterality_resolution_state'),
            }
            event = {
                'action': 'MANUAL_RESOLUTION',
                'reviewer': reviewer,
                'note': request.note.strip(),
                'timestamp': timestamp,
                'previous': previous,
                'new': new,
                'automatic_evidence': case.get('resolver_evidence'),
            }
            case.setdefault('resolution_history', []).append(event)
            case.setdefault('events', []).append(event)
            case['revision'] += 1
            store.put(case)
            return detail(image_id)

    @app.post('/v1/cases/{image_id}/confirm-image')
    def confirm_image(image_id: str, request: ConfirmImage):
        """Persist the routine image/context milestone as one clinician action."""
        image = get_image(image_id)
        reviewer = request.reviewer.strip()
        if not reviewer:
            raise HTTPException(422, 'Reviewer name required')
        store = current_store()
        with store.lock:
            case, current = case_with_admission(image_id)
            if request.revision != case['revision']:
                raise HTTPException(409, 'Case changed; reload before confirming image')
            if current is None:
                current = legacy_admission(image)
            timestamp = datetime.now(timezone.utc).isoformat()
            admission = dict(current)
            prior_modality = admission.get('retinal_modality', 'UNKNOWN')
            chosen_modality = request.retinal_modality or prior_modality
            admission['retinal_modality'] = chosen_modality
            admission['retinal_modality_state'] = (
                'RESOLVED' if chosen_modality != 'UNKNOWN' else 'NEEDS_CONFIRMATION'
            )
            admission['retinal_modality_method'] = (
                'MANUAL' if request.retinal_modality is not None else admission.get('retinal_modality_method', 'NONE')
            )
            if admission.get('modality_admission') == 'NEEDS_REVIEW':
                admission['modality_admission'] = 'FUNDUS_ACCEPTED'
                admission['admission_reason_code'] = 'MANUAL_CONFIRM_IMAGE'
                admission['admission_method'] = 'MANUAL'
            if admission.get('quality_state') == 'NEEDS_REVIEW':
                admission['quality_state'] = 'GRADABLE'
                admission['quality_reason_code'] = 'MANUAL_CONFIRM_IMAGE'
                admission['admission_method'] = 'MANUAL'
            admission['updated_at'] = timestamp
            admission['reviewed_by'] = reviewer
            admission['reviewed_at'] = timestamp
            admission['review_note'] = request.note.strip() or None
            admission = AdmissionMetadata.model_validate(admission).model_dump(mode='json')
            case['admission'] = admission
            app.state.admissions[image_id] = admission
            if chosen_modality != prior_modality:
                if case.get('global') or case.get('lesion'):
                    case.setdefault('superseded_model_results', []).append({
                        'timestamp': timestamp, 'previous_modality': prior_modality,
                        'global': case.get('global'), 'lesion': case.get('lesion'),
                    })
                    case['global'] = None
                    case['lesion'] = None
                    case['ai_annotation_reviews'] = []
                case['analysis_derivative'] = None
                if case.get('grade_review_source') == 'AI_ACCEPTED':
                    case['state'] = 'PENDING'
                    case['reviewed_grade'] = None
                    case['grade_review_source'] = None
                    case['grade_status'] = GRADE_STATUS_NOT_REVIEWED
                    case['reviewed_grade_label'] = None
                    case['clinician_review'] = None
            if chosen_modality == 'UWF':
                try:
                    prepared = app.state.derivatives.prepare_analysis(image, source_modality='UWF')
                    case['analysis_preparation'] = {
                        'status': 'READY', 'derivative': prepared.audit_record(),
                    }
                except RetinalFieldNeedsReview as exc:
                    preparation = {
                        'status': 'NEEDS_REVIEW', 'reason_code': str(exc),
                        'source_sha256': image.sha256,
                    }
                    candidate = exc.candidate
                    if candidate is not None and candidate.mask_sha256 is not None:
                        preparation.update({
                            'candidate_mask_sha256': candidate.mask_sha256,
                            'candidate_mask_valid_fraction': candidate.valid_fraction,
                            'candidate_mask_representation_version': MASK_OVERLAY_REPRESENTATION_VERSION,
                        })
                    case['analysis_preparation'] = preparation
                except DerivativeError:
                    case['analysis_preparation'] = {
                        'status': 'FAILED', 'reason_code': 'PREPARATION_FAILED',
                        'source_sha256': image.sha256,
                    }
            else:
                case['analysis_preparation'] = {'status': 'NOT_APPLICABLE', 'source_sha256': image.sha256}

            case['visit_context'] = {
                'visit_key': request.visit_key.strip() if request.visit_key else None,
                'captured_at': request.captured_at.strip() if request.captured_at else None,
                'capture_sequence': request.capture_sequence,
                'device': request.device.strip() if request.device else None,
                'evidence_state': 'PROVIDED' if any((request.visit_key, request.captured_at,
                                                     request.capture_sequence is not None, request.device))
                else 'UNKNOWN',
            }

            patient_key = request.patient_key.strip() if request.patient_key else ''
            if patient_key:
                try:
                    patient_key = normalize_patient_key(patient_key)
                except ValueError as error:
                    raise HTTPException(422, str(error)) from None
                case['patient_key'] = patient_key
                case['patient_resolution_state'] = 'RESOLVED'
                case['patient_resolution_method'] = 'MANUAL'
                case['patient_reason_code'] = 'MANUAL_CONFIRMED'
                case['patient_confidence_or_strength'] = 'HIGH'
            else:
                case['patient_key'] = None
                case['patient_resolution_state'] = 'UNLINKED'
                case['patient_resolution_method'] = 'MANUAL'
                case['patient_reason_code'] = 'MANUAL_LEFT_UNLINKED'
                case['patient_confidence_or_strength'] = None
            case['laterality'] = request.laterality
            case['laterality_candidate'] = request.laterality
            case['laterality_resolution_state'] = 'RESOLVED'
            case['laterality_resolution_method'] = 'MANUAL'
            case['laterality_reason_code'] = 'MANUAL_UNKNOWN' if request.laterality == 'UNKNOWN' else 'MANUAL_SET'
            case['resolver_state'] = combined_resolution_state(
                case.get('patient_resolution_state', 'UNLINKED'),
                case.get('laterality_resolution_state', 'UNLINKED'),
            )
            case.setdefault('admission_history', []).append({
                'action': 'CONFIRM_IMAGE',
                'reviewer': reviewer,
                'timestamp': timestamp,
                'new': {
                    'modality_admission': admission['modality_admission'],
                    'quality_state': admission['quality_state'],
                    'retinal_modality': chosen_modality,
                },
            })
            case.setdefault('resolution_history', []).append({
                'action': 'CONFIRM_IMAGE',
                'reviewer': reviewer,
                'timestamp': timestamp,
                'new': {
                    'patient_key': case.get('patient_key'),
                    'laterality': case.get('laterality'),
                },
                'automatic_evidence': case.get('resolver_evidence'),
            })
            case.setdefault('events', []).append({
                'action': 'CONFIRM_IMAGE',
                'reviewer': reviewer,
                'timestamp': timestamp,
                'note': request.note.strip(),
                'identity_assurance': 'LOCAL_POC_SELF_DECLARED',
                'retinal_modality': chosen_modality,
            })
            case['revision'] += 1
            store.put(case)
            return detail(image_id)

    @app.put('/v1/cases/{image_id}/annotations')
    def save_human_annotations(image_id: str, request: HumanAnnotationSave):
        image = get_image(image_id)
        reviewer = request.reviewer.strip()
        if not reviewer:
            raise HTTPException(422, 'Reviewer name required')
        try:
            saved = []
            timestamp = datetime.now(timezone.utc).isoformat()
            seen_ids = set()
            for annotation in request.annotations:
                shape_id = annotation.shape_id or f'human-{uuid4().hex}'
                if shape_id in seen_ids:
                    raise ValueError('Annotation shape IDs must be unique')
                seen_ids.add(shape_id)
                saved.append({
                    'shape_id': shape_id,
                    'type': annotation.type,
                    'label': annotation.label,
                    'geometry': clean_geometry(annotation, image.size[0], image.size[1]),
                    'locked': annotation.locked,
                    'source_detection_id': annotation.source_detection_id,
                    'source': 'HUMAN',
                    'reviewer': reviewer,
                    'created_at': timestamp,
                })
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        store = current_store()
        with store.lock:
            case = store.get(image_id)
            if request.revision != case['revision']:
                raise HTTPException(409, 'Case changed; reload before saving annotations')
            previous_by_id = {
                annotation.get('shape_id'): annotation
                for annotation in (case.get('human_annotations') or [])
                if annotation.get('shape_id')
            }
            for annotation in saved:
                previous = previous_by_id.get(annotation['shape_id'])
                if annotation.get('source_detection_id') is None and previous is not None:
                    annotation['source_detection_id'] = previous.get('source_detection_id')
            saved_by_id = {annotation['shape_id']: annotation for annotation in saved}
            annotation_changes = {
                'added': sorted(set(saved_by_id) - set(previous_by_id)),
                'removed': sorted(set(previous_by_id) - set(saved_by_id)),
                'changed': sorted(
                    shape_id for shape_id in set(previous_by_id) & set(saved_by_id)
                    if previous_by_id[shape_id].get('label') != saved_by_id[shape_id].get('label')
                    or previous_by_id[shape_id].get('geometry') != saved_by_id[shape_id].get('geometry')
                ),
            }
            case['human_annotations'] = saved
            case['annotation_hash'] = annotation_set_hash(case)
            if case.get('confirmed_annotation_hash') != case['annotation_hash']:
                case['lesion_review_state'] = 'REQUIRES_CONFIRMATION'
            case['revision'] += 1
            case.setdefault('events', []).append({
                'action': 'HUMAN_ANNOTATIONS_SAVED',
                'reviewer': reviewer,
                'count': len(saved),
                'annotation_changes': annotation_changes,
                'timestamp': timestamp,
                'new_revision': case['revision'],
            })
            store.put(case)
            return detail(image_id)

    @app.put('/v1/cases/{image_id}/annotation-completeness')
    def update_annotation_completeness(image_id: str, request: AnnotationCompletenessUpdate):
        get_image(image_id)
        reviewer = request.reviewer.strip()
        if not reviewer:
            raise HTTPException(422, 'Reviewer name required')
        if request.state == 'NOT_REVIEWED':
            raise HTTPException(422, 'Completeness state requires a deliberate review action')
        store = current_store()
        with store.lock:
            case = store.get(image_id)
            if request.revision != case['revision']:
                raise HTTPException(409, 'Case changed; reload before saving completeness')
            timestamp = datetime.now(timezone.utc).isoformat()
            previous = (case.get('annotation_completeness') or {}).get(request.group)
            record = {
                'group': request.group,
                'state': request.state,
                'reviewer': reviewer,
                'timestamp': timestamp,
                'taxonomy_version': request.taxonomy_version.strip(),
                'note': request.note.strip(),
            }
            case.setdefault('annotation_completeness', {})[request.group] = record
            case['revision'] += 1
            case.setdefault('events', []).append({
                'action': 'ANNOTATION_COMPLETENESS_UPDATED',
                'group': request.group,
                'previous': previous,
                'new': record,
                'timestamp': timestamp,
                'new_revision': case['revision'],
            })
            store.put(case)
            return detail(image_id)

    @app.post('/v1/cases/{image_id}/annotations/from-ai')
    def derive_human_annotation(image_id: str, request: HumanAnnotationDerive):
        image = get_image(image_id)
        reviewer = request.reviewer.strip()
        if not reviewer:
            raise HTTPException(422, 'Reviewer name required')
        store = current_store()
        with store.lock:
            case = store.get(image_id)
            existing = next(
                (entry for entry in case.get('human_annotations', [])
                 if entry.get('source_detection_id') == request.detection_id),
                None,
            )
            if existing is not None:
                return detail(image_id)
            if request.revision != case['revision']:
                raise HTTPException(409, 'Case changed; reload before deriving an annotation')

            lesion_result = case.get('lesion') or {}
            lesion_view = lesion_review_view(lesion_result)
            target = next(
                (entry for entry in lesion_view.get('lesions', [])
                 if entry.get('detection_id') == request.detection_id),
                None,
            )
            if target is None:
                raise HTTPException(404, 'AI lesion suggestion is no longer available')
            latest_decision = next(
                (entry for entry in reversed(case.get('ai_annotation_reviews', []))
                 if entry.get('detection_id') == request.detection_id),
                None,
            )
            if latest_decision and latest_decision.get('action') == 'REJECT':
                raise HTTPException(409, 'This AI lesion suggestion was removed from the reviewed result')

            label = (latest_decision or {}).get('corrected_label') or target['canonical_label']
            rectangle = (latest_decision or {}).get('corrected_rectangle') or target['rectangle']
            x1, y1, x2, y2 = rectangle
            draft = HumanAnnotationDraft(
                type='rectangle',
                label=label,
                geometry={'x': x1, 'y': y1, 'width': x2 - x1, 'height': y2 - y1},
                source_detection_id=request.detection_id,
                locked=False,
            )
            try:
                geometry = clean_geometry(draft, image.size[0], image.size[1])
            except ValueError as error:
                raise HTTPException(422, str(error)) from None

            timestamp = datetime.now(timezone.utc).isoformat()
            annotation_id = f'human-{uuid4().hex}'
            annotation = {
                'shape_id': annotation_id,
                'type': 'rectangle',
                'label': label,
                'geometry': geometry,
                'locked': False,
                'source_detection_id': request.detection_id,
                'source': 'HUMAN',
                'reviewer': reviewer,
                'created_at': timestamp,
            }
            case.setdefault('human_annotations', []).append(annotation)
            case['annotation_hash'] = annotation_set_hash(case)
            if case.get('confirmed_annotation_hash') != case['annotation_hash']:
                case['lesion_review_state'] = 'REQUIRES_CONFIRMATION'
            case['revision'] += 1
            case.setdefault('events', []).append({
                'action': 'HUMAN_ANNOTATION_DERIVED_FROM_AI',
                'intent': request.intent,
                'source_detection_id': request.detection_id,
                'annotation_id': annotation_id,
                'reviewer': reviewer,
                'timestamp': timestamp,
                'new_revision': case['revision'],
            })
            store.put(case)
            return detail(image_id)

    @app.post('/v1/cases/{image_id}/cvat/{action}')
    def cvat(image_id: str, action: Literal['send', 'sync']):
        image = get_image(image_id)
        store = current_store()
        sync = Sync(store, app.state.remote)
        try:
            return sync.send(image) if action == 'send' else sync.pull(image)
        except OnlineError as error:
            raise HTTPException(503, str(error)) from None
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @app.get('/v1/cases/{image_id}/export')
    def export(image_id: str):
        return detail(image_id)

    @app.post('/v1/cases/{image_id}/manual-sync')
    def manual(image_id: str, request: ManualImport):
        from .contracts import LABELS
        from .cvat import reviewed_shapes
        image = get_image(image_id)
        if request.image_sha256 != image.sha256 or set(request.label_ids) != set(LABELS.values()):
            raise HTTPException(422, 'Image hash and exact four-label mapping required')
        if len(set(request.label_ids.values())) != 4:
            raise HTTPException(422, 'Label IDs must be unique')
        if request.annotations.get('tracks') or request.annotations.get('tags'):
            raise HTTPException(422, 'Only single-image shapes supported by manual sync')
        try:
            shapes = reviewed_shapes(request.annotations, request.label_ids, *image.size)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        store = current_store()
        with store.lock:
            case = store.get(image_id)
            if case['revision'] != request.revision:
                raise HTTPException(409, 'Case changed; reload')
            fingerprint = digest(request.annotations)
            if case.get('annotation_source_hash') != fingerprint:
                case['annotation_source_hash'] = fingerprint
                case['annotations'] = shapes
                case['annotation_raw'] = request.annotations
                case['annotation_hash'] = annotation_set_hash(case)
                if case.get('confirmed_annotation_hash') != case['annotation_hash']:
                    case['lesion_review_state'] = 'IMPORTED_REQUIRES_REVIEW'
                case['revision'] += 1
                case['events'].append({'action': 'MANUAL_SYNC', 'warning': 'Remote project/author not verified',
                                       'annotation_source_hash': fingerprint,
                                       'annotation_hash': case['annotation_hash']})
                store.put(case)
            return detail(image_id)
