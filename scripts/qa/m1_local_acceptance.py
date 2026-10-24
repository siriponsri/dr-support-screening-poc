"""Read-only PostgreSQL evidence for local Hospital M1 acceptance checks (TEST_ONLY).

Captures what the review app persisted for one case so a GUI action can be
checked against an independent SQL read (AC-07) and compared across an app
restart (AC-08). It never writes to the database, never prints the database
URL or credentials, and never prints patient keys.

Commands:

  snapshot --workspace-id ID --case-id ID --label NAME [--out DIR]
      Read the case in a READ ONLY transaction and print a JSON record of the
      clinician-owned fields with canonical SHA-256 digests. With --out the
      record is also written to DIR/NAME.json (DIR must already exist).
  compare BEFORE.json AFTER.json
      Print which recorded fields are equal between two snapshots.
  Identity-bearing payload keys are never hashed per key; see IDENTITY_KEYS.
  failure-checks --workspace-id ID --case-id ID [--base-url URL] [--out DIR]
      Send rejected requests to the running local app (stale revision,
      malformed body, unknown case, analysis while the Model API is
      unreachable) and prove with before/after SQL reads that the case did not
      change. It stops unless the app and the SQL read show the same revision
      and the Model API reports the model unreachable, so no real inference is
      sent. Use only on a TEST_ONLY workspace.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib import error as urlerror, request as urlrequest

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_KEYS = ('DR_SUPPORT_DATABASE_URL', 'DR_SUPPORT_DATABASE_SCHEMA', 'DR_SUPPORT_DATABASE_CONNECT_TIMEOUT')
# Top-level keys that carry patient identity or filenames: never hashed per key
# (a short identifier could be recovered by guessing).
IDENTITY_KEYS = frozenset({'patient_key', 'patient_candidate', 'patient_display_label', 'visit_context',
                           'resolution_history', 'resolver_evidence', 'resolver_ui', 'filename', 'display_name',
                           'image_url', 'source', 'source_reference'})
# Admission subfields that carry identity; the rest of admission is hashed.
ADMISSION_IDENTITY = frozenset({'trusted_patient_key', 'filename', 'source_reference', 'integrity'})
# Only these server details are recorded verbatim; anything else is dropped.
SAFE_DETAILS = frozenset({'Case changed; reload before reviewing', 'Image not admitted',
                          'AI analysis is not available; manual review remains available.'})
FIELDS = ('revision', 'grade_status', 'clinician_review', 'human_annotations', 'annotation_confirmation',
          'core_completeness', 'ai_annotation_reviews', 'inference_history', 'source_sha256', 'quality_state')


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def load_database_environment(env_file: Path) -> None:
    """Copy only the database keys from the app's .env into this process."""
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding='utf-8').splitlines():
        key, separator, value = line.strip().partition('=')
        if separator and key in DB_KEYS and value and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def read_case(workspace_id: str, case_id: str):
    from psycopg import sql
    from dr_support.persistence import PostgresDatabase, PostgresSettings
    database = PostgresDatabase(PostgresSettings.from_env())
    with database.session(autocommit=False) as connection:
        with connection.transaction():
            connection.execute('SET TRANSACTION READ ONLY')
            rows = connection.execute(sql.SQL(
                'SELECT revision, payload FROM {}.review_cases WHERE workspace_id=%s AND case_id=%s'
            ).format(sql.Identifier(database.settings.schema)), (workspace_id, case_id)).fetchall()
    if len(rows) != 1:
        raise SystemExit('EXACT_PERSISTED_CASE_REQUIRED')
    return rows[0]


def payload_key_digests(payload: dict) -> dict:
    digests = {}
    for key, value in sorted(payload.items()):
        if key in IDENTITY_KEYS:
            continue
        if key == 'admission' and isinstance(value, dict):
            value = {name: item for name, item in value.items() if name not in ADMISSION_IDENTITY}
        digests[key] = digest(value)
    return digests


