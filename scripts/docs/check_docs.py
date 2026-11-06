"""Documentation checks for the cut-down layout (1 November 2026).

Run from the repository root with ``python scripts/docs/check_docs.py``.

Checks:
1. every required document exists;
2. relative links in every Markdown file (outside ignored folders) point at existing files;
3. PDFs live only in docs/pdfs and use one of the three Thai guide names; all three must exist
   (REQUIRE_PDFS) and so must their Thai Markdown sources in docs/th.

Rebuild the PDFs with ``python scripts/docs/build_pdfs.py`` (needs Microsoft Edge and Playwright).

Older documents are recoverable from the tag ``archive/docs-before-cut-20261101``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
PDF_DIR = DOCS / "pdfs"

REQUIRED = [
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "DESIGN.md",
    "HANDOFF.md",
    "GOAL.md",
    "README_START_HERE.md",
    "THIRD_PARTY_NOTICES.md",
    "LICENSE",
    "docs/README.md",
    "docs/ARCHITECTURE.md",
    "docs/developer/CONFIGURATION.md",
    "docs/developer/DR_TRAIN_ACCESS.md",
    "docs/developer/MODEL_SERVER_OPERATIONS.md",
    "docs/developer/SECURITY.md",
    "docs/developer/DATASET_MANIFEST.md",
    "docs/developer/BACKUP_RESTORE.md",
    # Thai sources of the three PDF guides (built by scripts/docs/build_pdfs.py).
    "docs/th/user-manual.md",
    "docs/th/deployment-guide.md",
    "docs/th/test-report.md",
    "docs/th/assets/anuphan.css",
    "docs/th/assets/anuphan-LICENSE.txt",
]

# The three Thai guides.
PDF_NAMES = {
    "DEPLOYMENT_GUIDE_TH.pdf",
    "TEST_REPORT_TH.pdf",
    "USER_MANUAL_TH.pdf",
}
REQUIRE_PDFS = True

# Folders that are never part of the published documentation.
IGNORED_DIRS = {".git", ".archives", "local-state", "node_modules", "dist", ".venv", "__pycache__"}

LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s#]+)(?:#[^)]*)?\)")
CODE_BLOCK = re.compile(r"```.*?```", flags=re.S)


def walk(pattern: str) -> list[Path]:
    """Files matching ``pattern`` under the repository, skipping ignored folders."""
    return sorted(
        path for path in ROOT.rglob(pattern)
        if path.is_file() and not IGNORED_DIRS.intersection(path.relative_to(ROOT).parts)
    )


def check_required() -> list[str]:
    return [f"missing required document: {name}" for name in REQUIRED if not (ROOT / name).exists()]


def check_links(files: list[Path]) -> list[str]:
    errors: list[str] = []
    for source in files:
        text = CODE_BLOCK.sub("", source.read_text(encoding="utf-8"))
        for target in LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "@")):
                continue
            if not (source.parent / target).resolve().exists():
                errors.append(f"{source.relative_to(ROOT).as_posix()}: missing link target {target}")
    return errors


def check_pdfs() -> list[str]:
    errors: list[str] = []
    for pdf in walk("*.pdf"):
        name = pdf.relative_to(ROOT).as_posix()
        if pdf.parent != PDF_DIR:
            errors.append(f"PDF outside docs/pdfs: {name}")
        elif pdf.name not in PDF_NAMES:
            errors.append(f"unexpected PDF (allowed: {', '.join(sorted(PDF_NAMES))}): {name}")
    present = {pdf.name for pdf in PDF_DIR.glob("*.pdf")} if PDF_DIR.exists() else set()
    for missing in sorted(PDF_NAMES - present):
        if REQUIRE_PDFS:
            errors.append(f"missing PDF: docs/pdfs/{missing}")
        else:
            print(f"not yet built (allowed for now): docs/pdfs/{missing}")
    return errors


def main() -> int:
    markdown = walk("*.md")
    errors = [*check_required(), *check_links(markdown), *check_pdfs()]
    if errors:
        print("Documentation QA failed:\n- " + "\n- ".join(errors))
        return 1
    print(f"Documentation QA passed ({len(markdown)} Markdown files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
