"""Qualification controls with synthetic files/ports; not live DB evidence."""
from copy import deepcopy
import json
import os
from types import SimpleNamespace

import pytest

from dr_support.providers.prism_remote_bound import ExplicitHttpChannel, RemoteBoundTransportCandidate
from dr_support.services.prism_preview import canonical
from dr_support.store import new_case
from scripts.qa import qualify_m1_workspace_context as module
from test_m1_workspace_context import rig as _context_rig


@pytest.fixture
def context_rig(tmp_path):
    return _context_rig.__wrapped__(tmp_path)


@pytest.fixture
def scope(tmp_path, monkeypatch):
    base, private = tmp_path / 'artifacts', tmp_path / 'private'
    base.mkdir()
    private.mkdir()
    monkeypatch.setattr(module, 'ARTIFACT_BASE', base)
    monkeypatch.setattr(module, 'PRIVATE_DIRECTORY', private)
    monkeypatch.setattr(module, 'has_reparse_component', lambda _: False)
    monkeypatch.setattr(module, 'private_hospital_root', lambda _: True)
    values = {'DR_SUPPORT_DATABASE_URL': f'host=127.0.0.1 port=54805 dbname={module.DATABASE} '
              f'user={module.RUNTIME} password=synthetic-not-a-credential',
              'DR_SUPPORT_DATABASE_SCHEMA': 'dr_support', 'DR_SUPPORT_DATABASE_MIGRATION_MODE': 'verify'}
    return SimpleNamespace(base=base, private=private, values=values, output=base / 'm1-context-qualification-control')


def save_configuration(scope, values=None):
    (scope.private / 'm1_runtime.env').write_text('\n'.join(f'{key}={value}' for key, value in
                                                        (values or scope.values).items()), encoding='utf-8')


def test_default_plan_never_reads_private_file_connects_or_creates_output(scope, monkeypatch):
    monkeypatch.setattr(module, '_runtime_configuration', lambda: pytest.fail('no private read in plan'))
    monkeypatch.setattr(module, 'PostgresDatabase', lambda *_: pytest.fail('no DB in plan'))
    result = module.qualify(scope.output)
    assert result['status'] == 'PLAN_ONLY' and result['inference'] == 'NOT_RUN'
    assert not scope.output.exists() and not list(scope.private.iterdir())


@pytest.mark.parametrize('kind', ['outside', 'wrong_name', 'occupied', 'redirect'])
def test_output_scope_and_no_overwrite_are_checked_before_credentials(scope, monkeypatch, kind):
    path = scope.output
    if kind == 'outside':
        path = scope.base.parent / path.name
    elif kind == 'wrong_name':
        path = scope.base / 'HANDOFF.md'
    elif kind == 'occupied':
        path.mkdir()
        (path / 'retained.txt').write_text('keep')
    else:
        monkeypatch.setattr(module, 'has_reparse_component', lambda _: True)
    monkeypatch.setattr(module, '_runtime_configuration', lambda: pytest.fail('no private read'))
    result = module.qualify(path, apply=True)
    assert result['status'] == 'BLOCKED' and result['failed_stage'] == 'OUTPUT_SCOPE'
    if kind == 'occupied':
        assert (path / 'retained.txt').read_text() == 'keep'


def test_private_privacy_refusal_precedes_runtime_file_open(scope, monkeypatch):
    monkeypatch.setattr(module, 'private_hospital_root', lambda _: False)
    result = module.qualify(scope.output, apply=True)
    assert result['reason'] == 'APPROVED_PRIVATE_CONFIGURATION_CHECK_REQUIRED'
    assert not scope.output.exists()


def test_only_three_exact_provisioned_keys_and_pinned_password_route_are_read(scope):
    save_configuration(scope)
    assert module._runtime_configuration() == scope.values


@pytest.mark.parametrize('change', ['host', 'port', 'dbname', 'user', 'password', 'service', 'schema', 'migration', 'extra'])
def test_wrong_configuration_is_refused_without_database_use(scope, change):
    values = deepcopy(scope.values)
    if change in {'host', 'port', 'dbname', 'user', 'password'}:
        from psycopg.conninfo import conninfo_to_dict, make_conninfo
        fields = conninfo_to_dict(values['DR_SUPPORT_DATABASE_URL'])
        fields[change] = '' if change == 'password' else 'unapproved'
        values['DR_SUPPORT_DATABASE_URL'] = make_conninfo(**fields)
    elif change == 'service':
        values['DR_SUPPORT_DATABASE_URL'] += ' service=unapproved'
    elif change == 'schema':
        values['DR_SUPPORT_DATABASE_SCHEMA'] = 'public'
    elif change == 'migration':
        values['DR_SUPPORT_DATABASE_MIGRATION_MODE'] = 'apply'
    else:
        values['REMOTE_MODEL_TOKEN'] = 'synthetic-never-print'
    save_configuration(scope, values)
    result = module.qualify(scope.output, apply=True)
    assert result['status'] == 'BLOCKED' and result['failed_stage'] == 'PRIVATE_CONFIGURATION'
    assert 'synthetic-never-print' not in json.dumps(result) and not scope.output.exists()


