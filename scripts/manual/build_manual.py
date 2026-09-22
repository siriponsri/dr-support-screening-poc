"""Build the clinician manual PDF from the final manual and screenshots."""
from __future__ import annotations

import html
import os
import re
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'docs' / 'CLINICIAN_USER_MANUAL.md'
OUTPUT = ROOT / 'docs' / 'CLINICIAN_USER_MANUAL.pdf'
TEMP = ROOT / 'local-state' / 'manual'


def markdown_to_html(source: str) -> str:
    blocks: list[str] = []
    paragraph: list[str] = []
    in_list = False

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            text = ' '.join(paragraph)
            text = re.sub(r'`([^`]+)`', r'<code>\1</code>', html.escape(text))
            blocks.append(f'<p>{text}</p>')
            paragraph = []

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            blocks.append('</ul>')
            in_list = False

    for raw in source.splitlines():
        line = raw.strip()
        if not line:
            flush_paragraph()
            close_list()
            continue
        image = re.match(r'!\[([^]]*)\]\(([^)]+)\)', line)
        if image:
            flush_paragraph()
            close_list()
            alt, path = image.groups()
            image_path = (SOURCE.parent / path).resolve()
            image_uri = image_path.as_uri() if image_path.exists() else path
            blocks.append(f'<figure><img src="{html.escape(image_uri)}" alt="{html.escape(alt)}"><figcaption>{html.escape(alt)}</figcaption></figure>')
            continue
        if line.startswith('# '):
            flush_paragraph(); close_list(); blocks.append(f'<h1>{html.escape(line[2:])}</h1>'); continue
        if line.startswith('## '):
            flush_paragraph(); close_list(); blocks.append(f'<h2>{html.escape(line[3:])}</h2>'); continue
        if line.startswith('- '):
            flush_paragraph()
            if not in_list:
                blocks.append('<ul>'); in_list = True
            item = re.sub(r'`([^`]+)`', r'<code>\1</code>', html.escape(line[2:]))
            blocks.append(f'<li>{item}</li>')
            continue
        if line.startswith('```'):
            flush_paragraph(); close_list(); continue
        if line.startswith('![', 0):
            continue
        paragraph.append(line)

    flush_paragraph()
    close_list()
    return '\n'.join(blocks)


def main() -> None:
    TEMP.mkdir(parents=True, exist_ok=True)
    body = markdown_to_html(SOURCE.read_text(encoding='utf-8'))
    document = f'''<!doctype html><html><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 16mm 15mm 18mm; }}
body {{ font-family: Arial, sans-serif; color: #202428; font-size: 10.5pt; line-height: 1.45; }}
h1 {{ font-family: Georgia, serif; color: #164d38; font-size: 25pt; margin: 0 0 10pt; }}
h2 {{ color: #164d38; font-size: 15pt; margin: 18pt 0 6pt; border-bottom: 1px solid #d6dbd6; padding-bottom: 3pt; }}
p {{ margin: 0 0 8pt; }} ul {{ margin-top: 4pt; }} li {{ margin-bottom: 3pt; }}
code {{ font-family: Consolas, monospace; background: #f0f3ef; padding: 1px 3px; }}
figure {{ margin: 10pt 0 14pt; break-inside: avoid; }} figure img {{ display: block; width: 100%; max-height: 175mm; object-fit: contain; border: 1px solid #d6dbd6; }} figcaption {{ color: #66706b; font-size: 8.5pt; margin-top: 3pt; }}
img[src*="screenshots"] {{ max-height: 140mm; }}
</style></head><body>{body}</body></html>'''
    source_html = TEMP / 'manual.html'
    source_html.write_text(document, encoding='utf-8')
    executable = os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE')
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=executable)
        page = browser.new_page()
        page.goto(source_html.as_uri(), wait_until='load')
        page.pdf(path=str(OUTPUT), format='A4', print_background=True)
        browser.close()
    print(f'Wrote {OUTPUT}')


if __name__ == '__main__':
    main()