def record_from_payload(revision: int, payload: dict) -> dict:
    review = payload.get('clinician_review') or None
    annotations = [{key: shape.get(key) for key in ('shape_id', 'type', 'label', 'geometry', 'source', 'reviewer')}
                   for shape in payload.get('human_annotations') or []]
    confirmation = payload.get('annotation_confirmation') or None
    fields = {
        'revision': revision,
        'grade_status': payload.get('grade_status'),
        'clinician_review': None if review is None else {key: review.get(key) for key in (
            'final_grade', 'review_action', 'reviewer', 'timestamp', 'revision')},
        'human_annotations': annotations,
        'annotation_confirmation': None if confirmation is None else {key: confirmation.get(key) for key in (
            'reviewer', 'timestamp', 'annotation_set_hash')},
        'core_completeness': ((payload.get('annotation_completeness') or {}).get('CORE') or {}).get('state'),
        'ai_annotation_reviews': {'count': len(payload.get('ai_annotation_reviews') or []),
                                  'sha256': digest(payload.get('ai_annotation_reviews') or [])},
        'inference_history': {'count': len(payload.get('inference_history') or []),
                              'sha256': digest(payload.get('inference_history') or [])},
        'source_sha256': payload.get('source_sha256') or payload.get('image_sha256'),
        'quality_state': (payload.get('admission') or {}).get('quality_state'),
    }
    from dr_support.presentation import annotation_set_hash
    recomputed = annotation_set_hash(payload)
    return {'fields': fields, 'field_sha256': {key: digest(value) for key, value in fields.items()},
            'payload_sha256': digest(payload),
            # Per top-level key, so a whole-payload change can be attributed.
            'payload_key_sha256': payload_key_digests(payload),
            # The stored confirmation hash must equal the hash of the current human set.
            'annotation_set_hash_recomputed': recomputed,
            'annotation_set_hash_matches': confirmation is not None
            and confirmation.get('annotation_set_hash') == recomputed}


def snapshot(args) -> int:
    # The repository .env, then the Windows launcher's project-owned PostgreSQL file.
    checkout = Path(args.checkout) if args.checkout else REPO_ROOT
    for env_file in (checkout / '.env', checkout / 'local-state' / 'release' / 'postgres.env'):
        load_database_environment(env_file)
    revision, payload = read_case(args.workspace_id, args.case_id)
    record = {'label': args.label, 'workspace_id': args.workspace_id, 'case_id': args.case_id,
              'evidence_type': 'TEST_ONLY_INDEPENDENT_SQL_READBACK', **record_from_payload(revision, payload)}
    text = json.dumps(record, indent=2, sort_keys=True, default=str)
    if args.out:
        directory = Path(args.out)
        if not directory.is_dir():
            raise SystemExit('EXISTING_EVIDENCE_DIRECTORY_REQUIRED')
        (directory / f'{args.label}.json').write_text(text + '\n', encoding='utf-8')
    print(text)
    return 0


def compare(args) -> int:
    before = json.loads(Path(args.before).read_text(encoding='utf-8'))
    after = json.loads(Path(args.after).read_text(encoding='utf-8'))
    result = {key: before['field_sha256'].get(key) == after['field_sha256'].get(key) for key in FIELDS}
    result['payload'] = before['payload_sha256'] == after['payload_sha256']
    keys = set(before.get('payload_key_sha256', {})) | set(after.get('payload_key_sha256', {}))
    result['payload_keys_changed'] = sorted(key for key in keys if before.get('payload_key_sha256', {}).get(key)
                                            != after.get('payload_key_sha256', {}).get(key))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def http_json(method: str, url: str, body: bytes | None, timeout: float = 120):
    started = time.monotonic()
    request = urlrequest.Request(url, data=body, method=method, headers={'Content-Type': 'application/json'})
    try:
        with urlrequest.urlopen(request, timeout=timeout) as response:
            status, text = response.status, response.read()
    except urlerror.HTTPError as exc:
        status, text = exc.code, exc.read()
    try:
        detail = json.loads(text or b'{}').get('detail')
    except (ValueError, AttributeError):
        detail = None
    return {'status': status, 'seconds': round(time.monotonic() - started, 2),
            'detail': detail if isinstance(detail, str) and detail in SAFE_DETAILS else None}


