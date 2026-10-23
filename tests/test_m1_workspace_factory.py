"""Workspace composition refusals before any store write; no DB, model or inference.

The positive composition path needs an actual approved PostgreSQL workspace and
is qualified separately; these tests only prove fail-closed ordering.
"""
from types import SimpleNamespace

import httpx
import pytest

from dr_support.api import _factory
from dr_support.persistence.entry_fence_plan import EntryFencePlan
from dr_support.providers.prism_remote_bound import ExplicitHttpChannel
from dr_support.providers.prism_workspace_remote import WorkspaceRemotePRISM, WorkspaceStatusReader
from dr_support.services import prism_workspace_authority as core
from dr_support.services.m1_workspace_context import WorkspaceContextError, WorkspaceContextReader
from dr_support.services.model_gateway import ModelGatewayProbe
from dr_support.services.prism_preview import MODEL_ID
from dr_support.services.prism_remote_transport import BASE, PROTOCOL, TRANSPORT


DATABASE = 'dr_support_m1_interactive_test_20261023'
ROLES = EntryFencePlan('dr_support', 'dr_support_entry_guard', 'dr_support_m1_owner_test',
                       'dr_support_m1_runtime_test', 'dr_support_m1_authority_test')
ENDPOINT = 'http://127.0.0.1:47860'
PINS = dict(model_id=MODEL_ID, source_revision='synthetic-reviewed-revision',
            preprocessing='synthetic-reviewed-preprocessing', config_sha256='a' * 64,
            checkpoint_sha256={'Final Models/fold 0/weights/best.pt': 'b' * 64})


def _endpoint(request):
    if request.url.path == BASE + '/capabilities':
        return httpx.Response(200, json=dict(
            transport=TRANSPORT, binding_protocol=PROTOCOL, epoch='synthetic-epoch', pins=PINS,
            workspace_runtime=dict(profile='HOSPITAL_M1', modalities=['CFP', 'UWF'],
                                   authorized_source_origins=['SYNTHETIC'],
                                   native_entry_protocol=PROTOCOL, load_state='LOADED')))
    if request.url.path == BASE + '/readiness':
        return httpx.Response(200, json=dict(state='LOADED', pins=PINS, epoch='synthetic-epoch'))
    pytest.fail('Composition must not perform model work: ' + request.url.path)


def global_probe(verified=True, models=None):
    models = models if models is not None else (
        dict(model_id='retfound-aptos5', task='global', ready=True, modalities=['CFP']),
        dict(model_id='uspec-uwf-grading', task='global', ready=True, modalities=['UWF']))
    return ModelGatewayProbe(True, True, verified, verified, 'CONNECTED' if verified else 'UNAVAILABLE',
                             'synthetic startup discovery', tuple(models))


@pytest.fixture
def owned(tmp_path, monkeypatch):
    # Privacy is mocked for this synthetic fixture only; ACLs are never edited.
    monkeypatch.setattr(core, 'private_hospital_root', lambda *a, **k: True)
    for key, value in dict(DR_SUPPORT_DEPLOYMENT_PROFILE='QA_SERVER', APP_PROFILE='review', MODEL_RUNTIME='remote',
                           REMOTE_MODEL_URL=ENDPOINT, REMOTE_MODEL_TOKEN='SYNTHETIC_CONTROL_ONLY',
                           DR_SUPPORT_CASE_STORE='postgres', DR_SUPPORT_DATABASE_MIGRATION_MODE='verify',
                           DR_SUPPORT_DATABASE_SCHEMA='dr_support',
                           DR_SUPPORT_DATABASE_URL=f'host=127.0.0.1 port=54805 dbname={DATABASE} '
                                                   f'user={ROLES.runtime_role} password=synthetic').items():
        monkeypatch.setenv(key, value)
    channel = ExplicitHttpChannel(ENDPOINT, transport=httpx.MockTransport(_endpoint),
                                  auth_headers=lambda *_: {})
    reader = WorkspaceContextReader(role_config=ROLES, database_name=DATABASE)
    fence = SimpleNamespace(read=lambda: None, acquire=lambda **_: pytest.fail('No entry'),
                            recover=lambda: None)
    authority = core.WorkspaceAuthority(tmp_path / 'authority', context_reader=reader, database_fence=fence,
                                        authenticated_status_reader=WorkspaceStatusReader(channel))
    provider = WorkspaceRemotePRISM(channel, source_authority=authority, expected_pins=PINS)
    provider.negotiate()
    value = SimpleNamespace(authority=authority, provider=provider, reader=reader, built=[], order=[],
                            workspace=SimpleNamespace(id='ws_m1_owned'), probe=global_probe())
    monkeypatch.setattr(_factory, '_build_case_store',
                        lambda *a, **k: value.built.append(a) or pytest.fail('store built'))
    monkeypatch.setattr(reader, 'preflight_runtime_database', lambda _db: value.order.append('preflight'))

    class Catalog:
        def __init__(self, _database):
            pass

        def get(self, workspace_id):
            value.order.append('catalog')
            return value.workspace if workspace_id == value.workspace.id else None
    monkeypatch.setattr(_factory, 'PostgresWorkspaceCatalog', Catalog)

    def probe(url, token):
        value.order.append(('probe', url, token))
        return value.probe
    monkeypatch.setattr(_factory, 'probe_model_connection', probe)
    try:
        yield value
    finally:
        authority.close()


