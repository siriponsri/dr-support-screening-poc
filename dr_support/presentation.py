"""Clinician-facing lesion selection policy.

Raw provider output stays intact in the case record. This module derives the bounded
review overlay / CVAT pre-label subset without changing model provenance.
"""
import hashlib
import json
import os
from dr_support.contracts import LABELS, LesionResult

DEFAULT_MAX_PER_CLASS = 25
DEFAULT_MAX_TOTAL = 80


def lesion_detection_id(lesion) -> str:
    """Return a stable, review-only identity without changing raw model output."""
    if isinstance(lesion, dict):
        source_label = lesion.get('source_label')
        canonical_label = lesion.get('canonical_label')
        rectangle = lesion.get('rectangle')
        score = lesion.get('score')
    else:
        source_label = lesion.source_label
        canonical_label = lesion.canonical_label
        rectangle = lesion.rectangle
        score = lesion.score
    payload = {
        'source_label': source_label,
        'canonical_label': canonical_label,
        'rectangle': list(rectangle),
        'score': score,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return 'ai-' + hashlib.sha256(encoded).hexdigest()[:20]


def _bounded_int(name: str, default: int, maximum: int = 500) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f'{name} must be an integer') from exc
    if not 1 <= value <= maximum:
        raise ValueError(f'{name} must be between 1 and {maximum}')
    return value


def review_policy() -> dict:
    raw = os.environ.get('REVIEW_THRESHOLDS', '{}') or '{}'
    try:
        thresholds = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError('REVIEW_THRESHOLDS must be a JSON object') from exc
    if not isinstance(thresholds, dict) or set(thresholds) - set(LABELS):
        raise ValueError('REVIEW_THRESHOLDS keys must be MA/HE/EX/SE')
    clean = {}
    for key, value in thresholds.items():
        try:
            score = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError('REVIEW_THRESHOLDS values must be numbers in [0,1]') from exc
        if not 0 <= score <= 1:
            raise ValueError('REVIEW_THRESHOLDS values must be numbers in [0,1]')
        clean[key] = score
    return {
        'thresholds': clean,
        'max_per_class': _bounded_int('REVIEW_MAX_PER_CLASS', DEFAULT_MAX_PER_CLASS, 200),
        'max_total': _bounded_int('REVIEW_MAX_TOTAL', DEFAULT_MAX_TOTAL, 500),
    }


def review_selection(result: LesionResult) -> tuple[list, dict]:
    """Return a bounded display/pre-label subset while preserving ``result.lesions``."""
    policy = review_policy()
    selected = []
    for source_label in LABELS:
        threshold = policy['thresholds'].get(source_label, 0.0)
        candidates = [x for x in result.lesions if x.source_label == source_label and x.score >= threshold]
        candidates.sort(key=lambda x: x.score, reverse=True)
        selected.extend(candidates[:policy['max_per_class']])
    selected.sort(key=lambda x: x.score, reverse=True)
    selected = selected[:policy['max_total']]
    return selected, policy


def lesion_review_view(raw_result: dict | None) -> dict | None:
    if not raw_result:
        return None
    result = LesionResult.model_validate(raw_result)
    selected, policy = review_selection(result)
    return {
        'raw_count': len(result.lesions),
        'suggestion_count': len(selected),
        'filtered_count': len(result.lesions) - len(selected),
        'policy': policy,
        'lesions': [
            {**x.model_dump(mode='json'), 'detection_id': lesion_detection_id(x)}
            for x in selected
        ],
        'note': 'Raw provider output is retained; this bounded subset is for clinician display and CVAT pre-label only.',
    }


def _review_status(case: dict) -> str:
    return {
        'REVIEWED': 'Reviewed',
        'NEEDS_CORRECTION': 'Needs correction',
        'ESCALATED': 'Escalated',
    }.get(case.get('state'), 'Pending review')


