# DR Screening M1 — Phase 2.1 Owner UAT Operation Simplification Patch

**Document revision:** Patch r1.0  
**Prepared:** 2026-10-02  
**Status:** `OWNER_DIRECTED_BOUNDED_PATCH`  
**Parent:** `M1_PHASE2_1_UX_HARDENING_SERVER_CONNECTION.md`  
**Prior owner-UAT patch:** `M1_PHASE2_1_OWNER_UAT_UX_PATCH.md`  
**Repository baseline:** `136d28a585988bbeab0d962fd2278a23d846780c`  
**Phase 2 state:** `READY_FOR_REVIEW`  
**Phase 3 state:** `NOT_STARTED`

> This patch is a final operation-focused refinement from Owner UAT. It is not a new phase and must not reopen accepted Phase 1 / Phase 2 work broadly. Its purpose is to reduce per-case cognitive load and clicks for high-volume clinical operation while preserving truthful longitudinal evidence and safe masked-analysis behavior.

---

# 1. Why this patch exists

The current Phase 2.1 build is substantially improved and technically validated, but Owner UAT identified two remaining operational friction points:

1. **Confirm Image asks for too much information at once.**  
   The current dialog exposes image type, patient key, eye, visit key, capture date/time, capture sequence, device, reviewer, and additional guidance. Even when fields are optional, the visible form makes the operator feel responsible for completing them.

2. **Mask review is not obvious enough.**  
   When a candidate mask exists, the retained/excluded regions are visually too subtle. When a safe mask is unavailable or below the current acceptance threshold, the user sees an unavailable state without an obvious operational path.

These issues matter because the target users may include:

- ophthalmologists reviewing large case volumes;
- trained clinical reviewers;
- nurses / assistants performing intake/context confirmation;
- future M2 users in lower-resource clinical settings.

The product must assume that users:

- have limited time per case;
- cannot spend time learning internal workflow terminology;
- should not have to understand preprocessing algorithms;
- should not manually enter metadata the system can derive safely;
- should not be blocked by unavailable AI or mask processing.

---

# 2. Primary operation goal

The normal case path should feel approximately like:

```text
Worklist
→ Confirm only uncertain essential context
→ Review image / optional processing evidence
→ Grade
→ Review / correct findings if needed
→ Finish
→ Next case
```

For a well-formed case, the operator should not need to fill a metadata form.

The system should prefer:

```text
auto-detect / prefill
→ show concise suggestion
→ user confirms only what is uncertain or clinically relevant
```

rather than:

```text
show every available metadata field
→ ask user to understand and populate each one
```

---

# 3. UAT-P0-1 — Minimal Confirm Image workflow

## 3.1 Current problem

The current Confirm Image dialog exposes too many fields at the primary decision surface:

- Image type
- Pseudonymous patient key
- Eye
- Visit key
- Capture date/time
- Capture sequence
- Camera / device
- Reviewer name

This is structurally complete but operationally expensive.

## 3.2 Required primary surface

The default Confirm Image view should contain only information that may require immediate human confirmation.

Preferred primary surface:

```text
Image
[thumbnail / filename]

Image type
[UWF / CFP / Not sure]

Eye
[Left / Right / Unknown]

Patient
[auto-detected / existing pseudonymous key]
only show editable control when unresolved or ambiguous

Reviewer
[remembered workstation default]

[ Confirm & continue ]
```

### Essential rule

If a field already has a high-confidence / previously confirmed value, do not make the user re-enter it.

Prefer a compact summary row over a full input.

Example:

```text
Patient   PAT0001       ✓ detected
Eye       Left          ✓ suggested from filename
Type      UWF           ✓ detected
```

Only uncertain items should expand into editable controls.

## 3.3 Metadata that should leave the primary form

Move these away from the default primary surface:

- Visit key
- Capture sequence
- Camera / device
- raw acquisition metadata
- technical source metadata

Place them under:

```text
Additional metadata ▾
```

or store them automatically when reliable evidence exists.

The normal clinician workflow must not require opening this section.

---

# 4. Filename-derived context suggestions

## 4.1 Owner direction

Where the hospital/public dataset filename contains useful structured information, the system should attempt to derive context automatically rather than forcing manual entry.

Potential filename-derived suggestions include:

