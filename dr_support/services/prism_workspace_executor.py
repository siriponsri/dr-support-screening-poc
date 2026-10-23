"""Unregistered ordinary-workspace executor; no startup or model work on import."""
from __future__ import annotations

from copy import deepcopy
import math
import time
from types import SimpleNamespace

from dr_support.images import BridgeImage
from dr_support.providers.prism_bound import BoundLocalPRISM
from .prism_owned_runtime import LoadedPrismExecutor, child_application, torch_load_forward_guard
from .prism_remote_transport import TransportError, canonical, sha
from .source_policy import HOSPITAL_ORIGIN, PUBLIC_ORIGINS, source_allowed_for_model


class LoadedWorkspacePrismExecutor(LoadedPrismExecutor):
    """Reuse exact native PRISM and its loaded lifecycle, without demo authority."""

    def __init__(self, provider, *, expected_pins, clock=time.monotonic,
                 load_guard=torch_load_forward_guard):
        self._workspace_provider = provider
        self._check_workspace_provider()
        super().__init__(provider, expected_pins=expected_pins, clock=clock, load_guard=load_guard)

    def _check_workspace_provider(self):
        provider = self._workspace_provider
        if (type(provider) is not BoundLocalPRISM
                or getattr(provider, '_batch_authorization', None) is not None
                or getattr(self, 'provider', provider) is not provider
                or getattr(self, 'demo_authorization', None) is not None):
            raise TransportError('EXACT_ORDINARY_BOUND_PROVIDER_REQUIRED', 503)

    def identity(self):
        self._check_workspace_provider()
        return super().identity()

    @staticmethod
    def _image(data, modality, origin, image_id='prepared_wire'):
        if not isinstance(data, bytes):
            raise TransportError('IMMUTABLE_WIRE_REQUIRED')
        if modality not in {'CFP', 'UWF'}:
            raise TransportError('WORKSPACE_FUNDUS_MODALITY_REQUIRED')
        media = 'image/png' if data.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg'
        return BridgeImage(image_id, data, origin, 'internal-workspace-prism-wire',
                           modality=modality, media_type=media, source_origin=origin)

    def prepare(self, wire, modality):
        self.loaded_identity()
        # No binding/origin exists at this CPU-only port. UNKNOWN is deliberately
        # ineligible for inference; it cannot confer source permission.
        candidate = self.provider.prepare_prism_preview_candidate(self._image(wire, modality, 'UNKNOWN'))
        self.loaded_identity()
        return candidate

    def _execution_image(self, wire, mask, binding, plan_hash):
        if (not isinstance(wire, bytes) or (mask is not None and not isinstance(mask, bytes))
                or sha(wire) != binding['wire_sha256'] or sha(canonical(binding)) != plan_hash):
            raise TransportError('OWNED_FROZEN_BINDING_CHANGED')
        admission = binding['admission']
        origin, modality = admission['source_origin'], binding['modality']
        if (not source_allowed_for_model(origin, model_api=True)
                or admission.get('modality_admission') != 'FUNDUS_ACCEPTED'
                or admission.get('quality_state') != 'GRADABLE'
                or admission.get('retinal_modality') != modality):
            raise TransportError('WORKSPACE_SOURCE_OR_ADMISSION_BLOCKED')
        return self._image(wire, modality, origin, binding['image_id'])

    def execute(self, wire, mask, binding, plan_hash, *, before_forward, on_roi_entry):
        try:
            self.loaded_identity()
            # Own a stable copy while the exact native API validates recorded
            # hashes, pins, candidate, mask, transform and replay consumption.
            binding = deepcopy(binding)
            image = self._execution_image(wire, mask, binding, plan_hash)
            if not callable(before_forward) or not callable(on_roi_entry):
                raise TransportError('FATAL_REMOTE_ENTRY_PORT_REQUIRED')
            request = SimpleNamespace(image_id=image.image_id, model_id=binding['model_id'],
                                      modality=image.modality)

            def gate():
                self.loaded_identity()
                self._execution_image(wire, mask, binding, plan_hash)
                before_forward()

            def entry():
                self.loaded_identity()
                self._execution_image(wire, mask, binding, plan_hash)
                on_roi_entry()  # Native provider keeps this outside ROI fallback.

            return self.provider.infer_remote_fenced_prism(
                request, image, mask_png=mask, binding=binding, plan_sha256=plan_hash,
                before_forward=gate, on_native_roi_entry=entry)
        except BaseException:
            self.poisoned = True
            raise


def workspace_child_application(executor, *, token, issue_id, epoch, clock=time.monotonic,
                                load_seconds=60, job_seconds=120):
    """Bootstrap existing authenticated child; never create a listener/process."""
    if type(executor) is not LoadedWorkspacePrismExecutor:
        raise TransportError('EXACT_WORKSPACE_EXECUTOR_REQUIRED', 503)
    executor._check_workspace_provider()
    if (type(job_seconds) not in {int, float} or not math.isfinite(job_seconds)
            or not 0 < job_seconds <= 120):
        raise ValueError('BOUNDED_WORKSPACE_JOB_REQUIRED')
    app, host = child_application(executor, token=token, issue_id=issue_id, epoch=epoch,
                                  clock=clock, load_seconds=load_seconds)
    enable = getattr(host, 'enable_workspace_executor', None)
    if not callable(enable):
        raise TransportError('WORKSPACE_HOST_BOOTSTRAP_REQUIRED', 503)
    enable(executor)
    host.allowed_origins = frozenset(origin for origin in PUBLIC_ORIGINS | {HOSPITAL_ORIGIN}
                                     if source_allowed_for_model(origin, model_api=True))
    host.job_seconds = job_seconds
    return app, host
