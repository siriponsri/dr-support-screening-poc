"""Small deterministic QA checks for release documentation."""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANUAL = ROOT / "docs" / "manual"
OPERATOR = ROOT / "docs" / "operator-manual"
MARKDOWN = [ROOT / "README.md", *ROOT.glob("docs/*.md"), *MANUAL.glob("*.qmd"), *OPERATOR.glob("*.qmd")]
LOCAL_LINK = re.compile(r"!?\[[^\]]*\]\(([^)#]+)(?:#[^)]+)?\)")
FORBIDDEN_MANUAL_TERMS = ("0.6.0", "AI Review", "PRISM evidence", "Confirm every", "README_DRAFT", "TODO", "TBD", "placeholder")


def check_links() -> list[str]:
    errors: list[str] = []
    for source in MARKDOWN:
        if not source.exists():
            continue
        for target in LOCAL_LINK.findall(source.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (source.parent / target).resolve()
            if not resolved.exists():
                errors.append(f"{source.relative_to(ROOT)} -> missing {target}")
    return errors


def check_manual_terms() -> list[str]:
    errors: list[str] = []
    for source in [*MANUAL.glob("*.qmd"), *OPERATOR.glob("*.qmd")]:
        text = source.read_text(encoding="utf-8")
        for term in FORBIDDEN_MANUAL_TERMS:
            if term in text:
                errors.append(f"{source.relative_to(ROOT)} contains stale/manual term {term!r}")
    return errors


def check_figures() -> list[str]:
    errors: list[str] = []
    hashes: dict[str, str] = {}
    for image in sorted((MANUAL / "screenshots").glob("*.png")):
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        if digest in hashes:
            errors.append(f"duplicate manual screenshot: {image.name} == {hashes[digest]}")
        hashes[digest] = image.name
    for source in [*MANUAL.glob("*.qmd"), *OPERATOR.glob("*.qmd")]:
        for target in LOCAL_LINK.findall(source.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (source.parent / target).exists():
                errors.append(f"{source.relative_to(ROOT)} -> missing figure/link {target}")
    return errors


def report_pdfs() -> None:
    pdfinfo = shutil.which("pdfinfo")
    if not pdfinfo:
        return
    for pdf in (ROOT / "docs" / "CLINICIAN_USER_MANUAL.pdf", ROOT / "docs" / "DEPLOYMENT_OPERATIONS_MANUAL.pdf"):
        if pdf.exists():
            result = subprocess.run([pdfinfo, str(pdf)], capture_output=True, text=True, check=True)
            pages = next((line.split(":", 1)[1].strip() for line in result.stdout.splitlines() if line.startswith("Pages:")), "unknown")
            print(f"{pdf.relative_to(ROOT)}: {pages} pages")


def main() -> None:
    errors = [*check_links(), *check_manual_terms(), *check_figures()]
    report_pdfs()
    if errors:
        raise SystemExit("Documentation QA failed:\n- " + "\n- ".join(errors))
    print(f"Documentation QA passed for {len(MARKDOWN)} source files.")


if __name__ == "__main__":
    main()
