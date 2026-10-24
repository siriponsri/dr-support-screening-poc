"""Draft the exact Hospital M1 24-operation continuation proposal for owner approval.

  draft   build PROPOSAL.json from reviewed pins, the approved private images and the
          nine historical failed jobs; print its SHA-256 for the owner
  draft-prism  build the PRISM window continuation from a FENCED 2026-10-23 source
          (its HANDOVER_EXPORT.json and closed Server window) and write the
          upstream path map for the host session
  approve write APPROVAL.json for an exact proposal SHA-256, ONLY after the owner
          approved that hash in the task conversation

No ledger, window, model, GPU or network action happens here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'qa' / 'batch_runtime'))
import m1_operations as operations  # noqa: E402
from batch_ledger import (M1_PRISM_DECISION, M1_PRISM_OPERATIONS, M1_PRISM_SERVER,  # noqa: E402
                          M1_PRISM_WINDOW)

SERVER, LOCAL = 'HOSPITAL_M1_QA_SERVER_20261023', 'HOSPITAL_M1_QA_LOCAL_20261023'
ANCHORS = ('batch_ledger', 'original_budget', 'second_budget', 'demo_requests', 'demo_activation',
           'demo_complete', 'demo_ready')
WINDOWS = {SERVER: 'QA_SERVER', LOCAL: 'QA_LOCAL'}
# Historical FAILED_NO_RETRY jobs (failure register); new scoped intents, never replays.
POST_FIX = [
    ('pf-retfound-d5e8689c2d3c', '05bf31a076f4ff03875eb5050e6116db9d7b2dd8a8bdb356c60a3fc94343a304', 'retfound-aptos5', 'CFP'),
    ('pf-uspec-4f81b1385489', '10da3b42b9d63109f518e64c5331ef81e20b4fcf9b28b93932109bc60a9a283d', 'uspec-uwf-grading', 'UWF'),
    ('pf-uspec-b55fcbf67128', '157f3532d1b72aa471b47deca6b3a37ecc68d03482c736daffdc3ff16c2503f9', 'uspec-uwf-grading', 'UWF'),
    ('pf-prism-cca990e31bc5', '00a03b50b8f9eb414704dcc13d1a4c18106ac7863c67a95acd457824f5033159', 'prism-dr-5fold', 'UWF'),
    ('pf-prism-f62327e97fc9', '02958b03aa9fdc1f03fa337a2fc6ee6b3bc828f887181bc3d0877e7d4f2750bf', 'prism-dr-5fold', 'CFP'),
    ('pf-prism-b4ae1fec4374', '1024a3a1185868253c538165119c08ff3458d4c73f6a22bd62f1f41e8409ea68', 'prism-dr-5fold', 'CFP'),
    ('pf-prism-d00b79a3552e', '10da3b42b9d63109f518e64c5331ef81e20b4fcf9b28b93932109bc60a9a283d', 'prism-dr-5fold', 'UWF'),
    ('pf-prism-067b04056744', '2a503e18f269a6c28f7db71b2bbedcecd0f5eb5c923e162ded5d59925b50490d', 'prism-dr-5fold', 'UWF'),
    ('pf-prism-78f185de1519', '9d2e8b139a4684afc40c5a2bd12f137d606091950999d666178c7c02b6bc5fdb', 'prism-dr-5fold', 'CFP'),
]


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def images(root):
    """Hashes of JPEG/PNG files in one approved private root, distinct by content."""
    from dr_support.services.filesystem_privacy import has_reparse_component, private_hospital_root
    root = Path(root)
    operations.require(root.is_dir() and not has_reparse_component(root) and private_hospital_root(root),
                       'APPROVED_PRIVATE_IMAGE_ROOT_REQUIRED')
    files = sorted(path for path in root.iterdir() if path.is_file() and path.suffix.lower() in {'.jpg', '.jpeg', '.png'})
    hashes = [sha_file(path) for path in files]
    operations.require(len(set(hashes)) == len(hashes), 'DUPLICATE_IMAGE_CONTENT_REJECTED')
    return hashes


def plan(uwf, cfp):
    """Deterministic allocation: Server 9, Local 6 (inactive until qualified), post-fix 9."""
    require = operations.require
    post_fix_sources = {source for _, source, _, _ in POST_FIX}
    # Acceptance images never share a source with a post-fix verification, so an
    # acceptance request can never consume a post-fix allocation (or vice versa).
    uwf = [source for source in uwf if source not in post_fix_sources]
    cfp = [source for source in cfp if source not in post_fix_sources]
    require(len(uwf) >= 5 and len(cfp) >= 5, 'FIVE_UWF_AND_FIVE_CFP_IMAGES_REQUIRED')
    rows = []
    for label, purpose, window, index in (('srv-fresh', 'server_acceptance', SERVER, 0),
                                          ('srv-restart', 'server_acceptance', SERVER, 1),
                                          ('srv-recovery', 'server_acceptance', SERVER, 2),
                                          ('loc-fresh', 'local_acceptance', LOCAL, 3),
                                          ('loc-restart', 'local_acceptance', LOCAL, 4)):
        prism_modality = 'CFP' if label.endswith('restart') else 'UWF'
        rows += [(f'{label}-uspec', purpose, window, uwf[index], 'uspec-uwf-grading', 'UWF'),
                 (f'{label}-retfound', purpose, window, cfp[index], 'retfound-aptos5', 'CFP'),
                 (f'{label}-prism-{prism_modality.lower()}', purpose, window,
                  uwf[index] if prism_modality == 'UWF' else cfp[index], 'prism-dr-5fold', prism_modality)]
    rows += [(operation_id, 'post_fix_verification', SERVER, source, model_id, modality)
             for operation_id, source, model_id, modality in POST_FIX]
    keys = [(window, source, model_id, modality) for _, _, window, source, model_id, modality in rows]
    require(len(set(keys)) == len(keys), 'INDISTINGUISHABLE_OPERATIONS_REJECTED')
    return rows


def draft(args):
    models = operations.reviewed_models(Path(args.models).read_bytes(), json.loads(Path(args.prism_pins).read_bytes()))
    jobs = [operations.operation(models, operation_id=operation_id, purpose=purpose, window_id=window,
                                 source_sha256=source, model_id=model_id, modality=modality)
            for operation_id, purpose, window, source, model_id, modality in
            plan(images(args.uwf_root), images(args.cfp_root))]
    upstream = {name: sha_file(Path(args.upstream_dir) / name) for name in ANCHORS}
    proposal = {'schema': 'hospital-m1-continuation.v1', 'decision_id': 'HOSPITAL_M1_ACCOUNTING_20261023',
                'base_used': 525, 'cap': 549, 'new_admissions_max': 24,
                'allocations': {'server_acceptance': 9, 'local_acceptance': 6, 'post_fix_verification': 9},
                'windows': {key: {'profile': profile, 'gpu_index': 0, 'gpu_seconds_cap': 10800,
                                  'wall_seconds_cap': 14400, 'refund_unused': False, 'renew': False}
                            for key, profile in WINDOWS.items()},
                'accounting_directory': args.accounting_directory, 'installation_sha256': args.installation_sha256,
                'upstream': upstream, 'operations': jobs}
    output = Path(args.output)
    raw = operations.canonical(proposal)
    with output.open('xb') as stream:
        stream.write(raw)
    print(json.dumps({'proposal': str(output), 'proposal_sha256': hashlib.sha256(raw).hexdigest(),
                      'operations': [{key: job[key] for key in ('operation_id', 'purpose', 'model_id', 'modality')}
                                     | {'source_sha256': job['source_sha256'][:12]} for job in jobs]}, indent=1))
    return 0


def draft_prism(args):
    """The source's unsent Server PRISM operations, unchanged except their window."""
    source = Path(args.source_accounting).resolve()  # The host session may run from another directory.
    files = {'handover_export': source / 'HANDOVER_EXPORT.json', 'source_proposal': source / 'PROPOSAL.json',
             'source_approval': source / 'APPROVAL.json', 'source_journal': source / 'LEDGER.jsonl',
             'source_journal_head': source / 'JOURNAL_HEAD.json',
             'source_server_budget': source / 'windows' / SERVER / 'BUDGET.json',
             'source_server_complete': source / 'windows' / SERVER / 'COMPLETE.json'}
    export, previous = (json.loads(files[key].read_bytes()) for key in ('handover_export', 'source_proposal'))
    operations.require(export.get('status') == 'SOURCE_FENCED_LOCAL_ADOPTION_NOT_QUALIFIED'
                       and export.get('destination_installation_sha256') == args.installation_sha256,
                       'FENCED_SOURCE_FOR_THIS_INSTALLATION_REQUIRED')
    remaining = set(export['remaining_job_ids'])
    jobs = []
    for origin in previous['operations']:
        if (origin['job_id'] in remaining and origin['purpose'] == 'server_acceptance'
                and origin['window_id'] == SERVER and origin['model_id'] == 'prism-dr-5fold'):
            body = {key: value for key, value in origin.items() if key != 'job_id'} | {'window_id': M1_PRISM_SERVER}
            jobs.append({**body, 'job_id': hashlib.sha256(operations.canonical(body)).hexdigest()})
    operations.require(len(jobs) == M1_PRISM_OPERATIONS, 'EXACT_UNSENT_PRISM_OPERATIONS_REQUIRED')
    base = export['global_used']
    proposal = {'schema': 'hospital-m1-prism-continuation.v1', 'decision_id': M1_PRISM_DECISION,
                'base_used': base, 'cap': base + M1_PRISM_OPERATIONS, 'new_admissions_max': M1_PRISM_OPERATIONS,
                'allocations': {'server_acceptance': M1_PRISM_OPERATIONS},
                'windows': {M1_PRISM_SERVER: dict(M1_PRISM_WINDOW)},
                'accounting_directory': args.accounting_directory, 'installation_sha256': args.installation_sha256,
                'upstream': {key: sha_file(path) for key, path in files.items()}, 'operations': jobs}
    raw = operations.canonical(proposal)
    with Path(args.output).open('xb') as stream:
        stream.write(raw)
    with Path(args.upstream_output).open('xb') as stream:
        stream.write(operations.canonical({key: str(path) for key, path in files.items()}))
    print(json.dumps({'proposal': str(args.output), 'proposal_sha256': hashlib.sha256(raw).hexdigest(),
                      'base_used': base, 'cap': proposal['cap'], 'window': M1_PRISM_SERVER,
                      'operations': [{key: job[key] for key in ('operation_id', 'model_id', 'modality')}
                                     | {'source_sha256': job['source_sha256'][:12]} for job in jobs]}, indent=1))
    return 0


