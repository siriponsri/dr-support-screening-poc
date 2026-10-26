"""Capture clinician-manual screenshots from a synthetic, public-sample-only Workbench.

  python scripts/docs/capture_manual_screenshots.py --out local-state/manual-capture

Starts its own review app on 127.0.0.1 (default port 8022) with a throwaway
SQLite state in a temporary folder and a Workspace holding only the ten pinned
public HRF samples (`python -m dr_support.fetch_samples`). No hospital root,
database, model server or token is configured, so AI panels show manual
review only; AI-dependent figures are not captured here. Uses the installed
Microsoft Edge through Playwright. Writes PNGs to --out for review before they
are copied into docs/manuals/clinician/screenshots/.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "local-state" / "bridge" / "samples"
REVIEWER = "Synthetic reviewer"
CLEAR = ("DR_SUPPORT_", "MODEL_", "REMOTE_MODEL", "PRISM_", "RETFOUND_", "USPEC_", "CVAT_", "PG", "APP_PROFILE")


class _Skip(Exception):
    """The action already wrote its own bounded capture."""


def call(base, method, path, body=None):
    request = urllib.request.Request(base + path, method=method, headers={"Content-Type": "application/json"},
                                     data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def start_app(state: Path, port: int, app_root: Path) -> subprocess.Popen:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))
    env = {key: value for key, value in os.environ.items() if not key.startswith(CLEAR)}
    env.update(DR_SUPPORT_CASE_STORE="sqlite", DR_SUPPORT_STATE=str(state / "review.sqlite"),
               DR_SUPPORT_WORKSPACE_CATALOG=str(state / "workspaces.sqlite"), PYTHONPATH=str(app_root))
    code = ("import uvicorn; from dr_support.api import create_app; "
            f"uvicorn.run(create_app(include_samples=False, include_demo_fixtures=False), host='127.0.0.1', port={port}, "
            "log_level='warning')")
    if not (app_root / "frontend" / "dist" / "index.html").is_file():
        raise SystemExit("BUILT_FRONTEND_REQUIRED: run npm run build in frontend/")
    process = subprocess.Popen([sys.executable, "-c", code], cwd=app_root, env=env)
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
            return process
        except OSError:
            time.sleep(1)
    process.terminate()
    raise SystemExit("SYNTHETIC_APP_NOT_READY")


def open_workspace(base: str, state: Path, samples: Path) -> None:
    images = sorted(samples.glob("*.jpg"))
    if len(images) != 10:
        raise SystemExit("PUBLIC_SAMPLES_REQUIRED: run python -m dr_support.fetch_samples")
    (state / "input").mkdir()
    (state / "output").mkdir()
    for image in images:
        shutil.copy2(image, state / "input" / image.name)
    created = call(base, "POST", "/v1/workspaces", {
        "name": "Synthetic walkthrough", "input_folder": str(state / "input"),
        "output_folder": str(state / "output"), "database_path": str(state / "workspace.sqlite")})
    workspace_id = created.get("id") or created["workspace"]["id"]
    call(base, "POST", f"/v1/workspaces/{workspace_id}/open", {})


def capture(base: str, out: Path) -> dict:
    from playwright.sync_api import sync_playwright
    done, failed = [], {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.add_init_script(f"localStorage.setItem('dr-support-screening.default-reviewer.v1', {json.dumps(REVIEWER)})")

        def shot(name, target=None, action=None):
            try:
                if action:
                    try:
                        action()
                    except _Skip:
                        done.append(name)
                        return
                page.wait_for_timeout(800)
                (target or page).screenshot(path=str(out / f"{name}.png"))
                done.append(name)
            except Exception as error:  # Keep going; the report lists what was not captured.
                failed[name] = f"{type(error).__name__}: {str(error).splitlines()[0][:160]}"

        dialog = page.get_by_role("dialog")

        def open_worklist():
            page.goto(base + "/app/#/worklist")
            page.get_by_role("button", name="Confirm image").first.wait_for(timeout=20000)
        shot("01-worklist-start", action=open_worklist)

        def open_confirm():
            page.get_by_role("button", name="Confirm image").first.click()
            dialog.wait_for()
        shot("02-confirm-image", dialog, action=open_confirm)

        def confirm():
            dialog.get_by_label("Image type").select_option("CFP")
            dialog.get_by_placeholder("Enter a pseudonymous key or leave blank").fill("SYN0001")
            dialog.get_by_label("Eye").select_option("LEFT")
            dialog.get_by_role("radio", name="Usable", exact=True).click()
            dialog.get_by_role("button", name="Confirm image & continue").click()
            page.wait_for_url("**/#/review/**")
        shot("03-review-overview", action=confirm)

        def to_grade():
            page.get_by_role("link", name="Continue to clinician review").click()
            page.wait_for_url("**/#/clinician-review/**")
            page.get_by_role("radiogroup").first.get_by_role("radio").nth(2).click()
        shot("05-confirm-dr-grade", action=to_grade)

        def confirm_grade():
            page.get_by_role("button", name="Confirm DR grade").click()
            page.get_by_text("Grading complete").wait_for()
        shot("06-dr-grade-recorded", action=confirm_grade)

        def to_editor():
            # Confirm DR grade opens the Annotation Editor itself; wait for the toast to clear.
            page.wait_for_url("**/#/edit/**")
            page.wait_for_timeout(6000)
        shot("07-annotation-editor", action=to_editor)

        def finish():
            page.get_by_role("button", name="Finish").first.click()
            page.wait_for_url("**/#/worklist**")
            page.get_by_role("dialog").wait_for()
        shot("19-case-complete", action=finish)

        def worklist_after_finish():
            page.get_by_role("dialog").get_by_role("button", name="Cancel").click()  # Not now for the next image.
            page.get_by_role("dialog").wait_for(state="hidden")
            page.wait_for_timeout(4000)
        shot("01-worklist", action=worklist_after_finish)

        def reviewer_preferences():
            # Only the preference block: the Workspace card above it shows local folder paths.
            page.goto(base + "/app/#/settings")
            top = page.get_by_text("Default reviewer", exact=True)
            bottom = page.get_by_text("Brief step hints only.")
            bottom.scroll_into_view_if_needed()
            first, last = top.bounding_box(), bottom.bounding_box()
            page.screenshot(path=str(out / "13-reviewer-default.png"), clip={
                "x": 270, "y": first["y"] - 24, "width": 1150, "height": last["y"] + last["height"] + 24 - (first["y"] - 24)})
            raise _Skip()
        shot("13-reviewer-default", action=reviewer_preferences)
        shot("14-dataset-summary", action=lambda: page.goto(base + "/app/#/datasets"))
        shot("14-dataset-readiness", action=lambda: page.get_by_role("tab", name="DR-ready").click())
        browser.close()
    return {"captured": done, "not_captured": failed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8022)
    parser.add_argument("--samples", type=Path, default=SAMPLES, help="the ten pinned public HRF samples")
    parser.add_argument("--app-root", type=Path, default=ROOT, help="checkout with a built frontend/dist")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    base = f"http://127.0.0.1:{args.port}"
    with tempfile.TemporaryDirectory(prefix="dr-manual-", ignore_cleanup_errors=True) as temporary:
        state = Path(temporary)
        process = start_app(state, args.port, args.app_root)
        try:
            open_workspace(base, state, args.samples)
            report = capture(base, args.out)
            print(json.dumps(report, indent=1), flush=True)
        finally:
            process.terminate()
            process.wait(timeout=20)
    return 0 if not report["not_captured"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
