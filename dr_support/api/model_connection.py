"""Model connection for the review app: the Model API connection routes, model and capability lists, and the
owned-session reachability check.

Installed by `api._factory.create_app`; code moved verbatim from create_app."""

import hmac
import os
import time
from threading import RLock
from types import SimpleNamespace

from fastapi import HTTPException

from dr_support.contracts import ModelConnectionInput, ModelConnectionResponse
from dr_support.providers.remote import RemoteModelProvider, provider_from_descriptor
from dr_support.runtime import runtime_snapshot

from ..phase3_registry import capability_descriptors
from ..services.deployment_profile import DeploymentProfileError, validate_deployment_environment
from ..services.model_gateway import ModelConnection, ModelGatewayProbe, _model_summary, response_payload
from ..services.source_mutation_gate import guard_writes, writer_scope


class OwnedReachability:
    """Live reachability of the owned M1 model route, checked at most once per ``ttl`` seconds.

    The check (health and model list) reuses the session's backend-held token and never
    returns it, never swaps the owned provider or endpoint, never enters a writer scope and
    never loads or runs a model. Any failure, including an unexpected one, means unreachable.
    """

    def __init__(self, check, *, clock=time.monotonic, ttl=5.0):
        self.check, self.clock, self.ttl = check, clock, ttl
        self.lock = RLock()
        self.checked = None
        self.reachable = False

    def __call__(self):
        with self.lock:
            now = self.clock()
            if self.checked is not None and 0 <= now - self.checked < self.ttl:
                return self.reachable
            try:
                live = self.check()
                self.reachable = bool(live.server_reachable and live.connection_verified)
            except Exception:
                self.reachable = False
            self.checked = self.clock()
            return self.reachable


def owned_status_probe(models, reachable):
    """Status for the owned M1 session: identity fixed at start, reachability live."""
    if reachable:
        return ModelGatewayProbe(True, True, True, True, 'CONNECTED',
                                 'Connected to the model server. Each result is checked when it is saved.', models)
    return ModelGatewayProbe(False, True, False, False, 'UNAVAILABLE',
                             'The model server is not reachable right now. Manual review remains available.', models)


