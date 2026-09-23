"""Render the Quarto deployment and operations manual."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs" / "operator-manual"
SITE = ROOT / "dist" / "manual" / "operator-site"
PDF = ROOT / "docs" / "DEPLOYMENT_OPERATIONS_MANUAL.pdf"


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
    raise RuntimeError("Quarto CLI was not found. Install Quarto or set QUARTO_BIN.")


def main() -> None:
    quarto = quarto_executable()
    subprocess.run([quarto, "render", str(SOURCE), "--to", "html"], cwd=ROOT, check=True)
    subprocess.run([quarto, "render", str(SOURCE), "--to", "pdf"], cwd=ROOT, check=True)
    rendered = SITE / "Retinal-Review-Workbench.pdf"
    if not rendered.exists():
        raise RuntimeError(f"Quarto did not produce {rendered}")
    shutil.copy2(rendered, PDF)
    print(f"HTML site: {SITE}")
    print(f"PDF: {PDF}")


if __name__ == "__main__":
    main()
