"""Grouped export: confirmed-grade folders and the separate AI-predicted (unverified) folders.
Mixed into `dataset.DatasetManifestService`; code moved verbatim from dataset.py."""

from __future__ import annotations

import io
import json
from pathlib import Path

from ..imaging import DerivativeError
from .dataset_common import (
    DatasetManifestError,
    _csv_bytes,
    _is_sha256,
    _sha256,
    _utc_now,
    label_class,
)

GROUPED_EXPORT_FIELDS = [
    "image_id", "group", "final_grade", "source_sha256", "source_was_dicom",
    "rendered_derivative_sha256", "export_format", "export_sha256", "output_path", "status",
]


AI_PREDICTED_DIRECTORY = "ai_predicted_unverified"


def _grouped_image_bytes(image, output_format: str, quality: int, derivative_service) -> tuple[bytes, str, bool]:
    from PIL import Image

    source_was_dicom = image.media_type == "application/dicom" or Path(image.filename).suffix.lower() in {
        ".dcm",
        ".dicom",
    }
    derivative = derivative_service.prepare_display(image)
    data = derivative.data
    rendered_sha256 = _sha256(data)
    if output_format == "PNG" and derivative.lineage.format == "PNG":
        return data, rendered_sha256, source_was_dicom
    try:
        with Image.open(io.BytesIO(data)) as decoded:
            decoded.load()
            rgb = decoded.convert("RGB")
            output = io.BytesIO()
            if output_format == "PNG":
                rgb.save(output, format="PNG", optimize=False, compress_level=9)
            else:
                rgb.save(output, format="JPEG", quality=quality, subsampling=0, optimize=False, progressive=False)
            return output.getvalue(), rendered_sha256, source_was_dicom
    except Exception as error:
        raise DatasetManifestError("The admitted image could not be rendered for grouped export.") from error


