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
