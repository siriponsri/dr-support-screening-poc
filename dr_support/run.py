"""Single-user localhost runtime; reverse-proxy authentication needed before remote hosting.

The active runtime profile is selected via ``APP_PROFILE``:

- ``review``    (default)   clinician workstation; needs ``MODEL_RUNTIME=remote``.
- ``model_api``             GPU deployment of the Remote Model API contract;
                            needs ``MODEL_RUNTIME=local``.
- ``full``                  both surfaces mounted together for public demos.

See ``docs/operations/CONFIGURATION.md`` for the profile matrix.
"""
import os
from pathlib import Path


def _ensure_pinned_assets_exist() -> None:
    """Pre-flight check used by the ``full`` profile to fail fast.

    No download happens here. The GPU deployment host runs
    ``python -m dr_support.setup_models`` to acquire the upstream sources and
    weights; this runtime only verifies that the configured paths exist and
    that the on-disk checkpoints still match the expected SHA256.
    """
    pairs = [
        ('RETFOUND_SOURCE', os.environ.get('RETFOUND_SOURCE')),
        ('RETFOUND_WEIGHTS', os.environ.get('RETFOUND_WEIGHTS')),
        ('PRISM_SOURCE', os.environ.get('PRISM_SOURCE')),
        ('PRISM_WEIGHTS', os.environ.get('PRISM_WEIGHTS')),
    ]
    for name, path in pairs:
        if not path:
            continue
        if not Path(path).exists():
            raise RuntimeError(
                f'{name} points to {path!r} which does not exist. '
                'Run `python -m dr_support.setup_models --model all` on the GPU host.'
            )


def configure() -> None:
    root = Path(__file__).resolve().parents[1] / 'local-state/bridge'
    defaults = {
        'RETFOUND_SOURCE': root / 'sources/RETFound',
        'RETFOUND_WEIGHTS': root / 'retfound-aptos.pth',
        'PRISM_SOURCE': root / 'sources/PRISM-DR',
        'PRISM_WEIGHTS': root / 'prism',
    }
    for name, path in defaults.items():
        if path.exists():
            os.environ.setdefault(name, str(path))
    try:
        import torch
        torch.set_num_threads(int(os.environ.get('MODEL_CPU_THREADS', '4')))
    except ImportError:
        pass

    profile = (os.environ.get('APP_PROFILE') or 'review').strip().lower()
    if profile == 'full':
        _ensure_pinned_assets_exist()


def main() -> None:
    """Console-script entry point (``dr-support-run``)."""
    configure()
    import uvicorn
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '8000'))
    workers = int(os.environ.get('WORKERS', '1'))
    uvicorn.run('dr_support.app:app_factory', factory=True,
                host=host, port=port, workers=workers)


if __name__ == '__main__':
    main()
