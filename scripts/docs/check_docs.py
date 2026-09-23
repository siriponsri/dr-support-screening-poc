"""Deterministic documentation QA for Retinal Review Workbench.

Run from the repository root:  python scripts/docs/check_docs.py

Checks:
  1. local Markdown/Quarto links and images resolve;
  2. every IMG-SAMP-### ID cited anywhere exists in the requirements register;
  3. presentation reveals match the Thai scripts ([กด Space] per reveal, scene by scene)
     and the product source map lists every scene with the right reveal count;
  4. no stale references to removed build/capture scripts;
  5. published presentations and the clinician guide load nothing from the network;
  6. clinician manuals avoid retired terms; PDF page counts are reported (clinician guide <= 2 pages).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
REGISTER = DOCS / "image-sampling-requirements" / "REQUIREMENTS_TRACEABILITY.md"
DECKS = [
    (DOCS / "demo" / "src" / "RETINAL_REVIEW_DEMO.source.html", DOCS / "demo" / "PRESENTATION_SCRIPT_TH.md",
     DOCS / "demo" / "PRESENTATION_SOURCE_MAP.md"),
    (DOCS / "demo" / "src" / "TECHNICAL_BRIEFING.source.html", DOCS / "demo" / "TECHNICAL_PRESENTATION_SCRIPT_TH.md", None),
]
PUBLISHED_HTML = [DOCS / "demo" / "RETINAL_REVIEW_DEMO.html", DOCS / "demo" / "TECHNICAL_BRIEFING.html",
                  DOCS / "image-selection" / "IMAGE_SELECTION_GUIDE.html"]
STALE = ("scripts/manual/build_manual.py", "scripts/operator_manual/", "capture_manual.py", "capture_server.py",
         "build_demo.py", "crop_figures.py")
RETIRED_MANUAL_TERMS = ("0.6.0", "AI Review", "PRISM evidence", "Confirm every", "README_DRAFT", "TODO", "TBD")
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s#]+)(?:#[^)]*)?\)")
ID = re.compile(r"IMG-SAMP-\d{3}")
SCENE = re.compile(r'<section class="scene"[^>]*data-steps="(\d+)"')


def text_sources() -> list[Path]:
    files = [ROOT / "README.md", ROOT / "AGENTS.md", *DOCS.rglob("*.md"), *DOCS.rglob("*.qmd")]
    return sorted({f for f in files if f.exists() and "node_modules" not in f.parts})


def check_links(files: list[Path]) -> list[str]:
    errors = []
    for source in files:
        text = re.sub(r"```.*?```", "", source.read_text(encoding="utf-8"), flags=re.S)
        for target in LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:")) or target.startswith("@"):
                continue
            if not (source.parent / target).exists():
                errors.append(f"{source.relative_to(ROOT)}: missing link target {target}")
    return errors


def check_ids(files: list[Path]) -> list[str]:
    defined = set(re.findall(r"^\| (IMG-SAMP-\d{3}) \|", REGISTER.read_text(encoding="utf-8"), flags=re.M))
    if not defined:
        return [f"{REGISTER.relative_to(ROOT)}: no requirements found"]
    errors = []
    extra = [DOCS / "demo" / "src" / "RETINAL_REVIEW_DEMO.source.html", DOCS / "demo" / "src" / "TECHNICAL_BRIEFING.source.html",
             DOCS / "image-selection" / "IMAGE_SELECTION_GUIDE.html"]
    for source in [*files, *[e for e in extra if e.exists()]]:
        for ident in sorted(set(ID.findall(source.read_text(encoding="utf-8")))):
            if ident not in defined:
                errors.append(f"{source.relative_to(ROOT)}: unknown requirement {ident}")
    print(f"requirements register: {len(defined)} IMG-SAMP requirements")
    return errors


def script_reveals(script: Path) -> list[int]:
    counts = []
    for block in re.split(r"^## Scene \d+", script.read_text(encoding="utf-8"), flags=re.M)[1:]:
        spoken = re.search(r"### บทพูด(.*?)(?=^### |\Z)", block, flags=re.S | re.M)
        counts.append(spoken.group(1).count("[กด Space]") if spoken else -1)
    return counts


def check_decks() -> list[str]:
    errors = []
    for source, script, source_map in DECKS:
        if not source.exists():
            errors.append(f"missing {source.relative_to(ROOT)}")
            continue
        steps = [int(n) for n in SCENE.findall(source.read_text(encoding="utf-8"))]
        spoken = script_reveals(script) if script.exists() else []
        if len(steps) != len(spoken):
            errors.append(f"{script.name}: {len(spoken)} scenes but {source.name} has {len(steps)}")
        for i, (a, b) in enumerate(zip(steps, spoken), 1):
            if a != b:
                errors.append(f"{script.name} scene {i:02d}: {b} x [กด Space] but {a} reveals in {source.name}")
        if source_map and source_map.exists():
            rows = re.findall(r"^\| (\d{2}) [^|]*\| (\d+) \|", source_map.read_text(encoding="utf-8"), flags=re.M)
            mapped = [int(r[1]) for r in rows]
            if mapped != steps:
                errors.append(f"{source_map.name}: reveal counts {mapped} do not match {steps}")
        print(f"{source.name}: {len(steps)} scenes, {sum(steps)} reveals; script synchronised: "
              f"{'yes' if steps == spoken else 'no'}")
    return errors


def check_stale(files: list[Path]) -> list[str]:
    errors = []
    for source in files:
        text = source.read_text(encoding="utf-8")
        for term in STALE:
            if term in text and "removed" not in text[max(0, text.find(term) - 200):text.find(term) + 200]:
                errors.append(f"{source.relative_to(ROOT)}: stale reference {term}")
    return errors


def check_offline() -> list[str]:
    errors = []
    for page in PUBLISHED_HTML:
        if not page.exists():
            errors.append(f"missing published page {page.relative_to(ROOT)}")
            continue
        html = page.read_text(encoding="utf-8")
        if re.search(r'<(script|img|link)[^>]+(src|href)="https?:', html):
            errors.append(f"{page.relative_to(ROOT)}: loads a network resource")
        if re.search(r'<(img)[^>]+src="(?!data:)[^"]+"', html) and "demo/src" not in str(page):
            errors.append(f"{page.relative_to(ROOT)}: image not inlined (rebuild with build_docs.py)")
        if re.search(r"<form|<input|localStorage|sessionStorage", html):
            errors.append(f"{page.relative_to(ROOT)}: contains a form, input, or browser storage")
    return errors


def check_manual_terms() -> list[str]:
    errors = []
    for source in [*(DOCS / "manual").glob("*.qmd"), *(DOCS / "operator-manual").glob("*.qmd")]:
        text = source.read_text(encoding="utf-8")
        errors += [f"{source.relative_to(ROOT)}: retired term {t!r}" for t in RETIRED_MANUAL_TERMS if t in text]
    return errors


def report_pdfs() -> list[str]:
    errors = []
    pdfinfo = shutil.which("pdfinfo")
    for pdf in sorted(DOCS.glob("*.pdf")):
        if not pdfinfo:
            print(f"{pdf.name}: present (pdfinfo not installed)")
            continue
        out = subprocess.run([pdfinfo, str(pdf)], capture_output=True, text=True).stdout
        pages = int(next((line.split(":")[1] for line in out.splitlines() if line.startswith("Pages:")), "0"))
        print(f"{pdf.name}: {pages} pages")
        if pdf.name == "CLINICIAN_IMAGE_SELECTION_GUIDE.pdf" and pages > 2:
            errors.append(f"{pdf.name}: {pages} pages (maximum 2)")
    return errors


def main() -> int:
    files = text_sources()
    errors = [*check_links(files), *check_ids(files), *check_decks(), *check_stale(files), *check_offline(),
              *check_manual_terms(), *report_pdfs()]
    if errors:
        print("Documentation QA failed:\n- " + "\n- ".join(errors))
        return 1
    print(f"Documentation QA passed ({len(files)} Markdown/Quarto sources).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
