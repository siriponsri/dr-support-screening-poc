"""Fetch pinned upstream sources/weights for the non-commercial public POC only."""
import argparse
import json
import subprocess
import urllib.request
import zipfile
from pathlib import Path
from .providers.assets import sha256, verify_source, verify_weight
from .providers.retfound import REVISION as RET_REVISION, WEIGHT_SHA256
from .providers.prism import REVISION as PRISM_REVISION

ROOT = Path(__file__).resolve().parents[1]


def source(name, url, revision):
    target = ROOT / 'local-state/bridge/sources' / name
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git', 'clone', '--no-checkout', url, str(target)], check=True)
        subprocess.run(['git', '-C', str(target), 'checkout', '--detach', revision], check=True)
    verify_source(target, revision)
    return target


def prepare(which):
    cache = ROOT / 'local-state/bridge'
    cache.mkdir(parents=True, exist_ok=True)
    if which in ('all', 'retfound'):
        source('RETFound', 'https://github.com/rmaphoh/RETFound.git', RET_REVISION)
        weight = cache / 'retfound-aptos.pth'
        if not weight.exists():
            import gdown
            partial = weight.with_suffix('.download')
            result = gdown.download(id='1Ujzb6Xd1naWC0NngHah-DbHSgqxOiyJX', output=str(partial), quiet=False)
            if not result:
                raise RuntimeError('Official checkpoint unavailable; no substitute used')
            verify_weight(partial, WEIGHT_SHA256)
            partial.replace(weight)
        verify_weight(weight, WEIGHT_SHA256)
        print('RETFound: verified official five-class checkpoint')
    if which in ('all', 'prism'):
        source('PRISM-DR', 'https://github.com/zubeyrozeren/PRISM-DR.git', PRISM_REVISION)
        lock = json.loads((ROOT/'dr_support/providers/prism_assets.json').read_text(encoding='utf-8'))
        archive = cache / 'prism-weights.zip'
        if not archive.exists():
            with urllib.request.urlopen('https://github.com/zubeyrozeren/PRISM-DR/releases/download/v1.0/weights.zip',
                                        timeout=60) as response, archive.with_suffix('.download').open('wb') as out:
                while chunk := response.read(1024*1024):
                    out.write(chunk)
            archive.with_suffix('.download').replace(archive)
        if sha256(archive) != lock['archive_sha256']:
            raise RuntimeError('PRISM archive hash mismatch')
        with zipfile.ZipFile(archive) as bundle:
            for name in bundle.namelist():
                if Path(name).is_absolute() or '..' in Path(name).parts:
                    raise RuntimeError('Unsafe archive member')
            bundle.extractall(cache / 'prism')
        for name, digest in lock['weights'].items():
            verify_weight(cache/'prism'/name, digest)
        print('PRISM: verified all 21 released weight files')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',choices=['all','retfound','prism'],default='all')
    args=parser.parse_args()
    prepare(args.model)
