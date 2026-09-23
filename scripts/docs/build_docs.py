"""Build the Retinal Review Workbench documentation set.

One entry point for every generated document. Run it from the repository root:

    python scripts/docs/build_docs.py all
    python scripts/docs/build_docs.py clinician-manual operator-manual
    python scripts/docs/build_docs.py sampling developer image-guide demo briefing diagrams

Targets and outputs:

    clinician-manual  docs/manual/**                    -> docs/CLINICIAN_USER_MANUAL.pdf
    operator-manual   docs/operator-manual/**           -> docs/DEPLOYMENT_OPERATIONS_MANUAL.pdf
    sampling          docs/image-sampling-requirements/ -> docs/IMAGE_SAMPLING_REQUIREMENTS.pdf
    developer         docs/developer-manual/**          -> docs/DEVELOPER_TECHNICAL_GUIDE.pdf
    image-guide       docs/image-selection/IMAGE_SELECTION_GUIDE.html
                                                        -> docs/CLINICIAN_IMAGE_SELECTION_GUIDE.pdf
    demo              docs/demo/src/RETINAL_REVIEW_DEMO.source.html -> docs/demo/RETINAL_REVIEW_DEMO.html
    briefing          docs/demo/src/TECHNICAL_BRIEFING.source.html  -> docs/demo/TECHNICAL_BRIEFING.html
    diagrams          docs/architecture/*.mmd           -> docs/architecture/rendered/*.png|svg

Tool requirements (only for the targets that use them):

    Quarto CLI + XeLaTeX  Quarto books (set QUARTO_BIN if quarto is not on PATH)
    Playwright + Chromium image-guide PDF (pip install playwright; set PLAYWRIGHT_CHROMIUM_EXECUTABLE to reuse a browser)
    mermaid-cli (mmdc)    diagrams (set MMDC_BIN; set PUPPETEER_EXECUTABLE_PATH to reuse a browser)

The demo and briefing builds use only the Python standard library. Add --html to
also render the Quarto HTML sites under dist/manual/ (gitignored).
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"

BOOKS = {
    "clinician-manual": (DOCS / "manual", "site", "Retinal-Review-Workbench.pdf", DOCS / "CLINICIAN_USER_MANUAL.pdf"),
    "operator-manual": (DOCS / "operator-manual", "operator-site", "Retinal-Review-Workbench.pdf",
                        DOCS / "DEPLOYMENT_OPERATIONS_MANUAL.pdf"),
    "sampling": (DOCS / "image-sampling-requirements", "sampling-site", "Image-Sampling-Requirements.pdf",
                 DOCS / "IMAGE_SAMPLING_REQUIREMENTS.pdf"),
    "developer": (DOCS / "developer-manual", "developer-site", "Developer-Technical-Guide.pdf",
                  DOCS / "DEVELOPER_TECHNICAL_GUIDE.pdf"),
}
PRESENTATIONS = {
    "demo": (DOCS / "demo" / "src" / "RETINAL_REVIEW_DEMO.source.html", DOCS / "demo" / "RETINAL_REVIEW_DEMO.html"),
    "briefing": (DOCS / "demo" / "src" / "TECHNICAL_BRIEFING.source.html", DOCS / "demo" / "TECHNICAL_BRIEFING.html"),
}
GUIDE_HTML = DOCS / "image-selection" / "IMAGE_SELECTION_GUIDE.html"
GUIDE_PDF = DOCS / "CLINICIAN_IMAGE_SELECTION_GUIDE.pdf"
ARCH = DOCS / "architecture"
ORDER = ["diagrams", "clinician-manual", "operator-manual", "sampling", "developer", "image-guide", "demo", "briefing"]


def _quarto() -> str:
    configured = os.environ.get("QUARTO_BIN")
    if configured:
        return configured
    found = shutil.which("quarto")
    if found:
        return found
    for candidate in (
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Quarto" / "bin" / "quarto.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Quarto" / "bin" / "quarto.exe",
    ):
        if candidate.exists():
            return str(candidate)
    raise SystemExit("Quarto CLI was not found. Install a released Quarto CLI or set QUARTO_BIN.")


def build_book(name: str, html: bool) -> None:
    source, site, rendered_name, target = BOOKS[name]
    quarto = _quarto()
    # Run inside the book folder: Quarto treats a .env.example beside the working
    # directory as a list of required variables, and the repository root has one.
    formats = ["pdf", "html"] if html else ["pdf"]
    for fmt in formats:
        subprocess.run([quarto, "render", ".", "--to", fmt], cwd=source, check=True)
    rendered = ROOT / "dist" / "manual" / site / rendered_name
    if not rendered.exists():
        raise SystemExit(f"Quarto did not produce {rendered}")
    shutil.copy2(rendered, target)
    print(f"{name}: {target.relative_to(ROOT)}")


def _chromium_launch_kwargs() -> dict:
    executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    return {"executable_path": executable} if executable else {}


def build_image_guide() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - tool guard
        raise SystemExit("image-guide needs Playwright: pip install playwright") from exc
    with sync_playwright() as p:
        browser = p.chromium.launch(**_chromium_launch_kwargs())
        page = browser.new_page()
        page.goto(GUIDE_HTML.resolve().as_uri(), wait_until="load")
        page.emulate_media(media="print")
        page.pdf(path=str(GUIDE_PDF), format="A4", print_background=True, prefer_css_page_size=True)
        browser.close()
    print(f"image-guide: {GUIDE_PDF.relative_to(ROOT)}")


_ASSET = re.compile(r'''(src|href)="((?!https?:|data:|#|mailto:)[^"]+\.(?:png|jpg|jpeg|svg|webp))"''')
_CSS = re.compile(r'<link rel="stylesheet" href="([^"]+\.css)">')
_JS = re.compile(r'<script src="([^"]+\.js)"></script>')


def _data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def build_presentation(name: str) -> None:
    source, target = PRESENTATIONS[name]
    if not source.exists():
        raise SystemExit(f"Missing presentation source {source.relative_to(ROOT)}")
    base = source.parent
    html = source.read_text(encoding="utf-8")
    html = _CSS.sub(lambda m: "<style>\n" + (base / m.group(1)).read_text(encoding="utf-8") + "\n</style>", html)
    html = _JS.sub(lambda m: "<script>\n" + (base / m.group(1)).read_text(encoding="utf-8") + "\n</script>", html)

    def inline(match: re.Match) -> str:
        path = (base / match.group(2)).resolve()
        if not path.exists():
            raise SystemExit(f"{source.name}: missing asset {match.group(2)}")
        return f'{match.group(1)}="{_data_uri(path)}"'

    html = _ASSET.sub(inline, html)
    hotspots = DOCS / "demo" / "assets" / "hotspots.json"
    if hotspots.exists():
        data = json.dumps(json.loads(hotspots.read_text(encoding="utf-8")), separators=(",", ":"))
        html = html.replace('<script id="hotspot-data" type="application/json">{}</script>',
                            f'<script id="hotspot-data" type="application/json">{data}</script>')
    html = html.replace("<!-- BUILD:SOURCE -->", "<!-- Generated by scripts/docs/build_docs.py from "
                        f"{source.relative_to(ROOT).as_posix()}; edit the source, not this file. -->")
    target.write_text(html, encoding="utf-8")
    print(f"{name}: {target.relative_to(ROOT)} ({target.stat().st_size // 1024} KiB)")


def build_diagrams() -> None:
    mmdc = os.environ.get("MMDC_BIN") or shutil.which("mmdc")
    if not mmdc:
        raise SystemExit("diagrams needs mermaid-cli: npm install -g @mermaid-js/mermaid-cli (or set MMDC_BIN)")
    out = ARCH / "rendered"
    out.mkdir(exist_ok=True)
    config = ARCH / "mermaid-config.json"
    puppeteer = {"args": ["--no-sandbox"]}
    if os.environ.get("PUPPETEER_EXECUTABLE_PATH"):
        puppeteer["executablePath"] = os.environ["PUPPETEER_EXECUTABLE_PATH"]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(puppeteer, handle)
        puppeteer_path = handle.name
    try:
        for source in sorted(ARCH.glob("*.mmd")):
            for suffix, extra in ((".png", ["-w", "1600", "-s", "2"]), (".svg", ["-w", "1600"])):
                subprocess.run([mmdc, "-q", "-i", str(source), "-o", str(out / (source.stem + suffix)),
                                "-c", str(config), "-p", puppeteer_path, "-b", "white", *extra], check=True)
            print(f"diagram: {source.name}")
    finally:
        os.unlink(puppeteer_path)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("targets", nargs="+", choices=[*ORDER, "all"])
    parser.add_argument("--html", action="store_true", help="also render Quarto HTML sites under dist/manual/")
    args = parser.parse_args(argv)
    targets = ORDER if "all" in args.targets else [t for t in ORDER if t in args.targets]
    for target in targets:
        if target in BOOKS:
            build_book(target, args.html)
        elif target in PRESENTATIONS:
            build_presentation(target)
        elif target == "image-guide":
            build_image_guide()
        elif target == "diagrams":
            build_diagrams()


if __name__ == "__main__":
    sys.exit(main())
