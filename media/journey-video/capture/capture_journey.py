"""Capture the screens for the Thai journey video from a throwaway demo Workbench.

  python media/journey-video/capture/capture_journey.py --samples <folder with the 10 public HRF samples>

Starts demo_app.DemoApp (temporary state, two throwaway local accounts, only
the ten pinned public HRF samples), signs in through the real sign-in page with
Microsoft Edge (Playwright, 1920x1080, Thai switched on) and walks one case
(03_dr.jpg) through the clinician journey. Writes PNGs and boxes.json (the
on-screen boxes of the controls the video highlights) to
media/journey-video/assets/screens/.

Demo AI: no model runs here. The grade suggestion shown on the Review screens is
the repository's own explicit mock result (dr_support/providers/mock.py, grade 2,
"synthetic-v1"), added only to this browser's view of the one demo case by a
Playwright response hook. The server never stores it; the physician's grade
(3, a correction) is recorded by the real app. The video labels every screen
that shows this suggestion as demo data.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_app import DOCTOR, DemoApp  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "assets" / "screens"
HERO = "03_dr.jpg"
REVIEWER = "แพทย์ตัวอย่าง"
# The repository's explicit mock global result (dr_support/providers/mock.py), shown for the demo case only.
MOCK_GLOBAL = {
    "schema_version": "bridge.v1", "model_id": "mock-global", "model_version": "synthetic-v1", "modality": "CFP",
    "state": "AI_SUGGESTION", "grade": 2, "probabilities": [0.05, 0.1, 0.7, 0.1, 0.05], "confidence": 0.7,
    "warnings": ["SYNTHETIC_FIXTURE_NOT_MODEL_INFERENCE"],
}


def capture(app: DemoApp, out: Path) -> dict:
    from playwright.sync_api import sync_playwright
    boxes: dict[str, dict] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        context = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=2,
                                      locale="th-TH")
        context.add_init_script(
            "localStorage.setItem('dr-support-screening.language.v1','th');"
            f"localStorage.setItem('dr-support-screening.default-reviewer.v1', {json.dumps(REVIEWER)});")
        page = context.new_page()
        base = app.base

        def box(shot: str, name: str, locator, pad: int = 8):
            try:
                rect = locator.bounding_box(timeout=4000)
            except Exception:  # A missing highlight is reported, not fatal.
                print(f"no box: {shot}/{name}", flush=True)
                return
            if rect:
                boxes.setdefault(shot, {})[name] = {"x": round(rect["x"] - pad), "y": round(rect["y"] - pad),
                                                    "w": round(rect["width"] + 2 * pad), "h": round(rect["height"] + 2 * pad)}

        def shot(name: str, settle: int = 900):
            page.mouse.move(1919, 1079)
            page.wait_for_timeout(settle)
            page.screenshot(path=str(out / f"{name}.png"))

        # 1. Sign in through the real page.
        page.goto(base + "/app/")
        username = page.get_by_label("Username")
        username.wait_for()
        # Edge adds its own password-reveal eye next to the app's; hide the browser's one in the picture.
        page.add_style_tag(content="input::-ms-reveal { display: none !important; }")
        page.wait_for_timeout(1500)
        box("s01a", "form", page.locator("form"), 16)
        box("s01a", "language", page.get_by_role("group", name="Language"))
        shot("s01a")
        username.fill(DOCTOR)
        page.get_by_role("textbox", name="Password").fill(app.passwords[DOCTOR])
        box("s01b", "signin", page.get_by_role("button", name="Sign in"))
        box("s01b", "video", page.get_by_role("button", name="ดูวิธีใช้งาน"))
        shot("s01b")
        page.get_by_role("button", name="Sign in").click()
        page.get_by_text("Signed in as").wait_for(timeout=20000)

        reply = page.request.get(base + "/v1/cases")
        listing = reply.json()
        if isinstance(listing, dict):
            listing = next(value for value in listing.values() if isinstance(value, list))
        hero_id = next(case["image_id"] for case in listing if case.get("filename") == HERO)

        def add_mock(route):
            response = route.fetch()
            body = response.json()
            if isinstance(body, dict) and body.get("image_id") == hero_id and body.get("global") is None:
                body["global"] = dict(MOCK_GLOBAL, provenance={
                    "image_sha256": body.get("image_sha256") or body.get("source_sha256"), "source_type": "PUBLIC",
                    "preprocessing": "synthetic-fixture-v1", "checkpoint_sha256": {}, "source_revision": "synthetic-v1"})
            route.fulfill(response=response, json=body)

        # 2. Today.
        page.get_by_text("Signed in as").wait_for()
        page.wait_for_timeout(1500)
        box("s02", "stats", page.locator("text=To review").locator("xpath=ancestor::div[3]").first, 10)
        box("s02", "import", page.get_by_role("button", name="นำเข้าหรือยืนยันภาพ"))
        shot("s02")

        # 3. Worklist and Scan input folder.
        page.goto(base + "/app/#/worklist")
        confirm_buttons = page.get_by_role("button", name="Confirm Image")
        confirm_buttons.first.wait_for(timeout=20000)
        page.wait_for_timeout(2500)
        scan = page.get_by_role("button", name="สแกนโฟลเดอร์นำเข้า")
        box("s03a", "scan", scan)
        box("s03a", "row", page.get_by_role("row").filter(has_text=HERO).first, 0)
        shot("s03a")
        scan.click()
        page.wait_for_timeout(2500)
        box("s03b", "scan", scan)
        box("s03b", "confirm", page.get_by_role("row").filter(has_text=HERO).get_by_role("button", name="Confirm Image"))
        shot("s03b", 300)

        # 4. Confirm Image for the demo case.
        page.get_by_role("row").filter(has_text=HERO).get_by_role("button", name="Confirm Image").click()
        dialog = page.get_by_role("dialog")
        dialog.wait_for()
        page.wait_for_timeout(1200)
        shot("s04a")
        box("s04a", "type", dialog.locator("#confirm-image-type"))
        dialog.locator("#confirm-image-type").select_option("CFP")
        dialog.get_by_placeholder("ใส่รหัสแฝง หรือเว้นว่างไว้").fill("DEMO-003")
        dialog.locator("#confirm-image-eye").select_option("LEFT")
        dialog.get_by_role("radio", name="ใช้ได้", exact=True).click()
        page.wait_for_timeout(600)
        box("s04b", "eye", dialog.locator("#confirm-image-eye"))
        box("s04b", "quality", dialog.get_by_role("radiogroup"))
        box("s04b", "confirm", dialog.get_by_role("button", name="ยืนยันภาพและทำต่อ"))
        shot("s04b")
        context.route(f"**/v1/cases/{hero_id}*", add_mock)
        dialog.get_by_role("button", name="ยืนยันภาพและทำต่อ").click()
        page.wait_for_url("**/#/review/**")

        # 5. Review with the demo AI suggestion.
        page.get_by_text("Model suggestion").wait_for(timeout=20000)
        page.wait_for_timeout(2500)
        box("s05", "assessment", page.get_by_text("DR assessment").locator("xpath=ancestor::div[3]"), 4)
        box("s05", "suggestion", page.get_by_text("Model suggestion"))
        box("s05", "image", page.locator("img[alt$='retinal image']").first, 0)
        box("s05", "next", page.get_by_role("link", name="ไปที่ Clinician review"))
        shot("s05")

        # 6. Clinician Review: the physician corrects the suggestion to grade 3.
        page.get_by_role("link", name="ไปที่ Clinician review").click()
        page.wait_for_url("**/#/clinician-review/**")
        page.get_by_text("Final DR grade").wait_for()
        page.wait_for_timeout(2000)
        grades = page.get_by_role("radiogroup").first
        box("s06a", "grades", grades, 8)
        box("s06a", "ai", page.get_by_text("ผล AI: Moderate NPDR").first, 6)
        shot("s06a")
        grades.get_by_role("radio").nth(3).click()
        page.wait_for_timeout(500)
        box("s06b", "grade3", grades.get_by_role("radio").nth(3), 6)
        box("s06b", "confirm", page.get_by_role("button", name="Confirm DR grade"))
        shot("s06b")
        page.get_by_role("button", name="Confirm DR grade").click()

        # 7. Annotation Editor: one human box, then Finish.
        page.wait_for_url("**/#/edit/**", timeout=20000)
        page.wait_for_timeout(6500)
        shot("s07a", 300)
        page.get_by_role("button", name="Box").first.click()
        page.locator("#new-annotation-class").select_option(index=2)
        # One box around the dark haemorrhage left of centre, inside the visible part of the viewer.
        stage = page.locator("img[alt$='retinal image']").first.bounding_box()
        x0, y0, x1, y1 = 885, 818, 955, 892
        assert stage["x"] < x0 and stage["y"] < y0 and x1 < stage["x"] + stage["width"], "viewer layout changed"
        page.mouse.move(x0, y0)
        page.mouse.down()
        page.mouse.move(x1, y1, steps=10)
        page.mouse.up()
        page.wait_for_timeout(2200)
        boxes.setdefault("s07b", {})["drawn"] = {"x": x0 - 14, "y": y0 - 26, "w": x1 - x0 + 28, "h": y1 - y0 + 40}
        box("s07b", "finish", page.get_by_role("button", name="Finish").first)
        box("s07b", "tools", page.get_by_role("button", name="Box").first.locator("xpath=.."), 6)
        shot("s07b")
        page.get_by_role("button", name="Finish").first.click()
        page.wait_for_url("**/#/worklist**", timeout=20000)
        page.wait_for_timeout(1500)
        next_dialog = page.get_by_role("dialog")
        if next_dialog.count():
            # The app offers the next image; the demo stops here ("ยกเลิก" = Cancel, nothing is confirmed).
            box("s07c", "next", next_dialog, 0)
            shot("s07c", 300)
            next_dialog.get_by_role("button", name="ยกเลิก").click()
            next_dialog.wait_for(state="hidden")

        # 8. Screening report: the grader chooses Refer, the physician signs.
        page.goto(base + f"/app/#/report/{hero_id}")
        page.get_by_role("group", name="ผล", exact=True).wait_for(timeout=20000)
        page.wait_for_timeout(2000)
        shot("s08a")
        result = page.get_by_role("group", name="ผล", exact=True)
        result.get_by_text("Refer", exact=True).click()
        page.wait_for_timeout(400)
        page.get_by_role("group", name="ส่งต่อไปที่").get_by_text("จักษุแพทย์", exact=True).click()
        page.get_by_role("group", name="ความเร่งด่วน").get_by_text("ภายใน 1 เดือน", exact=True).click()
        sign = page.get_by_role("button", name="ลงนามรายงาน")
        sign.scroll_into_view_if_needed()
        page.wait_for_timeout(800)
        box("s08b", "result", result.locator("xpath=ancestor::div[1]"), 8)
        box("s08b", "sign", sign)
        shot("s08b")
        sign.click()
        alert = page.get_by_role("alert").or_(page.locator(".chakra-alert")).first
        alert.wait_for(timeout=15000)
        page.wait_for_timeout(800)
        print("report:", alert.inner_text(), flush=True)
        box("s08c", "signed", alert, 6)
        shot("s08c", 300)

        # 9. Referrals.
        page.goto(base + "/app/#/referrals")
        page.wait_for_timeout(3500)
        shot("s09")

        # 10. Datasets.
        page.goto(base + "/app/#/datasets")
        page.wait_for_timeout(3500)
        shot("s10a")
        page.get_by_role("tab", name="DR-ready").click()
        page.wait_for_timeout(2000)
        shot("s10b")
        browser.close()
    (out / "boxes.json").write_text(json.dumps(boxes, indent=1), encoding="utf-8")
    return boxes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--samples", type=Path, required=True, help="folder with the ten pinned public HRF samples")
    parser.add_argument("--port", type=int, default=8047)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    with DemoApp(args.port, args.samples) as app:
        boxes = capture(app, args.out)
    print(json.dumps({"screens": sorted(path.stem for path in args.out.glob("*.png")), "boxes": sorted(boxes)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
