"""Unregistered read-only binder for the approved M1 PostgreSQL test scope.

No app construction, source authorization, RPC, enrichment or database writes.
Mock connection tests are not evidence of a real authenticated runtime login.
"""
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime
import os
import re
from threading import RLock

import httpx
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from ..images import BridgeImage
from ..imaging import DerivativeService
from ..persistence import PostgresCaseStore, PostgresDatabase, PostgresSettings, PostgresWorkspaceCatalog
from ..persistence.entry_fence_plan import EntryFencePlan
from ..providers.prism_remote_bound import ExplicitHttpChannel, RemoteBoundTransportCandidate
from .prism_preview import MAX_BYTES, MODEL_ID, canonical, preparation_context, sha
from .prism_remote_transport import PROTOCOL, TRANSPORT
from .source_identity import source_identity_reason
from .source_mutation_gate import SourceMutationGate
from .workspaces import WorkspaceManager


_DATABASE = 'dr_support_m1_interactive_test_20261023'
_SCOPE = ('dr_support', 'dr_support_entry_guard', 'dr_support_m1_owner_test',
          'dr_support_m1_runtime_test', 'dr_support_m1_authority_test')
_CONTEXT_LIMIT = 8 * 1024 * 1024
_PROTECTED_TABLES = ['workspaces', 'review_cases', 'legacy_migration_receipts']


class WorkspaceContextError(RuntimeError):
    """Secret-safe refusal to attest an unknown or inconsistent context."""


def _require(condition, code):
    if not condition:
        raise WorkspaceContextError(code)


def _digest(value):
    return type(value) is str and len(value) == 64 and all(ch in '0123456789abcdef' for ch in value)


def _profile_timestamp(value):
    if value is None:
        return None
    _require(type(value) is str, 'M1_CONTEXT_CATALOG_TIMESTAMP_INVALID')
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise WorkspaceContextError('M1_CONTEXT_CATALOG_TIMESTAMP_INVALID') from None
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
             'M1_CONTEXT_CATALOG_TIMESTAMP_INVALID')
    return parsed


@contextmanager
def _source_locks(manager, store):
    # Preview preparation may already own store.lock. Never wait for manager
    # while a workspace writer owns manager and is waiting for that store.
    _require(manager.lock.acquire(blocking=False), 'M1_CONTEXT_SOURCE_LOCK_BUSY')
    try:
        _require(store.lock.acquire(blocking=False), 'M1_CONTEXT_SOURCE_LOCK_BUSY')
        try:
            yield
        finally:
            store.lock.release()
    finally:
        manager.lock.release()


