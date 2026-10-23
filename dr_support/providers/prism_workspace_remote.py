"""Explicit, unregistered workspace PRISM transport; no model or factory load."""
from copy import deepcopy
import re

import httpx

from .prism_remote_bound import ExplicitHttpChannel, RemoteBoundTransportCandidate
from ..services.loaded_attestation import require_loaded_identity
from ..services.prism_remote_transport import BASE, PROTOCOL, TRANSPORT, TransportError, canonical
from ..services.prism_workspace_authority import STATUS_KEYS, WorkspaceAuthority
from ..services.source_policy import HOSPITAL_ORIGIN, PUBLIC_ORIGINS


_PIN_KEYS = {'model_id', 'source_revision', 'preprocessing', 'config_sha256', 'checkpoint_sha256'}
_RUNTIME_KEYS = {'profile', 'modalities', 'authorized_source_origins', 'native_entry_protocol', 'load_state'}
_ORIGINS = PUBLIC_ORIGINS | {HOSPITAL_ORIGIN}


def _require(condition, code):
    if not condition:
        raise TransportError(code, 503)


def _identifier(value):
    return type(value) is str and re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}', value) is not None


def _digest(value):
    return type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def _checkpoint_name(value):
    # Identity metadata only. Spaces/slashes in reviewed asset names are not
    # filesystem instructions and must never be resolved, opened or normalized.
    return type(value) is str and 0 < len(value) <= 512 and value.isprintable()


def _pins(value):
    _require(type(value) is dict and set(value) == _PIN_KEYS and value['model_id'] == 'prism-dr-5fold'
             and _identifier(value['source_revision']) and type(value['preprocessing']) is str
             and 0 < len(value['preprocessing']) <= 1000 and _digest(value['config_sha256'])
             and type(value['checkpoint_sha256']) is dict and 0 < len(value['checkpoint_sha256']) <= 64
             and all(_checkpoint_name(name) and _digest(digest) for name, digest in value['checkpoint_sha256'].items()),
             'M1_REVIEWED_MODEL_PINS_REQUIRED')
    return deepcopy(value)


def _channel(value):
    _require(type(value) is ExplicitHttpChannel and type(value.client) is httpx.Client
             and value.client.trust_env is False and value.client.follow_redirects is False
             and value.client.timeout == httpx.Timeout(2)
             and callable(value.auth_headers), 'M1_EXACT_EXPLICIT_CHANNEL_REQUIRED')


def _channel_binding(value):
    _channel(value)
    return value.client, value.client._transport, value.auth_headers, str(value.client.base_url)


def _same_channel(value, bound):
    current = _channel_binding(value)
    return all(a is b for a, b in zip(current[:3], bound[:3], strict=True)) and current[3] == bound[3]


class WorkspaceStatusReader:
    """Authenticated old-job read port, independent of provider negotiation.

    Its response is proof input, never permission to release an authority lease.
    The authority and database fence independently validate native/terminal proof.
    """

    def __init__(self, channel):
        _channel(channel)
        self.channel = self._channel = channel
        self._bound = _channel_binding(channel)

    def __call__(self, binding):
        _channel(self.channel)
        _require(self.channel is self._channel and _same_channel(self.channel, self._bound),
                 'M1_STATUS_CHANNEL_CHANGED')
        _require(type(binding) is dict and all(key in binding for key in STATUS_KEYS),
                 'M1_OLD_JOB_SCOPE_REQUIRED')
        frozen = deepcopy(binding)
        _require(all(_identifier(frozen[key]) for key in ('epoch', 'job_id', 'ticket_id', 'challenge_id'))
                 and _digest(frozen['plan_sha256']), 'M1_OLD_JOB_SCOPE_REQUIRED')
        _pins(frozen['pins'])
        # The durable old epoch is mandatory. Never substitute a newly
        # negotiated worker epoch while reconciling an old uncertain job.
        status = self.channel.request('GET', BASE + '/jobs/' + frozen['job_id'], epoch=frozen['epoch'])
        _require(type(status) is dict and all(status.get(key) == frozen[key] for key in STATUS_KEYS)
                 and type(status.get('forward_started')) is bool and type(status.get('terminal')) is bool,
                 'M1_AUTHENTICATED_OLD_JOB_SCOPE_CHANGED')
        return deepcopy(status)


