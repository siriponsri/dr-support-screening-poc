"""The Thai PDF builder renders Markdown into one self-contained HTML page. Offline; no browser needed."""
import importlib.util
import io
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_pdfs", ROOT / "scripts/docs/build_pdfs.py")
build_pdfs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_pdfs)

SOURCE = """---
title: คู่มือทดสอบ
subtitle: ทดสอบการสร้างเอกสาร
audience: ทีมงาน
version: 0.1
date: 1 พฤศจิกายน 2569
short: คู่มือทดสอบ
---

## บทนำ

ข้อความภาษาไทย

### ขั้นตอน

1. เปิดโปรแกรม
2. กด Sign in

![หน้าลงชื่อเข้าใช้](images/shot.jpg)

!!! warning "ข้อควรระวัง"
    ผล AI เป็นเพียงข้อเสนอ

| ก | ข |
| --- | --- |
| 1 | 2 |

## บทที่สอง

เนื้อหา
"""


@pytest.fixture
def source_dir(tmp_path):
    pytest.importorskip("markdown")
    from PIL import Image
    (tmp_path / "images").mkdir()
    buffer = io.BytesIO()
    Image.new("RGB", (8, 6), "white").save(buffer, format="JPEG")
    (tmp_path / "images" / "shot.jpg").write_bytes(buffer.getvalue())
    return tmp_path


def test_front_matter_is_split_from_the_body():
    meta, body = build_pdfs.parse_front_matter(SOURCE)
    assert meta["title"] == "คู่มือทดสอบ" and meta["short"] == "คู่มือทดสอบ"
    assert body.startswith("## บทนำ")


def test_the_page_has_cover_contents_numbered_chapters_figures_and_callouts(source_dir):
    page = build_pdfs.render_html(SOURCE, source_dir, pages={0: 3, 1: 3, 2: 4})
    assert page.startswith("<!doctype html>") and '<html lang="th">' in page
    assert '<section class="cover">' in page and "<h1>คู่มือทดสอบ</h1>" in page and "1 พฤศจิกายน 2569" in page
    assert '<nav class="toc">' in page and 'href="#sec-1"' in page and '<span class="pg">4</span>' in page
    assert '<h2 id="sec-0">1. บทนำ</h2>' in page and '<h3 id="sec-1">1.1 ขั้นตอน</h3>' in page
    assert '<h2 id="sec-2">2. บทที่สอง</h2>' in page
    assert "<figcaption><b>รูปที่ 1</b> หน้าลงชื่อเข้าใช้</figcaption>" in page
    assert 'src="data:image/jpeg;base64,' in page and "images/shot.jpg" not in page
    assert 'class="admonition warning"' in page and "<table>" in page and "<ol>" in page
    assert "@page" in page and "counter(page)" in page


def test_first_pass_markers_are_hidden_in_headings_and_absent_from_the_final_page(source_dir):
    first = build_pdfs.render_html(SOURCE, source_dir, markers=True)
    assert first.count('<span class="marker">QQH') == 3 and '<span class="pg">00</span>' in first
    final = build_pdfs.render_html(SOURCE, source_dir, pages={0: 3})
    assert 'class="marker"' not in final


def test_the_thai_font_is_embedded_from_the_vendored_assets():
    css = build_pdfs._font_css()
    assert "font-family:'Anuphan'" in css and "data:font/woff2;base64," in css
    assert (build_pdfs.ASSETS / "anuphan-LICENSE.txt").is_file()


def test_an_unsupported_image_type_stops_the_build(tmp_path):
    (tmp_path / "x.gif").write_bytes(b"GIF89a")
    with pytest.raises(ValueError, match="unsupported image type"):
        build_pdfs.data_uri(tmp_path / "x.gif")
