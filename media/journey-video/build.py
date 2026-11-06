"""Write the HyperFrames composition, the sound cue list and the Thai WebVTT file from scenes.json.

  python media/journey-video/build.py

Inputs: scenes.json (lines, shots, rings), assets/audio/timing.json (from tts.py or
retime_voice.py), assets/screens/boxes.json (from the capture script). A scene without
narration timing yet gets an estimate so the film can be previewed; build.py says so and
the render must wait for the narration. Outputs: index.html and compositions/*.html (static
HyperFrames source, editable in the HyperFrames desktop app), assets/audio/cues.json (what
soundtrack.py places: scene cuts, cursor clicks, highlights) and
frontend/public/media/journey-th.vtt.

Look: a dark canvas with a soft glow; each scene's app screen sits in a floating window
that turns in from a tilt and leaves through a short zoom with blur, so scenes run into
each other without a fade to a colour. A cursor travels to each button and presses it;
regions get a highlight. Captions are drawn in the picture: one line at a time, each
phrase lighting up as it is spoken.
"""
from __future__ import annotations

import base64
from html import escape
import json
from pathlib import Path
import re
import shutil

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
W, H = 1920, 1080
XFADE = 0.5          # cross-fade between shots inside one window
ENTER = 0.9          # window arrival at a scene start
EXIT = 0.4           # window exit (zoom with blur) at a scene end
CHARS_PER_SECOND = 9.0
CARD_LEAD = 1.0      # the title card builds a moment before the voice starts
END_TAIL = 2.2       # the end card holds after the last word

# Window: centred, its screen area 16:9.
WIN_W, BAR = 1260, 36
WIN_H = round(WIN_W * H / W)
WIN_X, WIN_Y = (W - WIN_W) // 2, 158
K = WIN_W / W        # page pixels to window pixels

BG, TEXT, MUTED, ACCENT, TEAL, AMBER = "#07110B", "#FFFFFF", "#9FB3A6", "#34D873", "#22D3EE", "#F5B940"
UI_FONT = "'Anuphan', sans-serif"
DISPLAY_FONT = "'Prompt', 'Anuphan', sans-serif"
CHECK = ('<svg viewBox="0 0 24 24" width="60" height="60" fill="none" stroke="currentColor" stroke-width="2.2" '
         'stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path class="tick" d="m8 12.5 3 3 5-6"/></svg>')
CURSOR = ('<svg viewBox="0 0 24 24" width="100%" height="100%"><path d="M4 2 L4 19 L8.6 14.9 L11.6 21.6 L14.6 20.3 '
          'L11.7 13.7 L18 13.4 Z" fill="#FFFFFF" stroke="#0B1510" stroke-width="1.4" stroke-linejoin="round"/></svg>')
CURSOR_PX = 34       # cursor size on screen
# Window entrances, rotated so neighbouring scenes never arrive the same way.
ENTRANCES = [
    "{ rotationX: 16, rotationY: -12, y: 70, scale: 0.9, opacity: 0, filter: 'blur(14px)' }",
    "{ rotationY: 18, x: 140, scale: 0.92, opacity: 0, filter: 'blur(14px)' }",
    "{ rotationX: -12, y: -50, scale: 0.92, opacity: 0, filter: 'blur(14px)' }",
    "{ rotationY: -18, x: -140, scale: 0.92, opacity: 0, filter: 'blur(14px)' }",
]


def font_faces() -> str:
    """Copy the deck's Thai fonts (presentation/vendor/fonts, SIL OFL) into assets/fonts and declare them."""
    target = HERE / "assets" / "fonts"
    target.mkdir(parents=True, exist_ok=True)
    rules = []
    for family in ("prompt", "anuphan"):
        css = (REPO / "presentation" / "vendor" / "fonts" / f"{family}.css").read_text(encoding="utf-8")
        for index, match in enumerate(re.finditer(r"@font-face\{[^}]*?font-weight:(\d+);[^}]*?base64,([A-Za-z0-9+/=]+)\)[^}]*?"
                                                  r"(?:unicode-range:([^;}]+))?;?\}", css)):
            weight, data, ranges = match.group(1), match.group(2), match.group(3)
            name = f"{family}-{weight}-{index}.woff2"
            (target / name).write_bytes(base64.b64decode(data))
            extra = f" unicode-range: {ranges.strip()};" if ranges else ""
            rules.append(f"@font-face {{ font-family: '{family.capitalize()}'; font-weight: {weight}; "
                         f"src: url('assets/fonts/{name}') format('woff2');{extra} }}")
    return "\n    ".join(rules)


