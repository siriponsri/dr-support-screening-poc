# DR local app + real API: Claude continuation

Prepared2026-10-31. Documentation handoff only; no implementation, runtime deployment, model invocation or ledger activation was performed to prepare it.

**Current state: owner approved the regular-service scope and resolved the GPU selection.** AI opportunity hours are06:00–22:00 Asia/Bangkok, with43200 GPU reservation seconds/day (12h), bounded idle unloading of owned DR models and no new AI admission after compute exhaustion. There is no57600s cap. Manual review/history/export/readback may remain available without GPU outside AI hours. Do not claim guaranteed continuous AI readiness for all16h.

## How to hand this to Claude

Use a normal follow-up in the existing Claude task. Read [the short continuation text](SHORT_PROMPT_TH.txt) and the documents below. If the old goal/task has expired, create a new goal with this scope and these documents as its starting checkpoint. **Do not blindly resume any closed finite GPU window, old approval file, terminal job or old one-lease runner.**

1. [Goal and deliverables](GOAL.md)
2. [Final owner authorization and quotas](AUTHORIZATION_AND_QUOTAS.md)
3. [Normative regular-service requirements](REGULAR_SERVICE_SPEC.md)
4. [Implementation and integration plan](IMPLEMENTATION_PLAN.md)
5. [Validation and evidence matrix](VALIDATION_MATRIX.md)
6. [Operations, packaging and rollback](OPERATIONS_AND_ROLLBACK.md)
7. [Current authority status as documentation metadata](AUTHORITY_STATUS.json)

The spec defines required behavior. Claude audits the existing implementation and decides the smallest compatible design; this packet does not pre-authorize competing shared types, migrations or alternate model providers.

## Approved workload and topology

3–5 users, about100 images/user/day, imported as one large local batch per user/day. Every eligible image needs its modality-specific grader and PRISM, yielding up to500 images/1000 baseline invocations plus50% engineering headroom under a **global1500 admitted model invocations/day** cap. Headroom is not automatic retry. The day is00:00–24:00 Asia/Bangkok. Commissioning/rechecks count inside that cap.

Each user has a separate local review-app process/workstation context with private data and authenticated identity; those apps share the protected Model API. Do not expose one process-global active workspace as a new shared multiuser web app. AI dispatch has at most5 active model-stage jobs (1 running+4 waiting), at most1 outstanding per user, with fair scheduling. The100-image batch manifest is durable backlog, not100 active GPU jobs.

## Starting snapshot and reading sources

Authoritative repository:`C:/Users/User/Desktop/myProject/dr-support-screening-poc`; main/locally recorded origin/main:`9c52853db8dd2b879f1151cb1308c860cb78b5af`. Recheck live refs/status before writing. Claude remains the application implementation writer. Existing untracked owner artifacts and dirty worktrees must be preserved.

Read [AGENTS](../../../../AGENTS.md), [README](../../../../README.md), [DESIGN](../../../../DESIGN.md), current [GOAL checkpoint](../../../../GOAL.md), [HANDOFF checkpoint](../../../../HANDOFF.md), [Claude guide](../../../../CLAUDE.md), [installation](../../../operations/INSTALLATION.md), [Model API operations](../../../operations/MODEL_SERVER.md), [security](../../../operations/SECURITY_PRIVACY.md), [clinician workflow](../../../manuals/clinician/02-workflow.qmd), [current Hospital M1 spec](../../../milestone/m1/HOSPITAL_M1_RELEASE_CANDIDATE_SPEC.md), [PRISM authority](../../../milestone/m1/M1_MUTABLE_PRISM_ENTRY_AUTHORITY.md) and [accounting contract](../../../milestone/m1/M1_ACCOUNTING_CONTINUATION.md).

Use the root HANDOFF as the existing engineering checkpoint that Claude/user have been maintaining, not as authority to override current AGENTS/owner permissions. This packet creates no new root HANDOFF source and does not overwrite any of those files during its preparation.

Evidence:[initial detailed audit](../owner-audit-20261031/AUDIT.md), [safe SSH/midnight addendum](../owner-audit-20261031/SERVICE_QUOTA_AND_SAFE_TESTS_20261031.md), [source/test snapshot](../owner-audit-20261031/SNAPSHOT.json), [validation receipt](../owner-audit-20261031/VALIDATION.json), [safe-test summary](../owner-audit-20261031/SAFE_TESTS.json), [current remote metadata](../owner-audit-20261031/SSH_DR_METADATA.json), [checker counterexamples](../owner-audit-20261031/CHECKER_PROBES.json).

Those audit documents preserve older100/day,300/day and12/20-window proposals. Their earlier suggested7-day pilot is **not** a requirement for this owner-approved regular service. This packet supersedes those capacity proposals; historical receipts/test counts remain unchanged. No artificial weekly expiry is introduced.
