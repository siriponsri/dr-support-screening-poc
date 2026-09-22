# Installation — Draft for S8 Rewrite

## Supported roles

### Review workstation
- browser or local workstation running `APP_PROFILE=review`;
- must not load model weights locally;
- connects to provider-neutral Model API when inference is required.

### Hospital model server
- Linux recommended for long-running GPU service;
- supported Python version must match final `pyproject.toml`;
- NVIDIA/CUDA only when required by chosen runtime;
- internet required only during approved initial asset setup.

## S8 tasks

1. Pin and document OS/Python/Node prerequisites actually tested.
2. Provide clean-clone commands.
3. Install review dependencies separately from GPU/model dependencies where practical.
4. Document DICOM extras separately if still optional.
5. Build frontend deterministically with lockfile.
6. Verify all commands on a clean machine/VM.

## Acceptance

A new operator following this file from a clean checkout must reach a working review application and, on the GPU server, a healthy Model API without undocumented developer steps.