- pseudonymous patient key;
- laterality (`L`, `R`, `OD`, `OS`, or approved pattern);
- visit/capture identifier;
- capture ordering token;
- image type only if the evidence is sufficiently reliable.

## 4.2 Evidence rule

Filename parsing produces **suggestions**, not clinical truth.

The current project principle remains:

```text
filename-derived value
→ evidence / suggestion
→ user or trusted source confirms when required
```

Do not silently overwrite a previously confirmed value from a filename parser.

When parsing is ambiguous:

```text
Unknown
```

is safer than guessing.

## 4.3 Parser behavior

Implement filename parsing through a small, explicit, tested parsing layer rather than UI-only string heuristics.

Requirements:

- deterministic;
- documented supported patterns;
- case-insensitive where appropriate;
- no accidental patient identity leakage;
- preserves original filename;
- records method/source of derived values;
- never infers unsupported medical facts;
- safe fallback to Unknown.

Example:

```text
FC8804 L1.jpg
```

may provide evidence for:

```text
patient candidate = FC8804
laterality candidate = LEFT
capture/order candidate = 1
```

only if that pattern is formally supported and tested.

Do not assume all filenames follow the same convention.

---

# 5. Visit / time / before-after handling

## 5.1 Do not make chronology a manual burden

M1 already needs visit/date/order evidence to support later same-eye comparison, but this must not become a mandatory per-image form-filling task.

Preferred evidence priority:

```text
1. trusted acquisition metadata / DICOM metadata
2. approved manifest / source metadata
3. supported timestamp encoded in filename
4. supported filename sequence token
5. manual entry only when operationally necessary
6. Unknown
```

## 5.2 Capture date/time

Capture date/time may remain available, but:

- auto-populate when reliable evidence exists;
- otherwise hide under Additional metadata;
- do not require the clinician to type it during routine labeling;
- Unknown / blank remains valid.

## 5.3 Before / After

Do **not** introduce a generic mandatory `Before / After` selector for every image.

Reason:

`Before / After` is meaningful only relative to a known same-patient / same-eye comparison and supported ordering evidence.

A filename sequence such as `L1` / `L2` may represent sequence evidence but does not automatically prove clinical chronology unless the dataset convention is known.

If a future same-eye pair is identified, the UI may display:

```text
Earlier / Later / Order unknown
```

or a similar pair-relative concept.

But Phase 2.1 must not convert an unsupported filename ordinal into a clinical before/after claim.

This preserves the existing project longitudinal boundary:

```text
same-eye pairing
!=
proven chronology
!=
improvement / worsening
```

---

# 6. Confirm Image progressive disclosure

## 6.1 Default state

The dialog should fit comfortably without requiring long vertical scrolling for the normal case.

Target:

```text
Confirm image

FC8804 L1.jpg

Image type     UWF
Patient        FC8804
Eye            Left

Only uncertain values need confirmation.

Reviewer       Test

[ Additional metadata ▾ ]

Cancel                  Confirm & continue
```

## 6.2 Uncertain state

If one value is uncertain:

```text
Eye
[ Left ] [ Right ] [ Unknown ]
```

The user should fix only that item.

Do not expose unrelated optional fields merely because one item needs confirmation.

## 6.3 High-volume operation

Optimize for repeated use:

- remember reviewer identity;
- preserve keyboard operation;
- autofocus the first unresolved required field;
- `Enter` may confirm when safe;
- avoid unnecessary confirmation dialogs;
- after successful confirm, proceed directly to the next workflow surface;
- do not force users to inspect collapsed metadata.

---

# 7. UAT-P0-2 — Mask preview must be visually obvious

## 7.1 Current problem

When a candidate mask is available, the current overlay can be difficult to distinguish from the retinal image.

The user should understand the mask in less than a second without reading technical text.

## 7.2 Required visual model

Use a clear but restrained three-part visual language:

### Retained retinal area

- keep the retinal image close to normal brightness/color;
- optionally apply a very light cool/green tint;
- do not obscure lesions.

### Excluded border / artifact area

- visibly dim and desaturate;
- use a semi-transparent neutral/slate overlay;
- make it substantially more obvious than the current treatment;
- excluded region should read as “not used for analysis”, not as disease.

