"""Windows side of the bounded Hospital M1 QA_SERVER session.

Commands (all fail closed; no ACL, credential, role or schema change):

  workspace --name NAME          create one new TEST_ONLY PostgreSQL workspace profile
  serve --workspace-id ID ...    own an SSH loopback tunnel to the host session, compose
                                 the reviewed workspace authority and serve the review app
  readback --workspace-id ID ... read the pending admission from the host STATUS, verify its
                                 persisted inference provenance in PostgreSQL and publish the
                                 trusted readback receipt to the host run directory

Secrets are read only from the approved private directory or, for the Model API
token, from the approved host file over the existing SSH identity into process
memory. They are never printed, logged or written to new files.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from dr_support.services.filesystem_privacy import has_reparse_component, private_hospital_root
from scripts.qa.configure_m1_test_credentials import PRIVATE_DIRECTORY
from scripts.qa.qualify_m1_entry_fence import AUTHORITY, DATABASE, PLAN, RUNTIME

HOST = 'siripon@100.77.149.83'
SSH_KEY = 'C:/Users/User/.ssh/id_ed25519_dr_train'
SSH = ['C:/Windows/System32/OpenSSH/ssh.exe', '-T', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
       '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10', '-i', SSH_KEY]
REMOTE_PROJECT = '/home/siripon/projects/dr-model-api-qa'
REMOTE_PORT = 7860
AUTHORITY_DIRECTORY = PRIVATE_DIRECTORY / 'workspace-authority'
HOSPITAL_ROOTS = {'UWF': PRIVATE_DIRECTORY / 'hospital-roots' / 'UWF',
                  'CFP': PRIVATE_DIRECTORY / 'hospital-roots' / 'CFP'}
WORKSPACE_FILES = PRIVATE_DIRECTORY / 'workspaces'
_CLEAR = re.compile(r'^(DR_SUPPORT_|MODEL_|PRISM_|RETFOUND_|USPEC_|CVAT_|REMOTE_MODEL_|DR_DEMO_|PG|APP_PROFILE$)')


class SessionError(RuntimeError):
    """Fixed, secret-free refusal codes only."""


def require(value, code):
    if not value:
        raise SessionError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def private_values(name, keys):
    """Exact keys from one bounded file inside the approved private directory."""
    directory, path = PRIVATE_DIRECTORY, PRIVATE_DIRECTORY / name
    require(directory.is_dir() and not has_reparse_component(directory) and private_hospital_root(directory),
            'APPROVED_PRIVATE_CONFIGURATION_CHECK_REQUIRED')
    require(path.is_file() and not has_reparse_component(path) and 0 < path.stat().st_size <= 16384,
            'BOUNDED_APPROVED_PRIVATE_FILE_REQUIRED')
    values = {}
    for line in path.read_bytes().decode('utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, separator, value = line.partition('=')
        require(separator and key in keys and key not in values, 'EXACT_PRIVATE_CONFIGURATION_KEYS_REQUIRED')
        values[key] = value.strip()
    require(set(values) == set(keys) and values['DR_SUPPORT_DATABASE_SCHEMA'] == PLAN.application_schema
            and values['DR_SUPPORT_DATABASE_MIGRATION_MODE'] == 'verify', 'EXACT_VERIFY_CONFIGURATION_REQUIRED')
    return values


def _route(dsn, user):
    parameters = conninfo_to_dict(dsn)
    require(set(parameters) == {'host', 'port', 'dbname', 'user', 'password'} and parameters['host'] == '127.0.0.1'
            and parameters['port'] == '54805' and parameters['dbname'] == DATABASE and parameters['user'] == user
            and bool(parameters['password']), 'EXACT_APPROVED_PASSWORD_ROUTE_REQUIRED')


def runtime_values():
    values = private_values('m1_runtime.env', {'DR_SUPPORT_DATABASE_URL', 'DR_SUPPORT_DATABASE_SCHEMA',
                                               'DR_SUPPORT_DATABASE_MIGRATION_MODE'})
    _route(values['DR_SUPPORT_DATABASE_URL'], RUNTIME)
    return values


def authority_database():
    from dr_support.persistence import PostgresDatabase, PostgresSettings
    values = private_values('m1_authority.env', {'DR_SUPPORT_AUTHORITY_DATABASE_URL', 'DR_SUPPORT_DATABASE_SCHEMA',
                                                 'DR_SUPPORT_DATABASE_MIGRATION_MODE'})
    _route(values['DR_SUPPORT_AUTHORITY_DATABASE_URL'], AUTHORITY)
    return PostgresDatabase(PostgresSettings(values['DR_SUPPORT_AUTHORITY_DATABASE_URL'],
                                             schema=values['DR_SUPPORT_DATABASE_SCHEMA']))


def roots():
    for root in HOSPITAL_ROOTS.values():
        require(root.is_dir() and not has_reparse_component(root) and private_hospital_root(root),
                'APPROVED_PRIVATE_HOSPITAL_ROOTS_REQUIRED')
    return {modality: str(root) for modality, root in HOSPITAL_ROOTS.items()}


@contextmanager
def session_environment(*, workspace_id=None, model_port=None, token=None):
    previous = dict(os.environ)
    try:
        for key in list(os.environ):
            if _CLEAR.match(key):
                del os.environ[key]
        os.environ.update(runtime_values())
        os.environ.update(DR_SUPPORT_CASE_STORE='postgres', APP_PROFILE='review', MODEL_RUNTIME='remote',
                          WORKERS='1', DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL='1',
                          DR_SUPPORT_HOSPITAL_SCOPE='PRIVATE_PROJECT_EVALUATION',
                          DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOTS=json.dumps(roots(), sort_keys=True))
        if workspace_id is not None:
            os.environ['DR_SUPPORT_WORKSPACE_ID'] = workspace_id
        if model_port is not None:
            os.environ.update(DR_SUPPORT_DEPLOYMENT_PROFILE='QA_SERVER',
                              REMOTE_MODEL_URL=f'http://127.0.0.1:{model_port}', REMOTE_MODEL_NAME='dr-train M1')
        if token is not None:
            os.environ['REMOTE_MODEL_TOKEN'] = token
        yield
    finally:
        os.environ.clear()
        os.environ.update(previous)


def ssh(command, *, data=None, timeout=30):
    completed = subprocess.run([*SSH, HOST, command], input=data, capture_output=True, timeout=timeout)
    require(completed.returncode == 0, 'APPROVED_SSH_COMMAND_FAILED')
    return completed.stdout


def host_token():
    """Owner-approved: read the existing host Model API token into memory only."""
    raw = ssh("python3 -c \"import sys; sys.path.insert(0, '" + REMOTE_PROJECT
              + "/deployments/demo-batch-20261022-b03r8/base-q06'); from approved_token_reader import "
              "read_private_token; sys.stdout.write(read_private_token('" + REMOTE_PROJECT
              + "/config/private/model-api.env'))\"")
    token = raw.decode('ascii').strip()
    require(32 <= len(token) <= 1024 and token.isascii() and ' ' not in token, 'APPROVED_HOST_TOKEN_REQUIRED')
    return token


def port_free(port):
    with socket.socket() as probe:
        return probe.connect_ex(('127.0.0.1', port)) != 0


@contextmanager
def owned_tunnel(port):
    """Our own loopback forward to the host session's loopback listener."""
    require(type(port) is int and 1024 < port < 65536 and port_free(port), 'FREE_LOCAL_TUNNEL_PORT_REQUIRED')
    process = subprocess.Popen([*SSH, '-N', '-o', 'ExitOnForwardFailure=yes',
                                '-L', f'127.0.0.1:{port}:127.0.0.1:{REMOTE_PORT}', HOST],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        until = time.monotonic() + 15
        while port_free(port) and time.monotonic() < until and process.poll() is None:
            time.sleep(.1)
        require(process.poll() is None and not port_free(port), 'OWNED_TUNNEL_NOT_ESTABLISHED')
        yield process
    finally:
        process.terminate()
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            process.kill()


def create_workspace(name):
    from datetime import datetime, timezone
    from uuid import uuid4
    from dr_support.contracts import WorkspaceProfile
    from dr_support.persistence import PostgresDatabase, PostgresSettings, PostgresWorkspaceCatalog, SchemaMigrator
    from dr_support.services.source_mutation_gate import SourceMutationGate
    require(re.fullmatch(r'[A-Za-z0-9 _-]{3,60}', name) is not None, 'SIMPLE_WORKSPACE_NAME_REQUIRED')
    with session_environment():
        database = PostgresDatabase(PostgresSettings.from_env())
        SchemaMigrator(database).verify()
        workspace_id = 'ws_m1_' + uuid4().hex[:20]
        folder = WORKSPACE_FILES / workspace_id
        require(not folder.exists(), 'NEW_WORKSPACE_FOLDER_REQUIRED')
        (folder / 'input').mkdir(parents=True)
        (folder / 'output').mkdir()
        require(private_hospital_root(folder), 'PRIVATE_WORKSPACE_FOLDER_REQUIRED')
        stamp = datetime.now(timezone.utc).isoformat()
        profile = WorkspaceProfile(id=workspace_id, name='TEST_ONLY ' + name, input_folder=str(folder / 'input'),
                                   output_folder=str(folder / 'output'), database_path=None,
                                   note='TEST_ONLY Hospital M1 QA_SERVER engineering workspace; not physician data',
                                   created_at=stamp, updated_at=stamp, last_opened=stamp)
        with SourceMutationGate().writer():
            PostgresWorkspaceCatalog(database).create_and_activate(profile)
    print(json.dumps({'workspace_id': workspace_id, 'name': profile.name}))
    return workspace_id


def compose(workspace_id, prism_pins, model_port, token):
    """Exact reviewed composition; preflight and recovery precede app construction."""
    import httpx
    from dr_support.api._factory import create_app
    from dr_support.persistence.entry_fence import PostgresEntryFence
    from dr_support.providers.prism_remote_bound import ExplicitHttpChannel
    from dr_support.providers.prism_workspace_remote import WorkspaceRemotePRISM, WorkspaceStatusReader
    from dr_support.services.m1_workspace_context import WorkspaceContextReader
    from dr_support.services.prism_workspace_authority import WorkspaceAuthority
    channel = ExplicitHttpChannel(f'http://127.0.0.1:{model_port}', transport=httpx.HTTPTransport(retries=0),
                                  auth_headers=lambda *_: {'Authorization': 'Bearer ' + token})
    status_reader = WorkspaceStatusReader(channel)
    reader = WorkspaceContextReader(role_config=PLAN, database_name=DATABASE)
    fence = PostgresEntryFence(authority_database(), plan=PLAN, authenticated_status_reader=status_reader)
    authority = WorkspaceAuthority(AUTHORITY_DIRECTORY, context_reader=reader, database_fence=fence,
                                   authenticated_status_reader=status_reader)
    authority.recover()
    provider = WorkspaceRemotePRISM(channel, source_authority=authority, expected_pins=prism_pins)
    provider.negotiate()
    app = create_app(include_samples=False, include_demo_fixtures=False, case_store_mode='postgres',
                     workspace_id=workspace_id, workspace_authority=authority, workspace_prism_provider=provider)
    return app, authority, channel


def serve(args):
    import uvicorn
    prism_pins = json.loads(Path(args.prism_pins).read_bytes())
    require(port_free(args.app_port), 'FREE_APP_PORT_REQUIRED')
    token = host_token()
    with owned_tunnel(args.model_port), session_environment(workspace_id=args.workspace_id,
                                                            model_port=args.model_port, token=token):
        app, authority, channel = compose(args.workspace_id, prism_pins, args.model_port, token)
        print(json.dumps({'phase': 'SERVING', 'url': f'http://127.0.0.1:{args.app_port}/app/',
                          'workspace_id': args.workspace_id, 'profile': 'QA_SERVER'}), flush=True)
        try:
            uvicorn.run(app, host='127.0.0.1', port=args.app_port, workers=1, access_log=False)
        finally:
            authority.close()
            channel.close()
    return 0


# ---------------------------------------------------------------- readback

def remote_status(run):
    require(re.fullmatch(REMOTE_PROJECT + r'/runs/m1-server-[A-Za-z0-9_-]{1,80}', run) is not None,
            'APPROVED_REMOTE_RUN_REQUIRED')
    return json.loads(ssh(f'cat {run}/STATUS.json'))


def pending_request(status):
    pending = [(request_id, entry) for request_id, entry in status['requests'].items()
               if entry.get('state') == 'RESPONSE_OBSERVED']
    require(len(pending) == 1, 'EXACTLY_ONE_PENDING_READBACK_REQUIRED')
    return pending[0]


def verify_persisted(case, entry, models):
    """Independent PostgreSQL provenance check for one admitted operation."""
    history = [item for item in case.get('inference_history', [])
               if item.get('model_id') == entry['model_id'] and item.get('source_sha256') == entry['source_sha256']]
    require(history, 'PERSISTED_INFERENCE_NOT_FOUND')
    latest = history[-1]
    pins = models[entry['model_id']]['pins']
    provenance = (latest.get('result') or {}).get('provenance') or {}
    checks = [
        latest.get('status') in {'APPLIED', 'STALE_RESULT'},
        latest.get('task') == ('lesion-roi' if entry['model_id'] == 'prism-dr-5fold' else 'global'),
        (latest.get('result') or {}).get('model_id') == entry['model_id'],
        (latest.get('result') or {}).get('modality') == entry['modality'],
        provenance.get('checkpoint_sha256') == pins['checkpoint_sha256'],
        provenance.get('source_revision') == pins['source_revision'],
        entry['model_id'] != 'prism-dr-5fold' or (latest.get('preview_binding') or {}).get('model_pins') == pins,
    ]
    return latest, all(checks)


def readback(args):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'model-server'))
    import m1_operations as operations
    from dr_support.persistence import PostgresDatabase, PostgresSettings
    models = operations.reviewed_models(Path(args.models).read_bytes(), json.loads(Path(args.prism_pins).read_bytes()))
    request_id, entry = pending_request(remote_status(args.run))
    with session_environment(workspace_id=args.workspace_id):
        database = PostgresDatabase(PostgresSettings.from_env())
        with database.session(autocommit=False) as connection:
            with connection.transaction():
                connection.execute('SET TRANSACTION READ ONLY')
                rows = connection.execute(sql.SQL(
                    "SELECT payload FROM {}.review_cases WHERE workspace_id=%s AND "
                    "(payload->>'source_sha256'=%s OR payload->>'image_sha256'=%s)").format(
                        sql.Identifier(database.settings.schema)),
                    (args.workspace_id, entry['source_sha256'], entry['source_sha256'])).fetchall()
    require(len(rows) == 1, 'EXACT_PERSISTED_CASE_REQUIRED')
    persisted, matches = verify_persisted(rows[0][0], entry, models)
    value = {'request_id': request_id, 'admission_id': entry['admission_id'],
             'readback_sha256': sha(canonical(persisted)), 'matches': matches}
    # The host parent reads trusted readback only from its separate readback/ directory.
    publish = ("python3 -c \"import os,sys,uuid; d=sys.argv[1]; p=os.path.join(d,sys.argv[2]+'.readback.json'); "
               "t=os.path.join(d,'.'+uuid.uuid4().hex+'.pending'); b=sys.stdin.buffer.read(); "
               "f=open(t,'xb'); f.write(b); f.flush(); os.fsync(f.fileno()); f.close(); os.link(t,p); os.unlink(t)\" "
               f"{args.run}/readback {request_id}")
    ssh(publish, data=canonical(value))
    print(json.dumps({'request_id': request_id, 'operation_id': entry['operation_id'], 'matches': matches,
                      'readback_sha256': value['readback_sha256']}))
    return 0 if matches else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['workspace', 'serve', 'readback'])
    parser.add_argument('--name')
    parser.add_argument('--workspace-id')
    parser.add_argument('--prism-pins', type=Path)
    parser.add_argument('--models', type=Path)
    parser.add_argument('--model-port', type=int, default=47860)
    parser.add_argument('--app-port', type=int, default=8010)
    parser.add_argument('--run')
    args = parser.parse_args()
    try:
        if args.command == 'workspace':
            create_workspace(args.name)
            return 0
        return serve(args) if args.command == 'serve' else readback(args)
    except SessionError as error:
        print(json.dumps({'status': 'REFUSED', 'code': str(error)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