def test_duplicate_and_oversized_runtime_config_are_refused(scope):
    save_configuration(scope)
    path = scope.private / 'm1_runtime.env'
    path.write_text(path.read_text() + '\nDR_SUPPORT_DATABASE_SCHEMA=dr_support', encoding='utf-8')
    with pytest.raises(module.ContextQualificationError, match='KEYS_REQUIRED'):
        module._runtime_configuration()
    path.write_bytes(b'x' * 16385)
    with pytest.raises(module.ContextQualificationError, match='BOUNDED_APPROVED'):
        module._runtime_configuration()


def test_child_environment_clears_all_external_selectors_and_restores_codex_home(scope, monkeypatch):
    selectors = {'DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOTS': 'synthetic-private', 'REMOTE_MODEL_URL': 'https://invalid/',
                 'CVAT_TOKEN': 'synthetic-secret', 'PGSERVICE': 'unapproved', 'DR_SUPPORT_TEST_DATABASE_URL': 'invalid',
                 'MODEL_RUNTIME': 'local', 'APP_PROFILE': 'model_api', 'CODEX_HOME': 'synthetic-preserve'}
    for key, value in selectors.items():
        monkeypatch.setenv(key, value)
    before = dict(os.environ)
    with pytest.raises(RuntimeError):
        with module.isolated_environment(scope.values, 'm1_context_synthetic'):
            assert os.environ['CODEX_HOME'] == selectors['CODEX_HOME']
            assert not any(key in os.environ for key in selectors if key not in {'CODEX_HOME', 'MODEL_RUNTIME', 'APP_PROFILE'})
            assert os.environ['MODEL_RUNTIME'] == 'remote' and os.environ['DR_SUPPORT_DATABASE_MIGRATION_MODE'] == 'verify'
            assert os.environ['DR_SUPPORT_WORKSPACE_ID'] == 'm1_context_synthetic'
            raise RuntimeError('synthetic')
    assert dict(os.environ) == before


def install_control_ports(scope, monkeypatch, *, fail=None):
    calls = []
    monkeypatch.setattr(module, '_runtime_configuration', lambda: calls.append('config') or scope.values)

    def preflight(_database):
        calls.append('preflight')
        assert not scope.output.exists()
        if fail == 'preflight':
            raise RuntimeError('private DSN must never appear in receipt')

    def verify():
        calls.append('verify')
        assert not scope.output.exists()
        if fail == 'verify':
            raise RuntimeError('private migration details')

    monkeypatch.setattr(module, 'WorkspaceContextReader', lambda **_: SimpleNamespace(preflight_runtime_database=preflight))
    monkeypatch.setattr(module, 'SchemaMigrator', lambda _: SimpleNamespace(verify=verify))

    def collision(database, workspace_id):
        calls.append('collision')
        assert workspace_id.startswith('m1_context_') and database.settings.schema == 'dr_support'
        return {'retained': True} if fail == 'collision' else None

    def construct(database, reader, output, workspace_id):
        calls.append('construct')
        assert list((output / 'input').iterdir()) == list((output / 'output').iterdir()) == []
        if fail == 'construct':
            raise RuntimeError('private source details')
        return {'complete_context': 'PASS', 'model_rpc_calls': 0, 'model_pins': 'CONTROL_ONLY_NO_MODEL'}

    monkeypatch.setattr(module, '_read_catalog', collision)
    monkeypatch.setattr(module, '_construct_and_read', construct)
    return calls


def test_apply_preflight_then_verify_then_new_workspace_and_exclusive_receipt(scope, monkeypatch):
    calls = install_control_ports(scope, monkeypatch)
    result = module.qualify(scope.output, apply=True)
    assert calls == ['config', 'preflight', 'verify', 'collision', 'construct']
    assert result['status'] == 'APP_CONTEXT_PASS' and result['evidence_logging'] == 'PASS'
    assert result['inference_requests'] == 0 and result['inference'] == 'NOT_RUN'
    stored = json.loads((scope.output / module.RECEIPT).read_bytes())
    assert stored == result and 'synthetic-not-a-credential' not in json.dumps(stored)
    again = module.qualify(scope.output, apply=True)
    assert again['reason'] == 'EXISTING_OUTPUT_NO_OVERWRITE_OR_RESUME'
    assert json.loads((scope.output / module.RECEIPT).read_bytes()) == stored


