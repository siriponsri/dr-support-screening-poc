"""Capture the screenshots for the Thai user manual (docs/pdfs/USER_MANUAL_TH.pdf).

  python scripts/docs/capture_thai_manual.py --demo-root C:/DRDemo

Starts its own review app on 127.0.0.1 with:
- a throwaway SQLite state and accounts file inside --demo-root (default: a new temporary folder);
- sign-in on, five throwaway accounts (one per role) with random passwords held only in memory;
- a Workspace whose input folder holds only the ten pinned public HRF samples
  (``python -m dr_support.fetch_samples``), checked byte for byte first;
- the generated synthetic fixture SYNTH_001 with the explicit mock models (synthetic only). Every AI result
  in the screenshots is this demo data, not real model inference.
No model server, hospital folder, database URL or token is used. The interface is switched to Thai. Uses the
installed Microsoft Edge through Playwright. Writes compressed JPEGs with numbered markers to --out
(default docs/th/images). A short --demo-root such as C:/DRDemo keeps the folder paths in the pictures short.
"""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from capture_manual_screenshots import SAMPLES, approved_samples  # noqa: E402

CLEAR = ("DR_SUPPORT_", "MODEL_", "REMOTE_MODEL", "PRISM_", "RETFOUND_", "USPEC_", "CVAT_", "PG", "APP_PROFILE",
         "DR_DEMO_FOLDER")
ACCOUNTS = [("admin.demo", "admin", False), ("dr.demo", "physician", False), ("nurse.demo", "nurse", True),
            ("expert.demo", "expert", False), ("research.demo", "researcher", False)]
VIEWPORT = {"width": 1600, "height": 1000}
MAX_WIDTH = 1600
JPEG_QUALITY = 80
MARK = (214, 69, 30)  # Marker colour: a strong orange-red that stands out on green and grey.


def make_accounts(auth_file: Path) -> dict[str, str]:
    """Throwaway demo accounts; passwords stay in this process and are never printed."""
    from dr_support.services.pilot_auth import UserStore
    store = UserStore(auth_file)
    passwords = {}
    for username, role, must_change in ACCOUNTS:
        passwords[username] = "Demo" + secrets.token_hex(6) + "7"
        store.set_user(username, passwords[username], role=role, must_change=must_change, enforce_policy=False)
    return passwords


def start_app(state: Path, port: int) -> subprocess.Popen:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))
    if not (ROOT / "frontend" / "dist" / "index.html").is_file():
        raise SystemExit("BUILT_FRONTEND_REQUIRED: run npm run build in frontend/")
    env = {key: value for key, value in os.environ.items() if not key.startswith(CLEAR)}
    # The legacy review factory with MODEL_RUNTIME=local: the mock models accept only the synthetic fixture,
    # and no real weights exist in a clean checkout, so nothing else can be analysed.
    env.update(MODEL_RUNTIME="local", DR_SUPPORT_CASE_STORE="sqlite", DR_SUPPORT_STATE=str(state / "review.sqlite"),
               DR_SUPPORT_WORKSPACE_CATALOG=str(state / "workspaces.sqlite"),
               DR_SUPPORT_AUTH_FILE=str(state / "config" / "accounts.json"), DR_SUPPORT_RELAX_DEVICE="1",
               INFERENCE_DEVICE="cpu", PYTHONPATH=str(ROOT))
    code = ("import uvicorn; from dr_support.api import create_app; "
            f"uvicorn.run(create_app(include_samples=False, include_demo_fixtures=True), host='127.0.0.1', "
            f"port={port}, log_level='warning')")
    process = subprocess.Popen([sys.executable, "-c", code], cwd=ROOT, env=env)
    for _ in range(90):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
            return process
        except OSError:
            time.sleep(1)
    process.terminate()
    raise SystemExit("DEMO_APP_NOT_READY")


