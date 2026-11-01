"""Dataset snapshot export: preview, versioned snapshot folder (optional grade folders) and snapshot
details. Mixed into `dataset.DatasetManifestService`; code moved verbatim from dataset.py."""

from __future__ import annotations

import json
import os
import re
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..presentation import review_evidence_view
from .dataset_common import (
    AI_EVIDENCE_FIELDS,
    COMPLETENESS_FIELDS,
    DR_LABEL_FIELDS,
    LESION_LABEL_FIELDS,
    NEGATIVE_POLICY_VERSION,
    SNAPSHOT_ELIGIBILITY_POLICY_VERSION,
    SNAPSHOT_RECORD_FIELDS,
    SNAPSHOT_SCHEMA_VERSION,
    DatasetManifestError,
    _canonical_json_bytes,
    _csv_bytes,
    _geometry_json,
    _sha256,
    _source_state_receipt,
    _utc_now,
)
from .filesystem_privacy import has_reparse_component
from .grading_folders import POLICY as GRADING_FOLDER_POLICY
from .grading_folders import GradingFolderError, plan_grading_folders


class SnapshotExportMixin:
    """Snapshot export methods of DatasetManifestService."""

    def snapshot_preview(self, *, include_grade_folders: bool = False) -> dict:
        images, annotations, cases, source_state, workspace_id, workspace_name = self._workspace_data_context()
        ai_evidence = self._snapshot_ai_evidence(cases, images)
        result = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "workspace_id": workspace_id,
            "workspace_name": workspace_name,
            "source_state_digest": source_state,
            "case_count": len(images),
            "row_counts": {
                "records.csv": len(images),
                "dr_labels.csv": sum(bool(row.get("dr_grade_training_ready")) for row in images),
                "lesion_labels.csv": sum(bool(item.get("include_in_training")) for item in annotations),
                "review_completeness.csv": len(images) * 2,
                "ai_evidence.csv": len(ai_evidence),
            },
            "source_origin_summary": self._source_summary(images),
            "export_authorization_summary": self._authorization_summary(images),
            "blocked_record_count": sum(
                str(row.get("export_authorization", "")).startswith("BLOCKED_") for row in images
            ),
            "negative_policy_version": NEGATIVE_POLICY_VERSION,
            "can_export": workspace_id is not None
            and not any(str(row.get("export_authorization", "")).startswith("BLOCKED_") for row in images),
        }
        if include_grade_folders:
            try:
                plan = plan_grading_folders(
                    cases, images, dict(self.app.state.images), deepcopy(self.app.state.admissions)
                )
                result["grading_folders"] = plan.summary()
                copied = {item["record_key"] for item in plan.manifest["items"] if item["output_path"]}
                confirmed = {
                    item["record_key"]
                    for item in plan.manifest["items"]
                    if item["confirmed_grade"] is not None
                }
                result["row_counts"]["dr_labels.csv"] = sum(bool(row.get("dr_grade_training_ready"))
                    and _sha256(str(row["image_id"]).encode()) in confirmed for row in images)
                result["row_counts"]["lesion_labels.csv"] = sum(bool(item.get("include_in_training"))
                    and _sha256(str(item["image_id"]).encode()) in copied for item in annotations)
            except GradingFolderError:
                result["grading_folders"] = {
                    "status": "BLOCKED_AUTHORIZATION",
                    "reason": "Matching source identity and existing source authorization are required for local copies.",
                }
                result["can_export"] = False
        return result

    @staticmethod
    def _snapshot_records(images: list[dict]) -> list[dict]:
        return [{field: row.get(field) for field in SNAPSHOT_RECORD_FIELDS} for row in images]

    @staticmethod
    def _snapshot_completeness(images: list[dict]) -> list[dict]:
        rows = []
        for image in images:
            for group in ("CORE", "ADVANCED"):
                prefix = group.lower() + "_completeness_"
                rows.append({
                    "image_id": image.get("image_id"),
                    "group": group,
                    "state": image.get(prefix + "state"),
                    "reviewer": image.get(prefix + "reviewer"),
                    "timestamp": image.get(prefix + "at"),
                    "taxonomy_version": image.get(prefix + "taxonomy_version"),
                    "case_revision": image.get("case_revision"),
                    "annotation_set_hash": image.get("annotation_set_hash"),
                    "negative_training_authorized": False,
                    "negative_eligibility_reason": image.get("negative_eligibility_reason"),
                })
        return rows

    def _snapshot_ai_evidence(self, cases: list[dict], images: list[dict]) -> list[dict]:
        rows = []
        image_by_id = {row["image_id"]: row for row in images}
        for case in cases:
            image_id = str(case.get("image_id"))
            image = image_by_id.get(image_id)
            if image is None:
                continue
            evidence = review_evidence_view(case)
            for item in evidence.get("items", []):
                if item.get("source") != "AI":
                    continue
                rows.append(
                    {
                        "image_id": image_id,
                        "source_sha256": image.get("source_sha256"),
                        "ai_kind": "LESION_SUGGESTION",
                        "annotation_id": item.get("annotation_id"),
                        "model_id": item.get("model_id"),
                        "model_version": item.get("model_version"),
                        "score": item.get("score"),
                        "status": item.get("status"),
                        "geometry_json": _geometry_json(
                            item.get("corrected_rectangle") or item.get("original_rectangle")
                        )
                        if item.get("original_rectangle")
                        else None,
                        "source_detection_id": item.get("annotation_id"),
                        "invocation_id": (case.get("selected_ai_evidence") or {}).get("invocation_id"),
                        "analysis_sha256": evidence.get("analysis_sha256"),
                        "provenance_status": "NON_GOLD_AI_EVIDENCE",
                    }
                )
        return rows

    @staticmethod
    def _verify_snapshot_file_hashes(export_dir: Path, expected: dict[str, str]) -> None:
        for filename, expected_digest in expected.items():
            path = export_dir / filename
            try:
                actual_digest = _sha256(path.read_bytes())
            except OSError as error:
                raise DatasetManifestError("Canonical snapshot file hash verification failed.") from error
            if actual_digest != expected_digest:
                raise DatasetManifestError("Canonical snapshot file hash verification failed.")

    def export_snapshot(self, *, include_grade_folders: bool = False,
                        expected_workspace_id: str | None = None,
                        expected_source_state_digest: str | None = None,
                        expected_grading_plan_sha256: str | None = None) -> dict:
        workspace = self._workspace()
        if workspace is None:
            raise DatasetManifestError("Open an active Workspace before creating a canonical snapshot.")
        folder_plan = None
        store_at_start = self.app.state.store
        output_root = Path(workspace.output_folder)
        if include_grade_folders and (expected_workspace_id != workspace.id
                                      or not expected_source_state_digest or not expected_grading_plan_sha256):
            raise DatasetManifestError("Preview grading folders for the current Workspace before creating a snapshot.")
        with self._read_snapshot_cases() as snapshot_cases:
            cases = (
                list(snapshot_cases)
                if hasattr(self.app.state.store, "repeatable_read_cases")
                else self._merge_case_records(snapshot_cases)
            )
            images, annotations = self._rows(cases)
            source_state = _source_state_receipt(workspace.id, cases)
            blocked = [row for row in images if str(row.get("export_authorization", "")).startswith("BLOCKED_")]
            if blocked:
                raise DatasetManifestError(
                    "Canonical snapshot is blocked because one or more records lack approved engineering export authorization."
                )
            self._assert_local_destination(images, workspace.output_folder)
            if include_grade_folders:
                if self.app.state.store is not store_at_start or self._workspace() is not workspace:
                    raise DatasetManifestError("Workspace changed; refresh the grading-folder preview.")
                try:
                    folder_plan = plan_grading_folders(
                        cases, images, dict(self.app.state.images), deepcopy(self.app.state.admissions)
                    )
                except GradingFolderError as error:
                    raise DatasetManifestError(str(error)) from None
                if (source_state["digest"] != expected_source_state_digest
                        or folder_plan.manifest["plan_sha256"] != expected_grading_plan_sha256):
                    raise DatasetManifestError("Snapshot inputs changed; refresh the grading-folder preview.")
                if not folder_plan.files:
                    raise DatasetManifestError(
                        "No supported, source-verified image can be copied; inspect the preview reasons."
                    )
                if (not output_root.is_absolute() or ".." in output_root.parts
                        or not output_root.is_dir() or has_reparse_component(output_root)):
                    raise DatasetManifestError("A direct existing Workspace output directory is required.")
                input_root = Path(workspace.input_folder).resolve()
                if output_root.resolve().is_relative_to(input_root):
                    raise DatasetManifestError("Grading-folder output must be outside the original input directory.")
                if shutil.disk_usage(output_root).free < folder_plan.manifest["copy_bytes"] + 1024 * 1024:
                    raise DatasetManifestError("Insufficient free space for a new grading-folder snapshot.")
                folder_items = {item["record_key"]: item for item in folder_plan.manifest["items"]}
                for row in images:
                    item = folder_items[_sha256(str(row["image_id"]).encode())]
                    row["dr_grade_training_ready"] = (
                        bool(row.get("dr_grade_training_ready")) and item["confirmed_grade"] is not None
                    )
                    if item["confirmed_grade"] is None:
                        row["grade_eligibility_reason"] = item["reason"]
                    if item["output_path"] is None:
                        row["lesion_training_ready"] = False
                        row["lesion_eligibility_reason"] = item["reason"]
                annotations = [
                    item
                    for item in annotations
                    if folder_items[_sha256(str(item["image_id"]).encode())]["output_path"]
                ]
        snapshot_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
        export_dir = output_root / f"dataset-snapshot-{snapshot_id}"
        completeness = self._snapshot_completeness(images)
        ai_evidence = self._snapshot_ai_evidence(cases, images)
        dr_labels = [
            {
                "image_id": row.get("image_id"),
                "source_sha256": row.get("source_sha256"),
                "dr_grade": row.get("clinician_grade"),
                "grade_provenance": row.get("grade_provenance"),
                "reviewer": row.get("reviewer"),
                "reviewed_at": row.get("reviewed_at"),
                "case_revision": row.get("case_revision"),
                "training_group_key": row.get("training_group_key"),
                "referral_status": row.get("referral_status"),
                "referral_rule_id": row.get("referral_rule_id"),
                "referral_rule_version": row.get("referral_rule_version"),
                "referral_source_grade_revision": row.get("referral_source_grade_revision"),
                "referral_reviewer": row.get("referral_reviewer"),
                "referral_reviewed_at": row.get("referral_reviewed_at"),
                "policy_version": SNAPSHOT_ELIGIBILITY_POLICY_VERSION,
            }
            for row in images
            if row.get("dr_grade_training_ready")
        ]
        row_by_id = {row["image_id"]: row for row in images}
        lesion_labels = []
        for item in annotations:
            if not item.get("include_in_training") or item.get("annotation_source") not in {
                "HUMAN",
                "HUMAN_CORRECTION",
                "CVAT_IMPORTED",
            }:
                continue
            row = row_by_id.get(item.get("image_id"), {})
            lesion_labels.append({
                "annotation_id": item.get("annotation_id"),
                "image_id": item.get("image_id"),
                "source_sha256": row.get("source_sha256"),
                "label": item.get("label"),
                "shape_type": item.get("shape_type"),
                "geometry_json": item.get("geometry_json"),
                "annotation_source": item.get("annotation_source"),
                "reviewer": item.get("reviewer"),
                "reviewed_at": item.get("created_at"),
                "source_detection_id": item.get("source_detection_id"),
                "case_revision": row.get("case_revision"),
                "annotation_set_hash": row.get("annotation_set_hash"),
                "confirmed_annotation_hash": row.get("confirmed_annotation_hash"),
                "policy_version": SNAPSHOT_ELIGIBILITY_POLICY_VERSION,
            })
        files = {
            "records.csv": _csv_bytes(self._snapshot_records(images), SNAPSHOT_RECORD_FIELDS),
            "dr_labels.csv": _csv_bytes(dr_labels, DR_LABEL_FIELDS),
            "lesion_labels.csv": _csv_bytes(lesion_labels, LESION_LABEL_FIELDS),
            "review_completeness.csv": _csv_bytes(completeness, COMPLETENESS_FIELDS),
            "ai_evidence.csv": _csv_bytes(ai_evidence, AI_EVIDENCE_FIELDS),
        }
        from .artifact_roi_assist import export_rows, scope_for_app
        artifact_rows = export_rows(
            cases, images=dict(self.app.state.images), admissions=deepcopy(self.app.state.admissions),
            provider=getattr(self.app.state, "artifact_roi_provider", None),
            scope=scope_for_app(self.app, self.app.state.store),
        )
        if artifact_rows:
            # Optional separate AI-visibility provenance, never lesion_labels or
            # confirmed-negative evidence. Authorized local export is separate
            # from clinical label eligibility and never grants network upload.
            files["artifact_roi_assist.json"] = _canonical_json_bytes({
                "schema": "annotation-artifact-visibility-export.v1",
                "provenance_class": "NON_GOLD_AI_VISIBILITY_ONLY", "cases": artifact_rows,
            })
        if folder_plan is not None:
            files.update(folder_plan.files)
            files["grading_folders/manifest.json"] = _canonical_json_bytes({
                "snapshot_id": snapshot_id, "source_state_digest": source_state["digest"], **folder_plan.manifest,
            })
        file_hashes = {name: _sha256(data) for name, data in files.items()}
        source_origins = self._source_summary(images)
        authorizations = self._authorization_summary(images)
        manifest = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "snapshot_id": snapshot_id,
            "created_at": _utc_now(),
            "workspace_id": workspace.id,
            "workspace_name": workspace.name,
            "application_version": getattr(self.app, "version", None),
            "git_commit": None,
            "eligibility_policy_version": SNAPSHOT_ELIGIBILITY_POLICY_VERSION,
            "taxonomy_versions": {"lesion": "canonical-v1", "completeness": "phase2-core-advanced-v1"},
            "coordinate_system": "original_image_pixels",
            "source_state_digest": source_state,
            "case_count": len(images),
            "files": ["manifest.json", *files.keys(), "receipt.json"],
            "file_sha256": file_hashes,
            "row_counts": {
                "records.csv": len(images),
                "dr_labels.csv": len(dr_labels),
                "lesion_labels.csv": len(lesion_labels),
                "review_completeness.csv": len(completeness),
                "ai_evidence.csv": len(ai_evidence),
            },
            "source_origin_summary": source_origins,
            "export_authorization_summary": authorizations,
            "negative_policy": {
                "version": NEGATIVE_POLICY_VERSION,
                "training_negative_authorized": False,
                "reviewed_none_found_is_completeness_only": True,
            },
            "patient_grouping_policy": "confirmed_resolved_pseudonymous_identity_only; no automatic split",
            "model_evidence_inclusion_policy": "ai_evidence.csv is NON_GOLD and never required to discover human labels",
            "limitations": [
                "Snapshot contains metadata and labels; source images are not copied.",
                "Live PostgreSQL qualification is environment-dependent.",
            ],
            "status": "SUCCESS",
        }
        receipt = {
            "snapshot_id": snapshot_id,
            "workspace_id": workspace.id,
            "created_at": manifest["created_at"],
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "policy_version": SNAPSHOT_ELIGIBILITY_POLICY_VERSION,
            "source_state_digest": source_state,
            "case_revisions": source_state["case_revisions"],
            "file_sha256": file_hashes,
            "row_counts": manifest["row_counts"],
            "source_origin_summary": source_origins,
            "authorization_status": authorizations,
            "status": "SUCCESS",
        }
        if folder_plan is not None:
            details = {**folder_plan.summary(), "manifest": "grading_folders/manifest.json"}
            manifest["grading_folders"] = details
            receipt["grading_folders"] = details
            manifest["grade_label_selection_policy"] = (
                f"{GRADING_FOLDER_POLICY}: current source-bound physician folder organization; TEST_ONLY labels kept separate; training eligibility remains independent"
            )
            manifest["limitations"][0] = (
                "Optional grading_folders copies original bytes; folder membership is not clinical UAT or lesion-training readiness."
            )
            if os.name == "nt" and any(len(str((export_dir / name).absolute())) >= 260 for name in files):
                raise DatasetManifestError("Workspace output path is too long; choose a shorter output directory.")
        created = False
        try:
            export_dir.mkdir(parents=False, exist_ok=False)
            created = True
            for name, data in files.items():
                relative = Path(name)
                target = export_dir / relative
                if (relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name
                        or not target.resolve().is_relative_to(export_dir.resolve())):
                    raise DatasetManifestError("Snapshot output path is invalid.")
                target.parent.mkdir(parents=True, exist_ok=True)
                if has_reparse_component(target.parent):
                    raise DatasetManifestError("Snapshot output contains a redirected directory.")
                with target.open("xb") as output:
                    output.write(data)
            self._verify_snapshot_file_hashes(export_dir, file_hashes)
            (export_dir / "manifest.json").write_bytes(_canonical_json_bytes(manifest))
            # Completion marker is written only after every copied file verifies.
            (export_dir / "receipt.json").write_bytes(_canonical_json_bytes(receipt))
        except Exception:
            if (created and export_dir.exists() and not has_reparse_component(export_dir)
                    and export_dir.resolve().parent == output_root.resolve()):
                shutil.rmtree(export_dir)
            raise
        return {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "snapshot_id": snapshot_id,
            "workspace_id": workspace.id,
            "workspace_name": workspace.name,
            "directory_name": export_dir.name,
            "manifest": manifest,
            "receipt": receipt,
        }

    def snapshot_detail(self, snapshot_id: str) -> dict:
        if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}", snapshot_id):
            raise DatasetManifestError("The requested snapshot identifier is invalid.")
        workspace = self._workspace()
        if workspace is None:
            raise DatasetManifestError("Open an active Workspace before inspecting a snapshot.")
        directory = (Path(workspace.output_folder) / f"dataset-snapshot-{snapshot_id}").resolve()
        root = Path(workspace.output_folder).resolve()
        if not directory.is_relative_to(root):
            raise DatasetManifestError("The requested snapshot is outside the Workspace output folder.")
        manifest_path = directory / "manifest.json"
        receipt_path = directory / "receipt.json"
        if not manifest_path.is_file() or not receipt_path.is_file():
            raise DatasetManifestError("The requested snapshot was not found.")
        try:
            return {
                "manifest": json.loads(manifest_path.read_text(encoding="utf-8")),
                "receipt": json.loads(receipt_path.read_text(encoding="utf-8")),
            }
        except (OSError, ValueError) as error:
            raise DatasetManifestError("The requested snapshot could not be read.") from error
