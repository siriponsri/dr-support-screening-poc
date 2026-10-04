"""Build reproducible, allowlisted no-code release packages.

The builder never copies local-state, environments, dependency trees, secrets,
databases, model weights, or patient data. It requires an already-built React
frontend for the workstation package.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "local-state" / "release" / "artifacts"
MODEL_IDENTITY = {
    "model_id": "uspec-uwf-grading",
    "artifact": "grading_state.pt",
    "expected_bytes": 1213535294,
    "expected_sha256": "8f07eb11859f638faee368a56c7c532ca946fee320f92f030a0cf25c63b769ac",
    "status": "IDENTITY_ONLY_NOT_ACQUIRED",
    "policy": "Do not download, include, load, or infer with this artifact in the release package.",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tracked(path: str) -> Path:
    result = ROOT / path
    if not result.exists():
        raise SystemExit(f"required release path is missing: {path}")
    return result


def copy_path(source: Path, target: Path) -> None:
    if source.is_dir():
        for item in source.rglob("*"):
            relative = item.relative_to(source)
            archive_path = relative.as_posix()
            if item.is_dir() or forbidden(archive_path):
                continue
            target_file = target / relative
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target_file)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def workstation_allowlist() -> list[str]:
    return [
        "AGENTS.md", "DESIGN.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "README_START_HERE.md",
        "pyproject.toml", "uv.lock", ".env.example", "frontend/package.json", "frontend/package-lock.json",
        "frontend/dist", "dr_support", "web", "scripts/windows/release-common.ps1",
        "scripts/windows/release-first-run.ps1", "scripts/windows/release-start.ps1",
        "scripts/windows/release-stop.ps1", "scripts/windows/release-check-system.ps1",
        "FIRST_RUN.bat", "START_DR_SCREENING.bat", "STOP_DR_SCREENING.bat", "CHECK_SYSTEM.bat",
        "docs/operations/INSTALLATION.md", "docs/operations/CONFIGURATION.md",
        "docs/operations/TROUBLESHOOTING.md", "docs/operations/SECURITY_PRIVACY.md",
        "docs/manuals/clinician", "docs/reference/DATASET_MANIFEST.md",
    ]


def model_api_allowlist() -> list[str]:
    return [
        "AGENTS.md", "DESIGN.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "README_START_HERE.md",
        "pyproject.toml", "uv.lock", ".env.example", "dr_support",
        "scripts/release/model_artifacts.json", "scripts/release/model-api-disabled-check.sh",
        "scripts/release/model-api-start.sh", "scripts/release/model-api-health.sh",
        "scripts/release/model-api-check.sh",
        "scripts/release/model-api-verify.sh",
        "scripts/release/README.md",
        "docs/operations/MODEL_SERVER.md", "docs/operations/DEPLOYMENT.md",
        "docs/operations/SECURITY_PRIVACY.md",
    ]


def forbidden(relative: str) -> bool:
    lower = relative.lower().replace("\\", "/")
    parts = lower.split("/")
    return any(part in {".git", ".venv", "node_modules", "local-state", "__pycache__"} for part in parts) or lower.endswith((".pt", ".pth", ".db", ".sqlite", ".sqlite3", ".log", ".env"))


def package(kind: str, version: str, out: Path, source_commit: str) -> Path:
    staging = out / f"staging-{kind}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    if kind == "workstation" and not (ROOT / "frontend/dist/index.html").is_file():
        raise SystemExit("required release path is missing: frontend/dist/index.html (build the frontend before packaging)")
    source_date = int(os.environ.get("SOURCE_DATE_EPOCH", git("show", "-s", "--format=%ct", source_commit)))
    allowlist = workstation_allowlist() if kind == "workstation" else model_api_allowlist()
    for item in allowlist:
        source = tracked(item)
        target = staging / item
        copy_path(source, target)
    manifest = {
        "package": "DR-Workstation" if kind == "workstation" else "DR-Model-API",
        "version": version,
        "source_commit": source_commit,
        "source_dirty": bool(git("status", "--porcelain")),
        "created_at_utc": datetime.fromtimestamp(source_date, timezone.utc).isoformat(),
        "model_runtime": "disabled" if kind == "model-api" else "remote optional",
        "weights_included": False,
        "local_state_included": False,
        "artifact_allowlist": allowlist,
    }
    if kind == "model-api":
        (staging / "scripts/release/model_artifacts.json").write_text(json.dumps(MODEL_IDENTITY, indent=2) + "\n", encoding="utf-8")
    (staging / "RELEASE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    archive_name = "DR-Screening-Workstation" if kind == "workstation" else "DR-Model-API"
    archive = out / f"{archive_name}-{version}.zip"
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for file in sorted(staging.rglob("*")):
            if file.is_file():
                relative = file.relative_to(staging).as_posix()
                if forbidden(relative):
                    raise SystemExit(f"forbidden release artifact selected: {relative}")
                timestamp = datetime.fromtimestamp(source_date, timezone.utc).replace(tzinfo=None)
                info = zipfile.ZipInfo(relative)
                info.date_time = (
                    max(timestamp.year, 1980), timestamp.month, timestamp.day,
                    timestamp.hour, timestamp.minute, timestamp.second,
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (file.stat().st_mode & 0o777) << 16
                bundle.writestr(info, file.read_bytes())
    shutil.rmtree(staging)
    return archive


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--allow-dirty", action="store_true", help="Allow a local validation build from uncommitted source.")
    args = parser.parse_args()
    version = args.version or f"{datetime.now(timezone.utc):%Y.%m.%d}.g{git('rev-parse', '--short=12', 'HEAD')}"
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    source_commit = git("rev-parse", "HEAD")
    if git("status", "--porcelain") and not args.allow_dirty:
        raise SystemExit("release source is dirty; commit the candidate or pass --allow-dirty for local validation only")
    archives = [package("workstation", version, out, source_commit), package("model-api", version, out, source_commit)]
    sums = [f"{sha256(path)}  {path.name}" for path in archives]
    sums_path = out / "SHA256SUMS.txt"
    sums_path.write_text("\n".join(sums) + "\n", encoding="utf-8")
    print(json.dumps({"version": version, "source_commit": source_commit, "artifacts": [{"name": p.name, "bytes": p.stat().st_size, "sha256": sha256(p)} for p in archives], "sums": str(sums_path)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
