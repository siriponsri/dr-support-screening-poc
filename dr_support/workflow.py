"""Durable review API with optimistic concurrency and explicit human actions."""
from datetime import datetime, timezone
from typing import Literal
from fastapi import HTTPException
from fastapi.responses import Response
from pydantic import Field
from .contracts import Contract
from .sync import Sync, digest
from .cvat import CVATOnline, OnlineError
from .presentation import lesion_review_view


class Review(Contract):
    revision: int = Field(ge=0)
    action: Literal['ACCEPT', 'MARK_INCORRECT', 'CORRECT_GRADE', 'ESCALATE', 'CONFIRM_ANNOTATIONS']
    reviewer: str = Field(min_length=1, max_length=80)
    grade: int | None = Field(default=None, ge=0, le=4, strict=True)
    comment: str = Field(default='', max_length=1000)


class ManualImport(Contract):
    revision: int = Field(ge=0)
    image_sha256: str
    annotations: dict
    label_ids: dict[str, int]


def install_workflow(app, store):
    app.state.store = store
    app.state.remote = CVATOnline()

    def get_image(image_id):
        if image_id not in app.state.images:
            raise HTTPException(404, 'Image not admitted')
        return app.state.images[image_id]

    def detail(image_id):
        image = get_image(image_id)
        case = store.get(image_id)
        return {**case, 'source_type': image.source_type, 'source': image.source,
                'image_sha256': image.sha256, 'width': image.size[0], 'height': image.size[1],
                'image_url': f'/v1/images/{image_id}', 'modality': image.modality,
                'lesion_review': lesion_review_view(case.get('lesion'))}

    @app.get('/v1/cases')
    def cases():
        return [detail(image_id) for image_id in app.state.images]

    @app.get('/v1/cases/{image_id}')
    def case(image_id: str):
        return detail(image_id)

    @app.get('/v1/images/{image_id}')
    def image_bytes(image_id: str):
        image = get_image(image_id)
        return Response(image.data, media_type='image/png' if image.source_type == 'SYNTHETIC' else 'image/jpeg',
                        headers={'Cache-Control': 'private, max-age=3600'})

    @app.post('/v1/cases/{image_id}/review')
    def review(image_id: str, request: Review):
        get_image(image_id)
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
            case['events'].append({**request.model_dump(), 'timestamp': datetime.now(timezone.utc).isoformat(),
                                   'new_revision': case['revision'], 'identity_assurance': 'LOCAL_POC_SELF_DECLARED'})
            store.put(case)
            return detail(image_id)

    @app.post('/v1/cases/{image_id}/cvat/{action}')
    def cvat(image_id: str, action: Literal['send', 'sync']):
        image = get_image(image_id)
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
