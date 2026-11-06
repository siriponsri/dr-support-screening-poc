"""Build the three Thai PDF guides from the Markdown sources in docs/th/.

  python scripts/docs/build_pdfs.py                 # all three guides
  python scripts/docs/build_pdfs.py user-manual     # one guide (source name without .md)

Each source starts with a small front matter block (title, subtitle, audience, version, date, short,
output). The Markdown becomes one self-contained HTML page: a cover page, a table of contents with page
numbers, numbered chapters, figures with captions (``![caption](images/file.jpg)`` on its own line),
callout boxes (``!!! warning "title"``, also ``note``, ``tip`` and ``danger``) and numbered steps. The Thai
font (Anuphan, SIL Open Font License, docs/th/assets) and every image are embedded, so the page renders the
same from a file. Microsoft Edge (Playwright) prints it to A4 with page numbers in the footer.

The table of contents needs two passes: the first PDF carries a tiny invisible marker in each heading, pypdf
finds the page of each marker, and the second pass prints the final PDF with those page numbers.
"""
from __future__ import annotations

import argparse
import base64
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "docs" / "th"
ASSETS = SOURCES / "assets"
OUT = ROOT / "docs" / "pdfs"
LOGO = ROOT / "assets" / "retinal-review-workbench-mark.png"
GUIDES = ("user-manual", "deployment-guide", "test-report")
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
        ".svg": "image/svg+xml"}
MARKER = "QQH{}QQ"
MARKER_FIND = re.compile(r"QQH(\d+)QQ")

