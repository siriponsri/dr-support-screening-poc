"""Single-repo, multi-runtime-profile entrypoint.

This module is the single ``create_app`` factory used by every deployment
profile. The active profile is selected via ``APP_PROFILE``:

- ``review``    (default)   clinician workstation: UI, cases, review, CVAT, remote-proxy.
- ``model_api``             GPU deployment of the Remote Model API contract.
- ``full``                  both review and model_api surfaces mounted on one app
                            for public/synthetic demos.

Profile invariants
------------------

- ``APP_PROFILE=review`` requires ``MODEL_RUNTIME=remote`` so the review
  workstation never tries to load RETFound / PRISM weights locally.
- ``APP_PROFILE=model_api`` requires ``MODEL_RUNTIME=local`` because the model
  API is the GPU-backed inference surface.
- ``APP_PROFILE=full`` is intended for demos and requires ``MODEL_RUNTIME=local``.

These invariants are enforced at startup; misconfiguration is a hard error,
not a silent fallback.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI

from .api import create_app as create_review_app
from .services.model_api import create_app as create_model_api_app


VALID_PROFILES = ('review', 'model_api', 'full')


def _resolve_profile(profile: str | None) -> str:
    value = (profile or os.environ.get('APP_PROFILE') or 'review').strip().lower()
    if value not in VALID_PROFILES:
        raise ValueError(
            f"Unknown APP_PROFILE={value!r}; expected one of {', '.join(VALID_PROFILES)}"
        )
    return value


def _resolve_runtime() -> str:
    return (os.environ.get('MODEL_RUNTIME') or 'local').strip().lower()


def _enforce_invariants(profile: str, runtime: str) -> None:
    if profile == 'review':
        if runtime == 'local':
            raise RuntimeError(
                "APP_PROFILE=review requires MODEL_RUNTIME=remote. "
                "Review workstations must not load RETFound/PRISM weights locally."
            )
        if runtime != 'remote':
            raise RuntimeError(f"APP_PROFILE=review requires MODEL_RUNTIME=remote, got {runtime!r}")
        if not os.environ.get('REMOTE_MODEL_URL'):
            raise RuntimeError(
                'APP_PROFILE=review requires REMOTE_MODEL_URL to be set in the runtime environment.'
            )
    elif profile == 'model_api':
        if runtime == 'remote':
            raise RuntimeError(
                "APP_PROFILE=model_api requires MODEL_RUNTIME=local. "
                "The model API is the GPU-backed inference surface; it cannot proxy to itself."
            )
        if runtime != 'local':
            raise RuntimeError(
                f"APP_PROFILE=model_api requires MODEL_RUNTIME=local, got {runtime!r}"
            )
    elif profile == 'full':
        if runtime == 'remote':
            raise RuntimeError(
                "APP_PROFILE=full is intended for local demos; it requires MODEL_RUNTIME=local, "
                "not remote."
            )
        if runtime != 'local':
            raise RuntimeError(
                f"APP_PROFILE=full requires MODEL_RUNTIME=local, got {runtime!r}"
            )


def _merge_apps(review: FastAPI, model_api: FastAPI, profile: str) -> FastAPI:
    """Build a single FastAPI app that exposes both surfaces.

    Both child apps already have title/version metadata. We assemble a new
    top-level FastAPI app and graft their routes on top. ``Mount`` entries
    (e.g. the static UI under ``/ui``) are transferred verbatim; route
    handlers keep their original docstrings.
    """
    app = FastAPI(title='DR Support Screening POC', version='0.3.0')

    for source_app in (review, model_api):
        for route in source_app.routes:
            # Mount entries carry no endpoint attribute; pass them through.
            if hasattr(route, 'endpoint') and callable(route.endpoint):
                route.endpoint.__doc__ = route.endpoint.__doc__ or ''
            app.router.routes.append(route)

    app.state.profile = profile
    app.state.runtime = _resolve_runtime()
    app.state.review_app = review
    app.state.model_api_app = model_api
    return app


def create_app(profile: str | None = None) -> FastAPI:
    """Build the FastAPI app for the configured profile.

    Parameters
    ----------
    profile:
        Optional explicit profile override. Falls back to the ``APP_PROFILE``
        environment variable, then to ``"review"``.
    """
    resolved_profile = _resolve_profile(profile)
    runtime = _resolve_runtime()
    _enforce_invariants(resolved_profile, runtime)

    if resolved_profile == 'review':
        app = create_review_app()
        app.state.profile = resolved_profile
        app.state.runtime = runtime
        return app
    if resolved_profile == 'model_api':
        app = create_model_api_app()
        app.state.profile = resolved_profile
        app.state.runtime = runtime
        return app
    # full
    review = create_review_app()
    model_api = create_model_api_app()
    return _merge_apps(review, model_api, resolved_profile)


def app_factory() -> Any:
    """Hook for ``uvicorn --factory dr_support.app:app_factory`` style invocations."""
    return create_app()
