---
status: Accepted (retrospective)
date: 2026-09-23
---

# ADR-0004: Use three human confirmation milestones and keep AI evidence non-authoritative

## Context and problem statement

Earlier iterations (S6, commit 124e073) exposed a detailed per-detection review surface, which was later simplified (e97151a, b47a7de). A per-lesion accept/reject queue is slow for clinicians and blurs the line between AI evidence and human truth.

## Considered options

- Per-detection confirmation queue
- Three case-level milestones (Confirm Image, Confirm DR Grade, Confirm Annotation) with optional AI ROI correction or removal

## Decision outcome

A case has exactly three human confirmations. AI suggestions are optional evidence. Correcting or removing an AI ROI appends a decision that keeps the original class, score, geometry, and model identity. A corrected ROI is shown without a score. Confirm Annotation binds to a hash of the active set, so any later change requires confirming again.

### Consequences

- Good: less clinician burden; clear provenance; AI is never promoted to ground truth.
- Bad: an empty confirmed set means *reviewed*, not *no lesions*, and the documentation must keep saying so.

### Follow-up (single-line flow v2)

The clinician UI presents the milestones as one forward line per image. Grade finalization has one action (**Confirm DR Grade**); the legacy `ESCALATE`/`MARK_INCORRECT` actions stay in the backend for compatibility and historical records only. Confirm Annotation completes the case and opens the next unfinished Worklist image. Case-level confirmation does not mean every AI ROI was individually verified.

## More information

`dr_support/workflow.py`, `dr_support/presentation.py`, Clinician User Manual.
