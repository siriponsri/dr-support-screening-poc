"""The Thai manual screenshot script: markers, compression and a demo app with no real model. Offline."""
import importlib.util
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("capture_thai_manual", ROOT / "scripts/docs/capture_thai_manual.py")
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


def test_markers_are_drawn_and_wide_screenshots_are_compressed_to_a_bounded_jpeg():
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (2000, 1000), "white").save(buffer, format="PNG")
    jpeg = capture.annotate(buffer.getvalue(), [({"x": 100, "y": 100, "width": 200, "height": 50}, "1")])
    image = Image.open(io.BytesIO(jpeg))
    assert image.format == "JPEG" and image.width == capture.MAX_WIDTH and image.height == 800
    assert image.getpixel((80, 80)) != (255, 255, 255)  # The marker is visible.


def test_the_demo_app_uses_only_the_synthetic_mock_models_and_no_model_server():
    source = (ROOT / "scripts/docs/capture_thai_manual.py").read_text(encoding="utf-8")
    assert 'MODEL_RUNTIME="local"' in source and "include_samples=False, include_demo_fixtures=True" in source
    assert "REMOTE_MODEL_URL" not in source and '"REMOTE_MODEL"' in source
    assert "approved_samples(args.samples)" in source  # The pinned public samples are checked first.


def test_demo_passwords_are_random_and_never_printed():
    source = (ROOT / "scripts/docs/capture_thai_manual.py").read_text(encoding="utf-8")
    assert "secrets.token_hex" in source and "print(passwords" not in source
