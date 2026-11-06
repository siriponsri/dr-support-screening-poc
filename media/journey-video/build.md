# Rebuilding the journey video

A narrated Thai walkthrough of the clinician journey (about 2 minutes 17 seconds), shown in the
"Watch how it works" dialog on the sign-in page. Output:

- `frontend/public/media/journey-th.mp4` (H.264 1280x720, AAC mono, at most 15 MB), captions drawn in the picture
- `frontend/public/media/journey-th.vtt` (the same Thai captions as a track, off by default in the player)

Both are served at `/app/media/...` (Vite `base` is `/app/`).

## What is in this folder

| File | Role |
| --- | --- |
| `scenes.json` | Source of truth: caption lines (the narration), shots, camera targets, highlight boxes |
| `narration_th.md` | The narration for reading and review (keep in step with `scenes.json`) |
| `capture/demo_app.py` | Throwaway demo Workbench: temp state, two local test accounts, ten public HRF samples |
| `capture/capture_journey.py` | Walks one demo case through the app in Edge, writes `assets/screens/*.png` and `boxes.json` |
| `capture/check_modal.py` | Checks the dialog and video in the built app |
| `tts.py` | Gemini TTS, voice Achernar: `assets/audio/<scene>.wav` and `timing.json` |
| `retime_voice.py` | Takes the narration back out of the first, narration-only MP4, faster and with shorter pauses (no Gemini call) |
| `build.py` | Writes `index.html`, `compositions/*.html` (HyperFrames), `assets/audio/cues.json` and the WebVTT file |
| `soundtrack.py` | Mixes narration, music bed and effects into `assets/audio/soundtrack.wav` |
| `encode.py` | Renders to the web MP4 under 15 MB |

Generated and not committed: screenshots, WAVs, fonts copied by `build.py`, renders (`.gitignore`).
`boxes.json`, `timing.json`, `cues.json` and the composition HTML are small and committed so the project
opens as is.

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
  showing it carries the label "ข้อมูลตัวอย่าง: ผล AI จำลอง".
- TTS: only the narration text goes to Google. The key is read from `GEMINI_API_KEY=` in
  `.env` at run time and never printed, logged or saved.
- Sound: the music bed and effects are made in code by `soundtrack.py` (no downloaded audio).

## Steps (Windows, from the repository root)

Prerequisites: `uv sync --python 3.12 --extra test --extra browser-test`, Microsoft Edge,
`ffmpeg`/`ffprobe` on PATH, Node 22+, `npm.cmd ci` in `frontend/`, the public samples in
`local-state/bridge/samples` (`python -m dr_support.fetch_samples`).

```powershell
# 1. Built frontend for the demo app
cd frontend; npm.cmd run build; cd ..

# 2. Screens (about 1 minute; port 8047 must be free)
.\.venv\Scripts\python.exe media\journey-video\capture\capture_journey.py --samples local-state\bridge\samples

# 3. Narration, either new takes (one request per scene; free tier: 10 requests a day per model)
.\.venv\Scripts\python.exe media\journey-video\tts.py --env .env
#    or rebuild the current WAVs from the first, narration-only version (no Gemini call; see below)
git show 18aa9af:media/journey-video/assets/audio/timing.json > media\journey-video\assets\audio\timing.json
git show 18aa9af:frontend/public/media/journey-th.mp4 > $env:TEMP\journey-v1.mp4
.\.venv\Scripts\python.exe media\journey-video\retime_voice.py $env:TEMP\journey-v1.mp4 --tempo 1.2 --pause 0.3

# 4. Composition, sound cues and captions, then the mixed sound track
.\.venv\Scripts\python.exe media\journey-video\build.py
.\.venv\Scripts\python.exe media\journey-video\soundtrack.py

# 5. Check, look, render (from media\journey-video)
cd media\journey-video
npx hyperframes check --json
npx hyperframes snapshot --at 1,15,36,60,88,118,130
npx hyperframes render --quality delivery --output renders\journey-master.mp4
cd ..\..

# 6. Web encode (tries CRF 24 upward until the file is at most 15 MB)
.\.venv\Scripts\python.exe media\journey-video\encode.py media\journey-video\renders\journey-master.mp4

# 7. Rebuild the frontend and check the dialog in the built app
cd frontend; npm.cmd run build; cd ..
.\.venv\Scripts\python.exe media\journey-video\capture\check_modal.py --samples local-state\bridge\samples
```

`retime_voice.py` works only on a video whose sound is the narration alone, which is the first
version (commit 18aa9af): the current video also carries music and effects. The November 2026
rebuild made its WAVs that way (`--tempo 1.2 --pause 0.3`: about 20% faster, pauses of 0.3 s).
In PowerShell, `git show ... > file` can alter binary files; if the MP4 will not open, use
`git show 18aa9af:frontend/public/media/journey-th.mp4` from Git Bash instead.

`tts.py --only <scene> --force` redoes one scene. If a scene's take has fewer pauses than
caption lines, `tts.py` stops for that scene; run it again with `--force` for a new take.
Some takes still begin by reading the director's notes aloud; `tts.py` drops that opening
and says so ("dropped ... s of spoken notes"). Listen to those scenes after any new take.

## Composition notes

- 1920x1080, 30 fps, dark canvas with a soft green glow, a faint grid and a thin progress line at the top.
- Each scene is one sub-composition. Its app screen sits in a floating window (16:9, 1260 px wide)
  that turns in from a tilt (four entrances, rotated) and leaves with a short zoom and blur, so scenes
  run into each other with no fade to a colour. Inside the window the camera moves to each shot's
  target and holds while the UI acts; shots cross-fade (0.5 s).
- The cursor travels to each button and presses it; regions get a green highlight. Highlights and
  the cursor sit in page coordinates inside the moving camera, so they stay on their control.
  Times are per caption line (`line`, `at` in `scenes.json`).
- Captions are drawn in the picture by `compositions/captions.html`: one line at a time, and each
  phrase (the Thai text split at its spaces) turns green while it is spoken. The WebVTT file carries
  the same lines for screen readers and players; the dialog leaves it off by default.
- Fonts: Prompt (titles) and Anuphan (text), copied by `build.py` from `presentation/vendor/fonts`
  (SIL Open Font License) into `assets/fonts/`.
- Sound (`soundtrack.py`): the narration, a music bed (A minor, 100 bpm; about 10 dB under the
  voice and lower again while she speaks; drums leave for the end card), a whoosh on each scene
  change (three takes, rotated), a click on each cursor press and a soft tick when a highlight
  lands; mixed to about -16 LUFS, peak under -1 dBTP. `--music <file>` uses a real track instead.
  The levels were measured, not listened to; listen once before sharing.
