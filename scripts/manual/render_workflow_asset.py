"""Render the maintained workflow SVG for HTML/PDF image compatibility."""
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
SVG = ROOT / "docs" / "manual" / "images" / "clinician-workflow.svg"
TARGETS = [
    ROOT / "docs" / "manual" / "images" / "clinician-workflow.png",
    ROOT / "assets" / "clinician-workflow.png",
]


def main() -> None:
    with sync_playwright() as playwright:
        executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        browser = playwright.chromium.launch(headless=True, executable_path=executable)
        page = browser.new_page(viewport={"width": 1200, "height": 360}, device_scale_factor=2)
        page.goto(SVG.as_uri())
        page.screenshot(path=str(TARGETS[0]), omit_background=False)
        browser.close()
    TARGETS[1].write_bytes(TARGETS[0].read_bytes())
    print(f"Rendered {TARGETS[0]}")


if __name__ == "__main__":
    main()
