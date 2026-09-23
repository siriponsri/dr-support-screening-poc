"""Acquire exactly the ten approved public HRF retinal review samples."""
import hashlib
import json
import urllib.request
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'https://huggingface.co/datasets/MedOtter/HRF'


def fetch_samples():
    root = ROOT / 'local-state/bridge/samples'
    root.mkdir(parents=True, exist_ok=True)
    url = 'https://datasets-server.huggingface.co/rows?dataset=MedOtter/HRF&config=default&split=train&offset=30&length=10'
    with urllib.request.urlopen(url, timeout=30) as response:
        rows = json.load(response)['rows']
    manifest = []
    for index, item in enumerate(rows, 1):
        row = item['row']
        expected = f'{index:02}_dr'
        if row['image_id'] != expected or row['subset'] != 'diabetic_retinopathy':
            raise ValueError('HRF viewer membership changed; do not silently substitute')
        with urllib.request.urlopen(row['image']['src'], timeout=45) as response:
            data = response.read()
        path = root / f'{expected}.jpg'
        pinned_path = ROOT / 'docs/SAMPLE_SOURCE_MANIFEST.json'
        if pinned_path.exists():
            pinned = {x['image_id']: x['sha256'] for x in json.loads(pinned_path.read_text(encoding='utf-8'))}
            if hashlib.sha256(data).hexdigest() != pinned.get(expected):
                raise RuntimeError('Mirror bytes changed; keep existing sample and review provenance')
        partial = path.with_suffix('.download')
        partial.write_bytes(data)
        partial.replace(path)
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
        manifest.append({'image_id': expected, 'filename': path.name, 'sha256': hashlib.sha256(data).hexdigest(),
                         'width': width, 'height': height, 'source_type': 'PUBLIC', 'modality': 'CFP',
                         'source': SOURCE, 'license': 'CC-BY-4.0 (mirror card)',
                         'warning': 'Viewer JPEG derivative; vessel GT only; no lesion or ordinal grading GT'})
        print(f'{expected}: verified {width}x{height}', flush=True)
    (root / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    fetch_samples()
