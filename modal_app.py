"""Modal deployment adapter for the DR Support Screening POC ``model_api`` profile.

This module is the **only** place the codebase imports the Modal SDK. It is
intentionally kept thin so the existing ``dr_support.app.create_app`` factory
remains the single source of truth for the FastAPI surface; the Modal adapter
just hosts that app on Modal's serverless GPU infrastructure.

Design invariants (M0.6)
------------------------

- **Profile**: ``APP_PROFILE=model_api`` (the GPU-backed Remote Model API
  contract). The clinician UI is never hosted in Modal; the review workstation
  remains a separate deployment that proxies here.
- **GPU**: defaults to ``T4`` (matches the v0.4.0 HF Docker Space target). The
  acceptable fallback ladder is ``L4`` → ``A10`` — see ``docs/MODAL_DEPLOYMENT.md``
  for the memory envelope rationale. Hardware is never changed silently.
- **Concurrency**: a single Modal container holds at most **one** inference call
  at a time. This preserves the v0.4.0 single-worker invariant: the api-level
  ``RLock`` keeps activation memory bounded by a single forward pass on the GPU.
- **Scale-to-zero**: no warm-pool is configured. Modal will spin the container
  down between requests; the first request pays the cold-start cost.
- **Secrets**: ``REMOTE_MODEL_TOKEN`` (when set) is injected via a Modal
  ``Secret`` named ``dr-support-remote-model-token``. The secret is never
  hardcoded, logged, or echoed by this module — it is forwarded verbatim into
  the FastAPI app via ``os.environ`` so the existing
  ``dr_support.services.model_api._require_bearer`` helper handles auth.
- **Image strategy**: the existing ``Dockerfile`` is reused via
  ``modal.Image.from_dockerfile``. We deliberately do **not** duplicate
  dependency definitions in this module: the Dockerfile already pins the
  CUDA-enabled ``torch`` stack, the project extras, and runs
  ``python -m dr_support.setup_models --model all`` to bake the SHA256-verified
  model sources + weights into the image. The Modal image is the same artefact
  that ships to the HF Docker Space target; no second source of truth.
- **Public / synthetic POC only**: no training, no calibration, no clinical
  guidance, no autonomous referral.

Local invocation
----------------

This module is **not** required to import the project; ``modal`` itself is an
optional dependency (``pip install -e ".[modal]"``). Local contract tests in
``tests/test_modal_adapter.py`` import the helpers but stub the ``modal``
namespace where possible so they do not require Modal cloud execution.

Operator workflow (see ``docs/MODAL_DEPLOYMENT.md`` for the full runbook):

    modal setup
    modal secret create dr-support-remote-model-token REMOTE_MODEL_TOKEN=...
    modal deploy modal_app.py
    modal app logs dr-support-screening-poc-model-api
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Public, importable helpers — usable without the modal SDK installed.
# ---------------------------------------------------------------------------


REPO_ROOT = Path(__file__).resolve().parent
DOCKERFILE_PATH = REPO_ROOT / 'Dockerfile'

APP_NAME = 'dr-support-screening-poc-model-api'

# Default GPU target. Matches the v0.4.0 HF Docker Space target (T4 small,
# 16 GB VRAM). PRISM loads 4 lesion classes x 5 folds = 20 ultralytics YOLO
# models plus the ROI cropper; the released checkpoint sizes (~6 MB each)
# fit comfortably on a T4. If the deployment operator observes OOM, see the
# documented fallback ladder below.
DEFAULT_GPU = 'T4'
# Documented fallback ladder. Used only when ``MODAL_GPU`` is explicitly set
# to one of these values; never silently.
ACCEPTED_GPUS = ('T4', 'L4', 'A10')

# Secret name on Modal that supplies ``REMOTE_MODEL_TOKEN``. The secret is
# OPTIONAL — when unset the model_api service is publicly reachable on the
# bearer-token-protected endpoints. The Modal dashboard is the canonical place
# to create this secret.
REMOTE_TOKEN_SECRET_NAME = 'dr-support-remote-model-token'

# Inference concurrency. The api-level ``RLock`` in
# ``dr_support.services.model_api`` is the actual correctness guard; we set
# ``max_inputs=1`` here so a single Modal container never tries to schedule
# two inference calls onto the same GPU at the same time. ``target_inputs=1``
# keeps Modal's autoscaler honest about cold starts.
MAX_INPUTS_PER_CONTAINER = 1
TARGET_INPUTS_PER_CONTAINER = 1

# We deliberately do NOT configure a warm pool. Modal will scale the container
# down between requests so the deployment only pays for active inference time.
# The container_idle_timeout keeps the cold-start penalty bounded for a short
# post-traffic window (default behaviour is fine; documented for clarity).


def _resolve_gpu() -> str:
    """Return the GPU string passed to ``@app.function(gpu=...)``.

    Honours the ``MODAL_GPU`` environment variable so the operator can opt
    into the documented fallback ladder without editing this file. Any value
    not in :data:`ACCEPTED_GPUS` is rejected — we never silently change
    hardware.
    """
    requested = (os.environ.get('MODAL_GPU') or DEFAULT_GPU).strip()
    if requested not in ACCEPTED_GPUS:
        raise ValueError(
            f'MODAL_GPU={requested!r} is not an accepted Modal GPU target; '
            f'expected one of {", ".join(ACCEPTED_GPUS)}.'
        )
    return requested


def build_asgi_app() -> Any:
    """Construct the ASGI app that ``@modal.asgi_app`` will serve.

    This is a thin wrapper around ``dr_support.app.create_app`` that pins the
    production profile. It deliberately lives in this module so the
    ``modal_app.py`` shape matches the way the operator invokes
    ``modal deploy modal_app.py`` — they can read this file top-to-bottom and
    see exactly what surface gets exposed.
    """
    # Set the runtime contract BEFORE importing the project so the dispatcher
    # sees the right ``APP_PROFILE``/``MODEL_RUNTIME`` invariants.
    os.environ.setdefault('APP_PROFILE', 'model_api')
    os.environ.setdefault('MODEL_RUNTIME', 'local')
    os.environ.setdefault('INFERENCE_DEVICE', 'cuda:0')
    os.environ.setdefault('HOST', '0.0.0.0')
    # Modal's @modal.asgi_app manages the port; we keep uvicorn happy with a
    # conventional value but the actual listening port is the one Modal
    # exposes to the ASGI frontend.
    os.environ.setdefault('PORT', '8000')
    os.environ.setdefault('WORKERS', '1')

    from dr_support.app import create_app

    return create_app()


# ---------------------------------------------------------------------------
# Modal SDK glue — only constructed when ``modal`` is importable. The
# decorators wrap a module-scope function (``web``) because Modal can only
# import functions defined in global scope.
# ---------------------------------------------------------------------------


def _build_modal_objects() -> dict[str, Any]:
    """Construct and register the Modal ``App``, ``Image``, and ASGI function.

    Returns a small namespace dict so callers (and tests) can introspect the
    pieces without depending on the Modal SDK's internal class hierarchy.
    The ``web`` function is registered as a *module-scope* binding by the
    caller; see the bottom of this file.
    """
    import modal  # local import so the module is importable without the SDK

    image = modal.Image.from_dockerfile(
        str(DOCKERFILE_PATH),
        # ``add_python`` is not needed because the Dockerfile installs Python
        # 3.12 via the deadsnakes PPA. ``context_dir`` defaults to the
        # directory containing the Dockerfile, which matches every relative
        # ``COPY`` in the current Dockerfile.
    )
    app = modal.App(APP_NAME, image=image)
    remote_token_secret = modal.Secret.from_name(
        REMOTE_TOKEN_SECRET_NAME,
        # Empty required_keys makes the secret optional at deploy time — the
        # server only asserts the key exists when the function is invoked. If
        # the operator deploys without the secret, the bearer-protected
        # endpoints simply accept anonymous requests (the existing
        # ``_require_bearer`` helper treats a missing ``REMOTE_MODEL_TOKEN``
        # as "no auth required").
        required_keys=[],
    )
    gpu = _resolve_gpu()
    return {
        'app': app,
        'image': image,
        'gpu': gpu,
        'remote_token_secret': remote_token_secret,
    }


# ``app`` and ``web`` are defined at module scope so Modal's source-loader
# can introspect them. The decorators are applied conditionally: when the
# ``modal`` SDK is not installed (e.g. local CPU-only contract tests),
# ``app`` is set to ``None`` and ``web`` is the plain callable that just
# returns the FastAPI app.
#
# We attach them to a single try/except ImportError guard because Modal is
# the only optional dependency that affects this module's import behaviour.

app: Any = None  # type: ignore[assignment]
web: Any = None  # type: ignore[assignment]
_MODAL_OBJECTS: dict[str, Any] | None = None

try:
    import modal  # noqa: F401  (probe whether the SDK is installed)

    _MODAL_OBJECTS = _build_modal_objects()
    _resolved_gpu = _MODAL_OBJECTS['gpu']
    _resolved_app = _MODAL_OBJECTS['app']
    _resolved_secret = _MODAL_OBJECTS['remote_token_secret']

    @_resolved_app.function(
        gpu=_resolved_gpu,
        secrets=[_resolved_secret],
        # Scale-to-zero. We deliberately do NOT pass ``scaledown_window``,
        # ``min_containers`` or any other warm-pool knob — the public POC
        # workload tolerates cold starts and the operator should not pay for
        # idle GPU time.
    )
    @modal.concurrent(
        max_inputs=MAX_INPUTS_PER_CONTAINER,
        target_inputs=TARGET_INPUTS_PER_CONTAINER,
    )
    @modal.asgi_app()
    def web() -> Any:
        """ASGI web function served by Modal.

        Imported lazily so the image-build phase never needs to import the
        FastAPI stack (matches the Dockerfile, which installs the project
        via ``pip install -e ".[models,test]"`` at build time).
        """
        return build_asgi_app()

    app = _resolved_app
except ImportError:
    # ``modal`` is not installed (e.g. local CPU-only contract tests). The
    # public helpers and ``build_asgi_app`` still work; the Modal-specific
    # ``app`` / ``web`` objects are unavailable. Tests that need the Modal
    # SDK can ``pip install -e ".[modal]"``.
    def web() -> Any:
        """Plain callable that returns the FastAPI app, used in local tests.

        When ``modal`` is installed this binding is replaced by the
        decorated ASGI web function above.
        """
        return build_asgi_app()
