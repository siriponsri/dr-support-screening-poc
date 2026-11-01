"""Review workflow routes: CVAT send/sync, case export and manual CVAT import.

Installed by `workflow.install_workflow`; code moved verbatim from workflow.py."""

from typing import Literal

from fastapi import HTTPException

from ..cvat import OnlineError
from ..presentation import annotation_set_hash
from ..services.source_mutation_gate import guard_writes
from ..sync import Sync, digest
from ..workflow import ManualImport


def install_cvat_routes(app, ctx):
    """CVAT send/sync, case export and manual CVAT import."""
    mutation_gate = ctx.mutation_gate
    current_store = ctx.current_store
    get_image = ctx.get_image
    detail = ctx.detail

    @app.post('/v1/cases/{image_id}/cvat/{action}')
    @guard_writes(mutation_gate)
    def cvat(image_id: str, action: Literal['send', 'sync']):
        image = get_image(image_id)
        store = current_store()
        sync = Sync(store, app.state.remote)
        try:
            return sync.send(image) if action == 'send' else sync.pull(image)
        except OnlineError as error:
            raise HTTPException(503, str(error)) from None
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @app.get('/v1/cases/{image_id}/export')
    def export(image_id: str):
        return detail(image_id)

    @app.post('/v1/cases/{image_id}/manual-sync')
    @guard_writes(mutation_gate)
    def manual(image_id: str, request: ManualImport):
        from ..contracts import LABELS
        from ..cvat import reviewed_shapes
        image = get_image(image_id)
        if request.image_sha256 != image.sha256 or set(request.label_ids) != set(LABELS.values()):
            raise HTTPException(422, 'Image hash and exact four-label mapping required')
        if len(set(request.label_ids.values())) != 4:
            raise HTTPException(422, 'Label IDs must be unique')
        if request.annotations.get('tracks') or request.annotations.get('tags'):
            raise HTTPException(422, 'Only single-image shapes supported by manual sync')
        try:
            shapes = reviewed_shapes(request.annotations, request.label_ids, *image.size)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        store = current_store()
        with store.lock:
            case = store.get(image_id)
            if case['revision'] != request.revision:
                raise HTTPException(409, 'Case changed; reload')
            fingerprint = digest(request.annotations)
            if case.get('annotation_source_hash') != fingerprint:
                case['annotation_source_hash'] = fingerprint
                case['annotations'] = shapes
                case['annotation_raw'] = request.annotations
                case['annotation_hash'] = annotation_set_hash(case)
                if case.get('confirmed_annotation_hash') != case['annotation_hash']:
                    case['lesion_review_state'] = 'IMPORTED_REQUIRES_REVIEW'
                case['revision'] += 1
                case['events'].append({'action': 'MANUAL_SYNC', 'warning': 'Remote project/author not verified',
                                       'annotation_source_hash': fingerprint,
                                       'annotation_hash': case['annotation_hash']})
                store.put(case)
            return detail(image_id)