def install_model_connection(
    app,
    *,
    deployment,
    qa_fixed_session,
    workspace_authority,
    workspace_prism_provider,
    workspace_global_probe,
    probe_model_connection,
):
    """Choose providers from the connection, add /v1/model-connection, /health, /v1/models and
    /v1/capabilities. Returns the helpers create_app and the inference routes still use."""
    def remote_transport():
        """Use the shared transport hook, preserving injected providers in tests."""

        transport = getattr(app.state, 'model_gateway_transport', None)
        if transport is not None:
            return transport
        for provider in getattr(app.state, 'providers', {}).values():
            if isinstance(provider, RemoteModelProvider):
                return provider._transport
        return None

    def connection_probe(connection: ModelConnection) -> ModelGatewayProbe:
        return probe_model_connection(
            connection.url,
            connection.token,
            transport=remote_transport(),
        )

    def providers_from_probe(
        connection: ModelConnection,
        probe: ModelGatewayProbe,
        *,
        reuse_existing: bool = False,
    ):
        providers = {}
        existing = app.state.providers if reuse_existing else {}
        for advertised in probe.models:
            try:
                provider = existing.get(advertised.get('model_id'))
                if not (
                    isinstance(provider, RemoteModelProvider)
                    and provider.base_url == connection.url
                    and provider._explicit_token == connection.token
                    and provider.task == advertised.get('task')
                ):
                    provider = provider_from_descriptor(
                        advertised,
                        base_url=connection.url,
                        token=connection.token,
                        transport=remote_transport(),
                    )
            except ValueError:
                continue
            providers[provider.model_id] = provider
        return providers

    workspace_global_descriptors = ()
    if workspace_authority is not None:
        workspace_global_descriptors = tuple(
            dict(item) for item in workspace_global_probe.models
            if item.get('task') == 'global' and item.get('model_id') != 'prism-dr-5fold'
        )
        global_providers = providers_from_probe(app.state.model_connection, ModelGatewayProbe(
            *(getattr(workspace_global_probe, key) for key in (
                'server_reachable', 'api_contract_valid', 'connection_verified', 'capabilities_ready',
                'status', 'message')),
            workspace_global_descriptors, workspace_global_probe.descriptor_status,
        ))
        # providers_from_probe skips a malformed descriptor; never continue as
        # a silent PRISM-only session.
        if not {'uspec-uwf-grading', 'retfound-aptos5'} <= set(global_providers):
            raise ValueError('The owned session requires USPEC UWF and RETFound CFP grading providers')
        app.state.providers = {**global_providers, 'prism-dr-5fold': workspace_prism_provider}

    def workspace_cached_probe():
        # Read-only: never a writer scope, so status polling cannot fence or
        # race preview entry, and it still answers while entry is FENCED.
        from ..providers.prism_workspace_remote import WorkspaceRemotePRISM
        try:
            current = validate_deployment_environment()
            connection = app.state.model_connection
            if (current != deployment or app.state.workspace_authority is not workspace_authority
                    or app.state.source_mutation_gate is not workspace_authority.gate
                    or app.state.providers.get('prism-dr-5fold') is not workspace_prism_provider
                    or workspace_prism_provider.authority is not workspace_authority
                    or connection.url != deployment.model_endpoint
                    or connection.token != owned_connection_token):
                raise ValueError()
            descriptor = WorkspaceRemotePRISM.prism_preview_identity(workspace_prism_provider)['descriptor']
            # Same summary shape as ordinary discovery (the response contract
            # forbids the provider descriptor's extra identity fields).
            summary = _model_summary([descriptor], assets_verified=True)
            if not summary:
                raise ValueError()
            descriptor = summary[0]
        except (ValueError, RuntimeError, AttributeError):
            raise HTTPException(
                409, 'The model session changed. Stop and restart with the approved configuration.'
            ) from None
        # Model identity stays the one authenticated at session start; only reachability is
        # rechecked live, so a dropped or restored link shows truthfully.
        return owned_status_probe((*workspace_global_descriptors, descriptor), workspace_reachable())

    # Authenticated control-plane check over the owned route with the backend-held token.
    workspace_reachable = OwnedReachability(
        lambda: probe_model_connection(deployment.model_endpoint, owned_connection_token))

    owned_connection_token = app.state.model_connection.token if workspace_authority is not None else None

    def owned_connection(request: ModelConnectionInput) -> ModelConnection:
        """Allow only a display-name change of the owned session connection.

        URL or token replacement is refused before any probe or state change:
        the owned channel, authority and plans are bound to the configured
        endpoint, so a swap requires stopping and restarting the session.
        """
        try:
            candidate = ModelConnection(request.name, request.url, request.token or owned_connection_token)
        except DeploymentProfileError as exc:
            raise HTTPException(422, str(exc)) from None
        if (candidate.url != deployment.model_endpoint
                or (request.token is not None and not hmac.compare_digest(
                    request.token.encode(), (owned_connection_token or '').encode()))):
            raise HTTPException(
                409,
                'The model connection is fixed for this session. Stop and restart with the approved configuration.',
            )
        return candidate

    @guard_writes(lambda: None if workspace_authority is not None else app.state.source_mutation_gate)
    def refresh_remote_state():
        if workspace_authority is not None:
            return workspace_cached_probe()
        if qa_fixed_session is not None:
            return None
        if not app.state.remote_runtime:
            return None
        connection = getattr(app.state, 'model_connection', None)
        if connection is None:
            return None
        probe = connection_probe(connection)
        app.state.model_connection_probe = probe
        providers = providers_from_probe(connection, probe, reuse_existing=True)
        if providers:
            app.state.providers = providers
        return probe

    def display_provider_metadata(provider, probe: ModelGatewayProbe | None = None):
        if not isinstance(provider, RemoteModelProvider) or probe is None:
            return provider.metadata()
        descriptor = next(
            (item for item in probe.models if item.get('model_id') == provider.model_id),
            None,
        )
        if descriptor is None:
            return {
                'model_id': provider.model_id,
                'task': provider.task,
                'runtime': 'remote',
                'remote_url': provider.base_url,
                'status': (
                    'REMOTE_MODEL_NOT_LISTED'
                    if probe.connection_verified
                    else probe.descriptor_status or probe.status
                ),
                'modalities': [],
                'ready': False,
                'warnings': [probe.message],
            }
        metadata = dict(descriptor)
        metadata['runtime'] = 'remote'
        metadata['remote_url'] = provider.base_url
        metadata['warnings'] = list(dict.fromkeys([
            *(metadata.get('warnings') or []),
            *provider._runtime_warnings(),
        ]))
        if not probe.connection_verified:
            metadata['ready'] = False
            metadata['warnings'].append(
                'Model API health is not verified; manual review remains available.'
            )
        return metadata

    @app.get('/v1/model-connection', response_model=ModelConnectionResponse)
    def model_connection():
        connection = getattr(app.state, 'model_connection', None)
        probe = refresh_remote_state() if connection is not None else None
        return response_payload(connection, probe=probe, managed_by_operator=workspace_authority is not None)

    @app.post('/v1/model-connection/test', response_model=ModelConnectionResponse)
    def test_model_connection(request: ModelConnectionInput):
        if workspace_authority is not None:
            owned_connection(request)
            return response_payload(
                app.state.model_connection, probe=workspace_cached_probe(), managed_by_operator=True
            )
        try:
            connection = ModelConnection(request.name, request.url, request.token)
        except DeploymentProfileError as exc:
            raise HTTPException(422, str(exc)) from None
        probe = connection_probe(connection)
        return response_payload(connection, probe=probe)

    @app.put('/v1/model-connection', response_model=ModelConnectionResponse)
    @guard_writes(lambda: None if workspace_authority is not None else app.state.source_mutation_gate)
    def save_model_connection(request: ModelConnectionInput):
        if workspace_authority is not None:
            with writer_scope(app.state.source_mutation_gate, invalidate=False):
                candidate = owned_connection(request)
                probe = workspace_cached_probe()
                app.state.model_connection = candidate
                return response_payload(candidate, probe=probe, managed_by_operator=True)
        previous = getattr(app.state, 'model_connection', None)
        token = request.token
        if token is None and previous is not None and previous.url == request.url:
            token = previous.token
        try:
            candidate = ModelConnection(request.name, request.url, token)
        except DeploymentProfileError as exc:
            raise HTTPException(422, str(exc)) from None
        probe = connection_probe(candidate)
        if not probe.verified:
            # Do not mutate either the active providers or the saved candidate.
            raise HTTPException(502, probe.message)
        providers = providers_from_probe(candidate, probe)
        if not providers:
            raise HTTPException(502, 'Model API advertised no supported inference capability.')
        app.state.providers = providers
        app.state.model_connection = candidate
        app.state.model_connection_probe = probe
        return response_payload(candidate, probe=probe)

    @app.get('/health')
    def health():
        snap = runtime_snapshot()
        return {
            'status': 'PASS_WITH_WARNINGS',
            'lane': (
                'PRIVATE_AUTHORIZED_RESEARCH_BRIDGE'
                if os.environ.get('DR_SUPPORT_HOSPITAL_SCOPE', '').strip() == 'PRIVATE_PROJECT_EVALUATION'
                and os.environ.get('DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL') == '1'
                else 'PUBLIC_SYNTHETIC_BRIDGE'
            ),
            'warnings': ['Research-only; model readiness is reported separately'],
            'requested_device': snap.requested_device,
            'effective_device': snap.effective_device,
            'cuda_available': snap.cuda_available,
        }

    @app.get('/v1/models')
    def models():
        # The review Worklist page depends on this endpoint returning valid
        # JSON. Each provider is wrapped in its own try/except so a single
        # failure degrades that descriptor instead of crashing the whole
        # response (which would surface as HTTP 500 + text/plain and break the
        # UI's `response.json()` call).
        probe = refresh_remote_state()
        synthetic = [
            {'model_id': name, 'task': task, 'status': 'SYNTHETIC_FIXTURE',
             'modalities': ['CFP'], 'capability_id': f'{name}-fixture',
             'revision': 'synthetic-v1', 'preprocessing': 'synthetic-v1',
             'warnings': ['Not real model inference']}
            for name, task in [('mock-global', 'global'), ('mock-lesion', 'lesion-roi')]
        ]
        remote = []
        for provider in app.state.providers.values():
            try:
                remote.append(display_provider_metadata(provider, probe))
            except Exception as exc:  # pragma: no cover - defensive guard
                # Provider.metadata() must already degrade, but belt-and-
                # suspenders so a regression never produces HTTP 500 here.
                remote.append({
                    'model_id': getattr(provider, 'model_id', 'unknown'),
                    'task': getattr(provider, 'task', 'unknown'),
                    'runtime': 'remote',
                    'status': 'REMOTE_INVALID_SCHEMA',
                    'modalities': [],
                    'warnings': [f'Provider metadata failed: {type(exc).__name__}: {exc}'],
                })
        return capability_descriptors([*synthetic, *remote], include_registry=False)

    @app.get('/v1/capabilities')
    def capabilities():
        """Return the full deterministic capability/readiness view."""

        probe = refresh_remote_state()
        return capability_descriptors([
            *(display_provider_metadata(provider, probe) for provider in app.state.providers.values())
        ])

    return SimpleNamespace(
        remote_transport=remote_transport, connection_probe=connection_probe,
        providers_from_probe=providers_from_probe, refresh_remote_state=refresh_remote_state,
        display_provider_metadata=display_provider_metadata,
    )
