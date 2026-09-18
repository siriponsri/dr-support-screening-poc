"""Only server-admitted, hashed public/synthetic images may enter the Online Bridge."""
import hashlib
import io
from dataclasses import dataclass
from PIL import Image, ImageDraw


@dataclass(frozen=True)
class BridgeImage:
    image_id: str
    data: bytes
    source_type: str
    source: str
    modality: str = 'CFP'

    @property
    def sha256(self):
        return hashlib.sha256(self.data).hexdigest()

    @property
    def size(self):
        with Image.open(io.BytesIO(self.data)) as image:
            return image.size


def synthetic_image():
    image = Image.new('RGB', (640, 480), '#101719')
    draw = ImageDraw.Draw(image)
    draw.ellipse((100, 20, 540, 460), fill='#6f392c')
    draw.ellipse((405, 200, 445, 240), fill='#c99c69')
    draw.line([(425, 220), (300, 160), (170, 150)], fill='#402720', width=5)
    draw.line([(425, 220), (330, 310), (180, 340)], fill='#402720', width=4)
    draw.text((16, 450), 'SYNTHETIC WORKFLOW FIXTURE - NOT A RETINAL PHOTOGRAPH', fill='white')
    out = io.BytesIO()
    image.save(out, format='PNG')
    return BridgeImage('SYNTH_001', out.getvalue(), 'SYNTHETIC', 'Generated workflow fixture')


def admitted_samples(root):
    import json
    manifest_path = root / 'docs/SAMPLE_MANIFEST.json'
    if not manifest_path.exists():
        return {}
    registry = {}
    for item in json.loads(manifest_path.read_text(encoding='utf-8')):
        path = root / 'local-state/bridge/samples' / item['filename']
        if not path.exists():
            continue
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != item['sha256']:
            raise RuntimeError('Public sample hash mismatch; admission rejected')
        registry[item['image_id']] = BridgeImage(item['image_id'], data, 'PUBLIC', item['source'])
    return registry
