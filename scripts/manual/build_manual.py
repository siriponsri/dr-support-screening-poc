"""Render the Quarto clinician manual HTML site and PDF."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANUAL = ROOT / "docs" / "manual"
SITE = ROOT / "dist" / "manual" / "site"
PDF = ROOT / "docs" / "CLINICIAN_USER_MANUAL.pdf"


def quarto_executable() -> str:
    configured = os.environ.get("QUARTO_BIN")
    if configured:
        return configured
    found = shutil.which("quarto")
    if found:
        return found
    candidates = [
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Quarto" / "bin" / "quarto.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Quarto" / "bin" / "quarto.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    raise RuntimeError("Quarto CLI was not found. Install a released Quarto CLI or set QUARTO_BIN.")


def render_quarto() -> None:
    command = [quarto_executable(), "render", str(MANUAL), "--to", "html"]
    subprocess.run(command, cwd=ROOT, check=True)
    if not (SITE / "index.html").exists():
        raise RuntimeError(f"Quarto did not produce {SITE / 'index.html'}")


def render_pdf() -> None:
    """Render the PDF directly through Quarto's configured PDF engine."""
    subprocess.run([quarto_executable(), "render", str(MANUAL), "--to", "pdf"], cwd=ROOT, check=True)
    source = SITE / "Retinal-Review-Workbench.pdf"
    if not source.exists():
        raise RuntimeError(f"Quarto did not produce {source}")
    shutil.copy2(source, PDF)


def main() -> None:
    render_quarto()
    render_pdf()
    print(f"HTML site: {SITE}")
    print(f"PDF: {PDF}")


if __name__ == "__main__":
    main()
