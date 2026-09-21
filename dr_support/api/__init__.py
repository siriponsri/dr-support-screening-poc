"""Provider-neutral review API for the DR Support Screening POC.

This package exposes the clinician workstation surface:

- ``GET /health``            liveness / status
- ``GET /v1/models``         provider readiness and metadata
- ``GET /v1/cases``          worklist of admitted cases
- ``GET /v1/cases/{id}``     case detail
- ``GET /v1/images/{id}``    admitted image bytes
- ``GET /v1/images/{id}/display`` browser-safe display representation
- ``POST /v1/infer/global``  grade inference (local mock or remote proxy)
- ``POST /v1/infer/lesion-roi`` lesion ROI inference (local mock or remote proxy)
- ``POST /v1/cases/{id}/review`` clinician review action
- ``PUT /v1/cases/{id}/annotations`` save explicit human annotations
- ``POST /v1/cases/{id}/cvat/{send,sync}`` CVAT Online round-trip
- ``POST /v1/cases/{id}/manual-sync`` manual CVAT sync fallback
- ``GET /ui/index.html``     V2 clinician UI (static)

The model_api profile uses a different surface; see
``dr_support.services.model_api``.

The single ``create_app`` factory preserves the historical behaviour used by
the V2 UI and the existing tests.

For backward compatibility with ``uvicorn dr_support.api:app`` invocations
(the historical single-server entrypoint used by ``START.cmd`` and the JS
UI smoke test), a module-level ``app`` instance is exposed. Production
deployments that need strict profile/runtime invariants should instead use
``dr_support.app:app_factory`` and set ``APP_PROFILE`` explicitly.
"""
from ._factory import create_app as _create_review_app

__all__ = ['create_app', 'app']


def create_app(state_path=None, include_samples=True, include_demo_fixtures=True):
    """Legacy review-API factory used by tests and the JS UI smoke.

    Delegates to ``dr_support.api._factory.create_app`` and preserves the
    historical single-server semantics (local inference by default,
    ``MODEL_RUNTIME=remote`` when the environment says so). The strict
    profile/runtime invariants enforced by ``dr_support.app.create_app``
    are intentionally NOT applied here so that the existing pytest suite
    and the V2 UI smoke can continue to import this symbol.
    """
    return _create_review_app(
        state_path=state_path,
        include_samples=include_samples,
        include_demo_fixtures=include_demo_fixtures,
    )


def _build_default_app():
    """Construct the default review app for ``dr_support.api:app``.

    Honours ``MODEL_RUNTIME`` exactly the way the legacy single-server mode did.
    """
    return _create_review_app(include_samples=True)


app = _build_default_app()