def load() -> tuple[dict, dict, dict]:
    config = json.loads((HERE / "scenes.json").read_text(encoding="utf-8"))
    timing_file = HERE / "assets" / "audio" / "timing.json"
    timing = json.loads(timing_file.read_text(encoding="utf-8")) if timing_file.exists() else {}
    boxes = json.loads((HERE / "assets" / "screens" / "boxes.json").read_text(encoding="utf-8"))
    return config, timing, boxes


def voice_timing(scene: dict, timing: dict) -> tuple[dict, bool]:
    if scene["id"] in timing and len(timing[scene["id"]]["lines"]) == len(scene["captions"]):
        return timing[scene["id"]], True
    lines, cursor = [], 0.0
    for line in scene["captions"]:
        length = len(line.replace(" ", "")) / CHARS_PER_SECOND
        lines.append({"start": round(cursor, 3), "end": round(cursor + length, 3)})
        cursor += length + 0.3
    return {"duration": round(cursor - 0.3, 3), "lines": lines}, False


def fit_zoom(zoom: dict) -> dict:
    """Keep the camera target 16:9 and inside the page."""
    w = min(W, zoom["w"])
    h = w * H / W
    cx, cy = zoom["x"] + zoom["w"] / 2, zoom["y"] + zoom["h"] / 2
    x = min(max(0, cx - w / 2), W - w)
    y = min(max(0, cy - h / 2), H - h)
    return {"x": x, "y": y, "w": w, "h": h}


def camera(zoom: dict) -> dict:
    scale = W / zoom["w"]
    return {"x": round(-zoom["x"] * scale, 2), "y": round(-zoom["y"] * scale, 2), "scale": round(scale, 4)}


def mix(a: dict, b: dict, t: float) -> dict:
    return {key: a[key] + (b[key] - a[key]) * t for key in a}


def at(scene_lines: list[dict], lead: float, line: int, fraction: float = 0.0) -> float:
    span = scene_lines[line]
    return lead + span["start"] + fraction * (span["end"] - span["start"])


def r(value: float) -> float:
    return round(value, 3)


def page(body: str, script: str, comp_id: str, style: str, faces: str) -> str:
    return f"""<template>
  <style>
    {faces}
    #root {{ position: absolute; inset: 0; overflow: hidden; font-family: {UI_FONT}; color: {TEXT}; }}
{style}
  </style>
  <div id="root" data-composition-id="{comp_id}" data-width="{W}" data-height="{H}">
{body}
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
{script}
    window.__timelines["{comp_id}"] = tl;
  </script>
</template>
"""


SCREEN_STYLE = f"""    .stage {{ position: absolute; inset: 0; perspective: 2200px; }}
    .win {{ position: absolute; left: {WIN_X}px; top: {WIN_Y}px; width: {WIN_W}px; height: {WIN_H + BAR}px; border-radius: 18px;
      overflow: hidden; background: #0E1A13; box-shadow: 0 40px 120px rgba(0, 0, 0, 0.55), 0 0 0 1px rgba(255, 255, 255, 0.09); }}
    .bar {{ position: absolute; left: 0; right: 0; top: 0; height: {BAR}px; display: flex; align-items: center; gap: 8px;
      padding: 0 16px; background: #0E1A13; }}
    .bar i {{ width: 11px; height: 11px; border-radius: 50%; background: #2C4635; }}
    .bar span {{ margin-left: 14px; padding: 3px 14px; border-radius: 8px; background: rgba(255, 255, 255, 0.06);
      font-size: 15px; color: {MUTED}; letter-spacing: 0.02em; }}
    .content {{ position: absolute; left: 0; top: {BAR}px; width: {WIN_W}px; height: {WIN_H}px; overflow: hidden; background: #F6F7F6; }}
    .screen {{ position: absolute; left: 0; top: 0; width: {W}px; height: {H}px; transform: scale({K:.5f}); transform-origin: 0 0; }}
    .shot {{ position: absolute; inset: 0; overflow: hidden; }}
    .fade {{ position: absolute; inset: 0; }}
    .cam {{ position: absolute; left: 0; top: 0; width: {W}px; height: {H}px; transform-origin: 0 0; }}
    .cam img {{ position: absolute; left: 0; top: 0; width: {W}px; height: {H}px; }}
    .ring {{ position: absolute; border-style: solid; border-color: {ACCENT}; background: rgba(52, 216, 115, 0.08); opacity: 0; }}
    .cursor {{ position: absolute; left: 0; top: 0; opacity: 0; filter: drop-shadow(0 4px 10px rgba(0, 0, 0, 0.35)); }}
    .head {{ position: absolute; left: {WIN_X}px; top: 100px; display: flex; align-items: baseline; gap: 22px; }}
    .head .step {{ font-family: {DISPLAY_FONT}; font-weight: 600; font-size: 22px; letter-spacing: 0.16em; color: {ACCENT}; }}
    .head .lab {{ font-family: {DISPLAY_FONT}; font-weight: 600; font-size: 44px; letter-spacing: -0.01em; color: {TEXT}; }}
    .demo {{ position: absolute; right: {WIN_X}px; top: 104px; display: flex; align-items: center; gap: 10px; padding: 8px 18px;
      border-radius: 999px; background: rgba(245, 185, 64, 0.12); border: 1px solid rgba(245, 185, 64, 0.45); color: #F8D58A;
      font-size: 20px; font-weight: 600; }}
    .demo i {{ width: 9px; height: 9px; border-radius: 50%; background: {AMBER}; }}"""