def review_evidence_view(case: dict) -> dict:
    """Build a compact audit projection without rewriting AI or human records."""
    lesion_result = case.get('lesion')
    lesion_view = lesion_review_view(lesion_result) if lesion_result else None
    decisions = {}
    decision_history = case.get('ai_annotation_reviews') or []
    for decision in decision_history:
        detection_id = decision.get('detection_id')
        if isinstance(detection_id, str):
            decisions[detection_id] = decision

    items = []
    unresolved = 0
    if lesion_view:
        model_id = lesion_result.get('model_id')
        model_version = lesion_result.get('model_version')
        for lesion in lesion_view['lesions']:
            detection_id = lesion['detection_id']
            decision = decisions.get(detection_id)
            action = decision.get('action') if decision else 'AI_SUGGESTED'
            if action == 'CONFIRM':
                status = 'CLINICIAN_CONFIRMED'
            elif action == 'REJECT':
                status = 'CLINICIAN_REMOVED'
            elif action == 'CORRECT':
                original_label = decision.get('original_label')
                original_rectangle = decision.get('original_rectangle')
                corrected_label = decision.get('corrected_label')
                corrected_rectangle = decision.get('corrected_rectangle')
                label_changed = corrected_label is not None and corrected_label != original_label
                geometry_changed = corrected_rectangle is not None and corrected_rectangle != original_rectangle
                status = 'CORRECTED'
                if label_changed and not geometry_changed:
                    status = 'LABEL_CHANGED'
                elif geometry_changed and not label_changed:
                    status = 'GEOMETRY_CHANGED'
            else:
                status = 'AI_SUGGESTED'
                unresolved += 1
            items.append({
                'annotation_id': detection_id,
                'source': 'AI',
                'label': lesion['canonical_label'],
                'score': lesion['score'],
                'original_score': decision.get('original_score') if decision else lesion['score'],
                'status': status,
                'model_id': model_id,
                'model_version': model_version,
                'reviewer': decision.get('reviewer') if decision else None,
                'timestamp': decision.get('timestamp') if decision else None,
                'original_label': decision.get('original_label') if decision else lesion['canonical_label'],
                'original_rectangle': decision.get('original_rectangle') if decision else lesion['rectangle'],
                'corrected_label': decision.get('corrected_label') if decision else None,
                'corrected_rectangle': decision.get('corrected_rectangle') if decision else None,
            })

    human_annotations = case.get('human_annotations') or []
    for annotation in human_annotations:
        items.append({
            'annotation_id': annotation.get('shape_id'),
            'source': 'HUMAN',
            'label': annotation.get('label'),
            'score': None,
            'original_score': None,
            'status': 'CLINICIAN_ADDED',
            'model_id': None,
            'model_version': None,
            'reviewer': annotation.get('reviewer'),
            'timestamp': annotation.get('created_at'),
            'original_label': None,
            'original_rectangle': None,
            'corrected_label': None,
            'corrected_rectangle': None,
            'source_detection_id': annotation.get('source_detection_id'),
        })

    confirmed = sum(item.get('status') == 'CLINICIAN_CONFIRMED' for item in items)
    removed = sum(item.get('status') == 'CLINICIAN_REMOVED' for item in items)
    corrected = sum(item.get('status') in {'CORRECTED', 'LABEL_CHANGED', 'GEOMETRY_CHANGED'} for item in items)
    added = sum(item.get('status') == 'CLINICIAN_ADDED' for item in items)
    latest = case.get('clinician_review') or {}
    if not latest:
        for item in reversed(items):
            if item.get('reviewer') or item.get('timestamp'):
                latest = item
                break
    admission = case.get('admission') or {}
    source_sha256 = admission.get('source_sha256')
    if not source_sha256 and lesion_result:
        source_sha256 = (lesion_result.get('provenance') or {}).get('image_sha256')

    return {
        'status': _review_status(case),
        'reviewer': latest.get('reviewer'),
        'timestamp': latest.get('timestamp'),
        'summary': {
            'confirmed': confirmed,
            'added': added,
            'removed': removed,
            'corrected': corrected,
        },
        'unresolved_count': unresolved,
        'items': items,
        'model_id': lesion_result.get('model_id') if lesion_result else None,
        'model_version': lesion_result.get('model_version') if lesion_result else None,
        'source_sha256': source_sha256,
        'analysis_sha256': ((case.get('analysis_derivative') or {}).get('analysis_sha256')),
        'note': 'Counts describe review actions, not model accuracy or clinical outcomes.',
    }


def annotation_set_payload(case: dict) -> dict:
    """Return the active annotation state used for case-level finality.

    AI evidence remains represented as AI evidence.  Human corrections and
    removals are projected into the active set only for the purpose of the
    deterministic finality hash; the original evidence stays in the case.
    """
    evidence = review_evidence_view(case)
    active = [
        {
            'annotation_id': item.get('annotation_id'),
            'source': item.get('source'),
            'label': item.get('corrected_label') or item.get('label'),
            'score': item.get('score') if item.get('corrected_label') is None else None,
            'rectangle': item.get('corrected_rectangle') or item.get('original_rectangle'),
            'status': item.get('status'),
        }
        for item in evidence.get('items', [])
        if item.get('status') != 'CLINICIAN_REMOVED'
    ]
    imported = [
        {
            'annotation_id': item.get('remote_id', index),
            'label': item.get('canonical_label'),
            'geometry': item.get('geometry'),
            'source': 'CVAT_IMPORTED',
        }
        for index, item in enumerate(case.get('annotations') or [])
    ]
    return {
        'active': sorted(active, key=lambda item: str(item.get('annotation_id'))),
        'human': case.get('human_annotations') or [],
        'cvat': sorted(imported, key=lambda item: str(item.get('annotation_id'))),
    }


def annotation_set_hash(case: dict) -> str:
    """Hash the current active annotation state without including PHI."""
    encoded = json.dumps(annotation_set_payload(case), sort_keys=True,
                          separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()
