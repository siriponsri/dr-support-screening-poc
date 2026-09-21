"""Dataset manifest preview and export routes."""

from fastapi import HTTPException

from ..services.dataset import DatasetManifestError, DatasetManifestService


def install_dataset_routes(app) -> None:
    service = DatasetManifestService(app)

    @app.get("/v1/dataset/manifest")
    def dataset_manifest():
        try:
            return service.preview()
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