def screen_scene(scene: dict, order: int, lead: float, lines: list[dict], duration: float, boxes: dict,
                 faces: str) -> tuple[str, list[str], list[tuple[str, float]]]:
    """One scene: header, floating window with shots, cursor and highlights. Returns html, problems, sound cues."""
    sid = scene["id"]
    body, script, problems, sounds = [], [], [], []
    shots = scene["shots"]
    starts = [0.0] + [at(lines, lead, shot["line"], shot.get("at", 0.0)) for shot in shots[1:]]
    full = {"x": 0.0, "y": 0.0, "w": float(W), "h": float(H)}
    previous = None
    layers = []
    for index, shot in enumerate(shots):
        begin = starts[index]
        end = starts[index + 1] + XFADE if index + 1 < len(shots) else duration
        span = r(end - begin)
        target = fit_zoom(shot["zoom"])
        origin = previous if previous is not None else mix(full, target, 0.35)
        cam_a, cam_b = camera(origin), camera(target)
        previous = target
        on_screen = K * cam_b["scale"]          # page pixels to frame pixels at the target framing
        prefix = f"{sid}-s{index}"
        items, cursor_moves = [], []
        for ring_index, ring in enumerate(shot.get("rings", [])):
            rect = ring.get("rect") or boxes.get(shot["screen"], {}).get(ring.get("box", ""))
            if rect is None:
                problems.append(f"{sid}: no box {shot['screen']}/{ring.get('box')}")
                continue
            ring_time = at(lines, lead, ring["line"], ring.get("at", 0.0)) - begin
            if not 0 <= ring_time < span - 0.6:
                problems.append(f"{sid}: ring {ring.get('box') or 'rect'} falls outside its shot")
                continue
            ring_id = f"{prefix}-r{ring_index}"
            items.append(
                f'<div id="{ring_id}" class="ring" style="left: {rect["x"]}px; top: {rect["y"]}px; width: {rect["w"]}px; '
                f'height: {rect["h"]}px; border-width: {r(3 / on_screen)}px; border-radius: {r(10 / on_screen)}px; '
                f'box-shadow: 0 0 0 {r(7 / on_screen)}px rgba(52, 216, 115, 0.18), 0 0 {r(30 / on_screen)}px rgba(52, 216, 115, 0.35);"></div>')
            if rect["h"] <= 90:     # a button: the cursor goes there and presses it, then the highlight lands
                cursor_moves.append((ring_time, rect["x"] + rect["w"] / 2, rect["y"] + rect["h"] / 2))
                show = ring_time + 0.12
                sounds.append(("click", begin + ring_time + 0.03))
            else:
                show = ring_time
                sounds.append(("pop", begin + ring_time + 0.03))
            script.append(f'    tl.fromTo("#{ring_id}", {{ opacity: 0, scale: 1.06 }}, {{ opacity: 1, scale: 1, duration: 0.35, '
                          f'ease: "power3.out" }}, {r(begin + show)});')
        if cursor_moves:
            size = r(CURSOR_PX / on_screen)
            cursor_id = f"{prefix}-c"
            items.append(f'<div id="{cursor_id}" class="cursor" style="width: {size}px; height: {size}px; '
                         f'margin-left: {r(-size * 4 / 24)}px; margin-top: {r(-size * 2 / 24)}px;">{CURSOR}</div>')
            first_t, fx, fy = cursor_moves[0]
            sx, sy = fx + 190 / on_screen, fy + 150 / on_screen
            appear = max(0.0, first_t - 0.9)
            script.append(f'    tl.fromTo("#{cursor_id}", {{ x: {r(sx)}, y: {r(sy)}, opacity: 0 }}, {{ opacity: 1, duration: 0.25, '
                          f'ease: "power1.out" }}, {r(begin + appear)});')
            px, py = sx, sy
            for move_t, tx, ty in cursor_moves:
                travel = min(0.6, max(0.25, move_t - appear - 0.05))
                script.append(f'    tl.fromTo("#{cursor_id}", {{ x: {r(px)}, y: {r(py)} }}, {{ x: {r(tx)}, y: {r(ty)}, '
                              f'duration: {r(travel)}, ease: "power3.inOut", immediateRender: false }}, {r(begin + move_t - travel)});')
                script.append(f'    tl.to("#{cursor_id}", {{ scale: 0.8, duration: 0.07, ease: "power2.in", yoyo: true, repeat: 1, '
                              f'transformOrigin: "{r(4 / 24 * 100)}% {r(2 / 24 * 100)}%" }}, {r(begin + move_t)});')
                px, py = tx, ty
        layers.append(
            f'        <div id="{prefix}" class="shot clip" data-start="{r(begin)}" data-duration="{span}" '
            f'data-track-index="{index % 2 + 1}" style="z-index: {index + 1};">\n'
            f'          <div id="{prefix}-fade" class="fade">\n'
            f'            <div id="{prefix}-cam" class="cam">\n'
            f'              <img id="{prefix}-img" src="assets/screens/{shot["screen"]}.png" alt="" />\n'
            + "".join(f"              {item}\n" for item in items)
            + "            </div>\n          </div>\n        </div>")
        move = r(min(1.1, max(0.5, (span - XFADE) * 0.5)))
        script.append(f'    tl.fromTo("#{prefix}-cam", {cam_a}, {{ ...{cam_b}, duration: {move}, ease: "power3.inOut" }}, '
                      f'{r(begin + (0.15 if index else 0.3))});'.replace("'", '"'))
        if index:
            script.append(f'    tl.fromTo("#{prefix}-fade", {{ opacity: 0 }}, {{ opacity: 1, duration: {XFADE}, ease: "sine.inOut" }}, '
                          f'{r(begin)});')

    # Header: one per run of shots with the same label, swapped with a blur.
    runs = []
    for index, shot in enumerate(shots):
        if runs and runs[-1]["label"] == shot["label"]:
            continue
        runs.append({"label": shot["label"], "step": shot["step"], "start": starts[index]})
    for index, run in enumerate(runs):
        stop = runs[index + 1]["start"] if index + 1 < len(runs) else duration
        hid = f"{sid}-h{index}"
        body.append(f'    <div id="{hid}" class="head clip" data-start="{r(run["start"])}" data-duration="{r(stop - run["start"])}" '
                    f'data-track-index="5"><span id="{hid}-n" class="step">STEP {int(run["step"]):02d}</span>'
                    f'<span id="{hid}-t" class="lab">{escape(run["label"])}</span></div>')
        enter_at = r(run["start"] + (0.15 if index == 0 else 0.0))
        script.append(f'    tl.fromTo(["#{hid}-n", "#{hid}-t"], {{ opacity: 0, filter: "blur(8px)" }}, {{ opacity: 1, filter: "blur(0px)", '
                      f'duration: 0.3, ease: "power2.out", stagger: 0.08 }}, {enter_at});')
        leave_at = r(stop - (EXIT if index + 1 == len(runs) else 0.2))
        script.append(f'    tl.to(["#{hid}-n", "#{hid}-t"], {{ opacity: 0, filter: "blur(8px)", duration: 0.18, ease: "power2.in" }}, '
                      f'{leave_at});')
    demo_text = "ข้อมูลตัวอย่าง: ผล AI จำลอง" if scene.get("demo") else "ข้อมูลตัวอย่าง"
    body.append(f'    <div id="{sid}-demo" class="demo clip" data-start="0" data-duration="{duration}" data-track-index="6">'
                f'<i></i><span id="{sid}-demo-t">{escape(demo_text)}</span></div>')
    script.append(f'    tl.fromTo("#{sid}-demo-t", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.3 }}, 0.4);')

    body.append(f'    <div id="{sid}-stage" class="stage">\n      <div id="{sid}-win" class="win">\n'
                f'        <div class="bar"><i></i><i></i><i></i><span>workbench / {escape(shots[0]["label"])}</span></div>\n'
                f'        <div class="content"><div class="screen">\n' + "\n".join(layers) + "\n        </div></div>\n      </div>\n    </div>")
    entrance = ENTRANCES[order % len(ENTRANCES)]
    script.insert(0, f'    tl.fromTo("#{sid}-win", {entrance}, {{ rotationX: 0, rotationY: 0, x: 0, y: 0, scale: 1, opacity: 1, '
                     f'filter: "blur(0px)", duration: {ENTER}, ease: "expo.out" }}, 0);')
    script.append(f'    tl.to("#{sid}-win", {{ scale: 1.08, opacity: 0, filter: "blur(12px)", duration: {EXIT}, ease: "power3.in" }}, '
                  f'{r(duration - EXIT)});')
    script.append(f'    tl.to("#{sid}-demo-t", {{ opacity: 0, duration: 0.2 }}, {r(duration - EXIT)});')
    return page("\n".join(body), "\n".join(script), f"sc-{sid}", SCREEN_STYLE, faces), problems, sounds