### Mask boundary

- use a clear thin high-contrast boundary;
- recommended restrained teal/cyan/blue-gray family;
- avoid alarm red/orange unless the existing semantic design system requires it.

## 7.3 Visual acceptance

At normal workstation size, a first-time user should immediately be able to answer:

```text
Which part of this image will be retained?
Which part will be excluded?
```

without opening technical details.

The overlay should remain visually professional and low-noise.

---

# 8. Mask preview states

Mask handling must be simple and truthful. The clinician should not need to understand thresholds.

Use three explicit states.

## 8.1 State A — Accepted analysis representation

Example:

```text
Mask status: Ready
```

User may switch between:

```text
Original
Analysis area
Mask preview
```

The system may use the accepted representation downstream according to the existing processing contract.

## 8.2 State B — Candidate exists but did not meet acceptance threshold

If the processing pipeline has a usable candidate representation but it failed an automatic confidence / quality gate:

**Do not hide the candidate from the reviewer.**

Allow:

```text
Mask preview
```

and label clearly:

```text
Candidate mask — review only
Not approved for model input
```

Visualize retained/excluded areas exactly as in State A.

Requirements:

- user inspection does not automatically approve it;
- do not silently send it to model inference;
- preserve threshold/status/provenance in Processing details;
- manual clinical review continues normally;
- no mandatory clinician “mask approval” workflow unless separately approved.

This is an explanation surface, not another clinical task.

## 8.3 State C — No safe candidate representation exists

If no valid/candidate mask representation can be produced at all:

Do not present the Mask Preview control as a mysterious disabled dead end.

Preferred behavior:

- keep `Mask preview` discoverable;
- selecting it opens a compact explanatory empty state, or
- show an adjacent info indicator.

Example:

```text
Mask preview unavailable

A safe analysis mask could not be produced for this image.
The original image remains available for manual review.
AI processing is unavailable for this image.

[ Continue with original ]
```

The user should not be asked to fix the mask.

The default operational path is:

```text
continue manual review
```

---

# 9. Do not turn mask thresholds into clinician work

Thresholds are technical processing policy.

Do not expose:

- raw threshold sliders;
- confidence tuning;
- algorithm parameters;
- retry parameters

to the normal clinician surface.

If an operator/technical user needs them, place them under:

```text
Processing details
```

or Models & Audit.

A physician reviewing hundreds of images should never need to ask:

> “What threshold should I choose?”

That is a system/engineering responsibility.

---

# 10. Mask preview and Explainability distinction

Keep the concepts separate:

```text
Mask preview
= preprocessing / processing evidence

Explainability
= model-specific evidence after inference
```

A mask is not an explanation of the model decision.

When AI is unavailable:

- Mask preview may still exist if preprocessing exists;
- Explainability may correctly be unavailable;
- manual review must remain uninterrupted.

Do not use explainability terminology to describe the mask itself.

---

# 11. Review screen information hierarchy

Preferred order:

```text
Retinal image
↓
Original | Analysis area | Mask preview | AI evidence
↓
one-line processing status
↓
Continue to clinician review
```

Secondary right-side information may include:

```text
AI assistance
Explainability
Processing details ▾
```

Do not let technical explanation dominate the retinal image.

---

# 12. Operational design principles

This patch must be reviewed against real clinical workload, not only feature completeness.

## 12.1 Time-to-understand

A first-time medical user should understand the primary action without reading a manual.

## 12.2 Time-per-case

Every visible control imposes review time even when untouched.

If a field/action is not routinely required, hide it by default.

## 12.3 System does the clerical work

Prefer:

```text
detect
prefill
remember
derive
validate
```

over manual re-entry.

## 12.4 Exceptions should be exceptional

Do not put rare-case controls on the main path.

## 12.5 No technical debugging burden on clinicians

Mask confidence, preprocessing thresholds, model availability, and provenance are system responsibilities.

The clinician receives:

```text
Ready
Review only
Unavailable — continue manually
```

not algorithm diagnostics.

## 12.6 Preserve expert speed

The system should not slow an ophthalmologist merely to make the interface educational.

Help and detail remain available on demand.

---

# 13. Required data-contract preservation

This patch changes presentation and automatic evidence handling, not the underlying clinical authority model.

