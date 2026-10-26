"""Read-only format check of one finished dataset export folder (AC-09).

  python -m scripts.qa.check_export_folder <dataset-export-folder>

Checks the folder the review app wrote with "Export dataset": exactly
manifest.json, images.csv and annotations.csv; the schema version; the CSV
headers; the file hashes and counts in the manifest; no absolute local paths;
AI rows and TEST_ONLY rows never training-ready. It never writes, moves or
copies anything, and prints counts and check names only, never row contents,
so it can also be run on an approved hospital destination later.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys

from dr_support.services.dataset import ANNOTATION_FIELDS, EXPORT_SCHEMA_VERSION, IMAGE_FIELDS

FILES = {"manifest.json", "images.csv", "annotations.csv"}
ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]|\\\\[^\\\s]+\\|(?:^|[\s\",;=])/(?:home|Users|mnt|var|tmp|srv)/")
MAX_FILE_BYTES = 512 * 1024 * 1024


def _rows(raw: bytes) -> tuple[list[str], list[dict]]:
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""))
    rows = list(reader)
    return list(reader.fieldnames or []), rows


def check(folder: Path) -> dict:
    """Return {status, checks: {name: bool}, counts}; FAIL if any check is False."""
    folder = Path(folder)
    checks: dict[str, bool] = {}
    counts: dict[str, int] = {}
    names = {path.name for path in folder.iterdir()} if folder.is_dir() else set()
    checks["exact_files"] = names == FILES
    if not checks["exact_files"] or any((folder / name).stat().st_size > MAX_FILE_BYTES for name in FILES):
        return {"status": "FAIL", "checks": checks, "counts": counts}
    raw = {name: (folder / name).read_bytes() for name in FILES}
    try:
        manifest = json.loads(raw["manifest.json"])
        image_fields, images = _rows(raw["images.csv"])
        annotation_fields, annotations = _rows(raw["annotations.csv"])
    except (UnicodeDecodeError, ValueError, csv.Error):
        checks["parseable"] = False
        return {"status": "FAIL", "checks": checks, "counts": counts}
    checks["parseable"] = isinstance(manifest, dict)
    if not checks["parseable"]:
        return {"status": "FAIL", "checks": checks, "counts": counts}
    counts.update(images=len(images), annotations=len(annotations))
    digests = {name: hashlib.sha256(raw[name]).hexdigest() for name in ("images.csv", "annotations.csv")}
    checks["schema_version"] = manifest.get("schema_version") == EXPORT_SCHEMA_VERSION
    checks["image_header"] = image_fields == IMAGE_FIELDS
    checks["annotation_header"] = annotation_fields == ANNOTATION_FIELDS
    checks["file_hashes"] = (manifest.get("file_sha256") == digests
                             and manifest.get("images_csv_sha256") == digests["images.csv"]
                             and manifest.get("annotations_csv_sha256") == digests["annotations.csv"])
    checks["file_list"] = manifest.get("files") == ["manifest.json", "images.csv", "annotations.csv"]
    checks["counts_match"] = (manifest.get("image_count") == len(images)
                              and manifest.get("annotation_count") == len(annotations))
    ready = sum(row.get("include_in_training") == "True" for row in images)
    counts["training_ready_images"] = ready
    checks["training_ready_count"] = manifest.get("training_ready_count") == ready
    checks["coordinate_system"] = manifest.get("coordinate_system") == "original_image_pixels"
    checks["ai_rows_not_training_ready"] = all(
        row.get("include_in_training") != "True" for row in annotations if row.get("annotation_source") == "AI")
    test_only = [row for row in images if row.get("label_class") == "TEST_ONLY"]
    counts["test_only_images"] = len(test_only)
    checks["test_only_not_training_ready"] = all(
        row.get("include_in_training") != "True" and row.get("dr_grade_training_ready") != "True"
        and row.get("lesion_training_ready") != "True" for row in test_only)
    checks["label_class_values"] = all(row.get("label_class") in {"TEST_ONLY", "CLINICIAN", ""} for row in images)
    checks["image_ids_unique"] = len({row.get("image_id") for row in images}) == len(images)
    image_ids = {row.get("image_id") for row in images}
    checks["annotations_reference_images"] = all(row.get("image_id") in image_ids for row in annotations)
    checks["no_absolute_paths"] = not any(ABSOLUTE_PATH.search(raw[name].decode("utf-8", "replace")) for name in FILES)
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks, "counts": counts}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python -m scripts.qa.check_export_folder <dataset-export-folder>", file=sys.stderr)
        return 2
    report = check(Path(argv[0]))
    print(json.dumps(report, indent=1, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
