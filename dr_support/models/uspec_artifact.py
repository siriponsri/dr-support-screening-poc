"""Read-only identity checks for the external USPEC grading artifact."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Mapping


MODEL_ID = "uspec-uwf-grading"
CAPABILITY_ID = "uspec-uwf-grading"
RESEARCH_MODEL_ID = "NBeye-research/USPEC"
SOURCE_REVISION = "47b5ed3e8837b280bd60c8ff5af77cdb1ac3489e5f5454a522f7ed8314a08493"
PREPROCESSING = "conservative_fov_rim_review_v4_rgb_letterbox1424_7x7_stride200_v1"
REPRESENTATION = "uspec-source-rgb-v1"
TRANSFORM = "source-preserving-rgb-v1"
CHECKPOINT_FILENAME = "grading_state.pt"

_FILE_SHA256 = (
    ("grading_state.pt", "8f07eb11859f638faee368a56c7c532ca946fee320f92f030a0cf25c63b769ac"),
    ("retina_grading_v4.py", "6dad5401d97f17f27251244df15202b6f4666e1cc3f9a9b4a6bf89892fcfdda5"),
    ("uspec_adapter.py", "73a0c1b7a188b216badf261cb5c83c04d045eda65daef7176fe11afec37548df"),
    ("offline_grading.py", "abb6aef21c98324abd56ee6a4f32a16ce4356db9a62fa36f68ea3272dd8690be"),
    ("requirements-local.txt", "abe26d23a8cd4966cafeaa0faa015ca6fdb9c9e3ccdd7c7ad1c38f4e81b76ae1"),
)


@dataclass(frozen=True)
class ArtifactContract:
    filename: str = CHECKPOINT_FILENAME
    size: int = 1_213_535_294
    sha256: str = "8f07eb11859f638faee368a56c7c532ca946fee320f92f030a0cf25c63b769ac"
    manifest_sha256: str = "1c92fe2cb78866a8b63793261f84c8221ee915a86e86f4215dcca05f0a071e77"
    files_sha256: tuple[tuple[str, str], ...] = _FILE_SHA256


EXPECTED = ArtifactContract()
MODEL_VERSION = f"{CHECKPOINT_FILENAME}-sha256:{EXPECTED.sha256}"

_MANIFEST_FIELDS = {
    "model_id": RESEARCH_MODEL_ID,
    "revision": SOURCE_REVISION,
    "encoder_choice": "uspec",
    "source_weight_sha256": SOURCE_REVISION,
    "uspec_production_rights": "UNVERIFIED",
    "model_domain": "UWF",
    "cfp_validation": "NOT_VALIDATED_FOR_CFP",
    "classes": [0, 1, 2, 3, 4],
    "binary_rule": "DR if grade > 0",
    "preprocessing": PREPROCESSING,
    "mask_version": "conservative_fov_rim_review_v4",
    "patch_grid": 7,
    "patch_size": 224,
    "patch_stride": 200,
    "canvas_size": 1424,
    "runtime": {"torch": "2.11.0+cu128", "transformers": "4.57.6"},
}


def _safe_directory(directory: str | Path) -> Path:
    path = Path(directory)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("USPEC model directory must be absolute and traversal-free")
    for parent in [*reversed(path.parents), path]:
        if parent.is_symlink():
            raise ValueError("USPEC model directory cannot contain symlinks")
    if not path.is_dir():
        raise ValueError("USPEC model directory is missing")
    repository_root = Path(__file__).resolve().parents[2]
    if path.resolve().is_relative_to(repository_root):
        raise ValueError("USPEC artifacts must remain outside the repository")
    return path


@contextmanager
def _regular_file(path: Path) -> Iterator[object]:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise RuntimeError("This platform cannot safely open USPEC artifacts")
    descriptor = os.open(path, os.O_RDONLY | nofollow | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("USPEC artifact must be a regular file")
        yield stream


def _hash_stream(stream: object) -> str:
    stream.seek(0)
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
        digest.update(block)
    stream.seek(0)
    return digest.hexdigest()


def verify_stream(stream: object, contract: ArtifactContract = EXPECTED) -> dict[str, object]:
    if os.fstat(stream.fileno()).st_size != contract.size:
        raise ValueError("USPEC checkpoint size mismatch")
    observed = _hash_stream(stream)
    if observed != contract.sha256:
        raise ValueError("USPEC checkpoint SHA-256 mismatch")
    return {
        "filename": contract.filename,
        "bytes": contract.size,
        "sha256": observed,
        "sha256_status": "VERIFIED_FROM_BYTES",
    }


def verify_source_files(
    directory: str | Path,
    expected_files: Mapping[str, str],
) -> dict[str, str]:
    """Verify source files listed by a reviewed manifest, without importing them."""
    root = _safe_directory(directory)
    verified: dict[str, str] = {}
    for filename, expected_sha256 in expected_files.items():
        if Path(filename).name != filename or "\\" in filename:
            raise ValueError("Unsafe USPEC source filename")
        if len(expected_sha256) != 64 or any(char not in "0123456789abcdef" for char in expected_sha256):
            raise ValueError("Invalid expected USPEC source SHA-256")
        with _regular_file(root / filename) as stream:
            observed = _hash_stream(stream)
        if observed != expected_sha256:
            raise ValueError(f"USPEC source SHA-256 mismatch: {filename}")
        verified[filename] = observed
    return verified


@contextmanager
def verified_artifact(
    directory: str | Path,
    contract: ArtifactContract = EXPECTED,
) -> Iterator[tuple[object, dict[str, object]]]:
    """Keep the verified checkpoint inode open through a restricted load."""
    directory = _safe_directory(directory)
    if contract.filename != CHECKPOINT_FILENAME:
        raise ValueError("Unexpected USPEC checkpoint filename")

    with _regular_file(directory / "manifest.json") as manifest_stream:
        if os.fstat(manifest_stream.fileno()).st_size > 65_536:
            raise ValueError("USPEC manifest is too large")
        manifest_bytes = manifest_stream.read()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_sha256 != contract.manifest_sha256:
        raise ValueError("USPEC manifest identity mismatch")

    manifest = json.loads(manifest_bytes)
    if any(manifest.get(key) != value for key, value in _MANIFEST_FIELDS.items()):
        raise ValueError("USPEC model or preprocessing identity mismatch")
    expected_files = dict(contract.files_sha256)
    if manifest.get("files_sha256") != expected_files:
        raise ValueError("USPEC source-file hash manifest mismatch")
    if expected_files.get(contract.filename) != contract.sha256:
        raise ValueError("USPEC checkpoint identity mismatch")
    if any(Path(name).name != name or "\\" in name for name in expected_files):
        raise ValueError("Unsafe USPEC manifest path")

    with _regular_file(directory / contract.filename) as checkpoint_stream:
        observed = verify_stream(checkpoint_stream, contract)
        observed["manifest_sha256"] = manifest_sha256
        yield checkpoint_stream, observed


def verify_directory(directory: str | Path) -> dict[str, object]:
    with verified_artifact(directory) as (_, observed):
        return observed
