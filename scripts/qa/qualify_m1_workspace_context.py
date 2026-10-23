"""Opt-in new isolated synthetic workspace qualification; never model inference."""
import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from uuid import uuid4

import httpx
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from dr_support.contracts import WorkspaceProfile
from dr_support.images import synthetic_image
from dr_support.persistence import PostgresDatabase, PostgresSettings, PostgresWorkspaceCatalog, SchemaMigrator
from dr_support.providers.prism_remote_bound import ExplicitHttpChannel, RemoteBoundTransportCandidate
from dr_support.services.admission import legacy_admission
from dr_support.services.filesystem_privacy import has_reparse_component, private_hospital_root
from dr_support.services.m1_workspace_context import WorkspaceContextReader
from dr_support.services.prism_preview import MODEL_ID, canonical, sha
from dr_support.services.prism_remote_transport import PROTOCOL, TRANSPORT
from dr_support.services.source_mutation_gate import SourceMutationGate
from scripts.qa.configure_m1_test_credentials import PRIVATE_DIRECTORY
from scripts.qa.qualify_m1_entry_fence import DATABASE, PLAN, RUNTIME


ARTIFACT_BASE = Path('C:/Users/User/Documents/Codex/2026-10-21/task')
RECEIPT = 'CONTEXT_QUALIFICATION.json'
_KEYS = {'DR_SUPPORT_DATABASE_URL', 'DR_SUPPORT_DATABASE_SCHEMA', 'DR_SUPPORT_DATABASE_MIGRATION_MODE'}
_CLEAR = re.compile(r'^(DR_SUPPORT_|MODEL_|PRISM_|RETFOUND_|USPEC_|CVAT_|REMOTE_MODEL_|DR_DEMO_|PG|APP_PROFILE$|CUDA_VISIBLE_DEVICES$)')


class ContextQualificationError(RuntimeError):
    """Only fixed, nonsecret error codes may reach this boundary."""


def require(value, code):
    if not value:
        raise ContextQualificationError(code)


def _output_path(output):
    output = Path(output)
    require(output.is_absolute() and output.parent == ARTIFACT_BASE
            and re.fullmatch(r'm1-context-qualification-[A-Za-z0-9_-]{1,100}', output.name),
            'NEW_APPROVED_CONTEXT_ARTIFACT_CHILD_REQUIRED')
    require(ARTIFACT_BASE.is_dir() and not has_reparse_component(ARTIFACT_BASE),
            'ARTIFACT_PARENT_UNAVAILABLE_OR_REDIRECTED')
    require(not output.exists() and not output.is_symlink(), 'EXISTING_OUTPUT_NO_OVERWRITE_OR_RESUME')
    return output


