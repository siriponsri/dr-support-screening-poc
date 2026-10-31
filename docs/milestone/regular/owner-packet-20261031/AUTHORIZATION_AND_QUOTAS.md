# Authorization and quota record

This is a documentation record of owner instructions, not a runtime approval file, credential, signed authorization or an instruction to activate an old window. See [current status metadata](AUTHORITY_STATUS.json).

## Owner evidence and approved scope

The owner requested practical use for3–5 users, answered approximately100 images/user/day with one large upload batch/day, extended AI hours to06:00–22:00, required grader+PRISM on every image, and approved Pepo's preceding proposal. The latest workload answer was:

> 1. คาดว่าประมาณ100 ภาพต่อคนต่อวัน และ upload ชุดใหญ่1 ครั้งต่อวัน
> 2. AI ขอขยายเป็น06:00–22:00 ครับ
> 3. แต่ละภาพต้องเรียก grader และ prism ครับ
> อนุมัติข้อเสนอ pepo ครับ

Spacing above is normalized for readability; preserve the original conversation as the approval evidence. Current permissions supersede earlier proposal quantities; do not fabricate a signature or imply a generated document approved itself.

| Item | Approved requirement |
|---|---|
| Product goal | Regular local app use with actual private Model API,3–5 users |
| Workload | About100 images/user/day, one large local batch/user/day |
| Model workflow | Appropriate grader then PRISM for each eligible image; frozen clinical/admission/PRISM gates remain |
| Daily global model ceiling | 1500 admitted top-level model invocations, including commissioning/rechecks and any separately safe explicit new attempt |
| Calendar | Asia/Bangkok;00:00 inclusive through next00:00 exclusive |
| AI hours |06:00 inclusive to22:00 exclusive, with funded bounded drain/cleanup margin |
| Topology | Separate local review-app contexts/workstations; shared private Model API; no process-global shared-workspace web deployment |
| Active dispatch | At most5 model-stage jobs,1 running+4 waiting, at most1 outstanding/user; fair scheduling |
| Final compute allowance | 43200 GPU reservation seconds/day (12h), including loading/idle/residency/drain; release owned DR models when idle and stop new inference admission when exhausted |
| Allowed GPU | Only existing DR RTX2080Ti UUID `GPU-044a8b11-4729-458b-a07b-297e45439419`, conditional on fresh ownership/headroom check and no interference |
| Excluded GPU/work | V100 UUID `GPU-277ccc57-c3e5-0731-cd49-f4f8695f7089` belongs to [other team]; no [other team]/other team service/job interference |
| Duration | Regular service until owner revokes/changes it; no invented7-day expiry or mandatory weekly trial |

## Final compute selection

The owner answered the12h-versus16h GPU question: **"โอ๊ะ งั้นคง12 ชั่วโมงต่อวันดีกว่าครับ"**. This resolves GPU reservation only; AI opportunity hours remain06:00–22:00. Final cap is43200s/day.57600s was considered and was not selected. No compute choice remains pending in this packet.

Release only owned DR models when idle under a finite qualified policy. Show remaining compute budget, opening hours/next eligibility, queue/backlog and budget-blocked state. Stop admitting new model work when the GPU cap is exhausted; CPU/manual/history/export/readback remain available without model load. This authorizes a16h opportunity window, not16h guaranteed warm readiness. Do not consume old residual2700s or use another GPU to extend the day.

Accounting unit is exclusive funded DR-worker residency time. A reservation interval is charged once; RETFound+USPEC+PRISM resident together on that one worker are not three additional time charges. Observed elapsed/busy timings are separate metrics, not added again to the same reservation. Non-overlapping reservations/segments must be durable/idempotent and globally bounded to43200s/day; overlapping workers are refused. Preserve conservative unknown-stop/overrun treatment without resetting budget. See RS-08 for lifecycle requirements.

Recorded status history:the first packet draft retained the pending12h/16h selection; the owner's final answer above supersedes that draft before handoff. No runtime action occurred during drafting. Routine engineering under these approved quantities needs no repeated general permission; concrete new security-sensitive actions remain scoped below.

## Count definition and historical separation

One model invocation means one newly admitted grader prediction or protected PRISM execution, not one image, upload batch, native forward/tile/fold or status call. Each eligible image normally costs2.500 images×2=1000; remaining500 is engineering headroom, not automatic retry. A later explicit new attempt consumes another slot if admitted; a sent/uncertain attempt remains consumed. Same accepted idempotency identity/request digest returns its existing state without a second dispatch/charge.

Health/discovery/status/prepare/grant/readback, reopening saved results, import/scan and definitive pre-admission rejection consume0 model admissions. They must never hide an inference/warmup. GPU load/idle still uses compute reservation. Exact image-pair holds versus consumed intents are defined in [the spec](REGULAR_SERVICE_SPEC.md).

Preserve independently:

- Historical service ledger base534 ->540/cap540;6 admissions terminal PASS_READBACK; all retained service/watchdog windows closed. Do not reopen/recycle them.
- Historical broader cap549 leaves9 restricted slots (Local6+post-fix3), not a generic new-service allowance. A local app using dr-train is QA_SERVER, not adoption of the old Local allowance.
- M1 reservations18900 of21600 leave2700 unreserved old seconds. They stay in the old scope. Pre-M1 preserved17002.874 remains visible separately.
- New recurring daily accounting must reference verified history and preserve lifetime cumulative audit totals. A day change creates a new derived bucket; it never resets an old ledger, terminal job, fence, clock, hash chain or reserved unknown outcome.

The old12/20-admission finite-window plan is no longer primary. Its projected charges22500/26100 were not caps preserving the old2700; equivalent old-cap-preserving limits would have been25200/28800. Do not carry those obsolete plans into this regular-service allowance.

## SSH and security-sensitive actions

Approved SSH test completed using the existing repository-configured identity:

`siripon@[DR host]`, existing key path `C:/Users/User/.ssh/id_ed25519_dr_train`, BatchMode/IdentitiesOnly/StrictHostKeyChecking enabled. DR project `/home/siripon/projects/dr-model-api-qa` is readable. Current metadata evidence is linked from [the packet index](README.md). No secret/key bytes were read and no credential was created or copied. Do not share the private key with other users or recreate DR under another account to avoid permissions.

Use existing backend-held token/configuration within established authorization. No raw token in React, browser storage, URLs, logs, API responses, Workspace DB or artifacts. Resolve the legacy token-entry UI in the owned service flow. A helper opt-in flag does not itself create owner approval.

New credentials/principals, persistent access, roles/grants, ACL/firewall/TLS/OS service configuration, privileged autostart or changes to team services require approval for the concrete security-sensitive action when needed. Prepare exact identities, least-privilege changes and rollback first; do not turn this into a repeated general approval gate for ordinary coding/testing already authorized. No reboot, system-Python/driver change, public exposure, force push or PR/protection bypass is granted here.

No new hospital image/PHI admission, transmission or data scope is granted. Commissioning uses public/hash-verified or synthetic inputs. Preserve authorized origins; do not relabel hospital images to pass gates. Source originals remain immutable.