def annotate(png: bytes, marks: list[tuple[dict, str]], clip: dict | None = None) -> bytes:
    """Draw numbered markers (box plus circle) and return a compressed JPEG."""
    from PIL import Image, ImageDraw, ImageFont
    image = Image.open(io.BytesIO(png)).convert("RGB")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arialbd.ttf", 20)
    except OSError:
        font = ImageFont.load_default()
    ox, oy = (clip["x"], clip["y"]) if clip else (0, 0)
    for box, label in marks:
        x0, y0 = box["x"] - ox - 4, box["y"] - oy - 4
        x1, y1 = x0 + box["width"] + 8, y0 + box["height"] + 8
        draw.rounded_rectangle((x0, y0, x1, y1), radius=6, outline=MARK, width=3)
        if label:
            r = 15
            cx, cy = max(r + 2, x0 - 6), max(r + 2, y0 - 6)
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=MARK, outline="white", width=2)
            draw.text((cx, cy), label, fill="white", font=font, anchor="mm")
    if image.width > MAX_WIDTH:
        image = image.resize((MAX_WIDTH, round(image.height * MAX_WIDTH / image.width)), Image.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return out.getvalue()


def union(*locators, pad: int = 0) -> dict:
    """One box around several elements (for a marker around a group)."""
    boxes = [locator.bounding_box() for locator in locators]
    x0 = min(box["x"] for box in boxes) - pad
    y0 = min(box["y"] for box in boxes) - pad
    x1 = max(box["x"] + box["width"] for box in boxes) + pad
    y1 = max(box["y"] + box["height"] for box in boxes) + pad
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}


class Shooter:
    def __init__(self, out: Path):
        self.out = out
        self.done: list[str] = []
        self.failed: dict[str, str] = {}

    def __call__(self, page, name: str, marks=(), clip=None, full=False, settle=700):
        page.wait_for_timeout(settle)
        boxes = []
        for target, label in marks:
            box = target if isinstance(target, dict) else target.bounding_box()
            if box:
                boxes.append((box, label))
        png = page.screenshot(clip=clip, full_page=full)
        (self.out / f"{name}.jpg").write_bytes(annotate(png, boxes, clip))
        self.done.append(name)