CSS = """
@page {
  size: A4;
  margin: 20mm 17mm 18mm 17mm;
  @top-right { content: "%(short)s"; font-family: 'Anuphan', sans-serif; font-size: 8.5pt; color: #6b7a72; }
  @bottom-center { content: counter(page) " / " counter(pages); font-family: 'Anuphan', sans-serif;
                   font-size: 9pt; color: #6b7a72; }
  @bottom-left { content: "Retinal Review Workbench"; font-family: 'Anuphan', sans-serif; font-size: 8pt;
                 color: #9aa7a0; }
}
@page :first { margin: 0; @top-right { content: none; } @bottom-center { content: none; }
               @bottom-left { content: none; } }
:root { --green: #1f5f3a; --green-dark: #163d28; --line: #d5ddd8; --soft: #f1f5f2; --text: #1d2420; }
* { box-sizing: border-box; }
html { font-size: 10.5pt; }
body { margin: 0; font-family: 'Anuphan', 'Leelawadee UI', Tahoma, sans-serif; color: var(--text);
       line-height: 1.62; font-weight: 400; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
strong, b { font-weight: 600; }
.cover { height: 297mm; width: 210mm; padding: 34mm 24mm 22mm; display: flex; flex-direction: column;
         background: linear-gradient(160deg, #163d28 0%%, #1f5f3a 62%%, #2f7a4d 100%%); color: #fff;
         break-after: page; }
.cover .brand { display: flex; align-items: center; gap: 12px; font-size: 12pt; font-weight: 500;
                letter-spacing: .2px; opacity: .95; }
.cover .brand img { width: 46px; height: 46px; border-radius: 50%%; background: #fff; padding: 3px; }
.cover h1 { font-size: 30pt; line-height: 1.25; margin: 44mm 0 6mm; font-weight: 600; }
.cover .subtitle { font-size: 14pt; font-weight: 400; opacity: .92; max-width: 150mm; }
.cover .meta { margin-top: auto; display: grid; grid-template-columns: 34mm 1fr; row-gap: 2.5mm;
               font-size: 11pt; border-top: 1px solid rgba(255,255,255,.35); padding-top: 7mm; }
.cover .meta span:nth-child(odd) { opacity: .75; }
.cover .notice { margin-top: 9mm; background: rgba(255,255,255,.12); border-left: 4px solid #f2c14e;
                 padding: 4mm 5mm; font-size: 10pt; border-radius: 0 6px 6px 0; }
nav.toc { break-after: auto; }
main { break-before: page; }
nav.toc h2 { margin-top: 0; }
nav.toc ol { list-style: none; padding: 0; margin: 0; }
nav.toc li { display: flex; align-items: baseline; gap: 6px; padding: 1.2mm 0; }
nav.toc li.l3 { padding-left: 9mm; font-size: 9.8pt; color: #3a463f; padding-top: .5mm; padding-bottom: .5mm; }
nav.toc li.l2 { font-weight: 500; margin-top: 1.6mm; }
nav.toc .dots { flex: 1; border-bottom: 1px dotted #9aa7a0; transform: translateY(-3px); }
nav.toc .pg { min-width: 7mm; text-align: right; font-variant-numeric: tabular-nums; }
nav.toc a { color: inherit; text-decoration: none; }
h2 { font-size: 17pt; color: var(--green-dark); font-weight: 600; margin: 0 0 4mm; padding-bottom: 2mm;
     border-bottom: 2px solid var(--green); line-height: 1.3; }
main h2 { break-before: %(chapter_break)s; margin-top: 7mm; }
main h2:first-child { margin-top: 0; break-before: auto; }
h3 { font-size: 12.5pt; color: var(--green); font-weight: 600; margin: 6mm 0 2mm; break-after: avoid; }
h4 { font-size: 11pt; font-weight: 600; margin: 4mm 0 1.5mm; break-after: avoid; }
p { margin: 0 0 2.6mm; }
a { color: var(--green); }
ul, ol { margin: 0 0 3mm; padding-left: 7mm; }
li { margin: .8mm 0; }
main ol { list-style: none; counter-reset: step; padding-left: 10mm; }
main ol > li { counter-increment: step; position: relative; }
main ol > li::before { content: counter(step); position: absolute; left: -9.5mm; top: .4mm; width: 6.2mm;
                       height: 6.2mm; border-radius: 50%%; background: var(--green); color: #fff;
                       font-size: 8.5pt; font-weight: 600; text-align: center; line-height: 6.2mm; }
code { font-family: Consolas, 'Anuphan', monospace; font-size: 9pt; background: #eef2ef; padding: .2mm 1.2mm;
       border-radius: 3px; }
pre { background: #f4f6f5; border: 1px solid var(--line); border-radius: 6px; padding: 3mm 4mm; font-size: 8.8pt;
      line-height: 1.45; white-space: pre-wrap; word-break: break-all; break-inside: avoid; }
pre code { background: none; padding: 0; font-size: inherit; }
table { width: 100%%; border-collapse: collapse; margin: 2mm 0 4mm; font-size: 9.4pt; break-inside: auto; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
th { background: var(--soft); color: var(--green-dark); font-weight: 600; text-align: left; }
th, td { border: 1px solid var(--line); padding: 1.6mm 2.4mm; vertical-align: top; }
figure { margin: 3mm 0 5mm; break-inside: avoid; text-align: center; }
figure img { max-width: 100%%; max-height: 122mm; border: 1px solid var(--line); border-radius: 4px; }
figcaption { font-size: 9pt; color: #4b5852; margin-top: 1.6mm; }
figcaption b { color: var(--green); }
.admonition { border-radius: 6px; padding: 3mm 4mm 1.2mm; margin: 3mm 0 4mm; border-left: 5px solid;
              break-inside: avoid; }
.admonition-title { font-weight: 600; margin-bottom: 1.2mm; }
.admonition.note, .admonition.info { background: #eef6f1; border-color: #2f7a4d; }
.admonition.tip { background: #eef4fb; border-color: #3b6fb6; }
.admonition.warning, .admonition.caution { background: #fff6e2; border-color: #d99a1c; }
.admonition.danger, .admonition.important { background: #fdecea; border-color: #c0392b; }
.marker { font-size: 1px; color: #fff; letter-spacing: 0; }
hr { border: 0; border-top: 1px solid var(--line); margin: 5mm 0; }
"""


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Split ``---`` ``key: value`` lines from the Markdown body."""
    if not text.startswith("---"):
        return {}, text
    head, _, body = text[3:].partition("\n---")
    meta = {}
    for line in head.strip().splitlines():
        key, _, value = line.partition(":")
        if key.strip():
            meta[key.strip()] = value.strip()
    return meta, body.lstrip("\n")


def data_uri(path: Path) -> str:
    mime = MIME.get(path.suffix.lower())
    if mime is None:
        raise ValueError(f"unsupported image type: {path.name}")
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _figures(body: str, base_dir: Path) -> str:
    count = 0

    def figure(match: re.Match) -> str:
        nonlocal count
        count += 1
        alt, src = html.unescape(match.group(1)), match.group(2)
        image = data_uri((base_dir / src).resolve())
        return (f'<figure><img src="{image}" alt="{html.escape(alt)}">'
                f'<figcaption><b>รูปที่ {count}</b> {html.escape(alt)}</figcaption></figure>')

    body = re.sub(r'<p><img alt="([^"]*)" src="([^"]+)"\s*/?></p>', figure, body)

    def inline(match: re.Match) -> str:  # Any other image is embedded too.
        return f'src="{data_uri((base_dir / match.group(1)).resolve())}"'
    return re.sub(r'src="(?!data:)([^"]+\.(?:jpe?g|png|webp|svg))"', inline, body)


def _headings(body: str, numbered: bool, markers: bool) -> tuple[str, list[dict]]:
    entries: list[dict] = []
    chapter = section = 0

    def heading(match: re.Match) -> str:
        nonlocal chapter, section
        level, text = int(match.group(1)), match.group(3)
        if level == 2:
            chapter, section = chapter + 1, 0
            number = f"{chapter}."
        else:
            section += 1
            number = f"{chapter}.{section}"
        label = f"{number} {text}" if numbered and chapter else text
        index = len(entries)
        anchor = f"sec-{index}"
        entries.append({"level": level, "html": label, "anchor": anchor})
        mark = f'<span class="marker">{MARKER.format(index)}</span>' if markers else ""
        return f'<h{level} id="{anchor}">{label}{mark}</h{level}>'

    return re.sub(r"<h([23])([^>]*)>(.*?)</h\1>", heading, body, flags=re.S), entries


def _toc(entries: list[dict], pages: dict[int, int] | None) -> str:
    rows = []
    for index, entry in enumerate(entries):
        page = str(pages.get(index, "")) if pages else "00"
        rows.append(f'<li class="l{entry["level"]}"><a href="#{entry["anchor"]}">{entry["html"]}</a>'
                    f'<span class="dots"></span><span class="pg">{page}</span></li>')
    return '<nav class="toc"><h2>สารบัญ</h2><ol>' + "".join(rows) + "</ol></nav>"


def _font_css() -> str:
    font = ASSETS / "anuphan.css"
    return font.read_text(encoding="utf-8") if font.is_file() else ""


def render_html(text: str, base_dir: Path, *, pages: dict[int, int] | None = None, markers: bool = False) -> str:
    """The complete, self-contained HTML page for one guide."""
    import markdown
    meta, body = parse_front_matter(text)
    converted = markdown.markdown(body, extensions=["tables", "fenced_code", "admonition", "attr_list",
                                                    "sane_lists"], output_format="html")
    converted = _figures(converted, base_dir)
    converted, entries = _headings(converted, meta.get("numbered", "yes") != "no", markers)
    title = html.escape(meta.get("title", "Untitled"))
    logo = f'<img src="{data_uri(LOGO)}" alt="">' if LOGO.is_file() else ""
    meta_rows = "".join(f"<span>{html.escape(label)}</span><span>{html.escape(meta[key])}</span>"
                        for key, label in (("audience", "สำหรับ"), ("version", "ฉบับ"), ("date", "วันที่"))
                        if meta.get(key))
    notice = (f'<div class="notice">{html.escape(meta["notice"])}</div>' if meta.get("notice") else "")
    cover = (f'<section class="cover"><div class="brand">{logo}<span>Retinal Review Workbench</span></div>'
             f'<h1>{title}</h1><div class="subtitle">{html.escape(meta.get("subtitle", ""))}</div>'
             f'<div class="meta">{meta_rows}</div>{notice}</section>')
    css = CSS % {"short": meta.get("short", "").replace('"', "'"),
                 "chapter_break": "page" if meta.get("chapter_break", "yes") != "no" else "auto"}
    return (f'<!doctype html><html lang="th"><head><meta charset="utf-8"><title>{title}</title>'
            f"<style>{_font_css()}{css}</style></head><body>{cover}{_toc(entries, pages)}"
            f"<main>{converted}</main></body></html>")


def marker_pages(pdf: bytes) -> dict[int, int]:
    """Page number (1-based) of each heading marker found in a first-pass PDF."""
    import io
    from pypdf import PdfReader
    pages: dict[int, int] = {}
    for number, page in enumerate(PdfReader(io.BytesIO(pdf)).pages, start=1):
        for found in MARKER_FIND.findall((page.extract_text() or "").replace(" ", "")):
            pages.setdefault(int(found), number)
    return pages


def print_pdf(page, document: str) -> bytes:
    page.set_content(document, wait_until="load")
    page.evaluate("document.fonts.ready.then(() => true)")
    page.wait_for_timeout(300)
    return page.pdf(prefer_css_page_size=True, print_background=True)


def build(names: list[str], html_out: Path | None = None) -> list[tuple[Path, int, int]]:
    from playwright.sync_api import sync_playwright
    from pypdf import PdfReader
    import io
    results = []
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        page = browser.new_page()
        for name in names:
            source = SOURCES / f"{name}.md"
            text = source.read_text(encoding="utf-8")
            meta, _ = parse_front_matter(text)
            first = print_pdf(page, render_html(text, source.parent, markers=True))
            pages = marker_pages(first)
            document = render_html(text, source.parent, pages=pages)
            if html_out:
                html_out.mkdir(parents=True, exist_ok=True)
                (html_out / f"{name}.html").write_text(document, encoding="utf-8")
            pdf = print_pdf(page, document)
            target = OUT / meta.get("output", f"{name}.pdf")
            target.write_bytes(pdf)
            count = len(PdfReader(io.BytesIO(pdf)).pages)
            missing = len(re.findall(r"<h[23] ", document)) - len(pages)
            results.append((target, count, len(pdf)))
            print(f"{target.relative_to(ROOT).as_posix()}: {count} pages, {len(pdf) / 1e6:.2f} MB"
                  + (f", {missing} headings without a page number" if missing else ""), flush=True)
        browser.close()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("guides", nargs="*", help=f"any of {', '.join(GUIDES)}; default: all three")
    parser.add_argument("--html-out", type=Path, help="also keep the final HTML pages here (for checking)")
    args = parser.parse_args()
    unknown = sorted(set(args.guides) - set(GUIDES))
    if unknown:
        parser.error(f"unknown guide: {', '.join(unknown)}")
    build(list(args.guides) or list(GUIDES), args.html_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
