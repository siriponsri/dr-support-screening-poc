# Clinician User Manual — Draft for S8 Rewrite

> S8 must regenerate this manual against the final UI and replace placeholders with Playwright-captured screenshots. Use only public/synthetic fixtures.

## 1. Open DR Support

**Screenshot:** `manual/screenshots/01-open-app.png`

Explain how the clinician reaches the application. Do not include server administration details here.

## 2. Create or select a workspace

**Screenshot:** `02-workspace.png`

Explain workspace purpose and where source images live.

## 3. Scan/add retinal images

**Screenshot:** `03-scan-input.png`

Show supported final formats only. Explain explicit unsupported states without technical codec detail unless needed.

## 4. Worklist

**Screenshot:** `04-worklist.png`

Explain patient/eye linking, review state, and how to open a case.

## 5. Review the retinal image

**Screenshot:** `05-review.png`

Keep the retinal image primary. Explain zoom/pan and clinician decision controls.

## 6. Optional AI assistance

**Screenshot:** `06-ai-overlay.png`

Explain RETFound grade suggestion and PRISM lesion overlay separately. A PRISM numeric confidence is a model detection score, not automatically a calibrated probability.

Do not instruct the clinician to confirm/reject every AI lesion individually. AI evidence is optional assistance.

## 7. Dense annotation when needed

**Screenshot:** `07-advanced-annotation.png`

Explain optional CVAT/advanced edit workflow only when detailed geometry correction is necessary.

## 8. Dataset status and export

**Screenshots:** `08-dataset.png`, `09-export.png`

Explain AI-only versus reviewed state using the final frozen semantics.

## 9. Models & Audit

**Screenshot:** `10-models-audit.png`

Explain readiness/provenance at a clinician-appropriate level; technical troubleshooting belongs in the Operator Runbook.

## Safety note

AI output supports clinician review. It is not autonomous diagnosis or referral.