class WorkspaceContextReader:
    """Trusted explicit ports only; bind once after case/provider assembly.

    The caller must first read the case through the existing store, then invoke
    this reader outside writer scopes. The returned case is original JSONB,
    never the default-enriched projection returned by PostgresCaseStore.get().
    """

    def __init__(self, *, role_config: EntryFencePlan, database_name: str,
                 max_source_bytes: int = MAX_BYTES):
        _require(type(role_config) is EntryFencePlan
                 and tuple(getattr(role_config, key) for key in
                           ('application_schema', 'guard_schema', 'owner_role', 'runtime_role', 'authority_role')) == _SCOPE
                 and type(database_name) is str and database_name == _DATABASE,
                 'M1_CONTEXT_APPROVED_TEST_SCOPE_REQUIRED')
        _require(type(max_source_bytes) is int and 0 < max_source_bytes <= MAX_BYTES,
                 'M1_CONTEXT_BOUNDED_SOURCE_REQUIRED')
        self._roles, self._database_name = role_config, database_name
        self._max_source_bytes = max_source_bytes
        self._app = self._gate = None
        self._bind_lock = RLock()

    def _database(self, database):
        _require(type(database) is PostgresDatabase
                 and type(database.settings) is PostgresSettings
                 and database.settings.schema == self._roles.application_schema,
                 'M1_CONTEXT_EXACT_RUNTIME_DATABASE_REQUIRED')
        parameters = conninfo_to_dict(database.settings.dsn)
        _require(not any(key.startswith('PG') and value for key, value in os.environ.items())
                 and set(parameters) <= {'host', 'port', 'dbname', 'user', 'password'}
                 and parameters.get('host') == '127.0.0.1' and parameters.get('port') == '54805'
                 and parameters.get('dbname') == self._database_name
                 and parameters.get('user') == self._roles.runtime_role,
                 'M1_CONTEXT_APPROVED_DATABASE_ROUTE_REQUIRED')
        return dict(host=parameters['host'], port=int(parameters['port']), dbname=parameters['dbname'],
                    user=parameters['user'], schema=database.settings.schema,
                    connect_timeout=database.settings.connect_timeout_seconds,
                    application_name=database.settings.application_name)

    def _runtime_context(self, store, provider):
        database = self._database(store.database)
        channel, capabilities = provider.channel, provider.capabilities
        _require(type(channel) is ExplicitHttpChannel and type(channel.client) is httpx.Client
                 and channel.client.trust_env is False and channel.client.follow_redirects is False,
                 'M1_CONTEXT_EXPLICIT_LOOPBACK_CHANNEL_REQUIRED')
        url = channel.client.base_url
        rendered = str(url)
        _require(url.scheme in {'http', 'https'} and url.host in {'127.0.0.1', '::1'}
                 and not url.username and not url.password and not url.query and not url.fragment
                 and not any(char in rendered for char in ('@', '?', '#'))
                 and url.path == '/' and (url.port is None or 1 <= url.port <= 65535),
                 'M1_CONTEXT_LOOPBACK_ROUTE_IDENTITY_REQUIRED')
        _require(type(capabilities) is dict and capabilities.get('transport') == TRANSPORT
                 and capabilities.get('binding_protocol') == PROTOCOL
                 and type(capabilities.get('epoch')) is str
                 and re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', capabilities['epoch']) is not None,
                 'M1_CONTEXT_CACHED_RUNTIME_IDENTITY_REQUIRED')
        return dict(database=database, model=dict(base_url=rendered,
                    worker_epoch=capabilities['epoch'], transport=capabilities['transport'],
                    binding_protocol=capabilities['binding_protocol']))

    def _principal_sql(self):
        """One catalog snapshot, including inherited privileged memberships."""
        # Name-to-regclass/regprocedure casts would require guard-schema USAGE,
        # which the runtime correctly lacks. Inspect public catalog OIDs instead.
        def function_oid(name, arguments):
            argument_checks = sql.SQL('').join(sql.SQL('''
                AND p.proargtypes[{}]=(SELECT t.oid FROM pg_catalog.pg_type t
                    JOIN pg_catalog.pg_namespace nt ON nt.oid=t.typnamespace
                    WHERE nt.nspname='pg_catalog' AND t.typname={})
            ''').format(sql.Literal(index), sql.Literal(argument))
                for index, argument in enumerate(arguments))
            return sql.SQL('''(SELECT p.oid FROM pg_catalog.pg_proc p
                JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
                WHERE n.nspname={} AND p.proname={} AND p.pronargs={} {})''').format(
                    sql.Literal(self._roles.guard_schema), sql.Literal(name),
                    sql.Literal(len(arguments)), argument_checks)

        table_oid = sql.SQL('''(SELECT c.oid FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname={} AND c.relname='entry_fence' AND c.relkind IN ('r','p'))''').format(
                sql.Literal(self._roles.guard_schema))
        return sql.SQL("""jsonb_build_object(
            'database', current_database(), 'current_user', current_user::text,
            'session_user', session_user::text,
            'login', (SELECT rolcanlogin FROM pg_catalog.pg_roles WHERE rolname=current_user),
            'roles_present', (SELECT count(*)=3 FROM pg_catalog.pg_roles WHERE rolname=ANY(%s)),
            'dangerous_membership', EXISTS (
                SELECT 1 FROM pg_catalog.pg_roles r WHERE pg_has_role(current_user, r.oid, 'MEMBER')
                AND (r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolbypassrls OR r.rolreplication)),
            'authority_membership', EXISTS (
                SELECT 1 FROM pg_catalog.pg_roles r WHERE r.rolname=ANY(%s)
                AND pg_has_role(current_user, r.oid, 'MEMBER')),
            'protected_tables', (SELECT count(*) FROM pg_catalog.pg_class c
                JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                WHERE c.relkind IN ('r','p') AND ((n.nspname=%s AND c.relname=ANY(%s))
                    OR (n.nspname=%s AND c.relname='entry_fence'))),
            'protected_owner', EXISTS (SELECT 1 FROM pg_catalog.pg_class c
                JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                WHERE ((n.nspname=%s AND c.relname=ANY(%s)) OR n.nspname=%s)
                AND pg_has_role(current_user, c.relowner, 'MEMBER')),
            'guard_write', has_schema_privilege(current_user, %s, 'CREATE')
                OR has_table_privilege(current_user, {}, 'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER'),
            'guard_execute', has_function_privilege(current_user, {}, 'EXECUTE')
                OR has_function_privilege(current_user, {}, 'EXECUTE')
                OR has_function_privilege(current_user, {}, 'EXECUTE'),
            'replication_origin', current_setting('session_replication_role')='origin'
        )""").format(
            table_oid,
            function_oid('begin_entry', ('text', 'text', 'jsonb', 'jsonb', 'jsonb')),
            function_oid('release_entry', ('jsonb',)), function_oid('read_entry', ()),
        )

    def _principal_parameters(self):
        roles = self._roles
        return ([roles.owner_role, roles.runtime_role, roles.authority_role],
                [roles.owner_role, roles.authority_role],
                roles.application_schema, _PROTECTED_TABLES, roles.guard_schema,
                roles.application_schema, _PROTECTED_TABLES, roles.guard_schema, roles.guard_schema)

    def _principal(self, connection, value):
        expected = {'database': self._database_name, 'current_user': self._roles.runtime_role,
                    'session_user': self._roles.runtime_role, 'login': True, 'roles_present': True,
                    'dangerous_membership': False, 'authority_membership': False,
                    'protected_tables': 4, 'protected_owner': False, 'guard_write': False,
                    'guard_execute': False, 'replication_origin': True}
        _require(type(value) is dict and canonical(value) == canonical(expected)
                 and getattr(getattr(connection, 'pgconn', None), 'used_password', None) == 1
                 and connection.info.user == self._roles.runtime_role
                 and connection.info.dbname == self._database_name
                 and connection.info.host == '127.0.0.1' and str(connection.info.port) == '54805',
                 'M1_CONTEXT_AUTHENTICATED_RUNTIME_PRINCIPAL_REQUIRED')

    def preflight_runtime_database(self, database):
        """Read-only principal check BEFORE a factory may construct/write stores.

        No cached success bypass: __call__ independently repeats this check on
        its actual case-read connection. No credentials are accepted or created.
        """
        self._database(database)
        try:
            with database.session(autocommit=False) as connection:
                with connection.transaction():
                    connection.execute('SET TRANSACTION READ ONLY')
                    connection.execute("SET LOCAL statement_timeout = '5s'")
                    row = connection.execute(sql.SQL('SELECT {}').format(self._principal_sql()),
                                             self._principal_parameters()).fetchone()
                    _require(type(row) is tuple and len(row) == 1, 'M1_CONTEXT_RUNTIME_PRINCIPAL_UNAVAILABLE')
                    self._principal(connection, row[0])
        except WorkspaceContextError:
            raise
        except Exception:
            raise WorkspaceContextError('M1_CONTEXT_RUNTIME_PRINCIPAL_UNAVAILABLE') from None

    def bind(self, app, gate):
        """Bind the exact app/gate once; no registration, SQL or state mutation."""
        with self._bind_lock:
            _require(self._app is None and type(gate) is SourceMutationGate,
                     'M1_CONTEXT_BIND_ONCE_WITH_EXACT_GATE')
            _require(getattr(app.state, 'source_mutation_gate', None) is gate,
                     'M1_CONTEXT_APP_GATE_MISMATCH')
            self._app, self._gate = app, gate

    def _objects(self):
        state = self._app.state
        store, manager = state.store, state.workspace_manager
        provider, derivatives = state.providers.get(MODEL_ID), state.derivatives
        _require(type(store) is PostgresCaseStore and type(manager) is WorkspaceManager
                 and type(provider) is RemoteBoundTransportCandidate and type(derivatives) is DerivativeService,
                 'M1_CONTEXT_REVIEWED_OBJECTS_REQUIRED')
        self._database(store.database)
        _require(state.source_mutation_gate is self._gate
                 and store.source_mutation_gate is self._gate and manager.source_mutation_gate is self._gate
                 and manager.app is self._app and manager.store is store
                 and manager.postgres_mode is True and manager.postgres_database is store.database
                 and type(manager.postgres_catalog) is PostgresWorkspaceCatalog
                 and manager.postgres_catalog.database is store.database,
                 'M1_CONTEXT_SHARED_BINDING_REQUIRED')
        _require(state.workspace_id == store.workspace_id == manager.active_workspace.id,
                 'M1_CONTEXT_WORKSPACE_IDENTITY_CHANGED')
        return store, provider, manager, derivatives

    @staticmethod
    def _pins(provider):
        _require(type(provider.capabilities) is dict, 'M1_CONTEXT_CACHED_PINS_REQUIRED')
        # Call the reviewed implementation, never an overridden method/RPC hook.
        identity = RemoteBoundTransportCandidate.prism_preview_identity(provider)
        pins = identity['model_pins']
        _require(type(pins) is dict and set(pins) == {
            'model_id', 'source_revision', 'preprocessing', 'config_sha256', 'checkpoint_sha256'}
            and pins['model_id'] == MODEL_ID
            and all(type(pins[key]) is str and 0 < len(pins[key]) <= 1024
                    for key in ('source_revision', 'preprocessing'))
            and _digest(pins['config_sha256']) and type(pins['checkpoint_sha256']) is dict
            and 0 < len(pins['checkpoint_sha256']) <= 64
            and all(type(key) is str and 0 < len(key) <= 200 and _digest(value)
                    for key, value in pins['checkpoint_sha256'].items()), 'M1_CONTEXT_REVIEWED_PIN_SCHEMA_REQUIRED')
        return pins

    def __call__(self, image_id):
        _require(self._app is not None and type(image_id) is str and 0 < len(image_id) <= 160,
                 'M1_CONTEXT_BOUND_IMAGE_REQUIRED')
        try:
            before = self._gate.snapshot()
            _require(before.writers == 0 and before.state in {'OPEN', 'FENCED', 'QUARANTINED'},
                     'M1_CONTEXT_WRITER_ACTIVE')
            objects = self._objects()
            store, provider, manager, _ = objects
            with _source_locks(manager, store):
                _require(all(left is right for left, right in zip(objects, self._objects(), strict=True)),
                         'M1_CONTEXT_OBJECTS_CHANGED')
                image = self._app.state.images.get(image_id)
                admission = deepcopy(self._app.state.admissions.get(image_id))
                _require(type(image) is BridgeImage and type(image.data) is bytes
                         and 0 < len(image.data) <= self._max_source_bytes,
                         'M1_CONTEXT_IMMUTABLE_BOUNDED_SOURCE_REQUIRED')
                source_hash, pins = sha(image.data), self._pins(provider)
                runtime_context = self._runtime_context(store, provider)
                with store.database.session(autocommit=False) as connection:
                    with connection.transaction():
                        connection.execute('SET TRANSACTION READ ONLY')
                        connection.execute("SET LOCAL statement_timeout = '5s'")
                        row = connection.execute(sql.SQL('''
                            SELECT c.workspace_id,c.case_id,c.revision,c.payload,to_jsonb(w),{}
                            FROM {}.review_cases c JOIN {}.workspaces w USING (workspace_id)
                            WHERE c.workspace_id=%s AND c.case_id=%s
                        ''').format(self._principal_sql(), store._schema, store._schema),
                            (*self._principal_parameters(), store.workspace_id, image_id)).fetchone()
                        _require(type(row) is tuple and len(row) == 6, 'M1_CONTEXT_ORIGINAL_ROW_REQUIRED')
                        self._principal(connection, row[5])
                workspace_id, case_id, revision, case, workspace, _ = row
                _require(workspace_id == store.workspace_id and case_id == image_id
                         and type(revision) is int and revision >= 0 and type(case) is dict
                         and case.get('image_id') == image_id and type(case.get('revision')) is int
                         and case['revision'] == revision and type(workspace) is dict
                         and workspace.get('workspace_id') == workspace_id and workspace.get('archived_at') is None,
                         'M1_CONTEXT_RAW_ROW_IDENTITY_CHANGED')
                _require(type(store._observed.get(image_id)) is str
                         and canonical(case).decode() == store._observed[image_id]
                         and type(store._observed_revision.get(image_id)) is int
                         and store._observed_revision[image_id] == revision,
                         'M1_CONTEXT_LOADED_RAW_CASE_CHANGED')
                fields = ('workspace_id', 'name', 'input_folder', 'output_folder', 'database_path',
                          'note', 'created_at', 'updated_at', 'last_opened')
                # JSONB timestamps and driver datetimes may format the same
                # instant differently. Normalize only the profile projection;
                # the complete raw workspace row remains untouched below.
                profile = PostgresWorkspaceCatalog._profile(tuple(
                    _profile_timestamp(workspace[key]) if key in {'created_at', 'updated_at', 'last_opened'}
                    else workspace[key] for key in fields))
                _require(profile.model_dump(mode='json') == manager.active_workspace.model_dump(mode='json'),
                         'M1_CONTEXT_CATALOG_PROJECTION_CHANGED')
                _require(type(admission) is dict and case.get('admission') == admission
                         and image.image_id == image_id and image.source_origin == admission.get('source_origin')
                         and admission.get('source_sha256') == source_hash
                         and source_identity_reason(case, image, admission) is None
                         and any(case.get(key) == source_hash for key in ('source_sha256', 'image_sha256'))
                         and all(case.get(key) in {None, source_hash} for key in ('source_sha256', 'image_sha256'))
                         and (admission.get('source_metadata') or {}).get('source_sha256') in {None, source_hash},
                         'M1_CONTEXT_RECORDED_SOURCE_CHANGED')
                value = dict(workspace_id=workspace_id, image_id=image_id, case=deepcopy(case),
                             workspace=deepcopy(workspace), admission=admission, source_sha256=source_hash,
                             preparation_context=preparation_context(case), model_pins=pins,
                             runtime_context=runtime_context)
                _require(len(canonical(value)) <= _CONTEXT_LIMIT, 'M1_CONTEXT_LIMIT')
                _require(all(left is right for left, right in zip(objects, self._objects(), strict=True))
                         and self._app.state.images.get(image_id) is image
                         and self._app.state.admissions.get(image_id) == admission
                         and canonical(self._pins(provider)) == canonical(pins)
                         and canonical(self._runtime_context(store, provider)) == canonical(runtime_context)
                         and self._gate.snapshot() == before, 'M1_CONTEXT_CHANGED_DURING_READ')
                return {**value, 'objects': objects}
        except WorkspaceContextError:
            raise
        except Exception:
            raise WorkspaceContextError('M1_CONTEXT_READ_UNAVAILABLE') from None