@pytest.mark.parametrize('failure,stage', [('preflight', 'AUTHENTICATED_RUNTIME_PREFLIGHT'),
    ('verify', 'MIGRATION_VERIFY'), ('collision', 'NEW_WORKSPACE_COLLISION_CHECK'),
    ('construct', 'ACTUAL_APP_AND_CONTEXT_READ')])
def test_apply_failure_retains_partial_state_and_does_not_print_exception(scope, monkeypatch, failure, stage):
    calls = install_control_ports(scope, monkeypatch, fail=failure)
    result = module.qualify(scope.output, apply=True)
    assert result['status'] == 'BLOCKED' and result['failed_stage'] == stage
    assert 'private ' not in json.dumps(result)
    if failure == 'construct':
        assert scope.output.is_dir() and (scope.output / module.RECEIPT).is_file()
    else:
        assert not scope.output.exists() and 'construct' not in calls


def test_receipt_failure_preserves_context_success_and_is_not_inference_failure(scope, monkeypatch):
    install_control_ports(scope, monkeypatch)

    def fail(output, result):
        (output / module.RECEIPT).write_bytes(b'partial')
        raise OSError('synthetic disk failure')

    monkeypatch.setattr(module, '_write_receipt', fail)
    result = module.qualify(scope.output, apply=True)
    assert result['status'] == 'APP_CONTEXT_PASS' and result['evidence_logging'] == 'BLOCKED'
    assert result['inference'] == 'NOT_RUN' and result['inference_requests'] == 0
    assert (scope.output / module.RECEIPT).read_bytes() == b'partial'


def test_control_provider_is_exact_cached_and_rejects_every_rpc():
    calls = []
    provider = module._control_provider(calls)
    try:
        assert type(provider) is RemoteBoundTransportCandidate and type(provider.channel) is ExplicitHttpChannel
        identity = RemoteBoundTransportCandidate.prism_preview_identity(provider)
        assert 'CONTROL_ONLY' in identity['model_pins']['source_revision'] and calls == []
        with pytest.raises(module.ContextQualificationError, match='RPC_FORBIDDEN'):
            provider.channel.request('GET', '/control-only-never-network')
        assert calls == [True]
    finally:
        provider.channel.close()


def test_actual_reader_compares_raw_case_catalog_objects_and_keeps_caches(context_rig, monkeypatch):
    rig = context_rig
    raw = new_case(rig.image.image_id)
    raw.update(rig.case)
    rig.case = raw
    rig.store._observed[rig.image.image_id] = canonical(raw).decode()
    monkeypatch.setattr(rig.store, 'get', lambda _: deepcopy(raw))
    monkeypatch.setattr(rig.store, 'read_original_case', lambda _: deepcopy(raw))
    monkeypatch.setattr(module, '_read_catalog', lambda *_: deepcopy(rig.workspace))
    # Existing reader fixture is already bound. Use a fresh actual reader for
    # this qualification's one-use bind; only its SQL driver port is synthetic.
    reader = module.WorkspaceContextReader(role_config=module.PLAN, database_name=module.DATABASE)
    result = module._check_context(rig.app, reader, rig.image, rig.gate, [])
    assert result['complete_context'] == result['raw_readback'] == 'PASS'
    assert result['model_rpc_calls'] == 0 and len(result['context_sha256']) == 64
    assert 'objects' not in result and 'case' not in result


def test_raw_catalog_disagreement_is_never_accepted(context_rig, monkeypatch):
    rig = context_rig
    raw = new_case(rig.image.image_id)
    raw.update(rig.case)
    rig.case = raw
    rig.store._observed[rig.image.image_id] = canonical(raw).decode()
    monkeypatch.setattr(rig.store, 'get', lambda _: deepcopy(raw))
    monkeypatch.setattr(rig.store, 'read_original_case', lambda _: deepcopy(raw))
    monkeypatch.setattr(module, '_read_catalog', lambda *_: {'unexpected': 'full raw catalog mismatch'})
    reader = module.WorkspaceContextReader(role_config=module.PLAN, database_name=module.DATABASE)
    with pytest.raises(module.ContextQualificationError, match='RAW_CASE_OR_CATALOG'):
        module._check_context(rig.app, reader, rig.image, rig.gate, [])
