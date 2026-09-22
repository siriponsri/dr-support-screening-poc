"""Additive provider contracts for Retinal Review Workbench.

Independent of any frozen scientific protocol. Mirrored by the remote model
API contract (see ``docs/MODEL_SERVER.md``).
"""
from ._schema import (
    LABELS,
    Contract,
    GlobalResult,
    InferenceRequest,
    Lesion,
    LesionResult,
    Provenance,
)
from .resolver import ResolverReview
from .workspaces import (
    DatabasePickerRequest,
    FolderPickerRequest,
    PickerResult,
    WorkspaceInput,
    WorkspaceProfile,
    is_absolute_local_path,
)
from .model_gateway import (
    ModelConnectionInput,
    ModelConnectionModel,
    ModelConnectionResponse,
)

__all__ = [
    'LABELS',
    'Contract',
    'GlobalResult',
    'InferenceRequest',
    'Lesion',
    'LesionResult',
    'Provenance',
    'AdmissionMetadata',
    'AdmissionReview',
    'ResolverReview',
    'DatabasePickerRequest',
    'FolderPickerRequest',
    'PickerResult',
    'WorkspaceInput',
    'WorkspaceProfile',
    'is_absolute_local_path',
    'ModelConnectionInput',
    'ModelConnectionModel',
    'ModelConnectionResponse',
]


def __getattr__(name):
    """Load admission contracts lazily so imaging contracts remain acyclic."""
    if name in {'AdmissionMetadata', 'AdmissionReview'}:
        from .admission import AdmissionMetadata, AdmissionReview
        globals().update({
            'AdmissionMetadata': AdmissionMetadata,
            'AdmissionReview': AdmissionReview,
        })
        return globals()[name]
    raise AttributeError(name)
