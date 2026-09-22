"""Pinned RETFound and PRISM-DR asset verification.

The model server may acquire assets during the one-time online setup, but the
normal runtime only calls the read-only verification functions in this module.
No function here downloads, clones, or mutates an asset.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .providers.assets import verify_source, verify_weight
from .providers.prism import REVISION as PRISM_REVISION
from .providers.retfound import REVISION as RETFOUND_REVISION, WEIGHT_SHA256


ROOT = Path(__file__).resolve().parents[1]
PRISM_LOCK = ROOT / 'dr_support/providers/prism_assets.json'


def default_asset_paths() -> dict[str, Path]:
    root = ROOT / 'local-state/bridge'
    return {
        'RETFOUND_SOURCE': Path(os.environ.get('RETFOUND_SOURCE') or root / 'sources/RETFound'),
        'RETFOUND_WEIGHTS': Path(os.environ.get('RETFOUND_WEIGHTS') or root / 'retfound-aptos.pth'),
        'PRISM_SOURCE': Path(os.environ.get('PRISM_SOURCE') or root / 'sources/PRISM-DR'),
        'PRISM_WEIGHTS': Path(os.environ.get('PRISM_WEIGHTS') or root / 'prism'),
    }


def _require_path(name: str, path: Path) -> Path:
    if not path.exists():
        raise RuntimeError(
            f'{name} is missing at {path}. Run the one-time online setup '
            'with scripts/model-server/setup.sh.'
        )
    return path


def verify_assets(which: str = 'all') -> dict[str, Any]:
    """Verify pinned source revisions and checkpoint hashes without downloads."""
    if which not in {'all', 'retfound', 'prism'}:
        raise ValueError(f'Unknown model selection: {which}')
    paths = default_asset_paths()
    verified: dict[str, Any] = {'status': 'VERIFIED', 'models': {}}

    if which in {'all', 'retfound'}:
        source = verify_source(_require_path('RETFOUND_SOURCE', paths['RETFOUND_SOURCE']), RETFOUND_REVISION)
        weight = verify_weight(_require_path('RETFOUND_WEIGHTS', paths['RETFOUND_WEIGHTS']), WEIGHT_SHA256)
        verified['models']['retfound-aptos5'] = {
            'source': str(source),
            'revision': RETFOUND_REVISION,
            'checkpoint': str(weight),
            'checkpoint_sha256': WEIGHT_SHA256,
        }

    if which in {'all', 'prism'}:
        source = verify_source(_require_path('PRISM_SOURCE', paths['PRISM_SOURCE']), PRISM_REVISION)
        weights_root = _require_path('PRISM_WEIGHTS', paths['PRISM_WEIGHTS'])
        lock = json.loads(PRISM_LOCK.read_text(encoding='utf-8'))
        for relative, digest in lock['weights'].items():
            verify_weight(weights_root / relative, digest)
        verified['models']['prism-dr-5fold'] = {
            'source': str(source),
            'revision': PRISM_REVISION,
            'weights_root': str(weights_root),
            'checkpoint_sha256': dict(lock['weights']),
            'archive_sha256': lock['archive_sha256'],
        }
    return verified
