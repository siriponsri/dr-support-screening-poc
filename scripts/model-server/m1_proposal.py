"""Draft the exact Hospital M1 24-operation continuation proposal for owner approval.

  draft   build PROPOSAL.json from reviewed pins, the approved private images and the
          nine historical failed jobs; print its SHA-256 for the owner
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
import m1_operations as operations  # noqa: E402

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
    files = sorted(path for path in Path(root).iterdir() if path.is_file() and path.suffix.lower() in {'.jpg', '.jpeg', '.png'})
    return [sha_file(path) for path in files]


def plan(uwf, cfp):
    """Deterministic allocation: Server 9, Local 6 (inactive until qualified), post-fix 9."""
    require = operations.require
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
    parser.add_argument('command', choices=['draft', 'approve'])
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
    return draft(args) if args.command == 'draft' else approve(args)


if __name__ == '__main__':
    raise SystemExit(main())
