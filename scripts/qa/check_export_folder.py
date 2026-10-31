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

from dr_support.services.dataset import ANNOTATION_FIELDS, EXPORT_SCHEMA_VERSION, IMAGE_FIELDS, TEST_ONLY_MARKER

FILES = {"manifest.json", "images.csv", "annotations.csv"}
# Checked on decoded values (JSON strings and CSV cells), so JSON escaping cannot fake or hide a match.
START = r"(?:^|[\s\"',;=(\[])"
ABSOLUTE_PATH = re.compile(
    r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]"           # C:\ or C:/
    + "|" + START + r"(?:\\\\|//)[^\\/\s]+[\\/]"  # \\server\share or //server/share
    + r"|file:/"                                   # file: URLs
    + r"|(?:^|[\s\"',;=(\[:])~[\\/]"               # ~/ home-relative
    + r"|(?:^|[\s\"',;=(\[:])/[^\s/\\\"',;]"       # /etc, /ผู้ป่วย/... (never the // of scheme://)
)
MAX_FILE_BYTES = 512 * 1024 * 1024


def _strings(value):
    """Every string key and value of decoded JSON."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _rows(raw: bytes) -> tuple[list[str], list[dict], list[list[str]]]:
    """Header, rows as dicts, and every raw row (so surplus or missing cells are visible)."""
    cells = list(csv.reader(io.StringIO(raw.decode("utf-8"), newline="")))
    header = cells[0] if cells else []
    return header, [dict(zip(header, row)) for row in cells[1:]], cells


def check(folder: Path) -> dict:
    """Return {status, checks: {name: bool}, counts}; FAIL if any check is False."""
    folder = Path(folder)
    checks: dict[str, bool] = {}
    counts: dict[str, int] = {}
    try:
        names = {path.name for path in folder.iterdir()} if folder.is_dir() else set()
        checks["exact_files"] = names == FILES
        if not checks["exact_files"] or any((folder / name).stat().st_size > MAX_FILE_BYTES for name in FILES):
            return {"status": "FAIL", "checks": checks, "counts": counts}
        raw = {name: (folder / name).read_bytes() for name in FILES}
    except OSError:
        return {"status": "FAIL", "checks": {"readable": False}, "counts": counts}  # No path is printed.
    try:
        manifest = json.loads(raw["manifest.json"])
        image_fields, images, image_cells = _rows(raw["images.csv"])
        annotation_fields, annotations, annotation_cells = _rows(raw["annotations.csv"])
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
    # Every row has exactly the header's width: a surplus or missing cell is malformed, never ignored.
    checks["row_widths"] = all(len(row) == len(cells[0]) for cells in (image_cells, annotation_cells)
                               for row in cells[1:])
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
    # dataset.label_class gives TEST_ONLY, CLINICIAN or None (an empty cell).
    checks["label_class_values"] = all(row.get("label_class") in {TEST_ONLY_MARKER, "CLINICIAN", ""} for row in images)
    checks["image_ids_unique"] = len({row.get("image_id") for row in images}) == len(images)
    image_ids = {row.get("image_id") for row in images}
    checks["annotations_reference_images"] = all(row.get("image_id") in image_ids for row in annotations)
    values = [*_strings(manifest), *(cell for cells in (image_cells, annotation_cells) for row in cells for cell in row)]
    checks["no_absolute_paths"] = not any(ABSOLUTE_PATH.search(value) for value in values)
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
