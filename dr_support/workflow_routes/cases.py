"""Review workflow routes: Case list, case detail and the prior-visit comparison (read only).

Installed by `workflow.install_workflow`; code moved verbatim from workflow.py."""

from fastapi import HTTPException

from ..comparison import compare_cases


def install_cases_routes(app, ctx):
    """Case list, case detail and the prior-visit comparison (read only)."""
    detail = ctx.detail

    @app.get('/v1/cases')
    def cases():
        image_ids = list(app.state.admissions)
        image_ids.extend(image_id for image_id in app.state.images if image_id not in app.state.admissions)
        return [detail(image_id) for image_id in image_ids]

    @app.get('/v1/cases/{image_id}')
    def case(image_id: str):
        return detail(image_id)

    @app.get('/v1/cases/{image_id}/comparison')
    def comparison(image_id: str, other_image_id: str | None = None):
        if image_id not in app.state.images and image_id not in app.state.admissions:
            raise HTTPException(404, 'Comparison image is not available in this workspace')
        current = detail(image_id)
        if other_image_id is not None:
            if image_id == other_image_id:
                return {'eligible': False, 'reason': 'SAME_IMAGE'}
            if other_image_id not in app.state.images and other_image_id not in app.state.admissions:
                raise HTTPException(404, 'Comparison image is not available in this workspace')
            previous = detail(other_image_id)
        else:
            from ..comparison import resolve_previous_case

            candidates = [detail(candidate_id) for candidate_id in app.state.admissions
                          if candidate_id != image_id]
            resolved = resolve_previous_case(current, candidates)
            if resolved is None:
                return {'eligible': False, 'reason': 'NO_VERIFIED_PREVIOUS_EXAM'}
            if isinstance(resolved, dict) and resolved.get('reason'):
                return {'eligible': False, 'reason': resolved['reason']}
            previous = resolved
        result = compare_cases(previous, current)
        if result.get('eligible'):
            result['comparison_state'] = 'AUTO_PREVIOUS' if other_image_id is None else 'EXPLICIT_PAIR'
        return result