class WorkspaceRemotePRISM(RemoteBoundTransportCandidate):
    """Explicit M1 provider only; construction does not register or qualify it."""

    prism_preview_protocol = PROTOCOL
    task = 'lesion-roi'
    model_id = 'prism-dr-5fold'
    capability_id = 'core_lesion_localization'

    def __init__(self, channel, *, source_authority, expected_pins, wait_seconds=120, poll_seconds=.01):
        _channel(channel)
        _require(type(source_authority) is WorkspaceAuthority, 'M1_EXACT_WORKSPACE_AUTHORITY_REQUIRED')
        self._expected_pins = _pins(expected_pins)
        self._bound_channel, self._bound_authority = channel, source_authority
        self._channel_binding = _channel_binding(channel)
        self._negotiated = None
        super().__init__(channel, source_authority=source_authority,
                         wait_seconds=wait_seconds, poll_seconds=poll_seconds)

    def _ports(self):
        _channel(self.channel)
        _require(self.channel is self._bound_channel and self.authority is self._bound_authority
                 and type(self.authority) is WorkspaceAuthority
                 and _same_channel(self.channel, self._channel_binding), 'M1_WORKSPACE_PORT_BINDING_CHANGED')

    def _evidence(self):
        self._ports()
        _require(self._negotiated is not None and type(self.capabilities) is dict
                 and canonical(self.capabilities) == self._negotiated,
                 'M1_AUTHENTICATED_LOADED_NEGOTIATION_REQUIRED')

    def negotiate(self):
        self.capabilities = self._negotiated = None
        self.tickets.clear()
        self._ports()
        value = self.channel.request('GET', BASE + '/capabilities')
        _require(type(value) is dict and value.get('transport') == TRANSPORT
                 and value.get('binding_protocol') == PROTOCOL and _identifier(value.get('epoch')),
                 'M1_WORKSPACE_PROTOCOL_REQUIRED')
        _require(_pins(value.get('pins')) == self._expected_pins, 'M1_EXPECTED_MODEL_PINS_MISMATCH')
        runtime = value.get('workspace_runtime')
        _require(type(runtime) is dict and set(runtime) == _RUNTIME_KEYS
                 and runtime['profile'] == 'HOSPITAL_M1' and runtime['modalities'] == ['CFP', 'UWF']
                 and runtime['native_entry_protocol'] == PROTOCOL and runtime['load_state'] == 'LOADED'
                 and type(runtime['authorized_source_origins']) is list
                 and 0 < len(runtime['authorized_source_origins']) <= 32
                 and all(_identifier(origin) for origin in runtime['authorized_source_origins'])
                 and len(set(runtime['authorized_source_origins'])) == len(runtime['authorized_source_origins']),
                 'M1_LOADED_WORKSPACE_CAPABILITY_REQUIRED')
        loaded = self.channel.request('GET', BASE + '/readiness', epoch=value['epoch'])
        require_loaded_identity(loaded, expected_pins=self._expected_pins, expected_epoch=value['epoch'])
        self._ports()
        self.capabilities = deepcopy(value)
        self._negotiated = canonical(value)

    def _descriptor(self, ready):
        pins = self._expected_pins
        origins = [] if not ready else sorted(set(self.capabilities['workspace_runtime']['authorized_source_origins']) & _ORIGINS)
        return dict(model_id=self.model_id, provider_id='prism', capability_id=self.capability_id,
                    task=self.task, revision=pins['source_revision'], model_version=pins['source_revision'],
                    status='LOADED' if ready else 'AUTHENTICATED_LOAD_REQUIRED', ready=ready,
                    modalities=['CFP', 'UWF'], supported_modalities=['CFP', 'UWF'], trained_domain='CFP',
                    uwf_use='EXPERIMENTAL', domain_status='EXPERIMENTAL_UWF_ADAPTATION',
                    clinical_validation_status='NOT_VALIDATED_FOR_UWF', rights_status='ACADEMIC_USE_REVIEW_REQUIRED',
                    release_status='RESEARCH_ONLY', production_authorization='NOT_AUTHORIZED',
                    runtime_qualification='AUTHENTICATED_LOADED_IDENTITY' if ready else 'PENDING_LOAD',
                    inference_validation='NOT_RUN', preprocessing=pins['preprocessing'],
                    preprocessing_version='prism-legacy-cfp-plus-experimental-uwf-v1',
                    authorized_source_origins=origins,
                    warnings=['Research model; no scientific performance claim.',
                              'PRISM is trained on CFP; UWF use is EXPERIMENTAL and NOT_VALIDATED_FOR_UWF.',
                              'Released weights require academic/research rights review.',
                              'Raw detections are retained; empty detections do not prove absence of lesions.'])

    def metadata(self):
        if self._negotiated is None:
            self._ports()
            return self._descriptor(False)
        self._evidence()
        return self._descriptor(True)

    def prism_preview_identity(self):
        self._evidence()
        return dict(model_version=self._expected_pins['source_revision'], model_pins=deepcopy(self._expected_pins),
                    descriptor=self._descriptor(True))

    def _request(self, method, path, value=None, *, authority=False):
        self._evidence()
        return super()._request(method, path, value, authority=authority)

    def prepare_prism_preview_candidate(self, wire):
        self._evidence()
        return super().prepare_prism_preview_candidate(wire)

    def refresh_prism_preview_candidate(self, wire):
        self._evidence()
        return super().refresh_prism_preview_candidate(wire)

    def infer_bound_prism(self, request, wire, *, mask_png, binding, plan_sha256, before_forward=None):
        self._evidence()
        WorkspaceAuthority.authorize_execute(self.authority, binding, plan_sha256)
        return super().infer_bound_prism(request, wire, mask_png=mask_png, binding=binding,
                                        plan_sha256=plan_sha256, before_forward=before_forward)
