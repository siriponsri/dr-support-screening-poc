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
FRONTEND_IDENTITY_NAME = "frontend/dist/build-identity.json"
SKIPPED_DIRECTORY_NAMES = {
    ".git", ".venv", "node_modules", "local-state", "__pycache__", ".pytest_cache",
    ".ruff_cache", ".mypy_cache", ".tox", ".nox",
}
FORBIDDEN_SUFFIXES = (
    ".pt", ".pth", ".ckpt", ".safetensors", ".onnx", ".h5", ".hdf5", ".weights",
    ".engine", ".tflite", ".joblib", ".pkl", ".pickle", ".bin", ".keras", ".model",
    ".npy", ".npz", ".msgpack", ".gguf", ".ggml", ".db", ".sqlite", ".sqlite3",
    ".db-wal", ".db-shm", ".sqlite-wal", ".sqlite-shm", ".sqlitedb", ".dump", ".bak",
    ".backup", ".log", ".pyc", ".pyo", ".tmp", ".temp", ".swp", ".swo",
)
FORBIDDEN_SECRET_SUFFIXES = (".pem", ".key", ".crt", ".cer", ".p12", ".pfx", ".jks", ".der")
FORBIDDEN_NAME_PARTS = {
    "credentials", "credential", "secret", "secrets", "token", "tokens", "password", "passwords",
    "passwd", "private-key", "private_key", "apikey", "api-key", "api_key",
}
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


def _git_tracked_files() -> set[str]:
    try:
        raw = subprocess.check_output(
            ["git", "ls-files", "--cached", "-z"], cwd=ROOT, stderr=subprocess.DEVNULL
        )
    except (OSError, subprocess.CalledProcessError):
        return set()
    return {item.decode("utf-8").replace("\\", "/") for item in raw.split(b"\0") if item}


def _root_relative(path: Path) -> str:
    root = ROOT.resolve()
    candidate = path.resolve(strict=False)
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise SystemExit(f"release path escapes repository root: {path}") from exc
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise SystemExit(f"unsafe release path: {path}")
    return relative.as_posix()


def _validate_source_entry(path: Path) -> str:
    """Reject links and paths that could escape the source repository."""

    relative = _root_relative(path)
    root = ROOT.resolve()
    current = root
    for part in Path(relative).parts:
        current /= part
        if current.is_symlink():
            raise SystemExit(f"unsafe symlink in release source: {relative}")
    if path.is_symlink():
        raise SystemExit(f"unsafe symlink in release source: {relative}")
    return relative


def tracked(path: str) -> Path:
    result = ROOT / path
    _validate_source_entry(result)
    if not result.exists():
        raise SystemExit(f"required release path is missing: {path}")
    return result


def copy_path(source: Path, target: Path, tracked_files: set[str] | None = None) -> None:
    tracked_files = _git_tracked_files() if tracked_files is None else tracked_files
    source_relative = _validate_source_entry(source)
    generated_frontend = source_relative == "frontend/dist" or source_relative.startswith("frontend/dist/")

    if source.is_file():
        if forbidden(source_relative):
            raise SystemExit(f"forbidden release artifact selected: {source_relative}")
        if not generated_frontend and source_relative not in tracked_files:
            raise SystemExit(f"required release path is not tracked: {source_relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return

    if not source.is_dir():
        raise SystemExit(f"required release path is not a file or directory: {source_relative}")

    for current, directories, files in os.walk(source, topdown=True, followlinks=False):
        current_path = Path(current)
        directories.sort()
        files.sort()
        retained_directories = []
        for directory in directories:
            directory_path = current_path / directory
            relative = _validate_source_entry(directory_path)
            if directory in SKIPPED_DIRECTORY_NAMES:
                continue
            if forbidden(relative):
                raise SystemExit(f"forbidden release directory selected: {relative}")
            retained_directories.append(directory)
        directories[:] = retained_directories
        for filename in files:
            item = current_path / filename
            relative = _validate_source_entry(item)
            if forbidden(relative):
                raise SystemExit(f"forbidden release artifact selected: {relative}")
            if not generated_frontend and relative not in tracked_files:
                continue
            relative_to_source = item.relative_to(source)
            target_file = target / relative_to_source
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target_file)


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
    name = parts[-1]
    stem = name.rsplit(".", 1)[0] if "." in name else name
    if any(part in SKIPPED_DIRECTORY_NAMES for part in parts):
        return True
    if name == ".env" or name.endswith(".env") or (".env." in name and name != ".env.example"):
        return True
    if lower.endswith(FORBIDDEN_SUFFIXES) or lower.endswith(FORBIDDEN_SECRET_SUFFIXES):
        return True
    return any(part in FORBIDDEN_NAME_PARTS for part in stem.replace(".", "_").replace("-", "_").split("_"))


def frontend_source_digest() -> str:
    frontend = ROOT / "frontend"
    files: list[Path] = []
    required = [frontend / "index.html", frontend / "package.json", frontend / "package-lock.json",
                frontend / "tsconfig.json", frontend / "vite.config.ts"]
    for path in required:
        if not path.is_file():
            raise SystemExit(f"required frontend source is missing: {_root_relative(path)}")
        files.append(path)
    for directory in (frontend / "src", frontend / "public"):
        if directory.exists():
            for path in directory.rglob("*"):
                if path.is_file():
                    _validate_source_entry(path)
                    files.append(path)
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(frontend).as_posix()):
        relative = path.relative_to(frontend).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def verify_frontend_build(source_commit: str) -> dict[str, str]:
    identity_path = ROOT / FRONTEND_IDENTITY_NAME
    if not identity_path.is_file():
        raise SystemExit("prebuilt frontend identity is missing; rebuild frontend/dist before packaging")
    try:
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit("prebuilt frontend identity is invalid") from exc
    expected_digest = frontend_source_digest()
    if (
        identity.get("schema_version") != "frontend-build-identity.v1"
        or identity.get("source_commit") != source_commit
        or identity.get("source_digest") != expected_digest
    ):
        raise SystemExit("prebuilt frontend is stale or was built from a different release candidate")
    return {
        "schema_version": identity["schema_version"],
        "source_commit": identity["source_commit"],
        "source_digest": identity["source_digest"],
    }


def package(kind: str, version: str, out: Path, source_commit: str) -> Path:
    staging = out / f"staging-{kind}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        if kind == "workstation" and not (ROOT / "frontend/dist/index.html").is_file():
            raise SystemExit("required release path is missing: frontend/dist/index.html (build the frontend before packaging)")
        source_date = int(os.environ.get("SOURCE_DATE_EPOCH", git("show", "-s", "--format=%ct", source_commit)))
        allowlist = workstation_allowlist() if kind == "workstation" else model_api_allowlist()
        frontend_identity = verify_frontend_build(source_commit) if kind == "workstation" else None
        tracked_files = _git_tracked_files()
        for item in allowlist:
            source = tracked(item)
            target = staging / item
            copy_path(source, target, tracked_files)
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
        if frontend_identity is not None:
            manifest["frontend_build_identity"] = frontend_identity
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
        return archive
    finally:
        if staging.exists():
            shutil.rmtree(staging)


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