def title_scene(scene: dict, lead: float, lines: list[dict], duration: float, faces: str) -> str:
    sid = scene["id"]
    style = f"""    .left {{ position: absolute; left: 192px; top: 250px; width: 900px; }}
    .brand {{ display: flex; align-items: center; gap: 18px; font-size: 28px; font-weight: 500; color: {MUTED}; }}
    .brand img {{ width: 56px; height: 56px; }}
    h1 {{ margin: 34px 0 0; font-family: {DISPLAY_FONT}; font-weight: 700; font-size: 132px; line-height: 1.05;
      letter-spacing: -0.02em; color: {TEXT}; }}
    h1 em {{ display: block; font-style: normal; font-size: 92px; color: {ACCENT}; }}
    h1 span {{ display: inline-block; }}
    .sub {{ margin-top: 30px; font-size: 36px; line-height: 1.45; color: {MUTED}; }}
    .pill {{ display: inline-flex; align-items: center; gap: 10px; margin-top: 34px; padding: 8px 18px; border-radius: 999px;
      background: rgba(245, 185, 64, 0.12); border: 1px solid rgba(245, 185, 64, 0.45); color: #F8D58A; font-size: 22px; font-weight: 600; }}
    .pill i {{ width: 9px; height: 9px; border-radius: 50%; background: {AMBER}; }}
    .deck {{ position: absolute; left: 1010px; top: 210px; width: 860px; height: 640px; perspective: 1800px; }}
    .rig {{ position: absolute; inset: 0; transform-style: preserve-3d; }}
    .card {{ position: absolute; width: 760px; height: 428px; border-radius: 16px; overflow: hidden;
      box-shadow: 0 40px 100px rgba(0, 0, 0, 0.55), 0 0 0 1px rgba(255, 255, 255, 0.1); }}
    .card img {{ width: 100%; height: 100%; display: block; }}
    .out {{ position: absolute; inset: 0; }}"""
    body = f"""    <div id="{sid}-out" class="out">
      <div class="left">
        <div id="{sid}-brand" class="brand"><img src="assets/logo.svg" alt="" /><span>Retinal Review Workbench</span></div>
        <h1><span id="{sid}-w0">วิธีใช้งาน</span><em><span id="{sid}-w1">สำหรับ</span><span id="{sid}-w2">ทีมคลินิก</span></em></h1>
        <div id="{sid}-sub" class="sub">ตั้งแต่ Sign in จนถึง Export ชุดข้อมูล</div>
        <div id="{sid}-pill" class="pill"><i></i>ภาพทั้งหมดเป็นข้อมูลตัวอย่าง</div>
      </div>
      <div class="deck"><div id="{sid}-rig" class="rig">
        <div id="{sid}-c0" class="card" style="left: 120px; top: 0px;"><img src="assets/screens/s03a.png" alt="" /></div>
        <div id="{sid}-c1" class="card" style="left: 60px; top: 110px;"><img src="assets/screens/s07b.png" alt="" /></div>
        <div id="{sid}-c2" class="card" style="left: 0px; top: 220px;"><img src="assets/screens/s06b.png" alt="" /></div>
      </div></div>
    </div>"""
    t_pill = r(at(lines, lead, 2, 0.0))
    script = f"""    tl.fromTo("#{sid}-rig", {{ rotationY: -24, rotationX: 8 }}, {{ rotationY: -12, rotationX: 4, duration: {r(duration)}, ease: "none" }}, 0);
    tl.fromTo(["#{sid}-c0", "#{sid}-c1", "#{sid}-c2"], {{ x: 260, opacity: 0, filter: "blur(16px)" }}, {{ x: 0, opacity: 1, filter: "blur(0px)", duration: 1.0, ease: "expo.out", stagger: 0.14 }}, 0.1);
    tl.fromTo("#{sid}-brand", {{ opacity: 0, filter: "blur(8px)" }}, {{ opacity: 1, filter: "blur(0px)", duration: 0.3, ease: "power2.out" }}, 0.15);
    tl.fromTo(["#{sid}-w0", "#{sid}-w1", "#{sid}-w2"], {{ opacity: 0, filter: "blur(10px)", y: 18 }}, {{ opacity: 1, filter: "blur(0px)", y: 0, duration: 0.45, ease: "expo.out", stagger: 0.12 }}, 0.3);
    tl.fromTo("#{sid}-sub", {{ opacity: 0, filter: "blur(8px)" }}, {{ opacity: 1, filter: "blur(0px)", duration: 0.3, ease: "power2.out" }}, 0.8);
    tl.fromTo("#{sid}-pill", {{ opacity: 0, scale: 0.9 }}, {{ opacity: 1, scale: 1, duration: 0.35, ease: "back.out(1.6)" }}, {t_pill});
    tl.to("#{sid}-out", {{ scale: 1.06, opacity: 0, filter: "blur(12px)", duration: {EXIT}, ease: "power3.in" }}, {r(duration - EXIT)});"""
    return page(body, script, f"sc-{sid}", style, faces)


