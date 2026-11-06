"""Write the HyperFrames composition and the Thai WebVTT file from scenes.json.

  python media/journey-video/build.py [--burn-captions]

Inputs: scenes.json (lines, shots, rings), assets/audio/timing.json (from tts.py),
assets/screens/boxes.json (from the capture script). A scene without narration
timing yet gets an estimate so the film can be previewed; build.py says so and the
render must wait for tts.py. Outputs: index.html, compositions/*.html (static
HyperFrames source, editable in the HyperFrames desktop app) and
frontend/public/media/journey-th.vtt.
"""
from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
W, H = 1920, 1080
XFADE = 0.8          # cross-fade between shots
VEIL = 0.5           # fade from and to the canvas colour at scene edges
CHARS_PER_SECOND = 9.0
CARD_LEAD = 1.4      # the title card holds a moment before the voice starts
END_TAIL = 2.6       # the end card holds after the last word

INK, SECONDARY, CANVAS, PANEL = "#172018", "#52605A", "#F6F7F6", "#FFFFFF"
GREEN, GREEN_SOFT, SIDEBAR, MARK, RED_SOIL = "#016301", "#E8F3E8", "#16231A", "#6FBF73", "#A73B24"
WARN_BG, WARN_BORDER, WARN_TEXT = "#FBF2D9", "#E6CD8B", "#6E4A00"
FONT = "Inter, 'Leelawadee UI', sans-serif"
FONT_FACE = "@font-face { font-family: 'Leelawadee UI'; src: local('Leelawadee UI'), local('LeelawadeeUI'); }"
CHECK = ('<svg viewBox="0 0 24 24" width="56" height="56" fill="none" stroke="currentColor" stroke-width="2" '
         'stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>')


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
        cursor += length + 0.7
    return {"duration": round(cursor - 0.7, 3), "lines": lines}, False


def fit_zoom(zoom: dict) -> dict:
    """Keep the push-in target 16:9 and inside the page."""
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


