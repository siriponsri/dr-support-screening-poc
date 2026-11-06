"""Make the Thai narration with Google Gemini TTS (voice Achernar): one WAV per scene.

  python media/journey-video/tts.py --env <path to .env> [--only intro,signin] [--force]

One request per scene speaks all its caption lines (one line per row of the
transcript). The reply is cut at the pauses that best match the caption lines,
each line is sped up a little (--tempo, default 1.08), its ends are faded softly and the lines
are joined again with a breathing pause (--pause, default 0.45 s) into assets/audio/<scene>.wav (48 kHz); the exact start and end of every line go to
assets/audio/timing.json, which the composition and the WebVTT file use. (If
assets/audio/lines/<scene>_<n>.wav exists for every line, those per-line takes
are used instead; the intro was made that way.) The free API tier allows only
10 requests a day per model, so a full run needs 9 or 10 requests. The API key is read at run time from the line
GEMINI_API_KEY= in the given .env; it is never printed, logged or written
anywhere. Only the narration text is sent to Google.

Prompt: the owner's style line is sent with every request. Sent as a bare prefix
("<style>: <line>") the model also read the style line aloud, so it goes in as
director's notes above the transcript instead (same words, not spoken).
"""
from __future__ import annotations

import argparse
import array
import base64
import io
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
import wave

HERE = Path(__file__).resolve().parent
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
RATE = 24000         # what Gemini returns
OUT_RATE = 48000     # what the composition and soundtrack.py use
SOFT_ENDS = "afade=t=in:d=0.012,areverse,afade=t=in:d=0.09,areverse"  # 12 ms fade in, 90 ms fade out: no clipped line ends
EDGE = 0.06          # silence kept before and after each spoken line
THRESHOLD = 330      # about -40 dBFS on 16-bit samples
NEWLINE = chr(10)    # one caption line per transcript row


def read_key(env_file: Path) -> str:
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("GEMINI_API_KEY="):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")
            if key:
                return key
    raise SystemExit("GEMINI_API_KEY is not set in the .env file")


def prompt(style: str, line: str) -> str:
    return ("Read the transcript below aloud in Thai. Follow the director's notes for the voice; "
            "do not read the notes or headings.\n\n### DIRECTOR'S NOTES\n"
            f"{style.rstrip().rstrip(':')}\n\n### TRANSCRIPT\n{line}")


def speak(key: str, model: str, voice: str, text: str) -> bytes:
    body = {"contents": [{"parts": [{"text": text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    request = urllib.request.Request(ENDPOINT.format(model=model), data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", "X-goog-api-key": key})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                reply = json.loads(response.read())
            break
        except urllib.error.HTTPError as error:
            # Status only: the body could echo request details.
            if error.code in (429, 500, 503) and attempt < 4:
                time.sleep(15 * (attempt + 1))
                continue
            raise SystemExit(f"TTS request failed with HTTP {error.code}") from None
    for part in reply["candidates"][0]["content"]["parts"]:
        data = (part.get("inlineData") or {}).get("data")
        if data:
            audio = base64.b64decode(data)
            if audio[:4] != b"RIFF":
                raise SystemExit("TTS reply was not a WAV file")
            return audio
    raise SystemExit("TTS reply had no audio")


def read_wav(wav_bytes: bytes) -> array.array:
    with wave.open(io.BytesIO(wav_bytes)) as source:
        if (source.getframerate(), source.getnchannels(), source.getsampwidth()) != (RATE, 1, 2):
            raise SystemExit("Unexpected WAV format from TTS")
        return array.array("h", source.readframes(source.getnframes()))


def trim(data: array.array) -> array.array:
    loud = [index for index, value in enumerate(data) if abs(value) > THRESHOLD]
    if not loud:
        raise SystemExit("TTS line was silent")
    edge = int(EDGE * RATE)
    return data[max(0, loud[0] - edge): loud[-1] + edge]


def split_lines(data: array.array, lines: list[str]) -> list[array.array]:
    """Cut one spoken scene into its caption lines at the best-matching pauses."""
    window = int(0.02 * RATE)
    loud = [max(abs(value) for value in data[start:start + window]) > THRESHOLD
            for start in range(0, len(data) - window, window)]
    first = loud.index(True)
    last = len(loud) - 1 - loud[::-1].index(True)
    # Some takes still start by reading the director's notes aloud (about 8 s, then a pause of 1 s or more).
    # When the take is far longer than its text needs, drop everything up to that first long pause.
    expected = sum(len(line.replace(" ", "")) for line in lines) / 9.0 + 0.5 * len(lines)
    if (last - first) * 0.02 > 1.2 * expected:
        run = None
        for index in range(first, min(last, first + int(13 / 0.02))):
            if not loud[index] and run is None:
                run = index
            elif loud[index] and run is not None:
                if index - run >= 45 and (run - first) * 0.02 >= 5:
                    print(f"  dropped {(index - first) * 0.02:.1f} s of spoken notes", flush=True)
                    first = index
                    break
                run = None
    gaps, run = [], None          # (start, end) in windows of each pause of 120 ms or more
    for index in range(first, last + 1):
        if not loud[index] and run is None:
            run = index
        elif loud[index] and run is not None:
            if index - run >= 6:
                gaps.append((run, index))
            run = None
    need = len(lines) - 1
    if len(gaps) < need:
        raise SystemExit(f"Only {len(gaps)} pauses for {len(lines)} lines; re-run this scene")
    weights = [len(line.replace(" ", "")) for line in lines]
    total, span = sum(weights), last - first
    expected = [first + span * sum(weights[:k + 1]) / total for k in range(need)]
    # Choose `need` pauses in order, minimising distance to the expected cut points (longer pauses preferred).
    best = {}

    def choose(k: int, start: int):
        if k == need:
            return 0.0, []
        if (k, start) in best:
            return best[(k, start)]
        result = (float("inf"), [])
        for g in range(start, len(gaps) - (need - k) + 1):
            middle = (gaps[g][0] + gaps[g][1]) / 2
            cost = (middle - expected[k]) ** 2 / max(1.0, gaps[g][1] - gaps[g][0])
            rest, picks = choose(k + 1, g + 1)
            if cost + rest < result[0]:
                result = (cost + rest, [g] + picks)
        best[(k, start)] = result
        return result

    picks = choose(0, 0)[1]
    cuts = [first * window] + [((gaps[g][0] + gaps[g][1]) // 2) * window for g in picks] + [(last + 1) * window]
    return [trim(data[cuts[k]:cuts[k + 1]]) for k in range(len(lines))]


def speed(piece: array.array, tempo: float) -> array.array:
    """Speed one line up with ffmpeg atempo (pitch kept), soften its ends and resample it to OUT_RATE."""
    command = ["ffmpeg", "-v", "error", "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-i", "-",
               "-af", f"atempo={tempo},{SOFT_ENDS}", "-ar", str(OUT_RATE), "-f", "s16le", "-"]
    out = array.array("h")
    out.frombytes(subprocess.run(command, input=piece.tobytes(), capture_output=True, check=True).stdout)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env", type=Path, default=HERE.parents[1] / ".env")
    parser.add_argument("--only", default="")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--tempo", type=float, default=1.08, help="speed-up of each line, pitch kept")
    parser.add_argument("--pause", type=float, default=0.45, help="seconds of silence between lines of one scene")
    args = parser.parse_args()
    config = json.loads((HERE / "scenes.json").read_text(encoding="utf-8"))
    out = HERE / "assets" / "audio"
    parts = out / "lines"
    parts.mkdir(parents=True, exist_ok=True)
    timing_file = out / "timing.json"
    timing = json.loads(timing_file.read_text(encoding="utf-8")) if timing_file.exists() else {}
    only = {item for item in args.only.split(",") if item}
    key = None
    for scene in config["scenes"]:
        if only and scene["id"] not in only:
            continue
        line_files = [parts / f"{scene['id']}_{index}.wav" for index in range(len(scene["captions"]))]
        whole = parts / f"{scene['id']}.wav"
        if all(path.exists() for path in line_files) and not args.force:
            pieces = [trim(read_wav(path.read_bytes())) for path in line_files]
        else:
            spans = scene.get("take_spans")
            if args.force or not whole.exists():
                key = key or read_key(args.env)
                whole.write_bytes(speak(key, config["model"], config["voice"],
                                        prompt(config["style_prefix"], NEWLINE.join(scene["captions"]))))
                print(f"{scene['id']}: spoken", flush=True)
                if spans:
                    print(f"  {scene['id']}: new take, so its take_spans in scenes.json no longer apply; "
                          "check the cut and remove or redo them", flush=True)
                    spans = None
            take = read_wav(whole.read_bytes())
            if spans:   # hand-checked line spans of this take (seconds), e.g. to skip spoken director's notes
                pieces = [trim(take[int(a * RATE):int(b * RATE)]) for a, b in spans]
            else:
                pieces = split_lines(take, scene["captions"])
        pieces = [speed(piece, args.tempo) for piece in pieces]
        joined, lines, cursor = array.array("h"), [], 0
        gap = array.array("h", bytes(int(args.pause * OUT_RATE) * 2))
        for index, piece in enumerate(pieces):
            if index:
                joined.extend(gap)
                cursor += len(gap)
            lines.append({"start": round(cursor / OUT_RATE, 3), "end": round((cursor + len(piece)) / OUT_RATE, 3)})
            joined.extend(piece)
            cursor += len(piece)
        with wave.open(str(out / f"{scene['id']}.wav"), "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(OUT_RATE)
            target.writeframes(joined.tobytes())
        timing[scene["id"]] = {"duration": round(cursor / OUT_RATE, 3), "lines": lines}
        print(f"{scene['id']}: {cursor / OUT_RATE:.2f} s", flush=True)
    timing_file.write_text(json.dumps(timing, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
