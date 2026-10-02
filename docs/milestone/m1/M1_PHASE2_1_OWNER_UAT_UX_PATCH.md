# DR Screening M1 — Phase 2.1 Owner UAT UX Patch

**Document revision:** Patch r1.0
**Prepared:** 2026-10-02
**Status:** `OWNER_DIRECTED_BOUNDED_PATCH`
**Parent:** `M1_PHASE2_1_UX_HARDENING_SERVER_CONNECTION.md`
**Repository baseline:** `50618f25fd088ce6c981e85120c1fd24780f1c3a`
**Phase 2 state:** `READY_FOR_REVIEW`
**Phase 3 state:** `NOT_STARTED`

> This patch records Owner UAT feedback after the Phase 2.1 integration. It is a bounded UX refinement only. It must not reopen accepted Phase 1 / Phase 2 engineering work broadly, start Phase 3, or change clinical grading semantics beyond the already approved ICO reference.

---

## 1. Purpose

Owner UAT confirms that the Phase 2.1 direction is improved, but four clinician-facing areas still need refinement before Phase 2 owner closeout:

1. Grade Guide should not occupy a large persistent panel.
2. Human annotation labels should visually match their annotation boxes.
3. The `Finish this image` area still exposes too much workflow/state complexity.
4. Mask / analysis-area explainability is still not sufficiently visible or intuitive.

The objective is to reduce cognitive load for expert ophthalmologists while keeping the interface understandable for less-experienced users.

---

# 2. Required patch items

## UAT-P0-1 — Grade Guide as on-demand help

### Current issue

The detailed Grade Guide is useful but occupies a large persistent part of the Clinician Review surface and competes with the primary task: selecting and confirming the DR grade.

### Required outcome

Replace the large persistent Grade Guide panel with an on-demand help surface:

```text
Grade guide
    ↓
modal / dialog / popover
```

The detailed content remains sourced from:

```text
docs/reference/ICO_DR_GRADING_0_4_REFERENCE.md
```

The help surface must retain:

- `0 - No apparent DR`
- `1 - Mild NPDR`
- `2 - Moderate NPDR`
- `3 - Severe NPDR`
- `4 - Proliferative DR (PDR)`
- full ICO 4-2-1 criteria for Severe NPDR
- explicit proliferative findings for Grade 4
- statement that `Ungradable` and `Needs Second Review` are workflow states outside 0-4
- statement that DME classification is separate from DR severity

Requirements:

- the normal expert grading path remains visible and minimal;
- opening/closing the guide must not lose current grade/reviewer state;
- keyboard/focus behavior must be accessible;
- no referral/treatment recommendation is added.

---

## UAT-P0-2 — Human annotation label color coherence

### Current issue

The `HUMAN-*` annotation label visually separates from the annotation box because the text color does not clearly follow the annotation color.

### Required outcome

Make the human annotation label visually belong to its geometry.

Requirements:

- label color should correspond to the annotation box/stroke color;
- preserve readable contrast against the retinal image;
- do not rely on color alone to communicate provenance;
- retain a clear human-source indicator;
- if wording is changed, prefer a readable form such as:
  - `Human · EX`
  - `Human · Hard exudate`
  over cryptic internal text where space allows;
- AI and Human overlays must remain visually distinguishable.

This is a presentation change only; annotation class, geometry, provenance, and coordinates must remain unchanged.

---

## UAT-P0-3 — Simplify `Finish this image`

### Current issue

The Finish panel still looks like a workflow/state-management form. Some controls appear clickable without producing a clear user-visible action, which increases uncertainty.

### Product rule

The clinician should not have to manage an internal state machine.

The normal task should feel like:

```text
inspect findings
→ correct/add only if needed
→ finish image
```

### Required outcome

Reduce the Finish area to the smallest set of controls that produce meaningful persisted behavior.

Requirements:

- one obvious primary completion action;
- remove controls that do not result in a meaningful persistence/state transition;
- informational states such as `Review in progress` should be text/badge/status, not misleading action buttons;
- preserve deliberate review-completeness semantics in persistence;
- zero annotations or zero AI detections must never silently become a reviewed-negative label;
- if a deliberate distinction is still required, expose only the minimum understandable choice at finish time, e.g.:
  - `Reviewed findings recorded`
  - `Reviewed none found`
- Advanced findings should remain optional, secondary, and collapsed by default;
- do not require the clinician to interact with Advanced findings to finish the normal Core workflow;
- keep reviewer identity and audit trail intact.

If a visible control has no effect on persisted state and no clear user value, remove it.

---

## UAT-P0-4 — Mask / Analysis explainability surface

### Current issue

