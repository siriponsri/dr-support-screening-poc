"""Explicit mock providers, never a fallback for unavailable real weights."""
from dr_support.contracts import GlobalResult, LesionResult, Lesion, Provenance


def infer_mock(request, image):
    if image.source_type != 'SYNTHETIC':
        raise ValueError('Mock providers accept synthetic fixtures only')
    provenance = Provenance(image_sha256=image.sha256, source_type=image.source_type,
                            preprocessing='synthetic-fixture-v1', source_revision='synthetic-v1')
    common = dict(model_id=request.model_id, model_version='synthetic-v1', modality=request.modality,
                  provenance=provenance, warnings=['SYNTHETIC_FIXTURE_NOT_MODEL_INFERENCE'])
    if request.model_id == 'mock-global':
        return GlobalResult(**common, state='AI_SUGGESTION', grade=2,
                            probabilities=[0.05, 0.1, 0.7, 0.1, 0.05], confidence=0.7)
    return LesionResult(**common, width=image.size[0], height=image.size[1], lesions=[
        Lesion(source_label='MA', canonical_label='MICROANEURYSM', rectangle=(250, 160, 264, 176), score=0.8)])