def approve(args):
    raw = Path(args.proposal).read_bytes()
    operations.require(hashlib.sha256(raw).hexdigest() == args.proposal_sha256, 'OWNER_APPROVED_PROPOSAL_HASH_REQUIRED')
    approval = {'schema': 'hospital-m1-owner-approval.v1', 'decision_id': json.loads(raw)['decision_id'],
                'proposal_sha256': args.proposal_sha256, 'status': 'EXPLICIT_OWNER_APPROVED_NOT_ACTIVATED'}
    data = operations.canonical(approval)
    with Path(args.output).open('xb') as stream:
        stream.write(data)
    print(json.dumps({'approval': str(args.output), 'approval_sha256': hashlib.sha256(data).hexdigest()}))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['draft', 'draft-prism', 'approve'])
    parser.add_argument('--source-accounting', type=Path)
    parser.add_argument('--upstream-output', type=Path)
    parser.add_argument('--models', type=Path)
    parser.add_argument('--prism-pins', type=Path)
    parser.add_argument('--uwf-root', type=Path)
    parser.add_argument('--cfp-root', type=Path)
    parser.add_argument('--upstream-dir', type=Path)
    parser.add_argument('--accounting-directory')
    parser.add_argument('--installation-sha256')
    parser.add_argument('--proposal', type=Path)
    parser.add_argument('--proposal-sha256')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'draft-prism':
        return draft_prism(args)
    return draft(args) if args.command == 'draft' else approve(args)


if __name__ == '__main__':
    raise SystemExit(main())