def failure_checks(args) -> int:
    checkout = Path(args.checkout) if args.checkout else REPO_ROOT
    for env_file in (checkout / '.env', checkout / 'local-state' / 'release' / 'postgres.env'):
        load_database_environment(env_file)
    base, case = args.base_url.rstrip('/'), args.case_id

    def state():
        revision, payload = read_case(args.workspace_id, case)
        return revision, record_from_payload(revision, payload)

    revision, before = state()
    current = json.loads(urlrequest.urlopen(f'{base}/v1/cases/{case}', timeout=30).read())
    # The app and the SQL read must describe the same case, or the stale request could land elsewhere.
    if current.get('revision') != revision:
        raise SystemExit('APP_AND_DATABASE_MUST_SHOW_THE_SAME_REVISION')
    models = json.loads(urlrequest.urlopen(f'{base}/v1/models', timeout=60).read())
    if any(model.get('model_id') == args.model_id and (model.get('ready') or model.get('status') == 'LOADED')
           for model in models):
        raise SystemExit('MODEL_API_REACHABLE_NO_REAL_REQUEST_SENT')
    checks = {
        # A revision far ahead of the current one can never be accepted.
        'stale_revision_review': http_json('POST', f'{base}/v1/cases/{case}/review', json.dumps(
            {'revision': revision + 10_000, 'action': 'ACCEPT', 'reviewer': 'TEST_ONLY_ENGINEERING',
             'grade': 0}).encode()),
        'malformed_review_body': http_json('POST', f'{base}/v1/cases/{case}/review', b'{not json'),
        'unknown_case': http_json('GET', f'{base}/v1/cases/{"0" * 64}', None),
        'analysis_while_model_api_unreachable': http_json('POST', f'{base}/v1/infer/global', json.dumps(
            {'image_id': case, 'modality': current.get('modality'), 'model_id': args.model_id}).encode()),
    }
    _, after = state()
    unchanged = {key: before['field_sha256'][key] == after['field_sha256'][key] for key in FIELDS}
    result = {'evidence_type': 'TEST_ONLY_CONTROLLED_FAILURE', 'workspace_id': args.workspace_id, 'case_id': case,
              'checks': checks, 'case_fields_unchanged': unchanged,
              'expected': {'stale_revision_review': 409, 'malformed_review_body': 422, 'unknown_case': 404,
                           'analysis_while_model_api_unreachable': 'non-2xx, bounded time, no inference entry'}}
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        directory = Path(args.out)
        if not directory.is_dir():
            raise SystemExit('EXISTING_EVIDENCE_DIRECTORY_REQUIRED')
        (directory / 'ac12-failure-checks.json').write_text(text + '\n', encoding='utf-8')
    print(text)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    take = commands.add_parser('snapshot')
    take.add_argument('--workspace-id', required=True)
    take.add_argument('--case-id', required=True)
    take.add_argument('--label', required=True)
    take.add_argument('--out')
    take.add_argument('--checkout', help='checkout whose running app is checked (default: this one)')
    diff = commands.add_parser('compare')
    diff.add_argument('before')
    diff.add_argument('after')
    fail = commands.add_parser('failure-checks')
    fail.add_argument('--workspace-id', required=True)
    fail.add_argument('--case-id', required=True)
    fail.add_argument('--base-url', default='http://127.0.0.1:8000')
    fail.add_argument('--out')
    fail.add_argument('--checkout')
    fail.add_argument('--model-id', default='retfound-aptos5')
    args = parser.parse_args(argv)
    return {'snapshot': snapshot, 'compare': compare, 'failure-checks': failure_checks}[args.command](args)


if __name__ == '__main__':
    sys.path.insert(0, str(REPO_ROOT))
    raise SystemExit(main())
