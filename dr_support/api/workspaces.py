"""FastAPI routes for the local S2 workspace manager."""

from __future__ import annotations

from fastapi import HTTPException

from ..contracts import DatabasePickerRequest, FolderPickerRequest, PickerResult, WorkspaceInput
from ..services.workspaces import (
    WorkspaceCatalogError,
    WorkspaceDatabaseError,
    WorkspaceManager,
    WorkspaceNotFoundError,
)


def _workspace_error(error: Exception) -> HTTPException:
    if isinstance(error, WorkspaceNotFoundError):
        return HTTPException(status_code=404, detail="Unknown workspace")
    if isinstance(error, WorkspaceDatabaseError):
        return HTTPException(status_code=409, detail=str(error))
    if isinstance(error, WorkspaceCatalogError):
        return HTTPException(status_code=503, detail=str(error))
    return HTTPException(status_code=503, detail="Workspace operation unavailable")


def _json_profile(profile) -> dict:
    return profile.model_dump(mode="json")


def _picker_result(value) -> PickerResult:
    if isinstance(value, PickerResult):
        return value
    try:
        return PickerResult.model_validate(value)
    except Exception:
        return PickerResult(
            status="unavailable",
            code="invalid_picker_result",
            message="The native picker returned an invalid result.",
        )


def install_workspace_routes(app, manager: WorkspaceManager) -> None:
    """Install the frozen workspace API surface on the review app."""

    @app.get("/v1/workspaces")
    def list_workspaces():
        try:
            return manager.list_payload()
        except (WorkspaceCatalogError, WorkspaceDatabaseError) as error:
            raise _workspace_error(error) from None

    @app.get("/v1/workspaces/active")
    def active_workspace():
        return manager.active_payload()

    @app.post("/v1/workspaces")
    def create_workspace(request: WorkspaceInput):
        try:
            profile = manager.create_and_open(request)
        except (WorkspaceCatalogError, WorkspaceDatabaseError, WorkspaceNotFoundError) as error:
            raise _workspace_error(error) from None
        return {"workspace": _json_profile(profile), "active": True, "warnings": list(manager.warnings)}
    @app.post("/v1/workspaces/pickers/folder")
    def pick_folder(request: FolderPickerRequest):
        try:
            result = app.state.workspace_picker.pick_folder(
                purpose=request.purpose,
                initial_path=request.initial_path,
            )
        except Exception as error:  # pragma: no cover - defensive adapter boundary
            result = PickerResult(
                status="unavailable",
                code="native_picker_unavailable",
                message=f"Native folder selection is unavailable: {type(error).__name__}: {error}",
            )
        return _picker_result(result).model_dump(mode="json")

    @app.post("/v1/workspaces/pickers/database")
    def pick_database(request: DatabasePickerRequest):
        try:
            result = app.state.workspace_picker.pick_database(
                mode=request.mode,
                initial_path=request.initial_path,
                suggested_name=request.suggested_name,
            )
        except Exception as error:  # pragma: no cover - defensive adapter boundary
            result = PickerResult(
                status="unavailable",
                code="native_picker_unavailable",
                message=f"Native database selection is unavailable: {type(error).__name__}: {error}",
            )
        return _picker_result(result).model_dump(mode="json")

    @app.put("/v1/workspaces/{workspace_id}")
    def update_workspace(workspace_id: str, request: WorkspaceInput):
        try:
            profile = manager.update_and_open(workspace_id, request)
        except (WorkspaceCatalogError, WorkspaceDatabaseError, WorkspaceNotFoundError) as error:
            raise _workspace_error(error) from None
        return {"workspace": _json_profile(profile), "active": True, "warnings": list(manager.warnings)}

    @app.post("/v1/workspaces/{workspace_id}/open")
    def open_workspace(workspace_id: str):
        try:
            profile = manager.open(workspace_id)
        except (WorkspaceCatalogError, WorkspaceDatabaseError, WorkspaceNotFoundError) as error:
            raise _workspace_error(error) from None
        return {"workspace": _json_profile(profile), "active": True, "warnings": list(manager.warnings)}
