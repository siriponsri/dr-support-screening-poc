"""Mix the journey video's one sound track: narration, a music bed and a few sound effects.

  python media/journey-video/soundtrack.py [--music <your track.wav|mp3>]

Reads assets/audio/cues.json (written by build.py) and the narration WAVs, and writes
assets/audio/soundtrack.wav (48 kHz mono, about -16 LUFS), which index.html plays as its
only audio clip. Needs numpy and ffmpeg.

- Music: a calm, steady bed made here in code (A minor, 100 bpm: pad, plucked arpeggio,
  soft bass and drums), so nothing is downloaded and there is no licence question. Pass
  --music to use a real track instead; it is looped or cut to length the same way.
  The bed dips under the voice and opens up between lines.
- Effects, each with a cause on screen: a whoosh on every scene change (three takes,
  rotated) and a softer one when a card rises over the screen, a click when the cursor presses a button, a soft tick when a highlight lands.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import wave

import numpy as np

HERE = Path(__file__).resolve().parent
AUDIO = HERE / "assets" / "audio"
RATE = 48000
BPM = 100
BEAT = 60 / BPM
BAR = 4 * BEAT
RNG = np.random.default_rng(7)      # fixed seed: the same mix every time

# A minor: Am7, Fmaj7, C, G, two bars each (MIDI note numbers).
CHORDS = [(57, [57, 60, 64, 67]), (53, [57, 60, 64, 65]), (48, [55, 60, 64, 67]), (55, [55, 59, 62, 67])]


def hz(note: float) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)


def env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / RATE
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-np.maximum(t - attack, 0) / decay)


def add(track: np.ndarray, at: float, sound: np.ndarray, gain: float = 1.0) -> None:
    start = int(round(at * RATE))
    if start >= len(track):
        return
    if start < 0:
        sound, start = sound[-start:], 0
    end = min(len(track), start + len(sound))
    track[start:end] += gain * sound[: end - start]


def soft_saw(freq: float, n: int, bright: float = 1.7) -> np.ndarray:
    t = np.arange(n) / RATE
    out = np.zeros(n)
    for k in range(1, 9):
        out += np.sin(2 * np.pi * freq * k * t + k) / k ** bright
    return out


def lowpass(signal: np.ndarray, cutoff: np.ndarray | float) -> np.ndarray:
    """One-pole low-pass; the cutoff may change per sample."""
    cutoff = np.broadcast_to(np.asarray(cutoff, dtype=float), signal.shape)
    alpha = 1 - np.exp(-2 * np.pi * cutoff / RATE)
    out = np.empty_like(signal)
    y = 0.0
    for i, (x, a) in enumerate(zip(signal, alpha)):
        y += a * (x - y)
        out[i] = y
    return out


def music(total: float, quiet_from: float) -> np.ndarray:
    n = int(total * RATE) + RATE
    pad, pluck, low, drums = (np.zeros(n) for _ in range(4))
    bars = int(total / BAR) + 2
    for bar in range(bars):
        root, notes = CHORDS[(bar // 2) % len(CHORDS)]
        t0 = bar * BAR
        if bar % 2 == 0:    # pad: one swell per chord (two bars), overlapping a little
            length = int((2 * BAR + 0.8) * RATE)
            shape = np.minimum(np.arange(length) / (0.7 * RATE), 1) * np.minimum((length - np.arange(length)) / (0.8 * RATE), 1)
            for note in notes:
                for detune in (-0.06, 0.06):
                    add(pad, t0, soft_saw(hz(note + detune), length) * shape, 0.05)
        arpeggio = [notes[0] + 12, notes[2] + 12, notes[1] + 12, notes[3] + 12, notes[2] + 24, notes[1] + 12, notes[3] + 12, notes[2] + 12]
        for step, note in enumerate(arpeggio):     # plucked eighth notes
            length = int(0.5 * RATE)
            tone = np.sin(2 * np.pi * hz(note) * np.arange(length) / RATE)
            tone += 0.25 * np.sin(4 * np.pi * hz(note) * np.arange(length) / RATE)
            add(pluck, t0 + step * BEAT / 2, tone * env(length, 0.004, 0.16), 0.11 if step % 2 == 0 else 0.08)
        for beat in (0, 2):                       # bass on beats 1 and 3
            length = int(1.0 * RATE)
            tone = soft_saw(hz(root - 12), length, bright=2.6)
            add(low, t0 + beat * BEAT, tone * env(length, 0.01, 0.45), 0.22)
        for beat in range(4):                     # drums
            length = int(0.3 * RATE)
            t = np.arange(length) / RATE
            kick = np.sin(2 * np.pi * (50 * t + 90 * 0.03 * (1 - np.exp(-t / 0.03)))) * env(length, 0.002, 0.11)  # 140 Hz down to 50 Hz
            add(drums, t0 + beat * BEAT, kick, 0.45)
            hat = np.diff(RNG.standard_normal(int(0.06 * RATE) + 1)) * env(int(0.06 * RATE), 0.001, 0.018)
            add(drums, t0 + beat * BEAT + BEAT / 2, hat, 0.05)
            if beat in (1, 3):
                noise = lowpass(np.diff(RNG.standard_normal(int(0.2 * RATE) + 1)), 3500.0)
                add(drums, t0 + beat * BEAT, noise * env(len(noise), 0.002, 0.07), 0.16)
    t = np.arange(n) / RATE
    # Arrangement: drums come in after two bars, leave for the end card, and everything fades out.
    drum_gain = np.clip((t - 2 * BAR) / BAR, 0, 1) * np.clip((quiet_from - t) / 1.5, 0, 1)
    mix = pad + pluck + low + drums * drum_gain
    fade = np.clip((total - t) / 3.0, 0, 1)
    return (mix * fade)[: int(total * RATE)]


def whoosh(take: int) -> np.ndarray:
    length = [0.55, 0.65, 0.5][take % 3]
    n = int(length * RATE)
    t = np.arange(n) / RATE
    peak = length * 0.62
    shape = np.where(t < peak, (t / peak) ** 2.2, np.exp(-(t - peak) / 0.07))
    sweep = 300 + [3600, 2800, 4400][take % 3] * np.sin(np.pi * np.clip(t / length, 0, 1)) ** 2
    noise = RNG.standard_normal(n)
    band = lowpass(noise, sweep) - lowpass(noise, sweep * 0.25)
    return band * shape / (np.abs(band).max() + 1e-9)


def click(take: int) -> np.ndarray:
    n = int(0.03 * RATE)
    noise = np.diff(RNG.standard_normal(n + 1))
    return lowpass(noise, [5200.0, 4300.0][take % 2]) * env(n, 0.0005, 0.006)


def tick() -> np.ndarray:
    n = int(0.05 * RATE)
    noise = RNG.standard_normal(n)
    noise = lowpass(noise, 2400.0) - lowpass(noise, 600.0)
    return noise * env(n, 0.001, 0.012)


def read_voice(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as handle:
        assert handle.getframerate() == RATE and handle.getnchannels() == 1, path
        return np.frombuffer(handle.readframes(handle.getnframes()), dtype=np.int16) / 32768.0


def load_music_file(path: Path, total: float) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(RATE), "-f", "f32le", "-"],
                         check=True, capture_output=True).stdout
    track = np.frombuffer(raw, dtype=np.float32).astype(float)
    n = int(total * RATE)
    track = np.tile(track, n // len(track) + 1)[:n]
    t = np.arange(n) / RATE
    return track * np.clip(t / 1.0, 0, 1) * np.clip((total - t) / 3.0, 0, 1)


def rms(signal: np.ndarray) -> float:
    return float(np.sqrt(np.mean(signal ** 2)) + 1e-12)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--music", type=Path, help="use this track as the bed instead of the one made here")
    args = parser.parse_args()
    cues = json.loads((AUDIO / "cues.json").read_text(encoding="utf-8"))
    total = cues["total"]
    n = int(total * RATE)
    voice = np.zeros(n)
    for clip in cues["voice"]:
        add(voice, clip["start"], read_voice(AUDIO / clip["file"]))
    end_card = next((s["start"] for s in cues["scenes"] if s.get("card") == "end"), total)
    bed = load_music_file(args.music, total) if args.music else music(total, end_card)
    # Voice level for ducking: a smoothed envelope, fast down and slow back up.
    level = np.abs(voice)
    smooth = np.convolve(level, np.ones(int(0.05 * RATE)) / int(0.05 * RATE), mode="same")
    talking = np.clip(smooth / 0.02, 0, 1)
    coarse = talking[::48]                                        # 1 kHz is plenty for a gain curve
    duck = lowpass(coarse, 1.2 * 48)[np.minimum(np.arange(n) // 48, len(coarse) - 1)]
    bed = bed / rms(bed) * rms(voice[voice != 0]) * 0.32          # bed about 10 dB under the voice
    bed *= 1 - 0.55 * np.clip(duck, 0, 1)                         # and a further 7 dB down while she speaks
    effects = np.zeros(n)
    for k, t in enumerate(cues["cuts"]):
        sound = whoosh(k)
        add(effects, t - len(sound) / RATE * 0.62, sound, 0.30)
    add(effects, 0.15, whoosh(1), 0.22)                           # the title cards fly in
    for t in cues.get("whoosh_soft", []):                        # a card rising over the screen
        sound = whoosh(2)
        add(effects, t + 0.25 - len(sound) / RATE * 0.62, sound, 0.16)
    for k, t in enumerate(cues["click"]):
        add(effects, t + 1 / 30, click(k), 0.45)
    for t in cues["pop"]:
        add(effects, t + 1 / 30, tick(), 0.25)
    mix = voice + bed + effects
    mix /= max(1.0, np.abs(mix).max() / 0.95)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "mix.wav"
        with wave.open(str(raw), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(RATE)
            handle.writeframes((mix * 32767).astype(np.int16).tobytes())
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                        "-ar", str(RATE), "-ac", "1", str(AUDIO / "soundtrack.wav")], check=True)
    print(json.dumps({"seconds": total, "cuts": len(cues["cuts"]), "clicks": len(cues["click"]), "ticks": len(cues["pop"]),
                      "music": str(args.music) if args.music else "made here"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
