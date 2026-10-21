"""App-owned SYNTHETIC fixed QA session; injected MockTransport only, no runtime registration."""
from contextvars import ContextVar
from copy import deepcopy
import os
import re
from threading import RLock
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.responses import JSONResponse, Response
from starlette.datastructures import State

from .prism_preview import MODEL_ID, canonical, sha
from ..images import BridgeImage
from .prism_remote_transport import TransportError
from .prism_synthetic_fence import SyntheticFenceAuthority
from .source_identity import source_identity_reason
from ..providers.prism_remote_bound import FixedSessionRemoteProvider

_RESULT_WRITE = ContextVar('fixed_qa_result_write', default=None)


class FrozenDict(dict):
    def denied(self, *args, **kwargs):
        raise TransportError('FIXED_QA_MUTATION_REJECTED')
    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = denied
    def __deepcopy__(self, memo):
        return {key: deepcopy(value, memo) for key, value in self.items()}


def freeze(value):
    if isinstance(value, dict): return FrozenDict({key: freeze(item) for key, item in value.items()})
    if isinstance(value, list): return FrozenList(freeze(item) for item in value)
    return value


class FrozenList(list):
    def denied(self, *args, **kwargs): raise TransportError('FIXED_QA_MUTATION_REJECTED')
    __setitem__ = __delitem__ = append = extend = insert = pop = remove = clear = reverse = sort = __iadd__ = __imul__ = denied
    def __deepcopy__(self, memo): return [deepcopy(value, memo) for value in self]


class FixedStore:
    def __init__(self, store, session):
        self._store, self._session, self.lock = store, session, store.lock
    def get(self, key): return deepcopy(self._store.get(key))
    def all_cases(self): return deepcopy(self._store.all_cases())
    def put(self, case):
        if _RESULT_WRITE.get() is not self._session:
            raise TransportError('FIXED_QA_CASE_WRITE_REJECTED')
        return self._store.put(case)


class FixedState(State):
    PROTECTED = {'store', 'images', 'admissions', 'providers', 'workspace_id', 'workspace_manager',
                 'derivatives', 'qa_fixed_session', 'model_connection', 'remote_runtime'}
    def __setattr__(self, name, value):
        if name in self.PROTECTED and name in self._state:
            raise TransportError('FIXED_QA_STATE_REPLACEMENT_REJECTED')
        super().__setattr__(name, value)
    def __delattr__(self, name):
        if name in self.PROTECTED:
            raise TransportError('FIXED_QA_STATE_REPLACEMENT_REJECTED')
        super().__delattr__(name)


