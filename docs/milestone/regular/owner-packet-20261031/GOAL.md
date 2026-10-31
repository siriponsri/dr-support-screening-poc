# Goal: regularly use the local review app with the real private API

Status: owner-approved engineering scope and final43200s/day GPU cap; implementation NOT_STARTED by Pepo. See [authorization](AUTHORIZATION_AND_QUOTAS.md) and read [the full spec](REGULAR_SERVICE_SPEC.md) before planning code.

Deliver a main-integrated, installable Windows review workstation connected to the actual private DR Model API, usable by3–5 clinicians/operators through separate local app contexts. Each user can import about100 images in one daily batch, see truthful progress, obtain the appropriate grader plus PRISM on every eligible image, review/edit/save/reopen/export, and recover from interruption without losing clinician work or repeating sent/uncertain inference. AI opportunity hours are06:00–22:00 Asia/Bangkok; daily admitted model cap1500 and GPU reservation cap43200s apply globally. Release owned DR models when idle under a bounded policy and stop new AI admission at compute exhaustion. CPU/manual/history/readback functions may remain available outside AI hours without loading GPU models. The16h opportunity window is not a guarantee of16h model residency/readiness.

Complete these outcomes:

1. Finish/review/integrate Claude's three existing branches and audited compatibility fixes, preserving their WIP and owner artifacts.
2. Add the regular-service authority, durable daily quota and bounded owned GPU lifecycle through a new adapter. Preserve the closed historical ledger/windows and old restricted allowances.
3. Add durable batch backlog and fair asynchronous stage dispatch.100 imported images are not100 active jobs; at most5 model jobs active,1 executing,1 outstanding/user. Preserve Confirm Image, required PRISM receipt/input acknowledgement and all clinical/source/model/coordinate gates.
4. Connect the canonical local launcher/status/stop and actual API with backend-only secrets, authenticated user/workstation attribution and isolated workspace selection. No terminal supervision per image.
5. Validate offline controls, actual main-browser/API/model/DB/review/export flow and an extracted secret-free installation candidate. Publish exact evidence, limitations, operator instructions and safe rollback.

The workload planning target is up to500 images/1000 baseline model invocations/day; the1500 ceiling does not prove that the RTX host sustains that throughput. Measure latency/queue wait/completion rate before any capacity claim. Prefer20 real commissioning invocations (10 images×2), counted inside that day's1500; necessary additional specified tests can use the approved remainder with full accounting.

Done requires applicable [validation rows](VALIDATION_MATRIX.md), the Git/main/build lifecycle in AGENTS, and the [operations handoff](OPERATIONS_AND_ROLLBACK.md). If deployment access or a concrete permission action is blocked, continue independent work and mark that action/target/next actor. Do not call a fixture, proposal, branch-only change, stale frontend, incomplete multiuser authentication or guarded-recovery rehearsal a production acceptance.

The outcome is practical supervised evaluation/annotation engineering. It does not establish clinical accuracy, regulated medical release, autonomous diagnosis/referral or permission to transmit new private hospital data. Full QA_LOCAL/hospital-hardware/guard-aware-recovery acceptance remains separately identified when not executed; do not erase existing M1 requirements or falsely claim the whole milestone DONE.