def page(body: str, script: str, comp_id: str, style: str) -> str:
    return f"""<template>
  <style>
    {FONT_FACE}
    #root {{ position: absolute; inset: 0; overflow: hidden; background: {CANVAS}; font-family: {FONT}; color: {INK}; }}
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


SCREEN_STYLE = f"""    .shot {{ position: absolute; inset: 0; overflow: hidden; }}
    .fade {{ position: absolute; inset: 0; }}
    .cam {{ position: absolute; left: 0; top: 0; width: {W}px; height: {H}px; transform-origin: 0 0; }}
    .cam img {{ position: absolute; left: 0; top: 0; width: {W}px; height: {H}px; }}
    .ring {{ position: absolute; border-style: solid; border-color: {GREEN}; opacity: 0; }}
    .tap {{ position: absolute; border-radius: 50%; background: rgba(1, 99, 1, 0.28); opacity: 0; }}
    .chip {{ position: absolute; left: 110px; top: 66px; display: flex; align-items: center; gap: 16px;
      padding: 10px 28px 10px 10px; border-radius: 999px; background: {SIDEBAR}; color: #FFFFFF;
      font-size: 30px; font-weight: 600; box-shadow: 0 10px 30px rgba(22, 35, 26, 0.25); }}
    .chip b {{ display: inline-flex; align-items: center; justify-content: center; width: 50px; height: 50px;
      border-radius: 50%; background: {MARK}; color: {SIDEBAR}; font-size: 30px; }}
    .demo {{ position: absolute; right: 110px; top: 70px; padding: 12px 24px; border-radius: 14px; background: {WARN_BG};
      border: 2px solid {WARN_BORDER}; color: {WARN_TEXT}; font-size: 30px; font-weight: 600; transform-origin: 100% 50%;
      box-shadow: 0 10px 30px rgba(22, 35, 26, 0.18); }}
    .veil {{ position: absolute; inset: 0; background: {CANVAS}; }}"""


def screen_scene(scene: dict, start_lead: float, lines: list[dict], duration: float, boxes: dict) -> tuple[str, list[str]]:
    sid = scene["id"]
    body, script, problems = [], [], []
    shots = scene["shots"]
    starts = [0.0] + [at(lines, start_lead, shot["line"], shot.get("at", 0.0)) for shot in shots[1:]]
    full = {"x": 0.0, "y": 0.0, "w": float(W), "h": float(H)}
    previous = None
    for index, shot in enumerate(shots):
        begin = starts[index]
        end = starts[index + 1] + XFADE if index + 1 < len(shots) else duration
        span = round(end - begin, 3)
        target = fit_zoom(shot["zoom"])
        # Each shot starts where the last one stopped, so a cross-fade never doubles the page.
        origin = previous if previous is not None else mix(full, target, 0.2)
        cam_a, cam_b = camera(origin), camera(target)
        previous = target
        move = round(span - XFADE, 3) if index + 1 < len(shots) else span
        prefix = f"{sid}-s{index}"
        rings_html = []
        for ring_index, ring in enumerate(shot.get("rings", [])):
            rect = ring.get("rect") or boxes.get(shot["screen"], {}).get(ring.get("box", ""))
            if rect is None:
                problems.append(f"{sid}: no box {shot['screen']}/{ring.get('box')}")
                continue
            ring_time = at(lines, start_lead, ring["line"], ring.get("at", 0.0)) - begin
            if not 0 <= ring_time < span - 0.6:
                problems.append(f"{sid}: ring {ring.get('box') or 'rect'} falls outside its shot")
                continue
            border = round(5 / cam_b["scale"], 2)
            radius = round(12 / cam_b["scale"], 2)
            glow = round(10 / cam_b["scale"], 2)
            ring_id = f"{prefix}-r{ring_index}"
            rings_html.append(
                f'<div id="{ring_id}" class="ring" style="left: {rect["x"]}px; top: {rect["y"]}px; width: {rect["w"]}px; '
                f'height: {rect["h"]}px; border-width: {border}px; border-radius: {radius}px; '
                f'box-shadow: 0 0 0 {glow}px rgba(1, 99, 1, 0.16);"></div>')
            script.append(f'    tl.fromTo("#{ring_id}", {{ opacity: 0, scale: 1.08 }}, {{ opacity: 1, scale: 1, duration: 0.55, '
                          f'ease: "power2.out" }}, {round(begin + ring_time, 3)});')
            if rect["h"] <= 90:     # a button: one soft tap at its centre
                size = round(min(rect["h"] * 1.6, 120))
                tap_id = f"{prefix}-t{ring_index}"
                rings_html.append(
                    f'<div id="{tap_id}" class="tap" style="left: {rect["x"] + rect["w"] / 2 - size / 2}px; '
                    f'top: {rect["y"] + rect["h"] / 2 - size / 2}px; width: {size}px; height: {size}px;"></div>')
                script.append(f'    tl.fromTo("#{tap_id}", {{ opacity: 0.85, scale: 0.3 }}, {{ opacity: 0, scale: 1.5, duration: 0.8, '
                              f'ease: "power1.out" }}, {round(begin + ring_time + 0.35, 3)});')
        chip = (f'<div id="{prefix}-chip" class="chip"><b>{escape(shot["step"])}</b><span>{escape(shot["label"])}</span></div>')
        body.append(
            f'    <div id="{prefix}" class="shot clip" data-start="{round(begin, 3)}" data-duration="{span}" '
            f'data-track-index="{index % 2 + 1}" style="z-index: {index + 1};">\n'
            f'      <div id="{prefix}-fade" class="fade">\n'
            f'        <div id="{prefix}-cam" class="cam">\n'
            f'          <img id="{prefix}-img" src="assets/screens/{shot["screen"]}.png" alt="" />\n'
            + "".join(f"          {item}\n" for item in rings_html)
            + "        </div>\n"
            f"        {chip}\n"
            "      </div>\n    </div>")
        script.append(f'    tl.fromTo("#{prefix}-cam", {cam_a}, {{ ...{cam_b}, duration: {move}, ease: "sine.inOut" }}, '
                      f'{round(begin, 3)});'.replace("'", '"'))
        if index:
            script.append(f'    tl.fromTo("#{prefix}-fade", {{ opacity: 0 }}, {{ opacity: 1, duration: {XFADE}, ease: "sine.inOut" }}, '
                          f'{round(begin, 3)});')
    demo_text = ("ข้อมูลตัวอย่าง: ผล AI จำลอง ไม่ได้มาจากโมเดลจริง" if scene.get("demo") else "ข้อมูลตัวอย่าง")
    body.append(f'    <div id="{sid}-demo" class="demo clip" data-start="0" data-duration="{duration}" data-track-index="3" '
                f'style="z-index: 50;">{escape(demo_text)}</div>')
    if scene["id"] == "ai":
        pulse = round(at(lines, start_lead, 2, 0.1), 3)
        script.append(f'    tl.fromTo("#{sid}-demo", {{ scale: 1 }}, {{ scale: 1.08, duration: 0.45, yoyo: true, repeat: 1, '
                      f'ease: "sine.inOut" }}, {pulse});')
    body.append(f'    <div id="{sid}-veil" class="veil clip" data-start="0" data-duration="{duration}" data-track-index="4" '
                f'style="z-index: 60;"></div>')
    script.append(f'    tl.fromTo("#{sid}-veil", {{ opacity: 1 }}, {{ opacity: 0, duration: {VEIL}, ease: "sine.out" }}, 0);')
    script.append(f'    tl.to("#{sid}-veil", {{ opacity: 1, duration: {VEIL}, ease: "sine.in" }}, '
                  f'{round(duration - VEIL - 0.02, 3)});')
    return page("\n".join(body), "\n".join(script), f"sc-{sid}", SCREEN_STYLE), problems


def title_scene(scene: dict, lead: float, lines: list[dict], duration: float) -> str:
    sid = scene["id"]
    style = f"""    .left {{ position: absolute; left: 150px; top: 0; bottom: 0; width: 860px; display: flex; flex-direction: column;
      justify-content: center; gap: 30px; }}
    .brand {{ display: flex; align-items: center; gap: 22px; font-size: 30px; font-weight: 600; color: {SECONDARY}; }}
    .brand img {{ width: 84px; height: 84px; }}
    h1 {{ margin: 0; font-size: 92px; line-height: 1.08; letter-spacing: -0.02em; font-weight: 700; color: {INK}; }}
    .sub {{ font-size: 44px; line-height: 1.45; color: {SECONDARY}; }}
    .rule {{ width: 120px; height: 6px; border-radius: 3px; background: {RED_SOIL}; }}
    .pill {{ align-self: flex-start; padding: 12px 24px; border-radius: 14px; background: {WARN_BG}; border: 2px solid {WARN_BORDER};
      color: {WARN_TEXT}; font-size: 28px; font-weight: 600; }}
    .panel {{ position: absolute; right: 0; top: 0; bottom: 0; width: 800px; background: {SIDEBAR}; overflow: hidden; }}
    .halo {{ position: absolute; right: -200px; top: -220px; width: 640px; height: 640px; border-radius: 50%;
      background: rgba(255, 255, 255, 0.06); }}
    .frame {{ position: absolute; left: 90px; top: 250px; width: 900px; height: 506px; border-radius: 18px; overflow: hidden;
      box-shadow: 0 30px 80px rgba(0, 0, 0, 0.45); border: 2px solid rgba(255, 255, 255, 0.12); }}
    .frame img {{ width: 100%; height: 100%; }}
    .veil {{ position: absolute; inset: 0; background: {CANVAS}; }}"""
    body = f"""    <div id="{sid}-panel" class="panel"><div class="halo"></div>
      <div id="{sid}-frame" class="frame"><img src="assets/screens/s06b.png" alt="" /></div>
    </div>
    <div class="left">
      <div id="{sid}-brand" class="brand"><img src="assets/logo.svg" alt="" /><span>Retinal Review Workbench</span></div>
      <div id="{sid}-rule" class="rule"></div>
      <h1 id="{sid}-title">วิธีใช้งาน<br />สำหรับทีมคลินิก</h1>
      <div id="{sid}-sub" class="sub">ตั้งแต่ Sign in จนถึง Export ชุดข้อมูล</div>
      <div id="{sid}-pill" class="pill">ภาพทั้งหมดเป็นข้อมูลตัวอย่าง</div>
    </div>
    <div id="{sid}-veil" class="veil clip" data-start="0" data-duration="{duration}" data-track-index="2" style="z-index: 60;"></div>"""
    t_pill = round(at(lines, lead, 2, 0.0), 3)
    script = f"""    tl.fromTo("#{sid}-panel", {{ x: 0 }}, {{ x: -24, duration: {round(duration, 2)}, ease: "sine.inOut" }}, 0);
    tl.fromTo("#{sid}-frame", {{ x: 0, y: 30, scale: 1.0 }}, {{ x: -40, y: 0, scale: 1.06, duration: {round(duration, 2)}, ease: "sine.inOut" }}, 0);
    tl.fromTo("#{sid}-rule", {{ scaleX: 0.25, transformOrigin: "0% 50%" }}, {{ scaleX: 1, duration: 1.2, ease: "power2.out" }}, 0.2);
    tl.fromTo("#{sid}-sub", {{ y: 20, opacity: 0 }}, {{ y: 0, opacity: 1, duration: 0.8, ease: "power2.out" }}, 0.6);
    tl.fromTo("#{sid}-pill", {{ y: 16, opacity: 0 }}, {{ y: 0, opacity: 1, duration: 0.7, ease: "power2.out" }}, {t_pill});
    tl.fromTo("#{sid}-veil", {{ opacity: 0 }}, {{ opacity: 1, duration: {VEIL}, ease: "sine.in" }}, {round(duration - VEIL - 0.02, 3)});"""
    return page(body, script, f"sc-{sid}", style)


def end_scene(scene: dict, lead: float, lines: list[dict], duration: float) -> str:
    sid = scene["id"]
    style = f"""    #root {{ background: {SIDEBAR}; color: #FFFFFF; }}
    .halo {{ position: absolute; left: -260px; bottom: -320px; width: 820px; height: 820px; border-radius: 50%;
      background: rgba(255, 255, 255, 0.05); }}
    .list {{ position: absolute; left: 230px; right: 230px; top: 190px; display: flex; flex-direction: column; gap: 46px; }}
    .item {{ display: flex; align-items: center; gap: 30px; font-size: 52px; line-height: 1.35; font-weight: 600; }}
    .item svg {{ flex: none; color: {MARK}; }}
    .foot {{ position: absolute; left: 230px; top: 720px; display: flex; align-items: center; gap: 20px; font-size: 30px;
      color: #A9BCAF; }}
    .foot img {{ width: 64px; height: 64px; }}
    .veil {{ position: absolute; inset: 0; background: {CANVAS}; }}
    .black {{ position: absolute; inset: 0; background: {SIDEBAR}; }}"""
    items = [("i0", "ไม่ใช่เครื่องมือวินิจฉัยโรค", 0), ("i1", "เกรดที่แพทย์ยืนยันคือผลที่ใช้จริง", 1),
             ("i2", "ส่งไป server ของทีมเฉพาะภาพสาธารณะ<br />หรือภาพที่ได้รับความยินยอม", 2)]
    body = [f'    <div id="{sid}-halo" class="halo"></div>', f'    <div id="{sid}-list" class="list">']
    script = []
    for key, text, line in items:
        body.append(f'      <div id="{sid}-{key}" class="item">{CHECK}<span>{text}</span></div>')
        script.append(f'    tl.fromTo("#{sid}-{key}", {{ x: -30, opacity: 0 }}, {{ x: 0, opacity: 1, duration: 0.8, ease: "power2.out" }}, '
                      f'{round(at(lines, lead, line, 0.0) - 0.1, 3)});')
    body.append("    </div>")
    body.append(f'    <div id="{sid}-foot" class="foot"><img src="assets/logo.svg" alt="" />'
                '<span>Retinal Review Workbench  |  โปรแกรมทดลองใช้เพื่องานวิจัย  |  ข้อมูลตัวอย่าง</span></div>')
    body.append(f'    <div id="{sid}-veil" class="veil clip" data-start="0" data-duration="{duration}" data-track-index="2" '
                'style="z-index: 60;"></div>')
    script.append(f'    tl.fromTo("#{sid}-foot", {{ opacity: 0 }}, {{ opacity: 1, duration: 1.0, ease: "sine.out" }}, 0.8);')
    script.append(f'    tl.fromTo("#{sid}-halo", {{ scale: 1 }}, {{ scale: 1.25, duration: {round(duration, 2)}, ease: "sine.inOut" }}, 0);')
    script.append(f'    tl.fromTo("#{sid}-list", {{ scale: 1, transformOrigin: "0% 0%" }}, {{ scale: 1.035, duration: {round(duration, 2)}, '
                  'ease: "sine.inOut" }, 0);')
    script.append(f'    tl.fromTo("#{sid}-veil", {{ opacity: 1 }}, {{ opacity: 0, duration: 0.7, ease: "sine.out" }}, 0);')
    return page("\n".join(body), "\n".join(script), f"sc-{sid}", style)


def vtt_time(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, rest = divmod(milliseconds, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--burn-captions", action="store_true",
                        help="draw the captions into the picture (off for the web video, which carries the WebVTT track)")
    args = parser.parse_args()
    config, timing, boxes = load()
    (HERE / "compositions").mkdir(exist_ok=True)
    shutil.copyfile(REPO / "frontend" / "src" / "assets" / "dr-support-logo.svg", HERE / "assets" / "logo.svg")
    cursor, hosts, audios, cues, problems, estimated = 0.0, [], [], [], [], []
    for scene in config["scenes"]:
        voice, real = voice_timing(scene, timing)
        if not real:
            estimated.append(scene["id"])
        lead = CARD_LEAD if scene.get("card") == "title" else config["lead_in"]
        tail = END_TAIL if scene.get("card") == "end" else config["tail"]
        duration = round(lead + voice["duration"] + tail, 3)
        lines = voice["lines"]
        if scene.get("card") == "title":
            html = title_scene(scene, lead, lines, duration)
        elif scene.get("card") == "end":
            html = end_scene(scene, lead, lines, duration)
        else:
            html, found = screen_scene(scene, lead, lines, duration, boxes)
            problems += found
        comp = f"sc-{scene['id']}"
        (HERE / "compositions" / f"{comp}.html").write_text(html, encoding="utf-8")
        hosts.append(f'      <div id="{comp}" data-composition-id="{comp}" data-composition-src="compositions/{comp}.html" '
                     f'data-start="{round(cursor, 3)}" data-duration="{duration}" data-track-index="1" data-track-kind="graphics" '
                     f'data-width="{W}" data-height="{H}" style="z-index: 1;"></div>')
        if real:
            audios.append(f'      <audio id="vo-{scene["id"]}" class="clip" src="assets/audio/{scene["id"]}.wav" '
                          f'data-start="{round(cursor + lead, 3)}" data-duration="{voice["duration"]}" data-track-index="6" '
                          'data-volume="1"></audio>')
        for index, (text, span) in enumerate(zip(scene["captions"], lines)):
            begin = cursor + lead + span["start"] - 0.15
            limit = cursor + lead + lines[index + 1]["start"] - 0.2 if index + 1 < len(lines) else cursor + duration - 0.3
            end = min(cursor + lead + span["end"] + 0.45, limit)
            cues.append((round(begin, 3), round(end, 3), text))
        cursor = round(cursor + duration, 3)
    total = cursor
    # The web player shows the WebVTT track (on by default, can be switched off); captions drawn into the
    # picture as well would show every line twice, so they stay hidden unless asked for.
    hidden = "" if args.burn_captions else " data-hidden"
    caption_body = []
    caption_script = []
    for index, (begin, end, text) in enumerate(cues):
        caption_body.append(f'    <div id="cap-{index}" class="cap clip" data-start="{begin}" data-duration="{round(end - begin, 3)}" '
                            f'data-track-index="1"><span id="cap-{index}-t" class="cap-t">{escape(text)}</span></div>')
        caption_script.append(f'    tl.fromTo("#cap-{index}-t", {{ opacity: 0, y: 8 }}, {{ opacity: 1, y: 0, duration: 0.3, ease: "power2.out" }}, {begin});')
        caption_script.append(f'    tl.to("#cap-{index}-t", {{ opacity: 0, duration: 0.2, ease: "power2.in" }}, {round(end - 0.2, 3)});')
    caption_style = """    #root { background: transparent; }
    .cap { position: absolute; left: 0; right: 0; bottom: 112px; text-align: center; }
    .cap-t { display: inline-block; max-width: 1560px; padding: 12px 32px 16px; border-radius: 16px;
      background: rgba(22, 35, 26, 0.88); color: #FFFFFF; font-size: 46px; line-height: 1.45; font-weight: 500; }"""
    (HERE / "compositions" / "captions.html").write_text(
        page("\n".join(caption_body), "\n".join(caption_script), "captions", caption_style), encoding="utf-8")
    index_html = f"""<!doctype html>
<html lang="th">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={W}, height={H}" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
    <style>
      {FONT_FACE}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: {W}px; height: {H}px; overflow: hidden; background: {CANVAS}; font-family: {FONT}; }}
      #bg {{ position: absolute; inset: 0; background: {CANVAS}; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{total}" data-width="{W}" data-height="{H}">
      <div id="bg"></div>
{chr(10).join(hosts)}
      <div id="captions" data-composition-id="captions" data-composition-src="compositions/captions.html" data-start="0"
        data-duration="{total}" data-track-index="3" data-track-kind="captions" data-width="{W}" data-height="{H}"{hidden}
        style="z-index: 10;"></div>
{chr(10).join(audios)}
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      window.__timelines["main"] = gsap.timeline({{ paused: true }});
    </script>
  </body>
</html>
"""
    (HERE / "index.html").write_text(index_html, encoding="utf-8")
    vtt = ["WEBVTT", "Language: th", ""]
    for index, (begin, end, text) in enumerate(cues, 1):
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
