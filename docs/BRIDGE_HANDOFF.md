# Standalone operational handoff

B0 PASS: independent Git repository. OcuForge is now read-only.
Owner authorizes B0–B8 pass-through and ten public HRF sample images.
Preserve prior OcuForge local history as audit only. Do not push there.
CVAT_TOKEN absent: live API smoke deferred, offline contract gates continue.
Next B1: commit and verify standalone provider-neutral API.

B1 PASS: independent generic contracts/API, 2 offline tests pass.

B2 PASS_WITH_WARNINGS: CVAT Online REST contracts, 4 offline tests pass; live token absent.

B3 PASS_WITH_WARNINGS: RETFound official APTOS five-class checkpoint verified and real standalone HRF smoke passed.
See RETFOUND_SMOKE.json. Non-commercial and uncalibrated; not a scientific champion.

B4 PASS_WITH_WARNINGS: all 21 released PRISM weight hashes verified, 5-fold real HRF smoke yields 200 AI suggestions.
Fixed upstream fusion call to specify non-delta mode (ensemble output); no training or accuracy claims.
See PRISM_SMOKE.json. Next B5 idempotent CVAT orchestration.

B5 PASS_WITH_WARNINGS: durable task mapping, idempotent sync and ambiguous-write protection; 7 offline tests pass.
Live CVAT project/task/upload/push/pull NOT_EXECUTED because CVAT_TOKEN is absent.
No fake live task is recorded. Continue B6.

B6 PASS_WITH_WARNINGS: independent English UI, four surfaces, ten pinned public HRF samples plus one synthetic fixture.
API and syntax checks passed. Browser localhost denied; pixel-level visual QA remains unverified.
Next B7: complete DOM/API and review round-trip acceptance.

B7 PASS_WITH_WARNINGS: 14 offline Python tests plus DOM/live-local-API interaction test pass.
Review state persists across restart; stale revisions rejected; changed corrections require fresh confirmation.
CVAT remote interactions remain fixtures; no clinician-authenticated live round-trip claimed.
Visual browser QA remains unverified. Next B8 packaging and secure runtime runbook.

## B8 — Standalone delivery

PASS_WITH_WARNINGS. Added pinned independent model setup, Windows launcher, offline recorded preview, runtime/CVAT/model documentation and final report. Official RETFound source/checkpoint and all 21 PRISM assets verified from standalone paths. GitHub publication unavailable; deliver full standalone bundle and patch. Live CVAT and visual browser validation remain explicitly pending.

## v0.1.1 owner audit patch

- KKU Red Soil clinical theme applied; see UI_THEME.md.
- Raw lesion output remains intact; `lesion_review` is a bounded display/CVAT view.
- Mask sync is explicitly unsupported; rectangle/ellipse/polygon/polyline/points are supported.
- Manual grading is explicitly labeled `MANUAL`; AI accepted/corrected review sources are separately recorded.
- Added LICENSE and THIRD_PARTY_NOTICES.md.
- Live CVAT project 445923 round-trip remains OWNER_ACTION_REQUIRED.


## v0.1.2 live CVAT overlay patch

The backend live round-trip has been observed on Project `445923`. The v0.1.2 UI now renders synced CVAT corrections distinctly from the original AI suggestion. Use the updated `START.cmd`; it falls back to a uv-managed Python 3.12 when Windows `py -3.12` is unavailable. See `LIVE_CVAT_ACCEPTANCE.md`.