def end_scene(scene: dict, lead: float, lines: list[dict], duration: float, faces: str) -> str:
    sid = scene["id"]
    style = f"""    .list {{ position: absolute; left: 260px; right: 220px; top: 230px; display: flex; flex-direction: column; gap: 44px; }}
    .item {{ display: flex; align-items: center; gap: 30px; font-family: {DISPLAY_FONT}; font-size: 54px; line-height: 1.3;
      font-weight: 600; color: {TEXT}; }}
    .item svg {{ flex: none; color: {ACCENT}; }}
    .foot {{ position: absolute; left: 260px; top: 800px; display: flex; align-items: center; gap: 18px; font-size: 26px; color: {MUTED}; }}
    .foot img {{ width: 52px; height: 52px; }}
    .out {{ position: absolute; inset: 0; }}"""
    items = [("i0", "ไม่ใช่เครื่องมือวินิจฉัยโรค", 0), ("i1", "เกรดที่แพทย์ยืนยันคือผลที่ใช้จริง", 1),
             ("i2", "ส่งไป server ของทีมเฉพาะภาพสาธารณะ<br />หรือภาพที่ได้รับความยินยอม", 2)]
    body = [f'    <div id="{sid}-out" class="out">', f'    <div id="{sid}-list" class="list">']
    script = []
    for key, text, line in items:
        body.append(f'      <div id="{sid}-{key}" class="item">{CHECK}<span id="{sid}-{key}-t">{text}</span></div>')
        t = r(at(lines, lead, line, 0.0) - 0.1)
        script.append(f'    tl.fromTo("#{sid}-{key}", {{ opacity: 0, filter: "blur(10px)" }}, {{ opacity: 1, filter: "blur(0px)", '
                      f'duration: 0.35, ease: "power2.out" }}, {t});')
        script.append(f'    tl.fromTo("#{sid}-{key} .tick", {{ strokeDasharray: 20, strokeDashoffset: 20 }}, {{ strokeDashoffset: 0, '
                      f'duration: 0.4, ease: "power2.out" }}, {r(t + 0.2)});')
    body.append("    </div>")
    body.append(f'    <div id="{sid}-foot" class="foot"><img src="assets/logo.svg" alt="" />'
                '<span>Retinal Review Workbench  |  โปรแกรมทดลองใช้เพื่องานวิจัย  |  ข้อมูลตัวอย่าง</span></div>')
    body.append("    </div>")
    script.append(f'    tl.fromTo("#{sid}-foot", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.6, ease: "sine.out" }}, 0.6);')
    script.append(f'    tl.to("#{sid}-out", {{ opacity: 0, duration: 0.8, ease: "sine.in" }}, {r(duration - 0.85)});')
    return page("\n".join(body), "\n".join(script), f"sc-{sid}", style, faces)