class GroupedExportMixin:
    """Grouped export method of DatasetManifestService."""

    def export_grouped(self, *, image_format: str = "PNG", jpeg_quality: int = 90, basis: str = "confirmed") -> dict:
        """Copies into grade folders. ``basis="ai_predicted"`` sorts an archive by the AI grade into a separate,
        clearly unverified folder; the clinician-confirmed folders are never mixed with it."""
        if basis not in {"confirmed", "ai_predicted"}:
            raise DatasetManifestError("Choose confirmed or AI-predicted grade folders.")
        ai_basis = basis == "ai_predicted"
        workspace = self._workspace()
        if workspace is None:
            raise DatasetManifestError("Open an active Workspace before exporting reviewed images.")
        if image_format not in {"PNG", "JPEG"}:
            raise DatasetManifestError("Choose PNG or JPEG for grouped image export.")

        directory_name = AI_PREDICTED_DIRECTORY if ai_basis else "grouped_by_grade"
        grouped_root = Path(workspace.output_folder) / directory_name
        manifest_dir = grouped_root / "_manifest"
        manifest_path = manifest_dir / "grouped_export_manifest.json"
        csv_path = manifest_dir / "grouped_images.csv"

        prior_items: list[dict] = []
        if manifest_path.is_file():
            try:
                previous = json.loads(manifest_path.read_text(encoding="utf-8"))
                for entry in previous.get("items", []):
                    relative = Path(entry.get("output_path", ""))
                    candidate = (grouped_root / relative).resolve()
                    if (relative.is_absolute() or ".." in relative.parts
                            or not candidate.is_relative_to(grouped_root.resolve())
                            or not candidate.is_file()):
                        continue
                    if _sha256(candidate.read_bytes()) == entry.get("export_sha256"):
                        prior_items.append(entry)
            except (OSError, ValueError, TypeError, AttributeError):
                prior_items = []

        run_items: list[dict] = []
        copied_count = 0
        identical_count = 0
        skipped_count = 0
        store = self.app.state.store
        with store.lock:
            snapshots = [
                (image_id, *self._case_context(image_id, store))
                for image_id in self._image_ids()
            ]
        grouped_rows = [
            self._rows([case])[0][0]
            for _image_id, case, _image, _admission in snapshots
        ]
        self._assert_export_authorized(grouped_rows)
        self._assert_local_destination(grouped_rows, workspace.output_folder)
        manifest_dir.mkdir(parents=True, exist_ok=True)

        workspace_now = self._workspace()
        for image_id, case, image, admission in snapshots:
            group, grade = _ai_grade_group(case, admission) if ai_basis else _grade_group(case, admission)
            if (
                not ai_basis
                and group.startswith("dr_grade_")
                and label_class(case, admission, workspace_now) == "TEST_ONLY"
            ):
                group, grade = "test_only", None  # DT-06: never a physician grade folder.
            source_sha256 = image.sha256 if image is not None else (admission or {}).get("source_sha256")
            item = {
                "image_id": image_id,
                "group": group,
                "final_grade": grade,
                "source_sha256": source_sha256 if _is_sha256(source_sha256) else None,
                "source_was_dicom": bool(
                    (image and (image.media_type == "application/dicom"
                                or Path(image.filename).suffix.lower() in {".dcm", ".dicom"}))
                    or (admission or {}).get("source_format") == "DICOM"
                    or (admission or {}).get("source_media_type") == "application/dicom"
                ),
                "rendered_derivative_sha256": None,
                "export_format": image_format,
                "export_sha256": None,
                "output_path": None,
                "status": "SKIPPED_SOURCE_UNAVAILABLE",
            }
            if (admission or {}).get("modality_admission") != "FUNDUS_ACCEPTED":
                item["status"] = "SKIPPED_NOT_FUNDUS_ACCEPTED"
                skipped_count += 1
                run_items.append(item)
                continue
            if image is None:
                skipped_count += 1
                run_items.append(item)
                continue

            try:
                image_bytes, rendered_sha256, source_was_dicom = _grouped_image_bytes(
                    image, image_format, jpeg_quality, self.app.state.derivatives
                )
            except DerivativeError as error:
                item["status"] = f"SKIPPED_UNSUPPORTED_{error.status.value}"
                skipped_count += 1
                run_items.append(item)
                continue
            except DatasetManifestError:
                item["status"] = "SKIPPED_DECODE_FAILED"
                skipped_count += 1
                run_items.append(item)
                continue

            export_sha256 = _sha256(image_bytes)
            item["source_was_dicom"] = source_was_dicom
            item["rendered_derivative_sha256"] = rendered_sha256
            item["export_sha256"] = export_sha256
            extension = "png" if image_format == "PNG" else "jpg"
            base = f"case_{source_sha256[:24]}__{group}"
            target_dir = grouped_root / group
            target_dir.mkdir(parents=True, exist_ok=True)
            suffix = 1
            while True:
                name = f"{base}.{extension}" if suffix == 1 else f"{base}__{suffix}.{extension}"
                target = target_dir / name
                try:
                    with target.open("xb") as output:
                        output.write(image_bytes)
                    item["status"] = "COPIED"
                    copied_count += 1
                    break
                except FileExistsError:
                    if _sha256(target.read_bytes()) == export_sha256:
                        item["status"] = "IDENTICAL_EXISTING"
                        identical_count += 1
                        break
                    suffix += 1
            item["output_path"] = target.relative_to(grouped_root).as_posix()
            run_items.append(item)

        merged = {entry["output_path"]: entry for entry in prior_items if entry.get("output_path")}
        skipped = [entry for entry in prior_items if not entry.get("output_path")]
        for item in run_items:
            if item["output_path"]:
                merged[item["output_path"]] = item
            else:
                skipped.append(item)
        items = [*merged.values(), *skipped]
        items.sort(
            key=lambda entry: (
                str(entry.get("group", "")),
                str(entry.get("image_id", "")),
                str(entry.get("output_path", "")),
            )
        )
        csv_bytes = _csv_bytes(items, GROUPED_EXPORT_FIELDS)
        file_hashes = {
            entry["output_path"]: entry["export_sha256"]
            for entry in items if entry.get("output_path") and entry.get("export_sha256")
        }
        manifest = {
            "schema_version": ("s1.grouped-grade-export.ai-predicted-unverified.v1" if ai_basis
                               else "s1.grouped-grade-export.v1"),
            "created_at": _utc_now(),
            "workspace_id": workspace.id,
            "workspace_name": workspace.name,
            "grouping_policy": ("AI-predicted grade only, NOT reviewed by a person; not a clinical grade and not a "
                                "training label; ungradable images are never filed as a grade"
                                if ai_basis else
                                "final clinician grade; unresolved cases are separated without changing source files"),
            "basis": "AI_PREDICTED_UNVERIFIED" if ai_basis else "CLINICIAN_CONFIRMED",
            "source_immutability": "copy_only",
            "format": image_format,
            "jpeg_quality": jpeg_quality if image_format == "JPEG" else None,
            "item_count": len(items),
            "copied_count": copied_count,
            "identical_existing_count": identical_count,
            "skipped_count": skipped_count,
            "items": items,
            "files": {
                "grouped_images.csv": _sha256(csv_bytes),
                "images": file_hashes,
            },
        }
        csv_path.write_bytes(csv_bytes)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return {
            "directory_name": directory_name,
            "image_format": image_format,
            "copied_count": copied_count,
            "identical_existing_count": identical_count,
            "skipped_count": skipped_count,
            "manifest": "_manifest/grouped_export_manifest.json",
        }


# These two helpers read DatasetManifestService and stay in dataset.py. Imported last, after the
# mixin class exists, so either module can be imported first without a circular-import error.
from .dataset import _ai_grade_group, _grade_group  # noqa: E402
