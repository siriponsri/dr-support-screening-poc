"""Capture real Workbench screens with real UWF images for the team deck.

  python presentation/capture/capture_real_screens.py --images <folder of consented UWF JPEGs>

The owner confirmed patient consent for the images in this folder (see
docs/developer/SECURITY.md, audit item 18). They are still kept as private as the
deck allows:

- Each file is copied byte for byte into a temporary Workspace under a neutral
  name (DEMO01 R1.jpg ...), so no hospital number appears on any screen. The
  original folder is only read.
- The app runs in a throwaway demo Workbench (media/journey-video/capture/demo_app.py):
  temporary state, two throwaway local accounts, no model server. No image
  leaves this computer and no AI runs, so the screens show no AI result.
- The grade and boxes the script enters are a walk-through of the controls,
  not a reading of the image. The deck says so on every screen that shows them.

Writes presentation/assets/screens/*.jpg (1920x1080) and
presentation/assets/uwf/*.jpg (the images the deck shows on its own).
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "media" / "journey-video" / "capture"))
from demo_app import ADMIN, DOCTOR, Client, DemoApp  # noqa: E402

DECK = ROOT / "presentation" / "assets"
NAME = re.compile(r"^(?P<patient>[A-Za-z]{2}\d{4}) (?P<eye>[LR]\d)\.jpe?g$")
HERO = "DEMO05 R2.jpg"
REVIEWER = "แพทย์ตัวอย่าง"
# Boxes for the walk-through, in original-image pixels (x0, y0, x1, y1): exudate clusters near the macula.
WALKTHROUGH_BOXES = [(955, 355, 1045, 405), (1080, 300, 1175, 395), (1245, 345, 1305, 400)]


def neutral_copies(folder: Path) -> dict[str, bytes]:
    """Byte-for-byte copies under neutral names; the hospital number is replaced by DEMO01, DEMO02, ..."""
    files = sorted(path for path in folder.iterdir() if NAME.match(path.name))
    if not files:
        raise SystemExit("NO_IMAGES: expected files named like 'AB1234 L1.jpg'")
    patients = sorted({NAME.match(path.name)["patient"] for path in files})
    alias = {patient: f"DEMO{i:02d}" for i, patient in enumerate(patients, 1)}
    return {f"{alias[NAME.match(p.name)['patient']]} {NAME.match(p.name)['eye']}.jpg": p.read_bytes() for p in files}


class ConsentedDemo(DemoApp):
    def __init__(self, port: int, images: dict[str, bytes]):
        self.port = port
        self.base = f"http://127.0.0.1:{port}"
        self.samples = images
        import secrets
        self.passwords = {ADMIN: secrets.token_urlsafe(12) + "a1", DOCTOR: secrets.token_urlsafe(12) + "a1"}

    def _open_workspace(self) -> None:
        (self.state / "input").mkdir()
        (self.state / "output").mkdir()
        for name, data in sorted(self.samples.items()):
            (self.state / "input" / name).write_bytes(data)
        admin = Client(self.base)
        admin.call("POST", "/v1/auth/login", {"username": ADMIN, "password": self.passwords[ADMIN]})
        created = admin.call("POST", "/v1/workspaces", {
            "name": "Demo clinic (UWF, consented)", "input_folder": str(self.state / "input"),
            "output_folder": str(self.state / "output"), "database_path": str(self.state / "workspace.sqlite")})
        self.workspace_id = created.get("id") or created["workspace"]["id"]
        admin.call("POST", f"/v1/workspaces/{self.workspace_id}/open", {})


def save_jpeg(png: bytes, target: Path, size=(1920, 1080), quality=84) -> None:
    from PIL import Image
    image = Image.open(io.BytesIO(png)).convert("RGB")
    if image.size != size:
        image = image.resize(size, Image.LANCZOS)
    image.save(target, "JPEG", quality=quality, optimize=True, progressive=True)


def capture(app: ConsentedDemo, out: Path, raw: Path) -> dict:
    from playwright.sync_api import sync_playwright
    boxes: dict[str, dict] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        context = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=2, locale="th-TH")
        context.add_init_script(
            "localStorage.setItem('dr-support-screening.language.v1','th');"
            f"localStorage.setItem('dr-support-screening.default-reviewer.v1', {json.dumps(REVIEWER)});")
        page = context.new_page()
        base = app.base

        def box(shot: str, name: str, locator, pad: int = 8):
            try:
                rect = locator.bounding_box(timeout=4000)
            except Exception:
                print(f"no box: {shot}/{name}", flush=True)
                return
            if rect:
                boxes.setdefault(shot, {})[name] = {"x": round(rect["x"] - pad), "y": round(rect["y"] - pad),
                                                    "w": round(rect["width"] + 2 * pad), "h": round(rect["height"] + 2 * pad)}

        def shot(name: str, settle: int = 900):
            page.mouse.move(1919, 1079)
            page.wait_for_timeout(settle)
            png = page.screenshot()
            (raw / f"{name}.png").write_bytes(png)
            save_jpeg(png, out / f"{name}.jpg")
            print("shot", name, flush=True)

        page.goto(base + "/app/")
        page.get_by_label("Username").wait_for()
        page.add_style_tag(content="input::-ms-reveal { display: none !important; }")
        page.get_by_label("Username").fill(DOCTOR)
        page.get_by_role("textbox", name="Password").fill(app.passwords[DOCTOR])
        page.get_by_role("button", name="Sign in").click()
        page.get_by_text("Signed in as").wait_for(timeout=20000)
        page.wait_for_timeout(1500)
        shot("today")

        listing = page.request.get(base + "/v1/cases").json()
        if isinstance(listing, dict):
            listing = next(value for value in listing.values() if isinstance(value, list))
        hero_id = next(case["image_id"] for case in listing if case.get("filename") == HERO)

        # Worklist with the real thumbnails.
        page.goto(base + "/app/#/worklist")
        page.get_by_role("button", name="Confirm Image").first.wait_for(timeout=20000)
        page.wait_for_timeout(3500)
        box("worklist", "row", page.get_by_role("row").filter(has_text=HERO).first, 0)
        shot("worklist")

        # Confirm Image: UWF, right eye, gradable.
        page.get_by_role("row").filter(has_text=HERO).get_by_role("button", name="Confirm Image").click()
        dialog = page.get_by_role("dialog")
        dialog.wait_for()
        dialog.locator("#confirm-image-type").select_option("UWF")
        if dialog.locator("#confirm-image-eye").count():  # The eye usually comes from the file name already.
            dialog.locator("#confirm-image-eye").select_option("RIGHT")
        dialog.get_by_role("radio", name="ใช้ได้", exact=True).click()
        page.wait_for_timeout(1200)
        box("confirm", "type", dialog.locator("#confirm-image-type"))
        box("confirm", "confirm", dialog.get_by_role("button", name="ยืนยันภาพและทำต่อ"))
        shot("confirm")
        dialog.get_by_role("button", name="ยืนยันภาพและทำต่อ").click()
        page.wait_for_url("**/#/review/**")

        # Review: the real image, no AI on this computer.
        page.locator("img[alt$='retinal image']").first.wait_for(timeout=20000)
        page.wait_for_timeout(3500)
        box("review", "image", page.locator("img[alt$='retinal image']").first, 0)
        shot("review")

        # Clinician review: the physician's grade (walk-through value).
        page.goto(base + f"/app/#/clinician-review/{hero_id}")
        page.get_by_text("Final DR grade").wait_for(timeout=20000)
        page.wait_for_timeout(2500)
        grades = page.get_by_role("radiogroup").first
        grades.get_by_role("radio").nth(2).click()
        page.wait_for_timeout(600)
        box("grade", "grades", grades, 8)
        box("grade", "confirm", page.get_by_role("button", name="Confirm DR grade"))
        shot("grade")
        page.get_by_role("button", name="Confirm DR grade").click()

        # Annotation Editor: draw the walk-through boxes on the real image.
        page.wait_for_url("**/#/edit/**", timeout=20000)
        page.wait_for_timeout(6500)
        shot("editor_empty", 300)
        image = page.locator("img[alt$='retinal image']").first
        natural = image.evaluate("i => [i.naturalWidth, i.naturalHeight]")
        rect = image.bounding_box()
        scale = min(rect["width"] / natural[0], rect["height"] / natural[1])
        ox = rect["x"] + (rect["width"] - natural[0] * scale) / 2
        oy = rect["y"] + (rect["height"] - natural[1] * scale) / 2
        print("image", natural, rect, flush=True)
        page.get_by_role("button", name="Box").first.click()
        page.locator("#new-annotation-class").select_option(index=2)
        drawn = []
        for x0, y0, x1, y1 in WALKTHROUGH_BOXES:
            sx0, sy0, sx1, sy1 = ox + x0 * scale, oy + y0 * scale, ox + x1 * scale, oy + y1 * scale
            page.mouse.move(sx0, sy0)
            page.mouse.down()
            page.mouse.move(sx1, sy1, steps=10)
            page.mouse.up()
            page.wait_for_timeout(700)
            drawn.append({"x": round(sx0), "y": round(sy0), "w": round(sx1 - sx0), "h": round(sy1 - sy0)})
        page.wait_for_timeout(2200)
        boxes["editor"] = {"drawn": drawn}
        box("editor", "finish", page.get_by_role("button", name="Finish").first)
        shot("editor")
        page.get_by_role("button", name="Finish").first.click()
        page.wait_for_url("**/#/worklist**", timeout=20000)
        page.wait_for_timeout(1500)
        next_dialog = page.get_by_role("dialog")
        if next_dialog.count():
            next_dialog.get_by_role("button", name="ยกเลิก").click()
            next_dialog.wait_for(state="hidden")

        # Screening report.
        page.goto(base + f"/app/#/report/{hero_id}")
        page.get_by_role("group", name="ผล", exact=True).wait_for(timeout=20000)
        page.wait_for_timeout(2000)
        result = page.get_by_role("group", name="ผล", exact=True)
        result.get_by_text("Refer", exact=True).click()
        page.wait_for_timeout(400)
        page.get_by_role("group", name="ส่งต่อไปที่").get_by_text("จักษุแพทย์", exact=True).click()
        page.get_by_role("group", name="ความเร่งด่วน").get_by_text("ภายใน 1 เดือน", exact=True).click()
        sign = page.get_by_role("button", name="ลงนามรายงาน")
        sign.click()
        page.get_by_role("alert").or_(page.locator(".chakra-alert")).first.wait_for(timeout=15000)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(1200)
        shot("report")

        page.goto(base + "/app/#/referrals")
        page.wait_for_timeout(3500)
        shot("referrals")

        page.goto(base + "/app/#/datasets")
        page.wait_for_timeout(3500)
        page.get_by_role("tab", name="DR-ready").click()
        page.wait_for_timeout(2000)
        shot("datasets")

        page.goto(base + "/app/#/worklist")
        page.get_by_role("button", name="Confirm Image").first.wait_for(timeout=20000)
        page.wait_for_timeout(3500)
        shot("worklist_after")
        browser.close()
    return boxes


def deck_images(images: dict[str, bytes], target: Path) -> None:
    """The images the deck shows on its own: 1600 px wide, JPEG."""
    from PIL import Image
    target.mkdir(parents=True, exist_ok=True)
    for name, data in images.items():
        image = Image.open(io.BytesIO(data)).convert("RGB")
        image = image.resize((1600, round(image.height * 1600 / image.width)), Image.LANCZOS)
        image.save(target / name.replace(" ", "_").lower(), "JPEG", quality=82, optimize=True, progressive=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--images", type=Path, required=True, help="folder of consented UWF JPEGs")
    parser.add_argument("--port", type=int, default=8049)
    args = parser.parse_args()
    images = neutral_copies(args.images)
    out = DECK / "screens"
    out.mkdir(parents=True, exist_ok=True)
    deck_images(images, DECK / "uwf")
    raw = Path(tempfile.mkdtemp(prefix="deck-raw-"))
    try:
        with ConsentedDemo(args.port, images) as app:
            boxes = capture(app, out, raw)
    finally:
        shutil.rmtree(raw, ignore_errors=True)
    (out / "boxes.json").write_text(json.dumps(boxes, indent=1), encoding="utf-8")
    print(json.dumps({"screens": sorted(p.stem for p in out.glob("*.jpg")), "uwf": len(images)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