class FixedQASession(SyntheticFenceAuthority):
    """The journal is reused, but authority reads the actual pinned app objects.

    All app-visible source/review writers are excluded for the session. Only the
    existing inference saver receives a scoped write permit. No lock is carried
    across ASGI/thread boundaries. Private injected backing references/external
    writers are outside session ownership; detected drift fails closed.
    """
    def __init__(self, directory, *, store, images, admissions, provider, authenticated_status_reader):
        if any(os.environ.get(name, '1') != '1' for name in ('WORKERS', 'WEB_CONCURRENCY')):
            raise TransportError('FIXED_QA_SINGLE_WORKER_REQUIRED', 503)
        if not isinstance(provider, FixedSessionRemoteProvider):
            raise TransportError('MOCK_ONLY_FIXED_QA_PROVIDER_REQUIRED', 503)
        if not images or set(images) != set(admissions) or len(images) > 16:
            raise TransportError('BOUNDED_SELECTED_RECORDS_REQUIRED')
        if any(not isinstance(image, BridgeImage) or image.source_origin != 'SYNTHETIC'
               or image.source_type != 'SYNTHETIC' or image.modality != 'UWF' for image in images.values()):
            raise TransportError('FIXED_QA_SYNTHETIC_ONLY')
        for key, image in images.items():
            case, admission = store.get(key), admissions[key]
            if (admission.get('source_origin') != 'SYNTHETIC' or admission.get('retinal_modality') != 'UWF'
                    or source_identity_reason(case, image, admission)
                    or any(value is not None and value != image.sha256 for value in
                           (case.get('image_sha256'), case.get('source_sha256')))):
                raise TransportError('FIXED_QA_RECORDED_SOURCE_INVALID')
        super().__init__(directory, authenticated_status_reader=authenticated_status_reader)
        self.raw_store = store
        self.store = FixedStore(store, self)
        self.images, self.admissions = dict(images), deepcopy(admissions)
        self.provider = provider
        provider.authority = self
        self.app = None
        self.cached_cases = {}
        self.expected_cases = {}
        self.session_lock = RLock()

    def bind(self, app):
        self._open()
        self.app = app
        self.workspace = app.state.workspace_id
        self.manager = app.state.workspace_manager
        self.derivatives = app.state.derivatives
        self.pins = deepcopy(self.provider.prism_preview_identity()['model_pins'])

    def validate(self, *, case_state=True):
        self._open()
        if any(os.environ.get(name, '1') != '1' for name in ('WORKERS', 'WEB_CONCURRENCY')):
            raise TransportError('FIXED_QA_SINGLE_WORKER_REQUIRED', 503)
        state = self.app.state
        if (state.store is not self.store or state.workspace_id != self.workspace
                or state.workspace_manager is not self.manager or state.derivatives is not self.derivatives
                or state.providers.get(MODEL_ID) is not self.provider
                or self.provider.prism_preview_identity()['model_pins'] != self.pins
                or dict(state.images) != self.images or deepcopy(state.admissions) != self.admissions):
            raise TransportError('FIXED_QA_IDENTITY_CHANGED')
        if case_state and any(self.store.get(key) != value for key, value in self.expected_cases.items()):
            raise TransportError('FIXED_QA_CASE_CONTEXT_CHANGED')

    def preview_capability(self, descriptor, modality):
        if modality != 'UWF' or descriptor.get('model_id') != MODEL_ID:
            raise TransportError('FIXED_QA_MODALITY_OR_MODEL_CHANGED')
        # Only the explicit MockTransport injection uses this offline capability;
        # do not promote its descriptor to clinically ready or register it.
        return SimpleNamespace(capability_id='core_lesion_localization')

    def authorize_prepare(self, wire, recorded_context=None, *, original_bytes=None):
        with self.session_lock:
            self.validate()
            if recorded_context is not None:
                if wire.image_id not in self.images or original_bytes != self.images[wire.image_id].data:
                    raise TransportError('FIXED_QA_SOURCE_NOT_PINNED')
                self.stage(recorded_context, original_bytes=original_bytes, wire_bytes=bytes(wire.data))
            super().authorize_prepare(wire)

    def register_preview_plan(self, snapshot, binding, plan_hash):
        with self.session_lock:
            self.validate()
            if (snapshot.runtime.store is not self.store or snapshot.runtime.provider is not self.provider
                    or sha(canonical(binding)) != plan_hash):
                raise TransportError('FIXED_QA_PLAN_HANDLE_MISMATCH')
            self.register_plan(binding)

    def acquire(self, binding, challenge, before_forward):
        with self.session_lock:
            self.validate()
            def revalidate():
                before_forward()
                self.validate()
            return super().acquire(binding, challenge, revalidate)

    def commit_result(self, save):
        with self.session_lock:
            self.validate(case_state=False)
            changed = any(self.store.get(key) != value for key, value in self.expected_cases.items())
            permit = _RESULT_WRITE.set(self)
            try: result = save()
            finally: _RESULT_WRITE.reset(permit)
            for key in self.images:
                self.expected_cases[key] = self.store.get(key)
                self.cached_cases[key].update(deepcopy(self.expected_cases[key]))
            if changed:
                # Preserve original-store stale-result saving, then close this
                # session after an out-of-band backing-store mutation.
                self.poisoned = True
            return result

    def seal(self):
        app = self.app
        # Use actual workflow projection/hydration once, before sealing.
        detail = next(route.endpoint for route in app.routes if getattr(route, 'path', '') == '/v1/cases/{image_id}')
        permit = _RESULT_WRITE.set(self)
        try: self.cached_cases = {key: deepcopy(detail(key)) for key in self.images}
        finally: _RESULT_WRITE.reset(permit)
        self.expected_cases = {key: self.store.get(key) for key in self.images}
        self.admissions = deepcopy(app.state.admissions)
        app.state.images = FrozenDict(self.images)
        app.state.admissions = freeze(self.admissions)
        app.state.providers = FrozenDict({MODEL_ID: self.provider})
        app.state = FixedState(app.state._state)
        session = self

        @app.middleware('http')
        async def fixed_session_routes(request, call_next):
            path, method = request.url.path, request.method
            try: session.validate()
            except (TransportError, ValueError):
                return JSONResponse({'detail': 'Fixed QA session closed or changed'}, status_code=423)
            if method == 'GET':
                if path == '/v1/cases': return JSONResponse(list(deepcopy(session.cached_cases).values()))
                match = re.fullmatch(r'/v1/cases/([A-Za-z0-9_-]+)', path)
                if match and match[1] in session.cached_cases: return JSONResponse(deepcopy(session.cached_cases[match[1]]))
                if path in {'/v1/models', '/v1/capabilities'}:
                    return JSONResponse([session.provider.prism_preview_identity()['descriptor']])
                if path in {'/v1/workspaces', '/v1/workspaces/active'}:
                    return JSONResponse({'workspace': None, 'workspaces': [], 'active_workspace': None,
                                         'database': {'status': 'QA_INJECTED'}, 'warnings': ['Fixed synthetic QA session']})
                if path == '/health': return JSONResponse({'status': 'FIXED_SYNTHETIC_QA_OFFLINE_ONLY'})
                match = re.fullmatch(r'/v1/images/([A-Za-z0-9_-]+)(?:/display)?', path)
                if match and match[1] in session.images:
                    image = session.images[match[1]]
                    return Response(image.data, media_type=image.media_type)
                if re.fullmatch(r'/v1/cases/[A-Za-z0-9_-]+/prism-input-preview/[a-f0-9]+/assets/(original|input|overlay)', path):
                    return await call_next(request)
                if path.startswith('/app/') or path.startswith('/ui/'): return await call_next(request)
            if method == 'POST' and re.fullmatch(r'/v1/cases/[A-Za-z0-9_-]+/prism-input-preview(?:/[a-f0-9]+/infer)?', path):
                return await call_next(request)
            return JSONResponse({'detail': 'Mutation or uncached read excluded by fixed QA session'}, status_code=423)


def require_fixed_session_read_only(app):
    if getattr(app.state, 'qa_fixed_session', None) is not None:
        raise HTTPException(423, 'Fixed QA session excludes this mutation')
