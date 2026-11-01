"""Review workflow routes: Grade review (Confirm DR Grade), queue include/exclude and AI lesion ROI decisions.

Installed by `workflow.install_workflow`; code moved verbatim from workflow.py."""

from datetime import datetime, timezone

from fastapi import HTTPException

from ..grade import (
    GRADE_STATUS_CONFIRMED,
    GRADE_STATUS_NEEDS_SECOND_REVIEW,
    GRADE_STATUS_NOT_REVIEWED,
    GRADE_STATUS_UNGRADABLE,
    grade_label,
)
from ..presentation import annotation_set_hash, lesion_review_view
from ..referral import current_referral, derive_referral
from ..services.source_identity import source_identity_reason
from ..services.source_mutation_gate import guard_writes
from ..workflow import (
    LesionReviewAction,
    QueueAction,
    Review,
    _current_global_result,
    _legacy_grade_reviews,
    _require_current_spatial_ai,
)


def install_review_routes(app, ctx):
    """Grade review (Confirm DR Grade), queue include/exclude and AI lesion ROI decisions."""
    mutation_gate = ctx.mutation_gate
    current_store = ctx.current_store
    admission_record = ctx.admission_record
    case_with_admission = ctx.case_with_admission
    get_image = ctx.get_image
    detail = ctx.detail

    @app.post('/v1/cases/{image_id}/review')
    @guard_writes(mutation_gate)
    def review(image_id: str, request: Review):
        get_image(image_id)
        store = current_store()
        with store.lock:
            case = store.get(image_id)
            # Historical CFP evidence cannot authorize AI provenance on a
            # source whose image type is now UWF or still unknown.
            current_admission = admission_record(image_id) or {}
            if request.action in {'ACCEPT', 'CORRECT_GRADE', 'ADJUDICATE_GRADE', 'CONFIRM_ANNOTATIONS'}:
                if source_identity_reason(case, app.state.images.get(image_id), current_admission):
                    raise HTTPException(409, 'Source identity changed; reload before confirming this image')
            current_ai = _current_global_result(case, app.state.images.get(image_id), current_admission)
            if request.revision != case['revision']:
                already_confirmed = (
                    request.action == 'CONFIRM_ANNOTATIONS'
                    and case.get('lesion_review_state') == 'REVIEWED'
                    and case.get('confirmed_annotation_hash') == annotation_set_hash(case)
                    and (case.get('annotation_confirmation') or {}).get('reviewer', '').strip().casefold()
                    == request.reviewer.strip().casefold()
                )
                if already_confirmed:
                    return detail(image_id)
                raise HTTPException(409, 'Case changed; reload before reviewing')
            if not request.reviewer.strip():
                raise HTTPException(422, 'Reviewer name required')
            previous_referral = current_referral(case)
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
                if (
                    request.action == 'ADJUDICATE_GRADE'
                    and case.get('grade_status') != GRADE_STATUS_NEEDS_SECOND_REVIEW
                ):
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
                'source_sha256': app.state.images[image_id].sha256,
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
                    'source_sha256': app.state.images[image_id].sha256,
                    'annotation_set_hash': case['confirmed_annotation_hash'],
                }
            if grade_action or request.action in {'MARK_INCORRECT', 'ESCALATE'}:
                referral = derive_referral(case)
                case['referral_current'] = referral
                case.setdefault('referral_history', []).append({
                    'timestamp': timestamp,
                    'revision': case['revision'],
                    'reviewer': request.reviewer.strip(),
                    'review_action': request.action,
                    'previous': previous_referral,
                    'current': referral,
                })
            store.put(case)
            return detail(image_id)

    @app.post('/v1/cases/{image_id}/queue')
    @guard_writes(mutation_gate)
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
    @guard_writes(mutation_gate)
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
            _require_current_spatial_ai(case, image, admission_record(image_id))
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
