# Rebuilding the journey video

A narrated Thai walkthrough of the clinician journey (about 3 minutes), shown in the
"Watch how it works" dialog on the sign-in page. Output:

- `frontend/public/media/journey-th.mp4` (H.264 1280x720, AAC mono, at most 15 MB)
- `frontend/public/media/journey-th.vtt` (Thai captions, on by default in the player)

Both are served at `/app/media/...` (Vite `base` is `/app/`).

## What is in this folder

| File | Role |
| --- | --- |
| `scenes.json` | Source of truth: caption lines (the narration), shots, push-in areas, highlight boxes |
| `narration_th.md` | The narration for reading and review (keep in step with `scenes.json`) |
| `capture/demo_app.py` | Throwaway demo Workbench: temp state, two local test accounts, ten public HRF samples |
| `capture/capture_journey.py` | Walks one demo case through the app in Edge, writes `assets/screens/*.png` and `boxes.json` |
| `capture/check_modal.py` | Checks the dialog and video in the built app |
| `tts.py` | Gemini TTS, voice Achernar: `assets/audio/<scene>.wav` and `timing.json` |
| `build.py` | Writes `index.html`, `compositions/*.html` (HyperFrames) and the WebVTT file |
| `encode.py` | Renders to the web MP4 under 15 MB |

Generated and not committed: screenshots, WAVs, renders (`.gitignore`). `boxes.json`,
`timing.json` and the composition HTML are small and committed so the project opens as is.

## Data and privacy

- Images: only the ten pinned public HRF samples (`python -m dr_support.fetch_samples`),
  checked byte for byte against `docs/reference/SAMPLE_SOURCE_MANIFEST.json`.
- Accounts: `demo.admin` and `demo.doctor`, created in a temporary folder with
  `python -m dr_support.services.pilot_auth set-user`; random passwords live only in memory
  and that folder, which is deleted when the script ends.
- AI: no model runs. The grade suggestion on the Review screens is the repository's own
  explicit mock result (`dr_support/providers/mock.py`: grade 2, `synthetic-v1`), added only
  to the browser's view of the one demo case by a Playwright response hook. The server never
  stores it; the physician's grade 3 is a real correction recorded by the app. Every screen
  showing it carries the label "ข้อมูลตัวอย่าง: ผล AI จำลอง ไม่ได้มาจากโมเดลจริง".
- TTS: only the narration text goes to Google. The key is read from `GEMINI_API_KEY=` in
  `.env` at run time and never printed, logged or saved.

## Steps (Windows, from the repository root)

Prerequisites: `uv sync --python 3.12 --extra test --extra browser-test`, Microsoft Edge,
`ffmpeg`/`ffprobe` on PATH, Node 22+, `npm.cmd ci` in `frontend/`, the public samples in
`local-state/bridge/samples` (`python -m dr_support.fetch_samples`).

```powershell
# 1. Built frontend for the demo app
cd frontend; npm.cmd run build; cd ..

# 2. Screens (about 1 minute; port 8047 must be free)
.\.venv\Scripts\python.exe media\journey-video\capture\capture_journey.py --samples local-state\bridge\samples

# 3. Narration: one request per scene (free tier: 10 requests a day per model)
.\.venv\Scripts\python.exe media\journey-video\tts.py --env .env

# 4. Composition and captions
.\.venv\Scripts\python.exe media\journey-video\build.py

# 5. Check, look, render (from media\journey-video)
cd media\journey-video
npx hyperframes check --json
npx hyperframes snapshot --at 10,40,80,120,160
npx hyperframes render --quality delivery --output renders\journey-master.mp4
cd ..\..

# 6. Web encode (tries CRF 24 upward until the file is at most 15 MB)
.\.venv\Scripts\python.exe media\journey-video\encode.py media\journey-video\renders\journey-master.mp4

# 7. Rebuild the frontend and check the dialog in the built app
cd frontend; npm.cmd run build; cd ..
.\.venv\Scripts\python.exe media\journey-video\capture\check_modal.py --samples local-state\bridge\samples
```

`tts.py --only <scene> --force` redoes one scene. If a scene's take has fewer pauses than
caption lines, `tts.py` stops for that scene; run it again with `--force` for a new take.
Some takes still begin by reading the director's notes aloud (about 8 to 10 s, then a
pause of a second or more); when a take is far longer than its text needs, `tts.py` drops
that opening and says so ("dropped ... s of spoken notes"). In the November 2026 build this
happened for confirm, annotate and report. Listen to those scenes after any new take.

## Composition notes

- 1920x1080, 30 fps. Each scene is one sub-composition; shots cross-fade (0.8 s) and every
  shot starts its slow push-in where the previous one stopped, so pages never double up.
- Highlight rings and a single soft tap sit in page coordinates inside the moving camera,
  so they stay on their control. Times are per caption line (`line`, `at` in `scenes.json`).
- Captions: the web MP4 carries no drawn captions; the WebVTT track shows them (on by
  default, the viewer can switch them off). `build.py --burn-captions` draws them into the
  picture for a copy meant for players without the track.
- Fonts: Inter (bundled) and Leelawadee UI (Windows system font, `local()`), the same Thai
  face the app shows on Windows. Colours follow `DESIGN.md` tokens.
- No music, by choice: the narration should stay soft and clear.
