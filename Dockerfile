# =============================================================================
# DR Support Screening POC — Hugging Face Docker Space image
# =============================================================================
# Default profile: model_api (the GPU deployment).
#
# This image builds once for three runtime profiles, selected via env vars:
#   APP_PROFILE=model_api   GPU deployment of the Remote Model API contract
#   APP_PROFILE=review      Clinician workstation; talks to a remote model_api
#   APP_PROFILE=full        Local demo with both surfaces
#
# The model_api profile is the primary HF deployment target. The image:
#   - installs pinned Python deps including the torch/ultralytics/sahi stack
#   - downloads RETFound and PRISM-DR sources + weights via
#     `python -m dr_support.setup_models --model all` (idempotent)
#   - launches uvicorn against `dr_support.app:app_factory` so the profile is
#     chosen at startup from APP_PROFILE / MODEL_RUNTIME
#
# Build and run locally:
#   docker build -t dr-support-model-api .
#   docker run --rm -p 7860:7860 \
#     -e APP_PROFILE=model_api -e MODEL_RUNTIME=local \
#     -e REMOTE_MODEL_TOKEN=changeme \
#     dr-support-model-api
#
# On a Hugging Face Docker Space with a T4 small:
#   SDK: docker   (in README.yaml)
#   hardware: t4-small
#   The space secrets provide REMOTE_MODEL_TOKEN; the runtime profile defaults
#   to model_api via the HF Space environment.
# =============================================================================

# Base on the official NVIDIA CUDA runtime image for T4 (sm_75). The python
# version matches the project's tested interpreter.
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04 AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:${PATH}"

# System packages: Python 3.12, build essentials for torch/timm wheels,
# and Pillow runtime libs. apt-get cleanups keep the image small.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.12 \
        python3.12-venv \
        python3.12-dev \
        git \
        curl \
        ca-certificates \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxrender1 \
        libxext6 \
        build-essential \
        ninja-build \
    && ln -sf /usr/bin/python3.12 /usr/bin/python \
    && ln -sf /usr/bin/python3.12 /usr/bin/python3 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------------------------
# Stage 1: install Python deps in an isolated virtualenv for better cache reuse.
# We install the full stack (including torch/ultralytics/sahi) because the
# model_api profile needs GPU inference on T4.
# -----------------------------------------------------------------------------
FROM base AS deps

WORKDIR /app
COPY pyproject.toml README.md ./

# Create a venv so `python` resolves to the project interpreter.
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip wheel setuptools

# Install the project + model extras in one shot so pip resolves everything
# against a single set of constraints. We DO NOT pin torch to a CUDA build via
# pyproject (HF Spaces install the CUDA-enabled wheel via the base image's
# torch runtime), but we DO install the matching torch/torchvision/timm stack.
# The CUDA torch wheel is pulled from PyTorch's CUDA 12.1 index.
RUN /opt/venv/bin/pip install \
        --extra-index-url https://download.pytorch.org/whl/cu121 \
        torch==2.5.1+cu121 \
        torchvision==0.20.1+cu121 && \
    /opt/venv/bin/pip install -e ".[models,test]"

# -----------------------------------------------------------------------------
# Stage 2: final runtime image.
# -----------------------------------------------------------------------------
FROM base AS runtime

WORKDIR /app
COPY --from=deps /opt/venv /opt/venv

# Copy the project source. Order matters for layer caching: copy pyproject.toml
# + README + package metadata first, then the source tree.
COPY pyproject.toml README.md CHANGELOG_V2.md ./
COPY dr_support ./dr_support
COPY web ./web
COPY tests ./tests
COPY docs ./docs

# Re-install the project itself so the editable install picks up our copy.
# (The earlier `-e .` install was against an empty source tree.)
RUN /opt/venv/bin/pip install -e .

# The local-state tree holds:
#   local-state/bridge/sources/{RETFound,PRISM-DR}
#   local-state/bridge/retfound-aptos.pth
#   local-state/bridge/prism/...
# We download these at image build time so the cold-start of the Space does not
# pay the multi-GB download. Source revisions are pinned in
# dr_support/providers/{retfound,prism}.py.
RUN mkdir -p /app/local-state/bridge && \
    /opt/venv/bin/python -m dr_support.setup_models --model all

# Hugging Face Docker Spaces expect the service on 0.0.0.0:7860.
EXPOSE 7860

# Default to the model_api profile on T4 hardware. Override by setting
# APP_PROFILE in the Space secrets / runtime config.
ENV APP_PROFILE=model_api \
    MODEL_RUNTIME=local \
    HOST=0.0.0.0 \
    PORT=7860 \
    INFERENCE_DEVICE=cuda:0 \
    PYTHONPATH=/app

# Lightweight liveness check. Hugging Face hits this on container start.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fsS http://127.0.0.1:${PORT}/health || exit 1

# Single-worker uvicorn: the GPU holds a process-wide lock on the model and
# sharing one worker avoids duplicate VRAM allocations. Set WORKERS=1 only.
CMD ["sh", "-c", "exec /opt/venv/bin/python -m dr_support.run"]
