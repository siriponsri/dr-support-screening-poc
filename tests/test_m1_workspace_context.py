"""Synthetic connection/objects only: NOT authenticated PostgreSQL qualification."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from threading import RLock
from types import SimpleNamespace

from fastapi import FastAPI
import pytest

from dr_support.images import synthetic_image
from dr_support.imaging import DerivativeService
from dr_support.persistence import PostgresCaseStore, PostgresDatabase, PostgresSettings, PostgresWorkspaceCatalog
from dr_support.persistence.entry_fence_plan import EntryFencePlan
from dr_support.providers.prism_remote_bound import RemoteBoundTransportCandidate
from dr_support.services.m1_workspace_context import WorkspaceContextError, WorkspaceContextReader
from dr_support.services.prism_preview import MODEL_ID, canonical, preparation_context
from dr_support.services.source_mutation_gate import SourceMutationGate
from dr_support.services.workspaces import WorkspaceManager


DATABASE = 'dr_support_m1_interactive_test_20261023'
ROLES = EntryFencePlan('dr_support', 'dr_support_entry_guard', 'dr_support_m1_owner_test',
                       'dr_support_m1_runtime_test', 'dr_support_m1_authority_test')


def principal():
    return dict(database=DATABASE, current_user=ROLES.runtime_role, session_user=ROLES.runtime_role,
                login=True, roles_present=True, dangerous_membership=False, authority_membership=False,
                protected_tables=4, protected_owner=False, guard_write=False, guard_execute=False,
                replication_origin=True)


class NoChannel:
    def request(self, *args, **kwargs):
        pytest.fail('Context reading must never perform an RPC')


def provider():
    value = RemoteBoundTransportCandidate(NoChannel())
    value.capabilities = {'pins': dict(model_id=MODEL_ID, source_revision='synthetic-reviewed-revision',
        preprocessing='synthetic-reviewed-preprocessing', config_sha256='a' * 64,
        checkpoint_sha256={'fold0': 'b' * 64})}
    return value


class MockConnection:
    """A SQL-inspection fixture, not a driver/authentication implementation."""
    def __init__(self, rig):
        self.rig = rig
        self.info = SimpleNamespace(user=ROLES.runtime_role, dbname=DATABASE)
        self.result = None
        self.closed = False

    @contextmanager
    def transaction(self):
        yield

    def execute(self, query, parameters=None):
        text = query if isinstance(query, str) else query.as_string(None)
        self.rig.queries.append((text, parameters))
        if text.startswith('SET '):
            return self
        assert 'SET TRANSACTION READ ONLY' in [item[0] for item in self.rig.queries]
        if 'SELECT c.workspace_id' in text:
            self.result = (self.rig.store.workspace_id, self.rig.image.image_id, self.rig.revision,
                           deepcopy(self.rig.case), deepcopy(self.rig.workspace), deepcopy(self.rig.principal))
            if self.rig.on_read:
                self.rig.on_read()
        else:
            self.result = (deepcopy(self.rig.principal),)
        return self

    def fetchone(self):
        return self.result

    def close(self):
        self.closed = True


@pytest.fixture
def rig(tmp_path):
    rig = SimpleNamespace(queries=[], on_read=None, revision=0, principal=principal())
    rig.connection = MockConnection(rig)
    rig.database = PostgresDatabase(PostgresSettings(
        f'dbname={DATABASE} user={ROLES.runtime_role}'), connector=lambda *a, **k: rig.connection)
    rig.store = PostgresCaseStore(rig.database, 'ws_synthetic_m1')
    rig.image = synthetic_image()
    admission = dict(source_origin='SYNTHETIC', source_sha256=rig.image.sha256,
                     integrity_status='OK', retinal_modality='CFP', source_metadata={},
                     integrity={'status': 'OK'})
    rig.case = dict(image_id=rig.image.image_id, revision=0, image_sha256=rig.image.sha256,
                    admission=admission, same_revision_state={'unprojected': 'preserve me'},
                    analysis_preparation={'status': 'READY', 'source_sha256': rig.image.sha256})
    stamp = '2026-10-23T00:00:00+00:00'
    rig.workspace = dict(workspace_id=rig.store.workspace_id, name='Synthetic fixture',
        input_folder=str(tmp_path / 'input'), output_folder=str(tmp_path / 'output'), database_path='',
        note=None, created_at=stamp, updated_at=stamp, last_opened=stamp, archived_at=None,
        unprojected_catalog_state={'keep': 'complete row'})
    columns = ('workspace_id', 'name', 'input_folder', 'output_folder', 'database_path', 'note',
               'created_at', 'updated_at', 'last_opened')
    rig.gate, rig.app = SourceMutationGate(), FastAPI()
    manager = WorkspaceManager.__new__(WorkspaceManager)
    manager.app, manager.store, manager.lock = rig.app, rig.store, RLock()
    manager.source_mutation_gate, manager.postgres_mode = rig.gate, True
    manager.postgres_database, manager.postgres_catalog = rig.database, PostgresWorkspaceCatalog(rig.database)
    manager.active_workspace = PostgresWorkspaceCatalog._profile(tuple(rig.workspace[key] for key in columns))
    rig.app.state.store, rig.app.state.workspace_manager = rig.store, manager
    rig.app.state.workspace_id, rig.app.state.source_mutation_gate = rig.store.workspace_id, rig.gate
    rig.app.state.providers, rig.app.state.derivatives = {MODEL_ID: provider()}, DerivativeService()
    rig.app.state.images, rig.app.state.admissions = {rig.image.image_id: rig.image}, {rig.image.image_id: deepcopy(admission)}
    rig.store.source_mutation_gate = rig.gate
    rig.store._observed[rig.image.image_id] = canonical(rig.case).decode()
    rig.store._observed_revision[rig.image.image_id] = 0
    rig.reader = WorkspaceContextReader(role_config=ROLES, database_name=DATABASE)
    rig.reader.bind(rig.app, rig.gate)
    return rig


def test_complete_raw_case_and_catalog_use_one_read_only_statement_without_enrichment(rig):
    caches = deepcopy((rig.store._observed, rig.store._observed_revision))
    context = rig.reader(rig.image.image_id)
    assert set(context) == {'workspace_id', 'image_id', 'case', 'workspace', 'admission',
                            'source_sha256', 'preparation_context', 'model_pins', 'objects'}
    assert context['case'] == rig.case and context['case'] is not rig.case
    assert context['workspace'] == rig.workspace
    assert 'global' not in context['case']  # Defaults are not silently added.
    assert context['source_sha256'] == rig.image.sha256
    assert context['preparation_context'] == preparation_context(rig.case)
    assert all(a is b for a, b in zip(context['objects'], (rig.store, rig.app.state.providers[MODEL_ID],
        rig.app.state.workspace_manager, rig.app.state.derivatives), strict=True))
    assert (rig.store._observed, rig.store._observed_revision) == caches
    queries = [text for text, _ in rig.queries if not text.startswith('SET ')]
    assert len(queries) == 1 and 'JOIN "dr_support".workspaces' in queries[0]
    assert 'to_jsonb(w)' in queries[0] and 'c.payload' in queries[0]
    assert rig.connection.closed


def test_preflight_checks_actual_read_connection_before_any_factory_write(rig):
    assert rig.reader.preflight_runtime_database(rig.database) is None
    selects = [text for text, _ in rig.queries if not text.startswith('SET ')]
    assert len(selects) == 1 and 'pg_catalog.pg_roles' in selects[0]
    assert 'pg_has_role' in selects[0] and 'protected_owner' in selects[0]
    assert 'has_function_privilege' in selects[0] and 'has_table_privilege' in selects[0]
    assert rig.connection.closed


@pytest.mark.parametrize('field,value', [
    ('current_user', 'unknown'), ('session_user', 'postgres'), ('database', 'unapproved'),
    ('login', False), ('roles_present', False), ('dangerous_membership', True),
    ('authority_membership', True), ('protected_tables', 3), ('protected_owner', True),
    ('guard_write', True), ('guard_execute', True), ('replication_origin', False),
])
def test_unknown_privileged_or_guard_capable_principal_is_refused(rig, field, value):
    rig.principal[field] = value
    with pytest.raises(WorkspaceContextError, match='AUTHENTICATED_RUNTIME_PRINCIPAL_REQUIRED'):
        rig.reader.preflight_runtime_database(rig.database)
    with pytest.raises(WorkspaceContextError, match='AUTHENTICATED_RUNTIME_PRINCIPAL_REQUIRED'):
        rig.reader(rig.image.image_id)


@pytest.mark.parametrize('field,value', [('user', 'postgres'), ('user', None), ('dbname', 'unknown')])
def test_set_session_authorization_is_not_a_genuine_runtime_login(rig, field, value):
    setattr(rig.connection.info, field, value)
    # SQL current/session may both name runtime after admin session authorization;
    # the actual driver's authenticated startup user must independently agree.
    with pytest.raises(WorkspaceContextError, match='AUTHENTICATED_RUNTIME_PRINCIPAL_REQUIRED'):
        rig.reader.preflight_runtime_database(rig.database)


def test_preflight_success_is_not_cached_as_future_connection_authority(rig):
    rig.reader.preflight_runtime_database(rig.database)
    rig.connection.info.user = 'postgres'
    with pytest.raises(WorkspaceContextError, match='AUTHENTICATED_RUNTIME_PRINCIPAL_REQUIRED'):
        rig.reader(rig.image.image_id)


def test_database_errors_are_secret_safe_and_close_the_read_connection(rig, monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError('synthetic confidential connection detail')
    monkeypatch.setattr(rig.connection, 'execute', unavailable)
    with pytest.raises(WorkspaceContextError, match='RUNTIME_PRINCIPAL_UNAVAILABLE') as caught:
        rig.reader.preflight_runtime_database(rig.database)
    assert 'confidential' not in str(caught.value) and rig.connection.closed


@pytest.mark.parametrize('change', ['same_revision', 'missing_cache', 'wrong_revision', 'missing_revision'])
def test_raw_payload_must_match_loaded_case_without_repairing_cache(rig, change):
    if change == 'same_revision': rig.case['same_revision_state']['unprojected'] = 'changed outside app'
    elif change == 'missing_cache': rig.store._observed.clear()
    elif change == 'wrong_revision': rig.store._observed_revision[rig.image.image_id] = 1
    else: rig.store._observed_revision.clear()
    caches = deepcopy((rig.store._observed, rig.store._observed_revision))
    with pytest.raises(WorkspaceContextError, match='LOADED_RAW_CASE_CHANGED'):
        rig.reader(rig.image.image_id)
    assert (rig.store._observed, rig.store._observed_revision) == caches


@pytest.mark.parametrize('change', ['row_revision', 'payload_image', 'catalog_workspace', 'archived'])
def test_inconsistent_raw_identity_or_catalog_is_never_normalized(rig, change):
    if change == 'row_revision': rig.revision = 1
    elif change == 'payload_image': rig.case['image_id'] = 'other'
    elif change == 'catalog_workspace': rig.workspace['workspace_id'] = 'other'
    else: rig.workspace['archived_at'] = '2026-10-23T00:00:00+00:00'
    with pytest.raises(WorkspaceContextError, match='RAW_ROW_IDENTITY_CHANGED'):
        rig.reader(rig.image.image_id)


def test_full_catalog_drift_is_returned_even_when_profile_projection_is_unchanged(rig):
    before = rig.reader(rig.image.image_id)
    rig.workspace['unprojected_catalog_state']['keep'] = 'same-profile drift'
    after = rig.reader(rig.image.image_id)
    assert before['workspace'] != after['workspace'] and before['case'] == after['case']
    rig.workspace['note'] = 'catalog no longer matches active profile'
    with pytest.raises(WorkspaceContextError, match='CATALOG_PROJECTION_CHANGED'):
        rig.reader(rig.image.image_id)


@pytest.mark.parametrize('target', ['app', 'store', 'manager'])
def test_every_app_writer_must_share_the_exact_gate_object(rig, target):
    other = SourceMutationGate()
    selected = {'app': rig.app.state, 'store': rig.store, 'manager': rig.app.state.workspace_manager}[target]
    selected.source_mutation_gate = other
    with pytest.raises(WorkspaceContextError, match='SHARED_BINDING_REQUIRED'):
        rig.reader(rig.image.image_id)


@pytest.mark.parametrize('target', ['store', 'provider', 'derivative', 'manager'])
def test_object_swaps_during_sql_read_are_refused(rig, target):
    def change():
        if target == 'store':
            store = PostgresCaseStore(rig.database, rig.store.workspace_id)
            store.source_mutation_gate = rig.gate
            rig.app.state.store = store
            rig.app.state.workspace_manager.store = store
        elif target == 'provider': rig.app.state.providers[MODEL_ID] = provider()
        elif target == 'derivative': rig.app.state.derivatives = DerivativeService()
        else: rig.app.state.workspace_manager = object()
    rig.on_read = change
    with pytest.raises(WorkspaceContextError): rig.reader(rig.image.image_id)


def test_idle_provider_replacement_is_exposed_as_new_object_identity(rig):
    before = rig.reader(rig.image.image_id)
    rig.app.state.providers[MODEL_ID] = provider()
    after = rig.reader(rig.image.image_id)
    assert before['model_pins'] == after['model_pins']
    assert before['objects'][1] is not after['objects'][1]


def test_cached_pin_drift_is_detected_without_rpc(rig):
    def change(): rig.app.state.providers[MODEL_ID].capabilities['pins']['config_sha256'] = 'c' * 64
    rig.on_read = change
    with pytest.raises(WorkspaceContextError, match='CHANGED_DURING_READ'):
        rig.reader(rig.image.image_id)


@pytest.mark.parametrize('invalid', ['extra_field', 'no_cache', 'invalid_hash'])
def test_only_existing_reviewed_nonsecret_cached_pin_schema_is_accepted(rig, invalid):
    selected = rig.app.state.providers[MODEL_ID]
    if invalid == 'extra_field': selected.capabilities['pins']['unreviewed_field'] = 'rejected'
    elif invalid == 'no_cache': selected.capabilities = None
    else: selected.capabilities['pins']['checkpoint_sha256']['fold0'] = 'not-a-digest'
    with pytest.raises(WorkspaceContextError): rig.reader(rig.image.image_id)


@pytest.mark.parametrize('data', [b'', bytearray(b'synthetic mutable bytes'), b'changed immutable bytes'])
def test_original_must_be_immutable_and_match_recorded_bytes(rig, data):
    rig.app.state.images[rig.image.image_id] = replace(rig.image, data=data)
    with pytest.raises(WorkspaceContextError): rig.reader(rig.image.image_id)


def test_source_bound_is_checked_before_hashing_or_database_read(rig):
    small = WorkspaceContextReader(role_config=ROLES, database_name=DATABASE, max_source_bytes=1)
    small.bind(rig.app, rig.gate)
    with pytest.raises(WorkspaceContextError, match='IMMUTABLE_BOUNDED_SOURCE_REQUIRED'):
        small(rig.image.image_id)
    assert rig.queries == []


def test_unknown_store_or_provider_never_uses_duck_typed_data_access(rig):
    rig.app.state.store = SimpleNamespace(get=lambda *a: pytest.fail('Unknown store read'))
    with pytest.raises(WorkspaceContextError, match='REVIEWED_OBJECTS_REQUIRED'):
        rig.reader(rig.image.image_id)
    rig.app.state.store = rig.store
    rig.app.state.providers[MODEL_ID] = SimpleNamespace(prism_preview_identity=lambda: pytest.fail('Unknown RPC'))
    with pytest.raises(WorkspaceContextError, match='REVIEWED_OBJECTS_REQUIRED'):
        rig.reader(rig.image.image_id)
    assert rig.queries == []


def test_writer_or_generation_change_is_refused_but_fenced_inspection_is_supported(rig):
    with rig.gate.writer():
        with pytest.raises(WorkspaceContextError, match='WRITER_ACTIVE'): rig.reader(rig.image.image_id)
    def changed():
        with rig.gate.writer(): pass
    rig.on_read = changed
    with pytest.raises(WorkspaceContextError, match='CHANGED_DURING_READ'): rig.reader(rig.image.image_id)
    rig.on_read = None
    permit = rig.gate.begin_entry(expected_generation=rig.gate.snapshot().generation)
    assert rig.reader(rig.image.image_id)['case'] == rig.case
    permit.quarantine()
    assert rig.reader(rig.image.image_id)['case'] == rig.case
    assert rig.gate.snapshot().state == 'QUARANTINED'


def test_context_is_bounded_canonical_json_and_bind_is_one_use(rig):
    with pytest.raises(WorkspaceContextError, match='BIND_ONCE'): rig.reader.bind(rig.app, rig.gate)
    rig.case['same_revision_state']['unprojected'] = 'x' * (8 * 1024 * 1024)
    rig.store._observed[rig.image.image_id] = canonical(rig.case).decode()
    with pytest.raises(WorkspaceContextError, match='CONTEXT_LIMIT'): rig.reader(rig.image.image_id)


def test_arbitrary_hospital_scope_is_not_approved_by_trusted_constructor():
    with pytest.raises(WorkspaceContextError, match='APPROVED_TEST_SCOPE'):
        WorkspaceContextReader(role_config=ROLES, database_name='hospital_production')
    unapproved = replace(ROLES, runtime_role='other_runtime')
    with pytest.raises(WorkspaceContextError, match='APPROVED_TEST_SCOPE'):
        WorkspaceContextReader(role_config=unapproved, database_name=DATABASE)