The owner still cannot clearly find or understand the masked-analysis representation and the retinal area that will be retained/excluded before downstream model processing.

### Required outcome

Provide a simple case-local visual explanation for the analysis representation.

Preferred viewer modes:

```text
Original
Analysis area
Mask preview
AI overlay
Explainability
```

Exact labels may be refined, but the concepts must remain distinct.

### Mask preview behavior

The Mask preview should show, on the retinal image:

- retained retinal area;
- excluded border / rim / machine artifact region;
- mask boundary;
- any fallback / review-needed state.

Use a restrained, professional visual treatment:

- low-saturation overlay;
- soft neutral/green/blue tones;
- no bright diagnostic-looking colors unless already part of an existing semantic system;
- clear legend;
- image remains readable.

The reference goal is explanatory clarity, not decorative heatmap styling.

### Important semantic rules

- Original remains immutable and the clinical source of truth.
- Mask preview is processing evidence, not a clinical diagnosis.
- `NEEDS_REVIEW` may be visually inspectable but must not silently become approved model input.
- Do not call the application-level masked representation the final `Model input` if provider-specific transforms may still follow.
- Prefer:
  - `Analysis area`
  - `Mask preview`
- Preserve:
  ```text
  Original
  → Analysis area
  → provider transform
  → actual model input
  → output / explanation
  ```
- no hidden double masking;
- no UWF-specific clinical severity rule is inferred from the mask.

### Information architecture

Do not make Explainability a global navigation destination.

Keep it case-local, for example:

```text
Viewer:
Original | Analysis area | Mask preview | AI overlay

Inspector / help:
Explainability
Processing details
Technical details
```

The user should understand the mask without navigating away from the case.

---

# 3. UX principles for this patch

Apply these principles consistently:

### One primary action

Each workflow step should have one obvious primary action.

### Progressive disclosure

Do not display exception paths, technical processing, or advanced findings until needed.

### Image-first

The retinal image should remain the dominant visual object.

### Clinician speed

Do not add a new confirmation step merely to explain the UI.

### Novice clarity

Labels and help should be understandable without requiring knowledge of internal enums or state-machine terminology.

### Professional restraint

Prefer fewer cards, fewer persistent explanations, fewer controls, and better hierarchy.

---

# 4. Scope constraints

## Preserve

- PostgreSQL authority
- immutable source images
- original-image coordinate storage
- annotation provenance
- AI vs Human distinction
- Grade 0-4 ICO clinical reference
- disagreement / second-review semantics
- completeness persistence semantics
- manual workflow when AI is unavailable
- existing audit/revision behavior
- legacy annotation geometry compatibility

## Do not

- start Phase 3
- enable an unqualified UWF model
- change ICO grading criteria
- add referral or treatment logic
- add DME grading into the DR 0-4 selector
- authorize real hospital-data use
- introduce a separate Simple/Expert mode
- delete backend support for Polygon / Point / Circle solely because the normal UI is Box-first
- expose secrets, DSNs, tokens, model weights, or private environment values

---

# 5. Validation

Use focused validation while implementing this patch.

At minimum cover:

- Grade Guide opens/closes and preserves current form state;
- Grade Guide content still matches the ICO reference;
- human annotation labels remain readable and visually tied to boxes;
- AI/Human provenance remains distinguishable;
- Finish panel only exposes meaningful actions;
- deliberate reviewed-negative state still requires explicit user action;
- Advanced findings remain non-blocking;
- mask/analysis modes render the correct representation and state;
- `NEEDS_REVIEW` does not silently approve a mask;
- Original image remains the source of truth;
- manual review remains available when AI is unavailable;
- changed controls remain keyboard accessible;
- no layout regression at supported workstation widths.

Run the repository's applicable final integration validation before merge.

---

# 6. Review / integration policy

This is one bounded patch.

```text
MAIN
→ bounded IMPLEMENT
→ focused validation
→ one independent exact-candidate REVIEW
→ fix BLOCKER / REQUIRED FIX only
→ affected re-review if required
→ integrate
→ final validation
→ Owner UAT
```

Do not open a new broad Phase 2 review cycle.

---

# 7. Completion receipt

Return:

```text
Starting SHA:
Candidate SHA:
Final main SHA:

Grade Guide:
Human annotation label:
Finish panel:
Mask / Analysis explainability:

Focused tests:
Backend:
Frontend:
Typecheck:
Build:
git diff --check:

Independent review:
Brain:
main == origin/main:
clean worktree:

Phase 2:
READY_FOR_REVIEW

Owner UAT:
PENDING
```

Do not mark Phase 2 `DONE`; owner acceptance is still required.

# End of Phase 2.1 Owner UAT UX Patch