def capture(base: str, out: Path, passwords: dict[str, str], demo: Path, debug: Path | None = None) -> dict:
    from playwright.sync_api import sync_playwright
    shot = Shooter(out)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")

        def context():
            ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=1, locale="th-TH")
            ctx.add_init_script("try{localStorage.setItem('dr-support-screening.language.v1','th');"
                                "localStorage.setItem('dr-support-screening.default-reviewer.v1','Demo Doctor')}"
                                "catch(e){}")
            return ctx.new_page()

        def sign_in(page, username):
            page.goto(base + "/app/")
            page.locator("input").first.wait_for()
            page.locator("input").first.fill(username)
            page.locator("input[type=password]").fill(passwords[username])
            page.locator("button[type=submit]").click()
            page.wait_for_timeout(1500)

        def step(name, action, page):
            try:
                action()
            except Exception as error:  # Keep going; the report lists what was not captured.
                shot.failed[name] = f"{type(error).__name__}: {str(error).splitlines()[0][:160]}"
                if debug:
                    page.screenshot(path=str(debug / f"{name}.png"))

        # 1. Sign-in page, language switch.
        anon = context()

        def sign_in_page():
            anon.goto(base + "/app/")
            anon.locator("input").first.wait_for()
            anon.wait_for_timeout(1500)
            shot(anon, "01-sign-in", [(anon.locator("input").first, "1"), (anon.locator("input[type=password]"), "2"),
                                      (anon.locator("button[type=submit]"), "3"),
                                      (anon.get_by_role("button", name="TH", exact=True), "4")],
                 clip={"x": 200, "y": 160, "width": 1200, "height": 680})
        step("01-sign-in", sign_in_page, anon)

        # 2. First sign-in: the nurse chooses a new password.
        nurse = context()

        def first_password():
            sign_in(nurse, "nurse.demo")
            fields = nurse.locator("input[type=password]")
            fields.nth(0).wait_for()
            new = "Nurse" + secrets.token_hex(6) + "5"
            fields.nth(0).fill(passwords["nurse.demo"])
            fields.nth(1).fill(new)
            fields.nth(2).fill(new)
            shot(nurse, "02-change-password", [(fields.nth(0), "1"), (fields.nth(1), "2"), (fields.nth(2), "3"),
                                               (nurse.locator("button[type=submit]"), "4")],
                 clip={"x": 200, "y": 160, "width": 1200, "height": 680})
            nurse.locator("button[type=submit]").click()
            nurse.wait_for_timeout(2000)
            passwords["nurse.demo"] = new
        step("02-change-password", first_password, nurse)

        # 3. Administrator: Workspace (import a folder), then the Admin tabs.
        admin = context()

        def workspace():
            sign_in(admin, "admin.demo")
            admin.goto(base + "/app/#/settings")
            new_button = admin.get_by_role("button", name="Workspace ใหม่")
            new_button.wait_for()
            new_button.click()
            admin.get_by_label("Workspace name").fill("Demo screening (public images)")
            admin.get_by_label("Workspace note").fill("Public HRF sample images for training")
            admin.get_by_label("Input folder", exact=True).fill(str(demo / "images"))
            admin.get_by_label("Output folder", exact=True).fill(str(demo / "output"))
            database = admin.get_by_label("SQLite database", exact=True)
            if database.count():
                database.fill(str(demo / "state" / "demo-workspace.sqlite"))
            create = admin.locator("form button[type=submit]")
            shot(admin, "05-workspace-create", [(new_button, "1"), (admin.get_by_label("Workspace name"), "2"),
                                                (admin.get_by_label("Input folder", exact=True), "3"),
                                                (admin.get_by_label("Output folder", exact=True), "4"),
                                                (create, "5")])
            create.click()
            admin.wait_for_timeout(2500)
        step("05-workspace-create", workspace, admin)

        def admin_tabs():
            admin.goto(base + "/app/#/admin")
            admin.get_by_role("tab", name="Users and sign-in").wait_for()
            admin.wait_for_timeout(1200)
            form = admin.locator("main input").first
            shot(admin, "20-admin-users", [(form, "1"), (admin.get_by_role("button", name="บันทึกบัญชี"), "2"),
                                           (admin.get_by_text("Sign-in policy", exact=True), "3")])
            admin.get_by_role("tab", name="AI server").click()
            admin.wait_for_timeout(1200)
            # Shows the choice and the test only; nothing is saved. (The per-workspace consent line appears only
            # with a PostgreSQL workspace, so it is not in this SQLite demo.)
            team = admin.locator("main label", has_text="dr-train").first
            team.click()
            test = admin.get_by_role("button", name="ทดสอบการเชื่อมต่อ").first
            test.click()
            admin.wait_for_timeout(1500)
            result = admin.get_by_text("No AI server is configured", exact=False).first
            shot(admin, "21-admin-ai-server", [(admin.locator("main label", has_text="Model server").first, "1"),
                                               (team, "2"), (admin.get_by_role("button", name="บันทึก AI server"), "3"),
                                               (test, "4"), (result, "5")],
                 clip={"x": 256, "y": 64, "width": 1344, "height": 460})
            admin.reload()
            admin.get_by_role("tab", name="Referral connector").wait_for()
            admin.get_by_role("tab", name="Referral connector").click()
            admin.wait_for_timeout(1200)
            options = admin.locator("main [role=tabpanel] label")
            shot(admin, "22-admin-referral-connector", [
                (options.nth(0), "1"), (options.nth(1), "2"), (options.nth(2), "3"),
                (admin.get_by_role("button", name="บันทึก connector"), "4")],
                clip={"x": 256, "y": 64, "width": 1344, "height": 480})
            admin.get_by_role("tab", name="Database").click()
            admin.wait_for_timeout(1500)
            shot(admin, "23-admin-database", [(admin.get_by_text("หน้านี้ใช้ดูอย่างเดียว").first, "1")])
        step("20-admin", admin_tabs, admin)

        # 4. Physician: Worklist, Confirm Image, AI suggestion, grade, annotations, Finish.
        doctor = context()

        def worklist():
            sign_in(doctor, "dr.demo")
            doctor.goto(base + "/app/#/worklist")
            confirm = doctor.get_by_role("button", name="Confirm Image")
            confirm.first.wait_for(timeout=20000)
            doctor.wait_for_timeout(1500)
            shot(doctor, "06-worklist", [(doctor.get_by_role("button", name="สแกนโฟลเดอร์นำเข้า"), "1"),
                                         (doctor.get_by_role("button", name="All 11"), "2"),
                                         (confirm.first, "3")])
        step("06-worklist", worklist, doctor)

        def fill_if_visible(locator, value):
            # With a default reviewer name saved on this computer the field is folded into a short line.
            if locator.count() and locator.is_visible():
                locator.fill(value)

        def open_confirm(row_text):
            row = doctor.locator("tr", has_text=row_text)
            row.get_by_role("button", name="Confirm Image").click()
            dialog = doctor.get_by_role("dialog")
            dialog.wait_for()
            return dialog

        def fill_confirm(dialog, key, eye):
            dialog.locator("#confirm-image-patient-key").fill(key)
            dialog.locator("#confirm-image-eye").select_option(label=eye)
            dialog.get_by_text("ใช้ได้", exact=True).click()
            fill_if_visible(dialog.locator("#confirm-image-reviewer"), "Demo Doctor")

        def confirm_image():
            dialog = open_confirm("03_dr.jpg")
            dialog.locator("#confirm-image-type").select_option(value="CFP")
            fill_confirm(dialog, "DEMO-0001", "ซ้าย")
            doctor.wait_for_timeout(400)
            shot(doctor, "07-confirm-image", [
                (dialog.get_by_text("ภาพถ่ายจอประสาทตาแบบปกติ (CFP)").first, "1"),
                (dialog.locator("#confirm-image-patient-key"), "2"),
                (dialog.locator("#confirm-image-eye"), "3"), (dialog.get_by_text("ใช้ได้", exact=True), "4"),
                (dialog.get_by_text("Demo Doctor").first, "5"), (dialog.locator("button[type=submit]"), "6")])
            dialog.locator("button[type=submit]").click()
            doctor.wait_for_url("**/#/review/**")
            doctor.wait_for_timeout(1500)
            shot(doctor, "07b-review-manual")
        step("07-confirm-image", confirm_image, doctor)

        def ai_suggestion():
            doctor.goto(base + "/app/#/worklist")
            doctor.get_by_role("button", name="Confirm Image").first.wait_for(timeout=20000)
            dialog = open_confirm("SYNTH_001.png")
            fill_confirm(dialog, "DEMO-0002", "ขวา")
            dialog.locator("button[type=submit]").click()
            doctor.wait_for_url("**/#/review/**")
            # Demo data: the explicit mock models answer for the synthetic fixture only.
            for task, model in (("global", "mock-global"), ("lesion-roi", "mock-lesion")):
                reply = doctor.request.post(base + f"/v1/infer/{task}",
                                            data={"image_id": "SYNTH_001", "model_id": model, "modality": "CFP"})
                if not reply.ok:
                    raise RuntimeError(f"mock {task} failed: {reply.status}")
            doctor.reload()
            assessment = doctor.get_by_text("DR assessment", exact=True)
            assessment.wait_for()
            doctor.wait_for_timeout(1500)
            doctor.mouse.wheel(0, 140)
            lesions = doctor.get_by_text("Lesion suggestions", exact=True)
            shot(doctor, "08-review-ai", [(assessment, "1"), (doctor.get_by_text("Moderate NPDR").first, ""),
                                          (lesions, "2"),
                                          (doctor.get_by_role("link", name="ไปที่ Clinician review"), "3")])
        step("08-review-ai", ai_suggestion, doctor)

        def grade():
            doctor.goto(base + "/app/#/clinician-review/SYNTH_001")
            severe = doctor.locator('button[aria-label="3 Severe NPDR"]')
            severe.wait_for()
            fill_if_visible(doctor.locator("#clinician-reviewer-name"), "Demo Doctor")
            severe.click()
            confirm = doctor.get_by_role("button", name="Confirm DR grade")
            shot(doctor, "09-clinician-grade", [(doctor.get_by_text("ผล AI: Moderate NPDR", exact=False).first, "1"),
                                                (severe, "2"), (doctor.locator("#clinician-review-remark"), "3"),
                                                (confirm, "4")])
            confirm.click()
            doctor.wait_for_url("**/#/edit/**")
            doctor.wait_for_timeout(5000)
        step("09-clinician-grade", grade, doctor)

        def annotations():
            box = doctor.locator("[data-ai-detection-id]").first
            box.wait_for()
            box.scroll_into_view_if_needed()
            doctor.mouse.wheel(0, 150)
            doctor.wait_for_timeout(600)
            box.click()
            popover = doctor.locator('[aria-label="AI suggestion"]')
            popover.wait_for()
            buttons = popover.get_by_role("button")
            accept = buttons.filter(has_text="ยืนยัน").first
            remove = buttons.filter(has_text="ลบ").first
            shot(doctor, "10-ai-roi-decision", [(box, "1"), (accept, "2"), (remove, "3")])
            accept.click()
            doctor.wait_for_timeout(1500)
            doctor.get_by_role("button", name="Box", exact=True).click()
            doctor.locator("#new-annotation-class").select_option(label="Hemorrhage")
            stage = doctor.locator('[aria-label="Retinal image annotation canvas"]')
            bb = stage.bounding_box()
            x0, y0 = bb["x"] + bb["width"] * 0.28, bb["y"] + bb["height"] * 0.46
            doctor.mouse.move(x0, y0)
            doctor.mouse.down()
            doctor.mouse.move(x0 + 70, y0 + 50, steps=8)
            doctor.mouse.up()
            doctor.wait_for_timeout(1800)
            finish = doctor.get_by_role("button", name="Finish image & next")
            drawn = {"x": x0, "y": y0, "width": 70, "height": 50}
            shot(doctor, "11-annotation-box", [(doctor.get_by_role("button", name="Box", exact=True), "1"),
                                               (doctor.locator("#new-annotation-class"), "2"), (drawn, "3"),
                                               (finish, "4")])
            finish.click()
            doctor.wait_for_timeout(2500)
            shot(doctor, "12-finish", [(doctor.get_by_text("เคสนี้เสร็จแล้ว").first, "1")], settle=200)
            dialog = doctor.get_by_role("dialog")
            if dialog.count():
                cancel = dialog.get_by_role("button").filter(has_text="ยกเลิก")
                if cancel.count():
                    cancel.first.click()
        step("10-annotations", annotations, doctor)

        def grade_public():
            # The public image: grade without AI (manual review), then Finish, so the exports have a record.
            doctor.goto(base + "/app/#/clinician-review/03_dr")
            doctor.wait_for_timeout(1500)
            if "clinician-review" not in doctor.url or not doctor.locator('button[aria-label="2 Moderate NPDR"]').count():
                case_id = [c["image_id"] for c in doctor.request.get(base + "/v1/cases").json()
                           if (c.get("filename") or c.get("admission", {}).get("filename")) == "03_dr.jpg"]
                doctor.goto(base + f"/app/#/clinician-review/{case_id[0]}")
            moderate = doctor.locator('button[aria-label="2 Moderate NPDR"]')
            moderate.wait_for()
            fill_if_visible(doctor.locator("#clinician-reviewer-name"), "Demo Doctor")
            moderate.click()
            doctor.get_by_role("button", name="Confirm DR grade").click()
            doctor.wait_for_url("**/#/edit/**")
            doctor.wait_for_timeout(4000)
            finish = doctor.get_by_role("button").filter(has_text="Finish").first
            finish.click()
            doctor.wait_for_timeout(2500)
        step("public-grade", grade_public, doctor)

        # 5. Screening report: the nurse prepares, the physician signs.
        def radio(scope, value):
            return scope.locator(f'label:has(input[value="{value}"])').first

        def report_nurse():
            nurse.goto(base + "/app/#/report/SYNTH_001")
            nurse.reload()  # Picks up the Workspace the administrator opened after this page first loaded.
            inputs = nurse.locator("main input[type=text], main input:not([type])")
            inputs.first.wait_for()
            nurse.wait_for_timeout(1500)
            values = ["Demo patient (synthetic)", "DEMO-0002", "60 / F", "10", "1 Nov 2026", "Demo clinic",
                      "Demo screening room"]
            for index, value in enumerate(values):
                inputs.nth(index).fill(value)
            radio(nurse, "TYPE_2").click()
            radio(nurse, "CFP").click()
            radio(nurse, "false").click()
            shot(nurse, "13-report-nurse", [(inputs.nth(0), "1"), (inputs.nth(1), "2"), (radio(nurse, "TYPE_2"), "3")])
            right = nurse.get_by_text("Right eye (RE)", exact=True).locator("xpath=..")
            radio(right, "GRADABLE").click()
            radio(right, "3").click()
            radio(right, "SUSPECTED").click()
            right.get_by_text("Haemorrhages", exact=True).click()
            right.get_by_text("Microaneurysms", exact=True).click()
            left = nurse.get_by_text("Left eye (LE)", exact=True).locator("xpath=..")
            radio(left, "GRADABLE").click()
            radio(left, "1").click()
            radio(left, "NO").click()
            radio(nurse, "CHANGED").click()
            right.scroll_into_view_if_needed()
            nurse.wait_for_timeout(500)
            shot(nurse, "14-report-findings", [(radio(right, "3"), "1"), (radio(left, "1"), "2")])
            radio(nurse, "REFER").click()
            nurse.wait_for_timeout(300)
            radio(nurse, "OPHTHALMOLOGIST").click()
            radio(nurse, "WITHIN_1_MONTH").click()
            nurse.locator("main textarea").fill("Demo data: synthetic image, not a real patient.")
            save = nurse.get_by_role("button", name="บันทึกร่าง")
            save.click()
            nurse.wait_for_timeout(1500)
            nurse.mouse.wheel(0, 3000)
            sign = nurse.get_by_role("button", name="ลงนามรายงาน")
            shot(nurse, "14b-report-result-nurse", [(radio(nurse, "REFER"), "1"), (radio(nurse, "OPHTHALMOLOGIST"), "2"),
                                                     (radio(nurse, "WITHIN_1_MONTH"), "3"), (save, "4"), (sign, "5")])
        step("13-report-nurse", report_nurse, nurse)

        def report_sign():
            doctor.goto(base + "/app/#/report/SYNTH_001")
            doctor.locator("main textarea").wait_for()
            doctor.wait_for_timeout(1500)
            sign = doctor.get_by_role("button", name="ลงนามรายงาน")
            sign.click()
            doctor.wait_for_timeout(1500)
            doctor.mouse.wheel(0, 3000)
            printing = doctor.locator("main a[href$='/print']")
            shot(doctor, "15-report-signed", [(doctor.get_by_text("ลงนามรายงานแล้ว").first, "1"), (printing, "2")])
            href = printing.get_attribute("href")
            doctor.goto(base + href)
            doctor.wait_for_timeout(1500)
            height = doctor.evaluate("document.documentElement.scrollHeight")
            shot(doctor, "16-report-print", full=True, clip={"x": 395, "y": 0, "width": 810, "height": height})
            doctor.goto(base + "/app/#/referrals")
            doctor.wait_for_timeout(2000)
            row = doctor.locator("main tbody tr").first
            shot(doctor, "17-referrals", [(row, "1"),
                                          (doctor.locator("main a", has_text="CSV"), "2"),
                                          (row.get_by_text("FHIR", exact=True), "3")],
                 clip={"x": 256, "y": 0, "width": 1344, "height": 420})
        step("15-report-sign", report_sign, doctor)

        # 6. Expert: Gold-100 blind grading.
        expert = context()

        def gold():
            sign_in(expert, "expert.demo")
            expert.goto(base + "/app/#/gold")
            expert.locator("main tbody tr").first.wait_for()
            expert.wait_for_timeout(2000)
            shot(expert, "18-gold-list", [(expert.locator("main a").filter(has_text="เปิด").first, "1")])
            expert.goto(base + "/app/#/gold/SYNTH_001")
            expert.wait_for_timeout(2500)
            gradable = expert.locator("main label").filter(has_text="ให้เกรดได้").first
            gradable.click()
            grade = expert.locator("main label").filter(has_text="3 Severe NPDR").first
            grade.click()
            save = expert.get_by_role("button", name="บันทึกเกรดของฉัน")
            reveal = expert.get_by_role("button", name="แสดงผล AI")
            shot(expert, "19-gold-grade", [(gradable, "1"), (grade, "2"), (save, "3"), (reveal, "4")])
            save.click()
            expert.wait_for_timeout(1500)
            reveal.click()
            expert.wait_for_timeout(1500)
            expert.mouse.wheel(0, 600)
            shot(expert, "19b-gold-reveal")
        step("18-gold", gold, expert)

        # 7. Datasets and Today.
        def datasets():
            doctor.goto(base + "/app/#/datasets")
            doctor.wait_for_timeout(2500)
            shot(doctor, "24-datasets", [(doctor.get_by_role("tab", name="DR-ready"), "1"),
                                         (doctor.get_by_role("tab", name="Lesion-positive ready"), "2"),
                                         (doctor.get_by_role("button", name="สร้าง canonical snapshot"), "3")])
            doctor.goto(base + "/app/#/today")
            doctor.wait_for_timeout(2500)
            main = doctor.locator("main")
            cards = union(main.get_by_text("To review", exact=True), main.get_by_text("Needs attention", exact=True),
                          pad=18)
            cards["height"] += 40
            language = union(doctor.get_by_role("button", name="EN", exact=True),
                             doctor.get_by_role("button", name="TH", exact=True))
            shot(doctor, "03-today", [(cards, "1"), (doctor.get_by_role("button", name="ตรวจภาพถัดไป"), "2"),
                                      (doctor.get_by_role("button", name="นำเข้าหรือยืนยันภาพ"), "3"),
                                      (language, "4")])
        step("24-datasets", datasets, doctor)

        def nurse_refused():
            # A nurse may not confirm the DR grade: the server refuses and nothing is saved.
            nurse.goto(base + "/app/#/worklist")
            nurse.get_by_role("button", name="Confirm Image").first.wait_for(timeout=20000)
            row = nurse.locator("tr", has_text="05_dr.jpg")
            row.get_by_role("button", name="Confirm Image").click()
            dialog = nurse.get_by_role("dialog")
            dialog.wait_for()
            dialog.locator("#confirm-image-type").select_option(value="CFP")
            dialog.locator("#confirm-image-eye").select_option(label="ขวา")
            fill_if_visible(dialog.locator("#confirm-image-reviewer"), "Demo Nurse")
            dialog.locator("button[type=submit]").click()
            nurse.wait_for_url("**/#/review/**")
            nurse.get_by_role("link", name="ไปที่ Clinician review").click()
            mild = nurse.locator('button[aria-label="1 Mild NPDR"]')
            mild.wait_for()
            fill_if_visible(nurse.locator("#clinician-reviewer-name"), "Demo Nurse")
            mild.click()
            nurse.get_by_role("button", name="Confirm DR grade").click()
            nurse.wait_for_timeout(1500)
            message = nurse.get_by_text("physician", exact=False).last
            shot(nurse, "25-nurse-refused", [(message, "1")], settle=200)
        step("25-nurse-refused", nurse_refused, nurse)
        browser.close()
    return {"captured": shot.done, "not_captured": shot.failed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "th" / "images")
    parser.add_argument("--port", type=int, default=8023)
    parser.add_argument("--samples", type=Path, default=SAMPLES, help="the ten pinned public HRF samples")
    parser.add_argument("--demo-root", type=Path, help="empty or absent folder for the throwaway demo state")
    parser.add_argument("--debug", type=Path, help="folder for full screenshots of failed steps")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    approved = approved_samples(args.samples)  # Before any copy or server start.
    temporary = None
    if args.demo_root is None:
        temporary = tempfile.mkdtemp(prefix="dr-manual-th-")
        demo = Path(temporary)
    else:
        demo = args.demo_root.resolve()
        if demo.exists() and any(demo.iterdir()):
            raise SystemExit("DEMO_ROOT_NOT_EMPTY: give an empty or absent folder")
    for name in ("images", "output", "state/config"):
        (demo / name).mkdir(parents=True, exist_ok=True)
    for name, data in approved.items():
        (demo / "images" / name).write_bytes(data)
    passwords = make_accounts(demo / "state" / "config" / "accounts.json")
    base = f"http://127.0.0.1:{args.port}"
    process = start_app(demo / "state", args.port)
    try:
        report = capture(base, args.out, passwords, demo, args.debug)
        print(json.dumps(report, indent=1), flush=True)
    finally:
        process.terminate()
        process.wait(timeout=20)
        if temporary:
            shutil.rmtree(temporary, ignore_errors=True)
    return 0 if not report["not_captured"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
