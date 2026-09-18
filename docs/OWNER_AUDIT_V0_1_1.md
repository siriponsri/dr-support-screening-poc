# Owner Audit Patch — v0.1.1

Date: 2026-09-18

This patch was produced from the standalone `dr-support-screening-poc` B8 bundle. OcuForge was not modified.

## Findings addressed

| Finding | Result | Implementation |
|---|---|---|
| KKU customer theme | FIXED | Added KKU Red Soil UI system (`#A73B24`) with clinical warm-white surfaces; lesion colors remain separate. |
| Raw PRISM output too dense for review | FIXED | Raw result is retained unchanged; clinician overlay/CVAT pre-label is derived through `REVIEW_THRESHOLDS`, `REVIEW_MAX_PER_CLASS`, `REVIEW_MAX_TOTAL`. Default cap: 25/class and 80 total. Recorded `01_dr` preview shows 67 of 200 raw suggestions. |
| CVAT geometry behavior unclear | FIXED | Rectangle, ellipse, polygon, polyline and points import are validated. Mask sync is explicitly rejected with a clear error; no silent data loss. |
| Invalid review actions | FIXED | Accept and Mark Incorrect require an AI grade. Manual grade remains supported and is recorded as `grade_review_source=MANUAL`; accepted/corrected AI review sources are separately recorded. |
| Repository-level licensing/provenance | FIXED | Added `LICENSE`, `THIRD_PARTY_NOTICES.md`; retained model revision/checkpoint provenance. |
| Threshold/cap tests | FIXED | Added tests proving raw inference remains intact while review selection is bounded. |
| Unsupported mask test | FIXED | Added explicit mask-rejection test. |
| Browser/UI test | PASS_WITH_WARNING | Existing Node/jsdom tests remain in repo. This audit environment could not fetch jsdom and Chromium navigation is blocked by host administrator policy. A Playwright real-browser smoke test was added and auto-skips only under that policy. JavaScript syntax validation passed. |
| Live CVAT round-trip | OWNER_ACTION_REQUIRED | Still requires owner CVAT PAT in runtime and one live send/edit/sync/confirm acceptance case. |

## Validation performed in this patch

- `python -m pytest -q` → **17 passed, 1 skipped**. The skipped test is the optional real-Chromium smoke because navigation is blocked by host administrator policy.
- `python -m compileall -q dr_support tests` → PASS.
- `node --check web/app.js` and Node test-file syntax checks → PASS.
- `npm test` was not re-executed because `jsdom` was not available locally and package installation could not complete in the audit environment. The original B8 delivery evidence is preserved; no new npm PASS claim is made.

## Remaining release warning

Do not mark the POC fully PASS until one live CVAT Online round-trip succeeds against project `445923` with an owner-injected `CVAT_TOKEN`.
