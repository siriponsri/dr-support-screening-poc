"""Durable review API with optimistic concurrency and explicit human actions."""
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4
from fastapi import HTTPException
from fastapi.responses import Response
from pydantic import Field
from .contracts import AdmissionMetadata, AdmissionReview, Contract
from .sync import Sync, digest
from .cvat import CVATOnline, OnlineError
from .presentation import lesion_review_view
from .services.admission import clinician_view, legacy_admission


class Review(Contract):
    revision: int = Field(ge=0)
    action: Literal['ACCEPT', 'MARK_INCORRECT', 'CORRECT_GRADE', 'ESCALATE', 'CONFIRM_ANNOTATIONS']
    reviewer: str = Field(min_length=1, max_length=80)
    grade: int | None = Field(default=None, ge=0, le=4, strict=True)
    comment: str = Field(default='', max_length=1000)


class HumanAnnotationDraft(Contract):
    shape_id: str | None = Field(default=None, max_length=80)
    type: Literal['rectangle', 'polygon', 'point', 'circle']
    label: Literal['MICROANEURYSM', 'HEMORRHAGE', 'HARD_EXUDATE', 'SOFT_EXUDATE']
    geometry: dict[str, object]
    # Omitted by older clients; saved legacy-style annotations stay protected by default.
    locked: bool = True


class HumanAnnotationSave(Contract):
    revision: int = Field(ge=0)
    reviewer: str = Field(min_length=1, max_length=80)
    annotations: list[HumanAnnotationDraft] = Field(default_factory=list, max_length=500)


class ManualImport(Contract):
    revision: int = Field(ge=0)
    image_sha256: str
    annotations: dict
    label_ids: dict[str, int]


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
        filename = image.filename if image is not None else record.get('filename')
        width = image.size[0] if image is not None else record.get('width')
        height = image.size[1] if image is not None else record.get('height')
        return {**case, 'source_type': image.source_type if image is not None else 'PUBLIC',
                'source': image.source if image is not None else 'WORKSPACE_INPUT',
                'filename': filename or None,
                'display_name': Path(filename).stem if filename else image_id,
                'image_sha256': image.sha256 if image is not None else None,
                'width': width, 'height': height,
                'image_url': f'/v1/images/{image_id}' if image is not None else None,
                'modality': image.modality if image is not None else 'CFP',
                'admission': record,
                'admission_ui': clinician_view(record) if record is not None else None,
                'admission_history': case.get('admission_history', []),
                'lesion_review': lesion_review_view(case.get('lesion')),
                'human_annotations': case.get('human_annotations', []),
                'clinician_review': case.get('clinician_review'),
                'review_history': case.get('review_history', [])}

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

    @app.post('/v1/cases/{image_id}/review')
    def review(image_id: str, request: Review):
        get_image(image_id)
        store = current_store()
        with store.lock:
            case = store.get(image_id)
            if request.revision != case['revision']:
                raise HTTPException(409, 'Case changed; reload before reviewing')
            if not request.reviewer.strip():
                raise HTTPException(422, 'Reviewer name required')
            if request.action == 'ACCEPT':
                if not case['global'] or case['global']['grade'] is None:
                    raise HTTPException(409, 'No grade suggestion to accept')
                case['reviewed_grade'] = case['global']['grade']
                case['grade_review_source'] = 'AI_ACCEPTED'
                case['state'] = 'REVIEWED'
            elif request.action == 'CORRECT_GRADE':
                if request.grade is None:
                    raise HTTPException(422, 'Corrected/manual grade required')
                case['reviewed_grade'] = request.grade
                case['grade_review_source'] = ('AI_CORRECTED' if case.get('global') and
                                               case['global'].get('grade') is not None else 'MANUAL')
                case['state'] = 'REVIEWED'
            elif request.action == 'CONFIRM_ANNOTATIONS':
                if not case.get('annotation_hash'):
                    raise HTTPException(409, 'Import or sync annotations first')
                case['lesion_review_state'] = 'REVIEWED'
                case['confirmed_annotation_hash'] = case['annotation_hash']
            else:
                if request.action == 'MARK_INCORRECT' and (not case.get('global') or
                                                            case['global'].get('grade') is None):
                    raise HTTPException(409, 'No AI grade suggestion to mark incorrect')
                case['state'] = 'NEEDS_CORRECTION' if request.action == 'MARK_INCORRECT' else 'ESCALATED'
                case['reviewed_grade'] = None
                case['grade_review_source'] = None
            case['revision'] += 1
            timestamp = datetime.now(timezone.utc).isoformat()
            event = {**request.model_dump(), 'timestamp': timestamp,
                     'new_revision': case['revision'], 'identity_assurance': 'LOCAL_POC_SELF_DECLARED'}
            case.setdefault('events', []).append(event)
            review_record = {
                'reviewer': request.reviewer.strip(),
                'final_grade': case.get('reviewed_grade'),
                'review_action': request.action,
                'remark': request.comment,
                'timestamp': timestamp,
                'revision': case['revision'],
            }
            case['clinician_review'] = review_record
            case.setdefault('review_history', []).append(review_record)
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
            case['human_annotations'] = saved
            case['revision'] += 1
            case.setdefault('events', []).append({
                'action': 'HUMAN_ANNOTATIONS_SAVED',
                'reviewer': reviewer,
                'count': len(saved),
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
            if case.get('annotation_hash') != fingerprint:
                case['annotation_hash'] = fingerprint
                case['annotations'] = shapes
                case['annotation_raw'] = request.annotations
                case['lesion_review_state'] = 'IMPORTED_REQUIRES_REVIEW'
                case['revision'] += 1
                case['events'].append({'action': 'MANUAL_SYNC', 'warning': 'Remote project/author not verified',
                                       'annotation_hash': fingerprint})
                store.put(case)
            return detail(image_id)
