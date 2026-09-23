"""Deterministic documentation QA for the canonical repository layout.

Run from the repository root with ``python scripts/docs/check_docs.py``.
The checker intentionally validates paths and generated-artifact boundaries so
documentation moves cannot silently reintroduce the retired layout.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
REGISTER = DOCS / "clinician" / "sampling" / "REQUIREMENTS_TRACEABILITY.md"
REQUIRED = [
    DOCS / "README.md",
    DOCS / "clinician" / "USER_WORKFLOW.md",
    DOCS / "clinician" / "FEATURE_REFERENCE.md",
    DOCS / "clinician" / "IMAGE_SELECTION_GUIDE.html",
    DOCS / "clinician" / "sampling" / "index.qmd",
    DOCS / "operations" / "INSTALLATION.md",
    DOCS / "operations" / "MODEL_SERVER.md",
    DOCS / "developer" / "FEATURE_IMPLEMENTATION_MAP.md",
    DOCS / "reference" / "DATASET_MANIFEST.md",
    DOCS / "manuals" / "clinician" / "index.qmd",
    DOCS / "manuals" / "operator" / "index.qmd",
    DOCS / "manuals" / "developer" / "index.qmd",
    DOCS / "adr" / "README.md",
    DOCS / "adr" / "architecture" / "README.md",
    DOCS / "presentation" / "hyperframes" / "index.html",
    DOCS / "presentation" / "RETINAL_REVIEW_DEMO.html",
    DOCS / "presentation" / "TECHNICAL_BRIEFING.html",
]
PDF_NAMES = {
    "CLINICIAN_USER_MANUAL.pdf",
    "CLINICIAN_IMAGE_SELECTION_GUIDE.pdf",
    "DEPLOYMENT_OPERATIONS_MANUAL.pdf",
    "DEVELOPER_TECHNICAL_GUIDE.pdf",
    "IMAGE_SAMPLING_REQUIREMENTS.pdf",
}
# Owner-provided source material stays at the repository root and is never a
# published artifact. Keep this allowlist exact so other PDFs cannot drift out
# of docs/pdfs unnoticed.
LOCAL_SOURCE_PDFS = {ROOT / "ICOGuidelinesforDiabeticEyeCare.pdf"}
TEMPORARY = {
    "CLINICIAN_UI_FLOW_REDESIGN_PATCH.md",
    "FULL_HYPERFRAMES_OPHTHALMOLOGIST_PRESENTATION_PATCH.md",
    "PHASE3_SETUP_AND_DOCS_INFORMATION_ARCHITECTURE_PATCH.md",
}
RETIRED_PATHS = (
    "docs/demo",
    "docs\\demo",
    "docs/image-selection",
    "docs\\image-selection",
    "docs/operator-manual",
    "docs\\operator-manual",
    "docs/developer-manual",
    "docs\\developer-manual",
    "docs/manual/",
    "docs\\manual\\",
    "docs/technical/",
)
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s#]+)(?:#[^)]*)?\)")
ID = re.compile(r"IMG-SAMP-\d{3}")


def text_sources() -> list[Path]:
    files = [ROOT / "README.md", ROOT / "AGENTS.md", *DOCS.rglob("*.md"), *DOCS.rglob("*.qmd")]
    return sorted({f for f in files if f.exists() and "node_modules" not in f.parts})


def path_sources() -> list[Path]:
    roots = [
        ROOT / "PRESENT_DEMO.cmd",
        ROOT / "PRESENT_TECHNICAL.cmd",
        ROOT / "SETUP.cmd",
        ROOT / "START.cmd",
        ROOT / "OPEN_APP.cmd",
        ROOT / "STOP.cmd",
        *((ROOT / "scripts").rglob("*.py") if (ROOT / "scripts").exists() else []),
        *((ROOT / "scripts").rglob("*.ps1") if (ROOT / "scripts").exists() else []),
    ]
    checker = Path(__file__).resolve()
    return sorted({f for f in [*text_sources(), *roots] if f.exists() and f.resolve() != checker})


def check_required() -> list[str]:
    return [f"missing canonical document: {path.relative_to(ROOT)}" for path in REQUIRED if not path.exists()]


def check_links(files: list[Path]) -> list[str]:
    errors: list[str] = []
    for source in files:
        text = re.sub(r"```.*?```", "", source.read_text(encoding="utf-8"), flags=re.S)
        for target in LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "@")):
                continue
            path = (source.parent / target).resolve()
            if not path.exists():
                errors.append(f"{source.relative_to(ROOT)}: missing link target {target}")
    return errors


HTML_LINK = re.compile(r"(?:src|href)=\"([^\"]+)\"")


def check_html_links(files: list[Path]) -> list[str]:
    errors: list[str] = []
    for source in files:
        text = source.read_text(encoding="utf-8")
        for target in HTML_LINK.findall(text):
            if target.startswith(("http://", "https://", "data:", "mailto:", "#", "javascript:")):
                continue
            target_path = target.split("#", 1)[0].split("?", 1)[0]
            if not target_path:
                continue
            path = (source.parent / target_path).resolve()
            if not path.exists():
                errors.append(f"{source.relative_to(ROOT)}: missing HTML link target {target}")
    return errors


def check_ids(files: list[Path]) -> list[str]:
    if not REGISTER.exists():
        return [f"missing requirements register: {REGISTER.relative_to(ROOT)}"]
    defined = set(re.findall(r"^\| (IMG-SAMP-\d{3}) \|", REGISTER.read_text(encoding="utf-8"), flags=re.M))
    errors: list[str] = []
    for source in files:
        for ident in sorted(set(ID.findall(source.read_text(encoding="utf-8")))):
            if ident not in defined:
                errors.append(f"{source.relative_to(ROOT)}: unknown requirement {ident}")
    print(f"requirements register: {len(defined)} IMG-SAMP requirements")
    return errors


def check_paths(files: list[Path]) -> list[str]:
    errors: list[str] = []
    for source in files:
        text = source.read_text(encoding="utf-8")
        for retired in RETIRED_PATHS:
            if retired in text:
                errors.append(f"{source.relative_to(ROOT)}: retired path reference {retired}")
    return errors


def check_artifacts() -> list[str]:
    errors: list[str] = []
    all_pdfs = list(ROOT.rglob("*.pdf"))
    for pdf in all_pdfs:
        if pdf in LOCAL_SOURCE_PDFS:
            continue
        if ROOT / "dist" in pdf.parents:
            continue
        if pdf.parent != DOCS / "pdfs":
            errors.append(f"published PDF outside docs/pdfs: {pdf.relative_to(ROOT)}")
    actual = {path.name for path in (DOCS / "pdfs").glob("*.pdf")} if (DOCS / "pdfs").exists() else set()
    for expected in sorted(PDF_NAMES - actual):
        errors.append(f"missing published PDF: docs/pdfs/{expected}")
    unexpected = actual - PDF_NAMES
    errors.extend(f"unexpected published PDF: docs/pdfs/{name}" for name in sorted(unexpected))
    for spec in sorted(TEMPORARY):
        if (ROOT / spec).exists():
            errors.append(f"temporary execution spec remains: {spec}")
    return errors


def check_presentation(path: Path) -> list[str]:
    if not path.exists():
        return [f"missing presentation: {path.relative_to(ROOT)}"]
    html = path.read_text(encoding="utf-8")
    errors: list[str] = []
    if re.search(r'<(script|img|link)[^>]+(?:src|href)="https?:', html):
        errors.append(f"{path.relative_to(ROOT)}: loads a network resource")
    if re.search(r'<img[^>]+src="(?!data:)', html):
        errors.append(f"{path.relative_to(ROOT)}: image is not inlined; rebuild with build_docs.py")
    if "application/hyperframes-slideshow+json" in html:
        match = re.search(
            r'<script[^>]+type="application/hyperframes-slideshow\+json"[^>]*>(.*?)</script>',
            html,
            flags=re.S,
        )
        if not match:
            return [f"{path.relative_to(ROOT)}: missing HyperFrames slideshow manifest"]
        try:
            manifest = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            return [f"{path.relative_to(ROOT)}: invalid HyperFrames manifest: {exc}"]
        scenes = {
            scene_id
            for scene_id in re.findall(r'data-composition-id="([^"]+)"', html)
        }
        refs = [*manifest.get("slides", [])]
        for sequence in manifest.get("slideSequences", []):
            refs.extend(sequence.get("slides", []))
        for ref in refs:
            if ref.get("sceneId") not in scenes:
                errors.append(f"{path.relative_to(ROOT)}: manifest references missing scene {ref.get('sceneId')}")
        if len(manifest.get("slides", [])) < 16:
            errors.append(f"{path.relative_to(ROOT)}: HyperFrames main line has fewer than 16 slides")
    return errors


def check_offline() -> list[str]:
    return [error for page in (DOCS / "presentation").glob("*.html") for error in check_presentation(page)]


def check_hyperframes_source() -> list[str]:
    path = DOCS / "presentation" / "hyperframes" / "index.html"
    if not path.exists():
        return [f"missing HyperFrames source: {path.relative_to(ROOT)}"]
    html = path.read_text(encoding="utf-8")
    errors: list[str] = []
    match = re.search(
        r'<script[^>]+type="application/hyperframes-slideshow\+json"[^>]*>(.*?)</script>',
        html,
        flags=re.S,
    )
    if not match:
        return [f"{path.relative_to(ROOT)}: missing HyperFrames slideshow manifest"]
    try:
        manifest = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        return [f"{path.relative_to(ROOT)}: invalid HyperFrames manifest: {exc}"]
    scenes = set(re.findall(r'data-composition-id="([^"]+)"', html))
    refs = [*manifest.get("slides", [])]
    for sequence in manifest.get("slideSequences", []):
        refs.extend(sequence.get("slides", []))
    for ref in refs:
        if ref.get("sceneId") not in scenes:
            errors.append(f"{path.relative_to(ROOT)}: manifest references missing scene {ref.get('sceneId')}")
    if len(manifest.get("slides", [])) < 19:
        errors.append(f"{path.relative_to(ROOT)}: HyperFrames main line has fewer than 19 scenes")
    sequences = {sequence.get("id"): sequence for sequence in manifest.get("slideSequences", [])}
    if len(sequences.get("clinical-questions", {}).get("slides", [])) < 2:
        errors.append(f"{path.relative_to(ROOT)}: clinical validation branch is incomplete")
    errors.extend(check_html_links([path]))
    return errors


def report_pdfs() -> list[str]:
    pdfinfo = shutil.which("pdfinfo")
    for pdf in sorted((DOCS / "pdfs").glob("*.pdf")):
        if not pdfinfo:
            print(f"{pdf.name}: present (pdfinfo not installed)")
            continue
        result = subprocess.run([pdfinfo, str(pdf)], capture_output=True, text=True, check=False)
        pages = next((line.split(":", 1)[1].strip() for line in result.stdout.splitlines() if line.startswith("Pages:")), "?")
        print(f"{pdf.name}: {pages} pages")
    return []


def main() -> int:
    files = text_sources()
    path_files = path_sources()
    errors = [
        *check_required(),
        *check_links(files),
        *check_html_links(sorted(DOCS.rglob("*.html"))),
        *check_ids(files),
        *check_paths(path_files),
        *check_artifacts(),
        *check_offline(),
        *check_hyperframes_source(),
        *report_pdfs(),
    ]
    if errors:
        print("Documentation QA failed:\n- " + "\n- ".join(errors))
        return 1
    print(f"Documentation QA passed ({len(files)} Markdown/Quarto sources).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
