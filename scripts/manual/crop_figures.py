"""Create focused manual figures from the final synthetic UI captures.

The source captures are kept out of the manual. Each output is a bounded region
chosen to keep the control or image area readable when printed on A4.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
SCREENSHOTS = ROOT / "docs" / "manual" / "screenshots"

# Coordinates are in the 1440px-wide source captures produced by Playwright.
CROPS = {
    "01-worklist.png": ("01-worklist.png", (0, 0, 1440, 900)),
    "02-review-overview.png": ("03-review-overview.png", (0, 0, 1440, 1060)),
    "03-ai-controls.png": ("03-review-overview.png", (0, 760, 1440, 1060)),
    "04-confirm-dr-grade.png": ("05-confirm-dr-grade.png", (0, 0, 1440, 1000)),
    "05-annotation-editor.png": ("06-annotation-editor.png", (0, 0, 1440, 1000)),
    "06-roi-popover.png": ("07-roi-popover.png", (0, 0, 1440, 1000)),
    "07-dataset-readiness.png": ("08-dataset-readiness.png", (0, 0, 1440, 900)),
    "08-models-audit.png": ("09-models-audit.png", (0, 0, 1440, 920)),
}


def main() -> None:
    source_images = {source: Image.open(SCREENSHOTS / source).copy() for source, _ in CROPS.values()}
    for path in SCREENSHOTS.glob("*.png"):
        path.unlink()
    for output, (source, box) in CROPS.items():
        image = source_images[source]
        cropped = image.crop(box)
        cropped.save(SCREENSHOTS / output, optimize=True)
    print(f"Created {len(CROPS)} focused figures in {SCREENSHOTS}")


if __name__ == "__main__":
    main()
