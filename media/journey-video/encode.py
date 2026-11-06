"""Encode the HyperFrames render into the web video served on the sign-in page.

  python media/journey-video/encode.py renders/journey-master.mp4

Writes frontend/public/media/journey-th.mp4: H.264 (yuv420p, faststart) at
1280x720 and AAC mono, trying CRF values from sharp to small until the file is at
most 15 MB (target 14.5 MB to leave a margin).
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
TARGET = HERE.parents[1] / "frontend" / "public" / "media" / "journey-th.mp4"
LIMIT = int(14.5 * 1024 * 1024)


def encode(source: Path, crf: int, out: Path) -> int:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(source),
                    "-vf", "scale=1280:720:flags=lanczos,format=yuv420p",
                    "-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-tune", "stillimage",
                    "-profile:v", "high", "-level", "4.0", "-g", "60",
                    "-c:a", "aac", "-b:a", "96k", "-ac", "1", "-ar", "48000",
                    "-movflags", "+faststart", str(out)], check=True)
    return out.stat().st_size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, default=TARGET)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    for crf in (24, 26, 28, 30, 32, 34):
        size = encode(args.source, crf, args.out)
        print(f"CRF {crf}: {size / 1024 / 1024:.2f} MB", flush=True)
        if size <= LIMIT:
            return 0
    raise SystemExit("Could not fit the size limit")


if __name__ == "__main__":
    raise SystemExit(main())