Preserve:

- PostgreSQL authoritative storage;
- immutable original image;
- revision/CAS behavior;
- audit history;
- reviewer identity;
- source/provenance;
- original-image coordinates;
- grade confirmation semantics;
- second-review/disagreement semantics;
- explicit completeness semantics;
- filename-derived values as evidence until appropriately confirmed;
- unknown values where evidence is insufficient;
- manual operation when AI/mask processing is unavailable.

Do not silently migrate historical records based on a new filename parser.

---

# 14. Suggested implementation boundaries

Likely affected areas may include:

```text
frontend/src/components/worklist/ConfirmImageDialog.tsx
frontend/src/pages/ReviewPage.tsx
frontend review/mask components
admission/resolver filename evidence logic
mask/derivative presentation metadata
focused frontend/backend tests
```

These are guidance only. MAIN/IMPLEMENT should inspect current code and choose the smallest coherent implementation.

Do not perform broad unrelated refactoring.

---

# 15. Validation requirements

## Confirm Image

Validate at least:

- fully resolved case requires minimal interaction;
- unresolved image type exposes only necessary choice;
- unresolved eye exposes only necessary choice;
- filename-supported eye/patient/sequence suggestions appear correctly;
- ambiguous filename safely returns Unknown;
- manual correction overrides suggestion;
- previously confirmed context is not silently replaced;
- Additional metadata is collapsed by default;
- optional metadata persists when intentionally entered;
- keyboard operation remains usable.

## Longitudinal evidence

Validate:

- sequence token is evidence, not automatic chronology;
- date/time outranks filename sequence when supported;
- before/after is not fabricated from unsupported order;
- Unknown remains valid;
- existing visit-context persistence remains compatible.

## Mask

Validate all three states:

```text
READY
CANDIDATE / BELOW GATE
UNAVAILABLE
```

For each:

- correct view availability;
- correct retained/excluded visual treatment;
- correct boundary rendering;
- no silent approval;
- no unqualified model inference;
- manual workflow remains available;
- no clinician threshold-setting burden.

## Visual / accessibility

Validate:

- retained vs excluded regions are distinguishable at normal workstation zoom;
- text/legend has adequate contrast;
- color is not the sole state indicator;
- no additional page transition is introduced;
- no primary workflow overflow at supported laptop resolution.

---

# 16. Review and integration policy

This remains one bounded Owner-UAT patch.

```text
MAIN
→ one bounded IMPLEMENT stream
→ focused validation
→ one exact-candidate independent REVIEW
→ fix BLOCKER / REQUIRED FIX only
→ affected re-review only if needed
→ integrate
→ final validation
→ Owner UAT
```

Do not reopen broad Phase 2 review.

---

# 17. Owner UAT acceptance checklist

Owner should be able to say YES to all:

### Confirm Image

- I can understand what needs confirmation immediately.
- I am not asked to fill metadata the system could derive.
- Optional metadata does not distract me.
- I can confirm a normal case quickly.
- Unknown/uncertain cases do not force a guess.

### Mask

- I can immediately tell retained from excluded area.
- I do not need to understand or adjust a threshold.
- If a candidate is below threshold, I can still inspect it without accidentally approving it.
- If no mask exists, I know immediately that I can continue with the original image.
- Mask failure never blocks manual review.

### Overall

- The system feels suitable for repeated high-volume clinical use.
- The interface does not make clinicians manage internal technical states.
- The normal path is shorter than the exception path.
- The retina remains the primary object on screen.

---

# 18. Completion receipt

Return:

```text
Starting SHA:
Candidate SHA:
Final main SHA:

Confirm Image:
primary fields:
auto-derived evidence:
Additional metadata:
filename parser:
chronology safeguards:

Mask:
READY behavior:
below-gate candidate behavior:
unavailable behavior:
retained/excluded visualization:
threshold hidden from clinician:

Focused tests:
Backend:
Frontend:
Typecheck:
Build:
git diff --check:

Independent review:
Brain:
main == origin/main:
clean:

Phase 2:
READY_FOR_REVIEW

Owner UAT:
PENDING
```

Do not mark Phase 2 `DONE`; Owner acceptance remains required.

# End of Phase 2.1 Owner UAT Operation Simplification Patch