def _runtime_configuration():
    directory = PRIVATE_DIRECTORY
    path = directory / 'm1_runtime.env'
    require(directory.is_dir() and not has_reparse_component(directory)
            and private_hospital_root(directory), 'APPROVED_PRIVATE_CONFIGURATION_CHECK_REQUIRED')
    require(path.is_file() and not has_reparse_component(path) and 0 < path.stat().st_size <= 16384,
            'BOUNDED_APPROVED_RUNTIME_FILE_REQUIRED')
    values = {}
    with path.open('rb') as stream:
        raw = stream.read(16385)
    require(0 < len(raw) <= 16384, 'BOUNDED_APPROVED_RUNTIME_FILE_REQUIRED')
    for line in raw.decode('utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, separator, value = line.partition('=')
        require(separator and key in _KEYS and key not in values, 'EXACT_RUNTIME_CONFIGURATION_KEYS_REQUIRED')
        values[key] = value.strip()
    require(set(values) == _KEYS and values['DR_SUPPORT_DATABASE_SCHEMA'] == PLAN.application_schema
            and values['DR_SUPPORT_DATABASE_MIGRATION_MODE'] == 'verify', 'EXACT_RUNTIME_VERIFY_CONFIGURATION_REQUIRED')
    parameters = conninfo_to_dict(values['DR_SUPPORT_DATABASE_URL'])
    require(set(parameters) == {'host', 'port', 'dbname', 'user', 'password'}
            and parameters['host'] == '127.0.0.1' and parameters['port'] == '54805'
            and parameters['dbname'] == DATABASE and parameters['user'] == RUNTIME
            and bool(parameters['password']), 'EXACT_APPROVED_PASSWORD_RUNTIME_ROUTE_REQUIRED')
    require(private_hospital_root(directory), 'PRIVATE_CONFIGURATION_CHANGED_DURING_READ')
    return values


@contextmanager
def isolated_environment(values, workspace_id):
    previous = dict(os.environ)
    try:
        for key in list(os.environ):
            if _CLEAR.match(key):
                del os.environ[key]
        os.environ.update(values)
        os.environ.update(DR_SUPPORT_CASE_STORE='postgres', DR_SUPPORT_WORKSPACE_ID=workspace_id,
                          MODEL_RUNTIME='remote', APP_PROFILE='review', CUDA_VISIBLE_DEVICES='-1')
        yield
    finally:
        os.environ.clear()
        os.environ.update(previous)


def _read_catalog(database, workspace_id):
    with database.session(autocommit=False) as connection:
        with connection.transaction():
            connection.execute('SET TRANSACTION READ ONLY')
            connection.execute("SET LOCAL statement_timeout = '5s'")
            row = connection.execute(sql.SQL('SELECT to_jsonb(w) FROM {}.workspaces w WHERE workspace_id=%s').format(
                sql.Identifier(database.settings.schema)), (workspace_id,)).fetchone()
    return row[0] if row else None


def _control_provider(rpc_calls):
    def forbidden_rpc(_request):
        rpc_calls.append(True)
        raise ContextQualificationError('CONTROL_ONLY_MODEL_RPC_FORBIDDEN')
    channel = ExplicitHttpChannel('http://127.0.0.1:48765', transport=httpx.MockTransport(forbidden_rpc),
                                  auth_headers=lambda *_args, **_kwargs: {})
    provider = RemoteBoundTransportCandidate(channel)
    provider.capabilities = {
        'pins': dict(model_id=MODEL_ID, source_revision='CONTROL_ONLY_NO_MODEL',
                     preprocessing='CONTROL_ONLY_NO_MODEL_NO_INFERENCE', config_sha256=sha(b'CONTROL_ONLY_CONFIG'),
                     checkpoint_sha256={'CONTROL_ONLY_NOT_A_WEIGHT': sha(b'CONTROL_ONLY_NO_WEIGHT')}),
        'epoch': 'CONTROL_ONLY_NO_WORKER', 'transport': TRANSPORT, 'binding_protocol': PROTOCOL,
    }
    return provider


def _check_context(app, reader, image, gate, rpc_calls):
    store = app.state.store
    store.get(image.image_id)  # Establish the actual observed raw baseline.
    raw_case = store.read_original_case(image.image_id)
    raw_catalog = _read_catalog(store.database, store.workspace_id)
    caches = deepcopy((store._observed, store._observed_revision))
    before = gate.snapshot()
    reader.bind(app, gate)
    first, second = reader(image.image_id), reader(image.image_id)
    objects = (store, app.state.providers[MODEL_ID], app.state.workspace_manager, app.state.derivatives)
    for value in (first, second):
        require(value['case'] == raw_case and value['workspace'] == raw_catalog,
                'RAW_CASE_OR_CATALOG_READBACK_CHANGED')
        require(value['admission'] == raw_case['admission'] and value['source_sha256'] == image.sha256,
                'SYNTHETIC_SOURCE_READBACK_CHANGED')
        require(all(left is right for left, right in zip(value['objects'], objects, strict=True)),
                'ACTUAL_CONTEXT_OBJECT_IDENTITY_CHANGED')
    values = [{key: value for key, value in context.items() if key != 'objects'} for context in (first, second)]
    require(canonical(values[0]) == canonical(values[1]) and gate.snapshot() == before
            and (store._observed, store._observed_revision) == caches, 'READ_ONLY_CONTEXT_OR_CACHES_CHANGED')
    require(not rpc_calls, 'CONTROL_ONLY_MODEL_RPC_FORBIDDEN')
    require(raw_case['reviewed_grade'] is None and not raw_case['human_annotations']
            and raw_case['global'] is None and raw_case['lesion'] is None
            and not raw_case['inference_history'], 'TEST_CASE_MUST_HAVE_NO_MODEL_OR_CLINICIAN_LABELS')
    return dict(context_sha256=sha(canonical(values[0])), case_sha256=sha(canonical(raw_case)),
                catalog_sha256=sha(canonical(raw_catalog)), source_sha256=image.sha256,
                revision=raw_case['revision'], source_origin='SYNTHETIC', raw_readback='PASS',
                complete_context='PASS', object_identity='PASS', observed_caches='UNCHANGED',
                gate_generation=before.generation, model_rpc_calls=0, model_pins='CONTROL_ONLY_NO_MODEL')


def _construct_and_read(database, reader, output, workspace_id):
    from dr_support.api._factory import create_app
    gate = SourceMutationGate()
    stamp = datetime.now(timezone.utc).isoformat()
    profile = WorkspaceProfile(id=workspace_id, name='TEST_ONLY ' + workspace_id,
        input_folder=str(output / 'input'), output_folder=str(output / 'output'), database_path=None,
        note='TEST_ONLY synthetic app/context qualification; no inference or clinical labels',
        created_at=stamp, updated_at=stamp, last_opened=stamp)
    with gate.writer():
        PostgresWorkspaceCatalog(database).create_and_activate(profile)
    app = create_app(include_samples=False, include_demo_fixtures=False, workspace_id=workspace_id,
                     case_store_mode='postgres', source_mutation_gate=gate)
    require(app.state.workspace_id == workspace_id and app.state.store.workspace_id == workspace_id
            and app.state.workspace_manager.active_workspace.id == workspace_id
            and not app.state.images and app.state.model_connection is None,
            'EXPLICIT_NEW_EMPTY_WORKSPACE_REQUIRED')
    image, rpc_calls = synthetic_image(), []
    provider = _control_provider(rpc_calls)
    try:
        with gate.writer():
            admission = legacy_admission(image)
            case = app.state.store.get(image.image_id)
            require(app.state.store._observed[image.image_id] is None, 'NEW_TEST_CASE_COLLISION_NO_OVERWRITE')
            case.update(admission=deepcopy(admission), source_sha256=image.sha256, image_sha256=image.sha256)
            app.state.store.put(case)
            app.state.images[image.image_id] = image
            app.state.admissions[image.image_id] = deepcopy(admission)
            app.state.providers = {MODEL_ID: provider}
        return _check_context(app, reader, image, gate, rpc_calls)
    finally:
        provider.channel.close()


def _write_receipt(output, result):
    with (output / RECEIPT).open('xb') as stream:
        raw = canonical(result)
        require(stream.write(raw) == len(raw), 'PARTIAL_RECEIPT_RETAINED')
        stream.flush()
        os.fsync(stream.fileno())


def qualify(output, *, apply=False):
    result = dict(status='PLAN_ONLY', database=DATABASE, runtime_role=RUNTIME,
                  scope='NEW_TEST_ONLY_SYNTHETIC_WORKSPACE', inference='NOT_RUN', inference_requests=0,
                  native_model='NOT_RUN', clinical_validation='NOT_RUN', automatic_resume=False,
                  partial_state_retained=True, evidence_logging='NOT_RUN')
    created = False
    stage = 'OUTPUT_SCOPE'
    try:
        output = _output_path(output)
        result['output'] = str(output)
        if not apply:
            return result
        stage = 'PRIVATE_CONFIGURATION'
        values = _runtime_configuration()
        workspace_id = 'm1_context_' + uuid4().hex
        result['workspace_id'] = workspace_id
        with isolated_environment(values, workspace_id):
            database = PostgresDatabase(PostgresSettings.from_env())
            reader = WorkspaceContextReader(role_config=PLAN, database_name=DATABASE)
            stage = 'AUTHENTICATED_RUNTIME_PREFLIGHT'
            reader.preflight_runtime_database(database)
            result['authenticated_runtime_preflight'] = 'PASS'
            stage = 'MIGRATION_VERIFY'
            SchemaMigrator(database).verify()
            result['migration_verify'] = 'PASS'
            stage = 'NEW_WORKSPACE_COLLISION_CHECK'
            require(_read_catalog(database, workspace_id) is None, 'EXISTING_WORKSPACE_NO_OVERWRITE_OR_RESUME')
            stage = 'NEW_ARTIFACT_DIRECTORIES'
            output.mkdir()
            created = True
            (output / 'input').mkdir()
            (output / 'output').mkdir()
            stage = 'ACTUAL_APP_AND_CONTEXT_READ'
            result.update(_construct_and_read(database, reader, output, workspace_id))
            result['status'] = 'APP_CONTEXT_PASS'
    except Exception as error:
        result.update(status='BLOCKED', failed_stage=stage,
                      reason=str(error) if type(error) is ContextQualificationError else 'DETAILS_REDACTED',
                      error_class=type(error).__name__ if type(error).__name__ in {
                          'ContextQualificationError', 'WorkspaceContextError', 'MigrationError',
                          'DatabaseUnavailableError', 'PermissionError', 'FileExistsError', 'OSError',
                          'ValueError', 'RuntimeError', 'ProgrammingError'} else 'OTHER')
    if created:
        try:
            _write_receipt(output, result | {'evidence_logging': 'PASS'})
            result['evidence_logging'] = 'PASS'
        except Exception:
            result['evidence_logging'] = 'BLOCKED'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--apply-test-workspace', action='store_true')
    args = parser.parse_args()
    result = qualify(args.output, apply=args.apply_test_workspace)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] in {'PLAN_ONLY', 'APP_CONTEXT_PASS'} and result['evidence_logging'] != 'BLOCKED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
