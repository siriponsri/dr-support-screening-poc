# Proposed additional inference scope for Hospital M1

Status: OWNER_APPROVED, NOT ACTIVATED. The owner approved this exact proposal
in the task conversation on 2026-10-23: 20 additional requests, cap549, at most
two named windows with the limits below. Approval does not reset any ledger or
start a service. Activation and each dispatch still require durable accounting.

Verified anchor: original closed batch ledger SHA256
`ebc4f23ac5b9d89f136ada7a36b08350ddacf186e338a50c0ea5ba6f5ba14d98`;
476 new intents + historical49 =525 used, cap529, four remaining. The finite
interactive preload session used zero image requests, was explicitly stopped
before inference for request-watchdog repairs, and confirmed owned cleanup.
Its observed521.948s and conservative2430s reservation remain recorded; original
4772.230s and9800.644s session charges/clocks are preserved, never reset/refunded.

| Proposed work | New requests | Conditions |
| --- | ---: | --- |
| QA Server fresh main smoke | 3 | One each USPEC UWF, RETFound CFP, PRISM through protected preview |
| QA Server restart persistence/inference | 3 | Same pinned models, new invocation identities, no automatic retry |
| QA Server explicit failure/recovery acceptance | 3 | Conservative attempt accounting even if delivery is uncertain; never replay a sent request |
| QA Local current/target hardware fresh smoke | 3 | All components local/offline; identify actual machine, do not claim hospital acceptance from another host |
| QA Local restart acceptance | 3 | Verify offline dependencies, persistence and new requests after controlled restart |
| Previously failed-case verification after concrete repairs | 9 | NEW separately scoped test intents referencing historical failures; originals remain closed, no automatic resubmission; do not spend on an unfixed/unknown path |
| Initial mask/post-filter comparison | 0 | Reuse retained actual230 PRISM outputs for baseline versus reversible post-filter; human false-ROI/hidden-lesion adjudication remains required |
| Total | 24 | Includes the existing four remaining slots |

Proposed extension: **20 additional requests**, cumulative cap **549**. This is
an upper bound for the listed work, not an instruction to exhaust it. No repeat
of the480-job batch, weights/threshold changes or additional paid service.
An external pre-mask/model-input ablation is outside this zero-request mask
comparison and needs a separate exact request proposal before execution.

Proposed time: at most one new QA Server window and one QA Local window, each
GPU0 <=3hours / wall <=4hours; total new reservation <=6GPU-hours across those
two sessions. Activate each only after its actual backend/profile/hardware and
source-policy preflight. Do not reserve/start a nonexistent hospital target or
infer IT/data-owner authorization from compute approval. Keep every historical
session intact. No session is renewed automatically; time exhaustion blocks its
remaining work rather than resetting the clock. Accounting for requests530+ must
be written durably before every additional dispatch after approval.

This proposal cannot remove the protected PRISM preview integration gate,
authorize PHI disclosure, broaden network access, or satisfy clinical validation.
