"""Encode the HyperFrames render into the web video served on the sign-in page.

  python media/journey-video/encode.py renders/journey-master.mp4

Writes frontend/public/media/journey-th.mp4: H.264 (yuv420p, faststart) at
1280x720 and AAC mono (about -17 LUFS, true peak under -1 dB), trying CRF values
from sharp to small until the file is at most 15 MB (target 14.5 MB to leave a margin).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
TARGET = HERE.parents[1] / "frontend" / "public" / "media" / "journey-th.mp4"
LIMIT = int(14.5 * 1024 * 1024)
LOUDNESS = "I=-17:TP=-2:LRA=11"  # -17: the AAC encode adds about 1.5 dB of peak overshoot


def loudness_filter(source: Path) -> str:
    """Two-pass loudnorm: measure the render, then apply one linear gain, so the true-peak ceiling holds."""
    log = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(source), "-vn",
                          "-af", f"loudnorm={LOUDNESS}:print_format=json", "-f", "null", "-"],
                         capture_output=True, text=True, check=True).stderr
    measured = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", log).group(0))
    return (f"loudnorm={LOUDNESS}:linear=true:measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
            f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
            f"offset={measured['target_offset']}")


def encode(source: Path, crf: int, out: Path, audio_filter: str) -> int:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(source),
                    "-vf", "scale=1280:720:flags=lanczos,format=yuv420p",
                    "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
                    "-profile:v", "high", "-level", "4.0", "-g", "60",
                    "-af", audio_filter, "-c:a", "aac", "-b:a", "96k", "-ac", "1", "-ar", "48000",
                    "-movflags", "+faststart", str(out)], check=True)
    return out.stat().st_size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, default=TARGET)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    audio_filter = loudness_filter(args.source)
    for crf in (24, 26, 28, 30, 32, 34):
        size = encode(args.source, crf, args.out, audio_filter)
        print(f"CRF {crf}: {size / 1024 / 1024:.2f} MB", flush=True)
        if size <= LIMIT:
            return 0
    raise SystemExit("Could not fit the size limit")


if __name__ == "__main__":
    raise SystemExit(main())