def caption_groups(cues: list[tuple[float, float, float, float, str]], faces: str) -> str:
    """One line on screen at a time; each phrase (Thai text split at its spaces) lights up as it is spoken."""
    body, script = [], []
    for index, (begin, end, speak_start, speak_end, text) in enumerate(cues):
        chunks = text.split()
        weights = [max(1, len(chunk)) for chunk in chunks]
        total = sum(weights)
        spans, cursor = [], speak_start
        gid = f"cap-{index}"
        for k, (chunk, weight) in enumerate(zip(chunks, weights)):
            chunk_start = cursor
            cursor += (speak_end - speak_start) * weight / total
            cid = f"{gid}-{k}"
            spans.append(f'<span id="{cid}" class="w">{escape(chunk)}</span>')
            script.append(f'    tl.to("#{cid}", {{ color: "{ACCENT}", duration: 0.12, ease: "power1.out" }}, {r(max(begin, chunk_start - 0.04))});')
            script.append(f'    tl.to("#{cid}", {{ color: "#FFFFFF", duration: 0.25, ease: "power1.out" }}, {r(cursor)});')
        body.append(f'    <div id="{gid}" class="cap clip" data-start="{r(begin)}" data-duration="{r(end - begin)}" data-track-index="1">'
                    f'<div id="{gid}-t" class="line">{" ".join(spans)}</div></div>')
        script.append(f'    tl.fromTo("#{gid}-t", {{ opacity: 0, filter: "blur(8px)" }}, {{ opacity: 1, filter: "blur(0px)", duration: 0.18, '
                      f'ease: "power2.out" }}, {r(begin)});')
        script.append(f'    tl.to("#{gid}-t", {{ opacity: 0, duration: 0.12, ease: "power2.in" }}, {r(end - 0.12)});')
    style = f"""    #root {{ background: transparent; }}
    .cap {{ position: absolute; left: 0; right: 0; top: 914px; text-align: center; overflow: visible; }}
    .line {{ display: inline-block; max-width: 1500px; font-family: {UI_FONT}; font-size: 46px; line-height: 1.4; font-weight: 600;
      text-shadow: 0 2px 16px rgba(0, 0, 0, 0.6); }}
    .w {{ color: rgba(255, 255, 255, 0.4); }}"""
    return page("\n".join(body), "\n".join(script), "captions", style, faces)


