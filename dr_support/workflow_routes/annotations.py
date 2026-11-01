"""Review workflow routes: Human annotation set, annotation completeness and annotations derived from an AI ROI.

Installed by `workflow.install_workflow`; code moved verbatim from workflow.py."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from ..presentation import annotation_set_hash, lesion_review_view
from ..services.source_mutation_gate import guard_writes
from ..workflow import (
    AnnotationCompletenessUpdate,
    HumanAnnotationDerive,
    HumanAnnotationDraft,
    HumanAnnotationSave,
    _require_current_spatial_ai,
)


def install_annotations_routes(app, ctx):
    """Human annotation set, annotation completeness and annotations derived from an AI ROI."""
    mutation_gate = ctx.mutation_gate
    current_store = ctx.current_store
    admission_record = ctx.admission_record
    get_image = ctx.get_image
    detail = ctx.detail
    clean_geometry = ctx.clean_geometry

    @app.put('/v1/cases/{image_id}/annotations')
    @guard_writes(mutation_gate)
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
    @guard_writes(mutation_gate)
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
    @guard_writes(mutation_gate)
    def derive_human_annotation(image_id: str, request: HumanAnnotationDerive):
        image = get_image(image_id)
        reviewer = request.reviewer.strip()
        if not reviewer:
            raise HTTPException(422, 'Reviewer name required')
        store = current_store()
        with store.lock:
            case = store.get(image_id)
            _require_current_spatial_ai(case, image, admission_record(image_id))
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
