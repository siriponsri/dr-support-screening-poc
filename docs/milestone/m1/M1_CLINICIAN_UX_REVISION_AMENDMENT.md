# M1 Clinician UX Revision Amendment

Status: owner-approved 2026-10-24 (UX revision plan
`docs/planning/HOSPITAL_M1_UX_REVISION_PLAN_20261024.md`, Phase A).
Amends: `PRE_PHASE3_CLINICAL_UX_DESIGN_FREEZE.md`.

This amendment records the clinician-workflow changes the owner approved in
chat. Recorded clinical semantics are unchanged: the same endpoints, actions
and stored meanings are used.

## 1. Confirm Image

- The dialog shows the retinal image beside the context fields.
- An optional "Image quality" choice (Usable / Not usable) records the existing
  admission review actions `QUALITY_ACCEPTABLE` / `QUALITY_INADEQUATE` after the
  image is confirmed. No choice means no quality call; the Review page still
  offers the quality step before PRISM.

## 2. Final DR grade

- The grade dropdown is replaced by one-click buttons 0-4 and Ungradable. A
  click only selects; the clinician still confirms with "Confirm DR grade"
  ("Confirm Ungradable" for Ungradable).
- No grade is preselected from the AI suggestion.
- Ungradable stays a separate review state (`MARK_UNGRADABLE`, no grade sent).

## 3. Reviewer name

- Remembering the reviewer on the workstation is on by default. A remembered
  name shows as "Reviewer: name" with a Change control. It is a workstation
  preference, not authentication.

## 4. PRISM quality gate

- PRISM input preparation from Review requires a confirmed image quality
  (`GRADABLE`), matching the host frozen-plan gate. The gate offers the
  "Image quality acceptable" action in place.

## 5. Text style

- Clinician-facing text does not use the middle dot or long dashes as
  separators; "/", ":" or "-" are used instead (see `DESIGN.md` 2.3).
