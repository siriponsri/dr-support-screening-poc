"""Check the built app's sign-in page video dialog in Microsoft Edge.

  python media/journey-video/capture/check_modal.py --samples <folder with the 10 public HRF samples> [--shots <dir>]

Starts the throwaway demo app (demo_app.DemoApp) on the built frontend/dist,
opens the sign-in page, opens "Watch how it works", plays the video muted until
it has data (readyState >= 2), checks the Thai caption track, then closes the
dialog with Escape and with the close button and checks the video stopped.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_app import DemoApp  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8048)
    parser.add_argument("--shots", type=Path)
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright
    result = {}
    with DemoApp(args.port, args.samples) as app, sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        media = page.request.get(app.base + "/app/media/journey-th.mp4")
        captions = page.request.get(app.base + "/app/media/journey-th.vtt")
        result["mp4_status"], result["mp4_type"] = media.status, media.headers.get("content-type")
        result["vtt_status"], result["vtt_type"] = captions.status, captions.headers.get("content-type")
        page.goto(app.base + "/app/")
        page.get_by_role("button", name="Watch how it works").click()
        dialog = page.get_by_role("dialog")
        dialog.wait_for()
        video = dialog.locator("video")
        result["src"] = video.get_attribute("src")
        result["autoplay"] = video.get_attribute("autoplay")
        page.wait_for_function("document.querySelector('[role=dialog] video').readyState >= 1", timeout=20000)
        result["duration"] = video.evaluate("v => v.duration")
        result["track_mode"] = video.evaluate("v => v.textTracks.length ? v.textTracks[0].mode : null")
        video.evaluate("v => { v.muted = true; return v.play(); }")
        page.wait_for_function("document.querySelector('[role=dialog] video').readyState >= 2 && "
                               "document.querySelector('[role=dialog] video').currentTime > 1.5", timeout=30000)
        result["ready_state"] = video.evaluate("v => v.readyState")
        result["played_to"] = round(video.evaluate("v => v.currentTime"), 2)
        if args.shots:
            args.shots.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(args.shots / "modal-playing.png"))
        page.keyboard.press("Escape")
        dialog.wait_for(state="hidden")
        result["closed_by_escape"] = True
        page.get_by_role("button", name="Watch how it works").click()
        dialog.wait_for()
        page.get_by_role("button", name="Close").first.click()
        dialog.wait_for(state="hidden")
        result["closed_by_button"] = True
        result["video_left_in_page"] = page.locator("video").count()
        browser.close()
    print(json.dumps(result, indent=1))
    ok = (result["mp4_status"] == 200 and result["vtt_status"] == 200 and result["ready_state"] >= 2
          and result["autoplay"] is None and result["track_mode"] == "showing" and result["video_left_in_page"] == 0)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