def vtt_time(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, rest = divmod(milliseconds, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def main() -> int:
    config, timing, boxes = load()
    faces = font_faces()
    (HERE / "compositions").mkdir(exist_ok=True)
    shutil.copyfile(REPO / "frontend" / "src" / "assets" / "dr-support-logo.svg", HERE / "assets" / "logo.svg")
    cursor, hosts, cues, problems, estimated = 0.0, [], [], [], []
    sound = {"scenes": [], "voice": [], "cuts": [], "click": [], "pop": []}
    screen_order = 0
    for scene in config["scenes"]:
        voice, real = voice_timing(scene, timing)
        if not real:
            estimated.append(scene["id"])
        lead = CARD_LEAD if scene.get("card") == "title" else config["lead_in"]
        tail = END_TAIL if scene.get("card") == "end" else config["tail"]
        duration = r(lead + voice["duration"] + tail)
        lines = voice["lines"]
        if scene.get("card") == "title":
            html = title_scene(scene, lead, lines, duration, faces)
        elif scene.get("card") == "end":
            html = end_scene(scene, lead, lines, duration, faces)
        else:
            html, found, hits = screen_scene(scene, screen_order, lead, lines, duration, boxes, faces)
            screen_order += 1
            problems += found
            for kind, t in hits:
                sound[kind].append(r(cursor + t))
        if cursor:
            sound["cuts"].append(r(cursor))
        comp = f"sc-{scene['id']}"
        (HERE / "compositions" / f"{comp}.html").write_text(html, encoding="utf-8")
        hosts.append(f'      <div id="{comp}" data-composition-id="{comp}" data-composition-src="compositions/{comp}.html" '
                     f'data-start="{r(cursor)}" data-duration="{duration}" data-track-index="1" data-track-kind="graphics" '
                     f'data-width="{W}" data-height="{H}" style="z-index: 2;"></div>')
        sound["scenes"].append({"id": scene["id"], "start": r(cursor), "duration": duration, "card": scene.get("card")})
        if real:
            sound["voice"].append({"file": f"{scene['id']}.wav", "start": r(cursor + lead), "duration": voice["duration"]})
        for index, (text, span) in enumerate(zip(scene["captions"], lines)):
            speak_start, speak_end = cursor + lead + span["start"], cursor + lead + span["end"]
            begin = speak_start - 0.12
            limit = cursor + lead + lines[index + 1]["start"] - 0.13 if index + 1 < len(lines) else cursor + duration - 0.25
            end = min(speak_end + 0.4, limit)
            cues.append((r(begin), r(end), r(speak_start), r(speak_end), text))
        cursor = r(cursor + duration)
    total = cursor
    sound["total"] = total
    (HERE / "compositions" / "captions.html").write_text(caption_groups(cues, faces), encoding="utf-8")
    (HERE / "assets" / "audio" / "cues.json").write_text(json.dumps(sound, indent=1), encoding="utf-8")
    index_html = f"""<!doctype html>
<html lang="th">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={W}, height={H}" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
    <style>
      {faces}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: {W}px; height: {H}px; overflow: hidden; background: {BG}; font-family: {UI_FONT}; }}
      #bg {{ position: absolute; inset: 0; background:
        radial-gradient(900px 620px at 18% 12%, rgba(52, 216, 115, 0.13), transparent 70%),
        radial-gradient(900px 700px at 88% 92%, rgba(34, 211, 238, 0.09), transparent 70%), {BG}; }}
      #grid {{ position: absolute; inset: 0; opacity: 0.5; background-image:
        linear-gradient(rgba(255, 255, 255, 0.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 255, 255, 0.035) 1px, transparent 1px); background-size: 64px 64px; }}
      #orb {{ position: absolute; left: 0; top: 0; width: 760px; height: 760px; border-radius: 50%;
        background: radial-gradient(circle, rgba(52, 216, 115, 0.10), transparent 65%); }}
      #progress {{ position: absolute; left: 0; right: 0; top: 0; height: 4px; background: rgba(255, 255, 255, 0.06); }}
      #progress-fill {{ position: absolute; left: 0; right: 0; top: 0; height: 4px; background: linear-gradient(90deg, {ACCENT}, {TEAL}); transform-origin: 0 50%; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{total}" data-width="{W}" data-height="{H}">
      <div id="bg"></div>
      <div id="grid"></div>
      <div id="orb" style="z-index: 1;"></div>
{chr(10).join(hosts)}
      <div id="captions" data-composition-id="captions" data-composition-src="compositions/captions.html" data-start="0"
        data-duration="{total}" data-track-index="3" data-track-kind="captions" data-width="{W}" data-height="{H}"
        style="z-index: 10;"></div>
      <div id="progress" style="z-index: 11;"></div>
      <div id="progress-fill" style="z-index: 12;"></div>
      <audio id="soundtrack" class="clip" src="assets/audio/soundtrack.wav" data-start="0" data-duration="{total}"
        data-track-index="6" data-volume="1"></audio>
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
      tl.fromTo("#orb", {{ x: 80, y: 40 }}, {{ x: 1100, y: 380, duration: {total}, ease: "sine.inOut" }}, 0);
      tl.fromTo("#progress-fill", {{ scaleX: 0 }}, {{ scaleX: 1, duration: {total}, ease: "none" }}, 0);
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
"""
    (HERE / "index.html").write_text(index_html, encoding="utf-8")
    # The WebVTT track stays for players and screen readers; the picture already carries the captions.
    vtt = ["WEBVTT", "Language: th", ""]
    for index, (begin, end, _s, _e, text) in enumerate(cues, 1):
        vtt += [str(index), f"{vtt_time(begin)} --> {vtt_time(end)}", text, ""]
    media = REPO / "frontend" / "public" / "media"
    media.mkdir(parents=True, exist_ok=True)
    (media / "journey-th.vtt").write_text("\n".join(vtt), encoding="utf-8")
    report = {"duration": total, "scenes": len(config["scenes"]), "cues": len(cues), "estimated_timing": estimated,
              "problems": problems}
    (HERE / "timeline.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
