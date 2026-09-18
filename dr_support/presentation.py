"""Clinician-facing lesion selection policy.

Raw provider output stays intact in the case record. This module derives the bounded
review overlay / CVAT pre-label subset without changing model provenance.
"""
import json
import os
from dr_support.contracts import LABELS, LesionResult

DEFAULT_MAX_PER_CLASS = 25
DEFAULT_MAX_TOTAL = 80


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
        'lesions': [x.model_dump(mode='json') for x in selected],
        'note': 'Raw provider output is retained; this bounded subset is for clinician display and CVAT pre-label only.',
    }
