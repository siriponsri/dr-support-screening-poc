"""Dataset manifest preview and export routes."""

from typing import Literal

from fastapi import HTTPException, Query
from pydantic import Field

from ..contracts._schema import Contract

from ..services.dataset import DatasetManifestError, DatasetManifestService


class GroupedGradeExportRequest(Contract):
    image_format: Literal["PNG", "JPEG"] = "PNG"
    jpeg_quality: int = Field(default=90, ge=1, le=100)


def install_dataset_routes(app) -> None:
    service = DatasetManifestService(app)

    @app.get("/v1/dataset/manifest")
    def dataset_manifest(include_annotations: bool = Query(default=True)):
        try:
            return service.preview(include_annotations=include_annotations)
        except DatasetManifestError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None

    @app.post("/v1/dataset/export")
    def dataset_export():
        try:
            return service.export()
        except DatasetManifestError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None
        except OSError:
            raise HTTPException(status_code=503, detail="The Workspace output folder is not available.") from None

    @app.post("/v1/dataset/export/grouped-by-grade")
    def grouped_grade_export(request: GroupedGradeExportRequest):
        try:
            return service.export_grouped(
                image_format=request.image_format,
                jpeg_quality=request.jpeg_quality,
            )
        except DatasetManifestError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None
        except OSError:
            raise HTTPException(status_code=503, detail="The Workspace output folder is not available.") from None

    @app.get("/v2/workspace-data/records")
    def workspace_data_records(
        page: int = Query(default=1, ge=1),
        limit: int = Query(default=25, ge=1, le=100),
        readiness: str = Query(default="all"),
        review_status: str | None = Query(default=None),
        laterality: str | None = Query(default=None),
        modality: str | None = Query(default=None),
        source_origin: str | None = Query(default=None),
        patient_grouped: bool | None = Query(default=None),
        q: str | None = Query(default=None, max_length=120),
    ):
        try:
            return service.workspace_data_records(
                page=page,
                limit=limit,
                readiness=readiness,
                review_status=review_status,
                laterality=laterality,
                modality=modality,
                source_origin=source_origin,
                patient_grouped=patient_grouped,
                q=q,
            )
        except DatasetManifestError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None

    @app.get("/v2/workspace-data/records/{image_id}")
    def workspace_data_record(image_id: str):
        try:
            return service.workspace_data_detail(image_id)
        except DatasetManifestError as error:
            raise HTTPException(status_code=404, detail=str(error)) from None

    @app.get("/v2/workspace-data/records/{image_id}/processing")
    def workspace_data_processing(image_id: str):
        try:
            return service.workspace_data_processing(image_id)
        except DatasetManifestError as error:
            raise HTTPException(status_code=404, detail=str(error)) from None

    @app.get("/v2/workspace-data/records/{image_id}/explainability")
    def workspace_data_explainability(image_id: str):
        try:
            return service.workspace_data_explainability(image_id)
        except DatasetManifestError as error:
            raise HTTPException(status_code=404, detail=str(error)) from None

    @app.get("/v2/dataset/snapshot/preview")
    def dataset_snapshot_preview():
        try:
            return service.snapshot_preview()
        except DatasetManifestError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None

    @app.post("/v2/dataset/snapshot")
    def dataset_snapshot():
        try:
            return service.export_snapshot()
        except DatasetManifestError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None
        except OSError:
            raise HTTPException(status_code=503, detail="The Workspace output folder is not available.") from None

    @app.get("/v2/dataset/snapshots/{snapshot_id}")
    def dataset_snapshot_detail(snapshot_id: str):
        try:
            return service.snapshot_detail(snapshot_id)
        except DatasetManifestError as error:
            raise HTTPException(status_code=404, detail=str(error)) from None
