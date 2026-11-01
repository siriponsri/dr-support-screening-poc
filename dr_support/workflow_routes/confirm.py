"""Review workflow routes: Admission review, patient/eye resolver review and Confirm Image.

Installed by `workflow.install_workflow`; code moved verbatim from workflow.py."""

from datetime import datetime, timezone

from fastapi import HTTPException

from ..contracts import AdmissionMetadata, AdmissionReview, ResolverReview
from ..grade import GRADE_STATUS_NOT_REVIEWED
from ..imaging import DerivativeError
from ..imaging.derivatives import MASK_OVERLAY_REPRESENTATION_VERSION
from ..imaging.retinal_field import RetinalFieldNeedsReview
from ..services.admission import legacy_admission
from ..services.patient_presentation import preserves_trusted_hospital_key
from ..services.resolver import combined_resolution_state, normalize_patient_key
from ..services.source_mutation_gate import guard_writes
from ..workflow import ConfirmImage


def install_confirm_routes(app, ctx):
    """Admission review, patient/eye resolver review and Confirm Image."""
    mutation_gate = ctx.mutation_gate
    current_store = ctx.current_store
    case_with_admission = ctx.case_with_admission
    ensure_resolution = ctx.ensure_resolution
    get_image = ctx.get_image
    detail = ctx.detail

    @app.post('/v1/cases/{image_id}/admission')
    @guard_writes(mutation_gate)
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
    @guard_writes(mutation_gate)
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
    @guard_writes(mutation_gate)
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
            preserve_patient = preserves_trusted_hospital_key(case, current, request.patient_key)
            patient_key = request.patient_key.strip() if request.patient_key else ''
            if patient_key and not preserve_patient:
                try:
                    patient_key = normalize_patient_key(patient_key)
                except ValueError as error:
                    raise HTTPException(422, str(error)) from None
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

            if preserve_patient:
                pass  # Preserve the trusted key and its authorized-source provenance.
            elif patient_key:
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
            if not (preserve_patient and request.laterality == case.get('laterality')):
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
