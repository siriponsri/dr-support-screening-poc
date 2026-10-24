"""One-time recorded source identity projection for an approved M1 workspace.

Part B of docs/milestone/m1/M1_RECORDED_SOURCE_IDENTITY_AMENDMENT.md. Not part of
the app, UI or API, and never scheduled.

Commands (all fail closed; no ACL, credential, role or schema change):

  plan  --workspace-id ID --out FILE
        read-only: classify every case and write the plan (hashes and reason codes
        only; no filenames, paths or clinical fields); prints the plan SHA-256
  apply --workspace-id ID --plan FILE --plan-sha256 HEX --backup-receipt FILE --out DIR
        only for a plan the owner approved: one transaction, refused whole if any
        eligible case changed since the plan; writes a private pre-image, the
        receipt and an independent readback

Outputs must be new and inside the approved private directory (M1PrivateConfig).

The written value always comes from the recorded admission hash. The current
source bytes, hashed by the normal admission scanner, can only veto a case.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from dr_support.persistence import DatabaseUnavailableError
from dr_support.services.filesystem_privacy import has_reparse_component, private_hospital_root
from dr_support.services.source_identity import RECORDED_KEYS, admitted_source_hash
from scripts.qa import m1_server_app as launcher
from scripts.qa.configure_m1_test_credentials import PRIVATE_DIRECTORY

PLAN_SCHEMA = 'm1-recorded-source-projection-plan.v1'
RECEIPT_SCHEMA = 'm1-recorded-source-projection-receipt.v1'
COMMAND_VERSION = 1
EVENT_ACTION = 'RECORDED_SOURCE_IDENTITY_PROJECTION'
# Owner approval 2026-10-24 (chat): this workspace only. Others need their own approval.
APPROVED_WORKSPACES = frozenset({'ws_m1_63ed86c7d44f46d59479'})
APP_PORTS = (8000, 8010)
MODEL_PORTS = (47860,)  # The launcher's default model tunnel.
CLASSES = ('ELIGIBLE', 'ALREADY_RECORDED', 'CONFLICT', 'INELIGIBLE')
REPOSITORY = Path(__file__).resolve().parents[2]


class ProjectionError(RuntimeError):
    """Fixed refusal codes only."""


def require(value, code):
    if not value:
        raise ProjectionError(code)


def classify(case_id, revision, payload, current_hashes):
    """Return (class, reason) for one raw case row (amendment RSI-B03/B04)."""
    if (not isinstance(payload, dict) or payload.get('image_id') != case_id
            or type(revision) is not int or payload.get('revision') != revision):
        return 'INELIGIBLE', 'ROW_IDENTITY_INCONSISTENT'
    admission = payload.get('admission')
    if not isinstance(admission, dict):
        return 'INELIGIBLE', 'ADMISSION_MISSING'
    digest = admitted_source_hash(payload, admission)
    recorded = [payload.get(key) for key in RECORDED_KEYS]
    if any(value is not None for value in recorded):
        if digest is not None and recorded == [digest, digest]:
            return 'ALREADY_RECORDED', 'RECORDED'
        return 'CONFLICT', 'RECORDED_IDENTITY_PARTIAL_OR_DIFFERENT'
    if digest is None:
        return 'INELIGIBLE', 'ADMISSION_IDENTITY_UNSOUND'
    if any(isinstance(item, dict) and item.get('source_sha256') not in {None, digest}
           for item in payload.get('inference_history') or []):
        return 'CONFLICT', 'INFERENCE_SOURCE_MISMATCH'
    if digest not in current_hashes:
        return 'INELIGIBLE', 'SOURCE_FILE_UNAVAILABLE_OR_CHANGED'
    return 'ELIGIBLE', 'ELIGIBLE'


def build_plan(workspace_id, rows, current_hashes, created_utc):
    cases = []
    for case_id, revision, payload in sorted(rows, key=lambda row: row[0]):
        kind, reason = classify(case_id, revision, payload, current_hashes)
        cases.append({'case_id': case_id, 'revision': revision, 'class': kind, 'reason': reason,
                      'payload_sha256': launcher.sha(launcher.canonical(payload))})
    counts = {kind: sum(item['class'] == kind for item in cases) for kind in CLASSES}
    return {'schema': PLAN_SCHEMA, 'command_version': COMMAND_VERSION, 'workspace_id': workspace_id,
            'created_utc': created_utc, 'current_source_count': len(current_hashes),
            'counts': counts, 'cases': cases}


def projected(payload, digest, plan_sha256, timestamp):
    """The only change: both keys, revision +1 and one audit event (RSI-B07)."""
    value = deepcopy(payload)
    value.update(source_sha256=digest, image_sha256=digest, revision=payload['revision'] + 1)
    value['events'] = [*(payload.get('events') or []), {
        'action': EVENT_ACTION, 'value_source': 'ADMISSION_RECORD', 'sha256': digest,
        'plan_sha256': plan_sha256, 'timestamp': timestamp}]
    return value


def changes(plan, rows, current_hashes, plan_sha256, timestamp):
    """Re-check every planned ELIGIBLE case against the locked rows; all or nothing."""
    by_id = {case_id: (revision, payload) for case_id, revision, payload in rows}
    updates = []
    for item in plan['cases']:
        if item['class'] != 'ELIGIBLE':
            continue
        revision, payload = by_id.get(item['case_id'], (None, None))
        require(revision == item['revision'] and payload is not None
                and launcher.sha(launcher.canonical(payload)) == item['payload_sha256']
                and classify(item['case_id'], revision, payload, current_hashes) == ('ELIGIBLE', 'ELIGIBLE'),
                'CHANGED_SINCE_PLAN')
        digest = admitted_source_hash(payload, payload['admission'])
        updates.append((item['case_id'], revision, payload, projected(payload, digest, plan_sha256, timestamp)))
    return updates


def _private_target(path, *, directory=False):
    """Outputs (the pre-image holds full payloads) stay in the approved private directory."""
    target = Path(path).resolve()
    require(target.is_relative_to(PRIVATE_DIRECTORY.resolve()) and not target.is_relative_to(REPOSITORY),
            'APPROVED_PRIVATE_OUTPUT_DIRECTORY_REQUIRED')
    require(not target.exists(), 'NEW_OUTPUT_PATH_REQUIRED')
    require(target.parent.is_dir(), 'EXISTING_PARENT_DIRECTORY_REQUIRED')
    require(not has_reparse_component(target.parent) and private_hospital_root(target.parent),
            'PRIVATE_OUTPUT_ACL_REQUIRED')
    if directory:
        target.mkdir()
    return target


def _write_new(path, value):
    with Path(path).open('xb') as output:
        output.write(launcher.canonical(value) + b'\n')


def current_source_hashes():
    """Current bytes of the approved roots, hashed by the normal admission scanner."""
    from dr_support.services.admission import scan_authorized_hospital_roots
    scan = scan_authorized_hospital_roots()
    require(scan.images, 'APPROVED_SOURCE_ROOTS_UNAVAILABLE')
    return frozenset(image.sha256 for image in scan.images.values())


def _rows(connection, schema, workspace_id, *, lock=False):
    query = 'SELECT case_id, revision, payload FROM {}.review_cases WHERE workspace_id=%s ORDER BY case_id'
    return connection.execute(sql.SQL(query + (' FOR UPDATE' if lock else '')).format(sql.Identifier(schema)),
                              (workspace_id,)).fetchall()


def preconditions(workspace_id):
    """Checked before any private configuration or case content is read (RSI-B01/B02)."""
    require(workspace_id in APPROVED_WORKSPACES, 'OWNER_APPROVED_WORKSPACE_REQUIRED')
    require(all(launcher.port_free(port) for port in APP_PORTS), 'REVIEW_APP_MUST_BE_STOPPED')
    require(all(launcher.port_free(port) for port in MODEL_PORTS), 'MODEL_TUNNEL_MUST_BE_CLOSED')


def require_entry_fence(connection, schema):
    """The m1_entry_fence trigger must guard review_cases (defence in depth)."""
    installed = connection.execute(
        "SELECT 1 FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE t.tgname = 'm1_entry_fence' "
        "AND c.relname = 'review_cases' AND n.nspname = %s AND NOT t.tgisinternal AND t.tgenabled IN ('O', 'A')",
        (schema,)).fetchone()
    require(installed, 'ENTRY_FENCE_TRIGGER_REQUIRED')


def _database():
    from dr_support.persistence import PostgresDatabase, PostgresSettings
    return PostgresDatabase(PostgresSettings.from_env())


def plan(args):
    preconditions(args.workspace_id)
    target = _private_target(args.out)
    with launcher.session_environment(workspace_id=args.workspace_id):
        database = _database()
        current = current_source_hashes()
        with database.session(autocommit=False) as connection:
            with connection.transaction():
                connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                require_entry_fence(connection, database.settings.schema)
                rows = _rows(connection, database.settings.schema, args.workspace_id)
    require(rows, 'WORKSPACE_CASES_REQUIRED')
    value = build_plan(args.workspace_id, rows, current, datetime.now(timezone.utc).isoformat())
    _write_new(target, value)
    digest = launcher.sha(target.read_bytes())
    print(json.dumps({'status': 'PLAN_ONLY', 'plan': str(target), 'plan_sha256': digest, 'counts': value['counts']}))
    return 0


def apply(args):
    preconditions(args.workspace_id)
    raw = Path(args.plan).read_bytes()
    plan_sha256 = launcher.sha(raw)
    require(plan_sha256 == args.plan_sha256, 'OWNER_APPROVED_PLAN_HASH_REQUIRED')
    value = json.loads(raw)
    require(value.get('schema') == PLAN_SCHEMA and value.get('workspace_id') == args.workspace_id, 'PLAN_SCOPE_MISMATCH')
    receipt_bytes = Path(args.backup_receipt).read_bytes()
    require(receipt_bytes, 'BACKUP_RECEIPT_REQUIRED')
    out = _private_target(args.out, directory=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    pending = out / 'PREIMAGE.pending.json'  # Renamed only after commit.
    with launcher.session_environment(workspace_id=args.workspace_id):
        database = _database()
        schema = database.settings.schema
        current = current_source_hashes()
        updated_all = False
        try:
            with database.session(autocommit=False) as connection:
                with connection.transaction():
                    require_entry_fence(connection, schema)
                    rows = _rows(connection, schema, args.workspace_id, lock=True)
                    updates = changes(value, rows, current, plan_sha256, timestamp)
                    require(updates, 'NO_ELIGIBLE_CASES')
                    _write_new(pending, [{'case_id': case_id, 'revision': revision, 'payload': before}
                                         for case_id, revision, before, _ in updates])
                    for case_id, revision, _, after in updates:
                        written = connection.execute(sql.SQL(
                            'UPDATE {}.review_cases SET revision=%s, payload=%s, updated_at=CURRENT_TIMESTAMP '
                            'WHERE workspace_id=%s AND case_id=%s AND revision=%s').format(sql.Identifier(schema)),
                            (revision + 1, Jsonb(after), args.workspace_id, case_id, revision)).rowcount
                        require(written == 1, 'CHANGED_SINCE_PLAN')
                    updated_all = True
        except psycopg.Error:
            if not updated_all:
                raise
            # Lost during COMMIT: the server may or may not have committed.
            print(json.dumps({'status': 'COMMIT_OUTCOME_UNKNOWN', 'output': str(out),
                              'next': 'run plan again to see which cases are recorded'}))
            return 1
        # Committed from here on: never report a refusal (review finding 1).
        try:
            stored = _readback(database, schema, args.workspace_id)
        except Exception:
            stored = None
    return _finish(args, out, pending, updates, stored, plan_sha256, receipt_bytes, value, timestamp)


def _readback(database, schema, workspace_id):
    """Independent read-only readback of every written case (RSI-B08)."""
    with database.session(autocommit=False) as connection:
        with connection.transaction():
            connection.execute('SET TRANSACTION READ ONLY')
            return {case_id: (revision, payload) for case_id, revision, payload in
                    _rows(connection, schema, workspace_id)}


def _finish(args, out, pending, updates, stored, plan_sha256, receipt_bytes, value, timestamp):
    cases = []
    for case_id, revision, before, after in updates:
        expected = launcher.sha(launcher.canonical(after))
        actual_revision, actual = (stored or {}).get(case_id, (None, None))
        state = ('UNAVAILABLE' if stored is None else 'PASS' if actual_revision == revision + 1
                 and actual is not None and launcher.sha(launcher.canonical(actual)) == expected else 'MISMATCH')
        cases.append({'case_id': case_id, 'before_revision': revision, 'after_revision': revision + 1,
                      'before_payload_sha256': launcher.sha(launcher.canonical(before)),
                      'after_payload_sha256': expected, 'readback': state})
    readback = next((state for state in ('UNAVAILABLE', 'MISMATCH')
                     if any(item['readback'] == state for item in cases)), 'PASS')
    summary = {'status': 'APPLIED' if readback == 'PASS' else 'APPLIED_READBACK_' + readback,
               'written': len(cases), 'readback': readback, 'output': str(out)}
    try:
        preimage = out / 'PREIMAGE.json'
        pending.rename(preimage)
        receipt = {'schema': RECEIPT_SCHEMA, 'workspace_id': args.workspace_id, 'plan_sha256': plan_sha256,
                   'backup_receipt_sha256': launcher.sha(receipt_bytes), 'applied_utc': timestamp,
                   'preimage_sha256': launcher.sha(preimage.read_bytes()), 'plan_counts': value['counts'],
                   'written': len(cases), 'readback': readback, 'cases': cases}
        _write_new(out / 'RECEIPT.json', receipt)
        summary['receipt_sha256'] = launcher.sha((out / 'RECEIPT.json').read_bytes())
    except Exception:
        # The rows ARE written; report that, with the per-case hashes, instead of a refusal.
        summary.update(status='APPLIED_RECEIPT_NOT_WRITTEN', cases=cases)
    print(json.dumps(summary))
    return 0 if summary['status'] == 'APPLIED' else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['plan', 'apply'])
    parser.add_argument('--workspace-id', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--plan')
    parser.add_argument('--plan-sha256')
    parser.add_argument('--backup-receipt')
    args = parser.parse_args(argv)
    try:
        if args.command == 'plan':
            return plan(args)
        require(args.plan and args.plan_sha256 and args.backup_receipt, 'APPLY_ARGUMENTS_REQUIRED')
        return apply(args)
    except (ProjectionError, launcher.SessionError) as error:
        print(json.dumps({'status': 'REFUSED', 'code': str(error)}), file=sys.stderr)
        return 2
    except DatabaseUnavailableError:
        print(json.dumps({'status': 'REFUSED', 'code': 'DATABASE_UNAVAILABLE'}), file=sys.stderr)
        return 2
    except psycopg.Error as error:
        # Raised only before commit (after it, apply reports APPLIED_*), e.g. SOURCE_ENTRY_FENCED
        # (55000): the transaction rolled back and nothing was written.
        print(json.dumps({'status': 'REFUSED', 'code': f'DATABASE_REFUSED_{error.sqlstate}'}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