def compose(owned, **overrides):
    options = dict(include_samples=False, include_demo_fixtures=False, case_store_mode='postgres',
                   workspace_id='ws_m1_owned', workspace_authority=owned.authority,
                   workspace_prism_provider=owned.provider)
    options.update(overrides)
    return _factory.create_app(**options)


def test_provider_without_its_exact_authority_is_refused(owned):
    with pytest.raises(ValueError, match='exact owned workspace authority'):
        compose(owned, workspace_authority=None)
    with pytest.raises(ValueError, match='exact owned workspace authority'):
        compose(owned, workspace_prism_provider=None)
    assert owned.built == owned.order == [] and owned.reader._app is None


@pytest.mark.parametrize('variable, value', [
    ('DR_SUPPORT_DEPLOYMENT_PROFILE', ''),
    ('DR_SUPPORT_DATABASE_MIGRATION_MODE', 'apply'),
])
def test_owned_session_requires_qa_profile_and_migration_verify(owned, monkeypatch, variable, value):
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValueError, match='explicit QA profile'):
        compose(owned)
    assert owned.built == owned.order == [] and owned.reader._app is None


def test_owned_session_requires_explicit_workspace_and_excludes_isolated_qa(owned):
    with pytest.raises(ValueError, match='explicit QA profile'):
        compose(owned, workspace_id=None)
    with pytest.raises(ValueError, match='own writer gate'):
        compose(owned, qa_batch_profile=object())
    assert owned.built == owned.order == []


def test_model_channel_must_match_configured_endpoint(owned, monkeypatch):
    monkeypatch.setenv('REMOTE_MODEL_URL', 'http://127.0.0.1:47861')
    with pytest.raises(ValueError, match='configured loopback endpoint'):
        compose(owned)
    assert owned.built == owned.order == []


def test_runtime_principal_preflight_precedes_catalog_probe_and_store(owned, monkeypatch):
    def preflight(database):
        owned.order.append(database.settings.schema)
        raise WorkspaceContextError('M1_CONTEXT_AUTHENTICATED_RUNTIME_PRINCIPAL_REQUIRED')
    monkeypatch.setattr(owned.reader, 'preflight_runtime_database', preflight)
    with pytest.raises(WorkspaceContextError, match='RUNTIME_PRINCIPAL_REQUIRED'):
        compose(owned)
    assert owned.order == ['dr_support'] and owned.built == [] and owned.reader._app is None


def test_unknown_workspace_is_refused_instead_of_created(owned):
    with pytest.raises(ValueError, match='existing PostgreSQL workspace profile'):
        compose(owned, workspace_id='ws_m1_typo')
    assert owned.order == ['preflight', 'catalog'] and owned.built == []


@pytest.mark.parametrize('probe', [
    'unverified', 'no_uspec', 'no_retfound', 'retfound_not_ready', 'uspec_wrong_modality',
])
def test_uspec_and_retfound_grading_must_be_ready_so_session_is_never_prism_only(owned, probe):
    retfound = dict(model_id='retfound-aptos5', task='global', ready=True, modalities=['CFP'])
    uspec = dict(model_id='uspec-uwf-grading', task='global', ready=True, modalities=['UWF'])
    owned.probe = {
        'unverified': global_probe(False),
        'no_uspec': global_probe(models=[retfound]),
        'no_retfound': global_probe(models=[uspec]),
        'retfound_not_ready': global_probe(models=[{**retfound, 'ready': False}, uspec]),
        'uspec_wrong_modality': global_probe(models=[retfound, {**uspec, 'modalities': ['CFP']}]),
    }[probe]
    with pytest.raises(ValueError, match='ready USPEC UWF and RETFound CFP'):
        compose(owned)
    assert owned.order == ['preflight', 'catalog', ('probe', ENDPOINT, 'SYNTHETIC_CONTROL_ONLY')]
    assert owned.built == [] and owned.reader._app is None


def test_startup_discovery_uses_only_the_owned_endpoint_and_token(owned):
    with pytest.raises(pytest.fail.Exception, match='store built'):
        compose(owned)
    assert owned.order == ['preflight', 'catalog', ('probe', ENDPOINT, 'SYNTHETIC_CONTROL_ONLY')]


def test_busy_or_already_bound_authority_is_refused_before_any_work(owned):
    with owned.authority.gate.writer():
        with pytest.raises(core.TransportError, match='FENCED_BUSY_OR_POISONED'):
            compose(owned)
    owned.reader._app = object()
    with pytest.raises(ValueError, match='already bound'):
        compose(owned)
    assert owned.built == [] and owned.order == []
