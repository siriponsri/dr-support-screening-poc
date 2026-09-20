"""Additive Bridge v1 contracts for the DR Support Screening POC.

Independent of any frozen scientific protocol. Mirrored by the remote model
API contract (see ``docs/REMOTE_MODEL_API.md``).
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
from .admission import AdmissionMetadata, AdmissionReview
from .resolver import ResolverReview
from .workspaces import (
    DatabasePickerRequest,
    FolderPickerRequest,
    PickerResult,
    WorkspaceInput,
    WorkspaceProfile,
    is_absolute_local_path,
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
]
