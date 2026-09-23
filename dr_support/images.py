"""Only server-admitted, hashed public/synthetic images enter the review app."""
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from PIL import Image, ImageDraw


SUPPORTED_DEMO_TYPES = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
}


@dataclass(frozen=True)
class BridgeImage:
    image_id: str
    data: bytes
    source_type: str
    source: str
    modality: str = 'CFP'
    filename: str = ''
    media_type: str = 'image/jpeg'
    dimensions: tuple[int, int] | None = None

    @property
    def sha256(self):
        return hashlib.sha256(self.data).hexdigest()

    @property
    def size(self):
        if self.dimensions is not None:
            return self.dimensions
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
    return BridgeImage('SYNTH_001', out.getvalue(), 'SYNTHETIC',
                       'Generated workflow fixture', filename='SYNTH_001.png', media_type='image/png')


def admitted_demo_images(folder):
    """Admit supported local demo images without changing their source bytes."""
    folder = Path(folder)
    if not folder.is_dir():
        raise RuntimeError(f'DR_DEMO_FOLDER does not exist or is not a folder: {folder}')

    paths = sorted(
        (path for path in folder.iterdir()
         if path.is_file() and path.suffix.lower() in SUPPORTED_DEMO_TYPES),
        key=lambda path: path.name.lower(),
    )
    if not paths:
        raise RuntimeError(f'DR_DEMO_FOLDER contains no .jpg, .jpeg, or .png images: {folder}')

    registry = {}
    for path in paths:
        data = path.read_bytes()
        try:
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
        except Exception as exc:
            raise RuntimeError(f'Demo image is not a valid image: {path.name}') from exc

        image_id = hashlib.sha256(data).hexdigest()
        # Identical bytes are one admitted case, regardless of filename.
        registry.setdefault(
            image_id,
            BridgeImage(
                image_id,
                data,
                'PUBLIC',
                f'DR-DEMO/{path.name}',
                filename=path.name,
                media_type=SUPPORTED_DEMO_TYPES[path.suffix.lower()],
            ),
        )
    return registry


def admitted_samples(root):
    import json
    manifest_path = root / 'docs/SAMPLE_SOURCE_MANIFEST.json'
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
        registry[item['image_id']] = BridgeImage(
            item['image_id'], data, 'PUBLIC', item['source'], filename=item['filename'],
        )
    return registry
