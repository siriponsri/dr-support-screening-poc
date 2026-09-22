"""Capture final clinician-manual figures from the running local UI.

Only public or synthetic data may be used. Start the review workstation before
running this script; it does not create mock screens or alter clinical state.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
SCREENSHOTS = ROOT / "docs" / "manual" / "screenshots"
BASE_URL = os.environ.get("MANUAL_BASE_URL", "http://127.0.0.1:8000/app/")
CHROME = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")


def api_root() -> str:
    return BASE_URL.split("/app", 1)[0].rstrip("/")


def open_route(page: Page, route: str) -> None:
    page.goto(f"{BASE_URL}#/{route}", wait_until="networkidle")
    page.wait_for_timeout(700)


def save(page: Page, name: str, locator: Locator | None = None) -> None:
    if locator is not None and locator.count():
        locator.screenshot(path=str(SCREENSHOTS / name))
    else:
        page.screenshot(path=str(SCREENSHOTS / name), full_page=True)


def demo_case_id(page: Page) -> str:
    response = page.request.get(f"{api_root()}/v1/cases")
    if response.ok:
        payload = response.json()
        cases = payload.get("value", []) if isinstance(payload, dict) else payload
        for case in cases:
            if case.get("admission", {}).get("modality_admission") == "FUNDUS_ACCEPTED":
                return case["image_id"]
        if cases:
            return cases[0]["image_id"]
    return "SYNTH_001"


def seed_synthetic_evidence(page: Page, case_id: str) -> None:
    headers = {"Content-Type": "application/json"}
    for route, model_id in (("global", "mock-global"), ("lesion-roi", "mock-lesion")):
        response = page.request.post(
            f"{api_root()}/v1/infer/{route}",
            data=json.dumps({"image_id": case_id, "model_id": model_id}),
            headers=headers,
        )
        if not response.ok:
            raise RuntimeError(f"Could not seed synthetic {route}: HTTP {response.status}")


def capture_final_ui(page: Page, case_id: str) -> None:
    open_route(page, "worklist")
    save(page, "01-worklist.png")

    confirm = page.get_by_role("button", name="Confirm Image").first
    if confirm.count():
        confirm.click()
        page.get_by_role("dialog").wait_for()
        save(page, "03-confirm-image.png", page.get_by_role("dialog"))
        page.keyboard.press("Escape")
    else:
        save(page, "03-confirm-image.png")

    open_route(page, f"review/{case_id}")
    save(page, "04-review.png")
    save(page, "05-ai-analysis.png")
    filter_box = page.get_by_label("Filter lesion overlays")
    if filter_box.count():
        filter_box.select_option("HEMORRHAGE")
    save(page, "06-prism-filter.png")

    open_route(page, f"clinician-review/{case_id}")
    grade = page.get_by_label("Final DR grade")
    if grade.count():
        grade.select_option("2")
    save(page, "07-confirm-dr-grade.png")

    open_route(page, f"edit/{case_id}")
    save(page, "08-edit-annotations.png")
    roi = page.locator("svg [data-ai-detection-id]").first
    if roi.count():
        roi.dispatch_event("click")
        page.get_by_text("Optional ROI action").wait_for()
    save(page, "09-ai-roi-popover.png")

    open_route(page, "datasets")
    save(page, "17-datasets.png")
    open_route(page, "models")
    save(page, "20-models-audit.png")


def main() -> None:
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=CHROME)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        case_id = demo_case_id(page)
        seed_synthetic_evidence(page, case_id)
        capture_final_ui(page, case_id)
        browser.close()
    print(f"Captured final manual figures in {SCREENSHOTS}")


if __name__ == "__main__":
    main()
