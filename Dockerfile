# =============================================================================
# DR Support Screening POC — Hugging Face Docker Space image (v0.4.0)
# =============================================================================
# Default profile: model_api (the GPU deployment).
#
# Asset strategy: download at image build time
# ------------------------------------------------
# Model sources + weights are SHA256-verified once during `docker build` via
# `python -m dr_support.setup_models --model all` and baked into the image.
# The container entrypoint NEVER re-runs setup_models so:
#   - cold-start latency is dominated only by uvicorn and model lazy-loading,
#     not a multi-GB re-download,
#   - the same image is bit-for-bit reproducible against the pinned upstream
#     revisions in `dr_support/providers/{retfound,prism}.py`.
#
# GPU readiness is verified at container startup (NOT at build time):
#   - `python -m dr_support.run` calls the profile dispatcher, which for
#     `APP_PROFILE=model_api` invokes `dr_support.runtime.assert_cuda_ready`.
#   - When `INFERENCE_DEVICE=cuda:0` is requested but no CUDA runtime is
#     visible, the container fails loudly with `DeviceUnavailable` instead of
#     silently degrading to CPU.
#   - The HF liveness probe `/health` reports `requested_device`,
#     `effective_device`, `cuda_available`, and `cuda_device_name` so the
#     HF platform dashboard sees the actual GPU wiring.
#
# Runtime profiles
# ----------------
#   APP_PROFILE=model_api  GPU deployment of the Remote Model API contract
#                          (default; intended for the HF Docker Space target)
#   APP_PROFILE=review     Clinician workstation; talks to a remote model_api
#   APP_PROFILE=full       Local demo with both surfaces mounted
#
# Hardware target
# ---------------
# Nvidia T4 small (16 GB VRAM). The PRISM 5-fold pipeline + ROI cropper fit
# comfortably; the api-level inference lock ensures only one inference call
# runs at a time so peak activation memory is bounded by a single forward pass.
# =============================================================================

# Base on the official NVIDIA CUDA 12.1 / cuDNN 8 runtime image. The HF Docker
# Space with hardware=t4-small mounts the matching CUDA driver at run time.
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04 AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System packages. Ubuntu 22.04 ships Python 3.10; we need 3.12 to match the
# project's `requires-python = ">=3.11,<3.13"`. deadsnakes PPA is the official
# maintained source and is pinned by checksum only if needed; for an air-gap
# HF Docker Space build, mirror the same packages on the build host.
RUN apt-get update && apt-get install -y --no-install-recommends \
        software-properties-common \
        ca-certificates \
        curl \
        git \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxrender1 \
        libxext6 \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.12 \
        python3.12-venv \
        python3.12-dev \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 \
    && curl -fsSL https://bootstrap.pypa.io/get-pip.py | python3.12 - \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Sanity check: the build layer must surface Python 3.12 + CUDA 12.1 headers.
RUN python -V && python -c "import sys; assert sys.version_info[:2] == (3, 12), sys.version"

# Create the project virtualenv at a stable path so the runtime stage can
# copy it without touching the system Python.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}" \
    VIRTUAL_ENV=/opt/venv

WORKDIR /app

# -----------------------------------------------------------------------------
# Install Python dependencies from the PyTorch CUDA 12.1 index.
# Order matters for layer caching: install the heavy torch stack first, then
# the project metadata, then the project itself.
# -----------------------------------------------------------------------------
RUN pip install --upgrade pip wheel setuptools && \
    pip install --extra-index-url https://download.pytorch.org/whl/cu121 \
        torch==2.5.1+cu121 \
        torchvision==0.20.1+cu121

# Copy project metadata + source so the editable install sees the real code.
# This is the only place we touch /app during the build, after which the
# layers above are immutable.
COPY pyproject.toml README.md CHANGELOG_V2.md ./
COPY dr_support ./dr_support
COPY web ./web
COPY tests ./tests
COPY docs ./docs
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN chmod +x /usr/local/bin/docker-entrypoint.sh && \
    pip install -e ".[models,test]"

# -----------------------------------------------------------------------------
# Acquire + verify model sources + weights at build time.
# -----------------------------------------------------------------------------
# `setup_models` is idempotent: if the assets are already present and match the
# pinned SHA256 it is a no-op, otherwise it re-downloads. We always run it so
# a clean `docker build` produces a fully-baked image regardless of the build
# cache. The pinned revisions live in `dr_support/providers/retfound.py`
# (`REVISION`, `WEIGHT_SHA256`) and `dr_support/providers/prism.py` (`REVISION`),
# with all 21 PRISM weight hashes in `dr_support/providers/prism_assets.json`.
#
# This step does NOT need CUDA. The HF Docker Space provides the CUDA driver
# at run time, not build time. We deliberately do not invoke any GPU-only
# commands during the build.
RUN mkdir -p /app/local-state/bridge && \
    python -m dr_support.setup_models --model all && \
    echo "[build] Model assets verified under /app/local-state/bridge"

# Hugging Face Docker Spaces expect the service on 0.0.0.0:7860.
EXPOSE 7860

# Production defaults for the GPU deployment. Override via the HF Space's
# "Variables" panel when needed. The entrypoint validates APP_PROFILE before
# execing uvicorn.
ENV APP_PROFILE=model_api \
    MODEL_RUNTIME=local \
    INFERENCE_DEVICE=cuda:0 \
    HOST=0.0.0.0 \
    PORT=7860 \
    WORKERS=1 \
    PYTHONPATH=/app

# Lightweight liveness check. Hugging Face hits this on container start. The
# endpoint is unauthenticated and reports provider readiness along with device
# metadata so the platform dashboard sees the real GPU wiring.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fsS http://127.0.0.1:${PORT}/health || exit 1

# Single-worker uvicorn: the GPU holds a process-wide lock on the model and
# sharing one worker avoids duplicate VRAM allocations. WORKERS > 1 is
# rejected by `dr_support.run.main`.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD []
