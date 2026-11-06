"""Rebuild the narration WAVs from a published journey video, faster and with shorter pauses.

  python media/journey-video/retime_voice.py <published journey-th.mp4> [--tempo 1.2] [--pause 0.3]

The per-scene WAVs from tts.py are generated files (not in Git). When they are gone, this
takes the same Achernar narration back out of the published MP4 instead of asking Gemini
again (the free key allows 10 requests a day). It works only on a video whose sound is the
narration alone: the first version (git show 18aa9af:frontend/public/media/journey-th.mp4) with
the timing.json of that commit. The current video also carries music and effects, so after this
rebuild keep the WAVs or make new takes with tts.py.

Each caption line is cut out on its own, sped up with ffmpeg atempo (pitch kept), and the
lines are joined again with a shorter pause. Writes assets/audio/<scene>.wav (48 kHz mono)
and a new timing.json. Needs ffmpeg on PATH.
"""
from __future__ import annotations

import argparse
import array
import json
from pathlib import Path
import subprocess
import wave

HERE = Path(__file__).resolve().parent
AUDIO = HERE / "assets" / "audio"
RATE = 48000
# How the first version (narration only, commit 18aa9af) was laid out: build.py lead_in, tail, CARD_LEAD, END_TAIL.
OLD_LEAD, OLD_TAIL, OLD_CARD_LEAD, OLD_END_TAIL = 0.8, 1.1, 1.4, 2.6


def cut(video: Path, start: float, end: float, tempo: float) -> array.array:
    command = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(video), "-vn",
               "-af", f"atempo={tempo}", "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"]
    raw = subprocess.run(command, check=True, capture_output=True).stdout
    samples = array.array("h")
    samples.frombytes(raw)
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video", type=Path)
    parser.add_argument("--tempo", type=float, default=1.2)
    parser.add_argument("--pause", type=float, default=0.3, help="seconds of silence between lines")
    args = parser.parse_args()
    scenes = json.loads((HERE / "scenes.json").read_text(encoding="utf-8"))["scenes"]
    old = json.loads((AUDIO / "timing.json").read_text(encoding="utf-8"))
    cursor, timing = 0.0, {}
    for scene in scenes:
        voice = old[scene["id"]]
        lead = OLD_CARD_LEAD if scene.get("card") == "title" else OLD_LEAD
        tail = OLD_END_TAIL if scene.get("card") == "end" else OLD_TAIL
        voice_start = cursor + lead
        out, lines = array.array("h"), []
        for index, line in enumerate(voice["lines"]):
            if index:
                out.extend([0] * round(args.pause * RATE))
            piece = cut(args.video, voice_start + line["start"], voice_start + line["end"], args.tempo)
            begin = len(out) / RATE
            out.extend(piece)
            lines.append({"start": round(begin, 3), "end": round(len(out) / RATE, 3)})
        with wave.open(str(AUDIO / f"{scene['id']}.wav"), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(RATE)
            handle.writeframes(out.tobytes())
        timing[scene["id"]] = {"duration": round(len(out) / RATE, 3), "lines": lines}
        cursor = round(cursor + lead + voice["duration"] + tail, 3)
        print(f"{scene['id']}: {voice['duration']:.1f} s -> {timing[scene['id']]['duration']:.1f} s", flush=True)
    (AUDIO / "timing.json").write_text(json.dumps(timing, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
