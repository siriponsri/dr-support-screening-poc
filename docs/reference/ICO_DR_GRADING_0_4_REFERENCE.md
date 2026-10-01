# ICO Diabetic Retinopathy Grading Reference for M1 (0-4)

**Source basis:** International Council of Ophthalmology (ICO), *ICO Guidelines for Diabetic Eye Care*, Updated 2017.

**Purpose:** This file is the clinical reference for the M1 five-level diabetic retinopathy (DR) grade shown in the clinician UI. It is intended to make the 0-4 labels explicit and consistent. It does not create a new grading system and does not authorize referral, treatment, or DME decisions.

**Project mapping:**

| Internal value | Clinician-facing label | ICO severity category |
|---|---|---|
| `0` | No apparent DR | No apparent diabetic retinopathy |
| `1` | Mild NPDR | Mild nonproliferative diabetic retinopathy |
| `2` | Moderate NPDR | Moderate nonproliferative diabetic retinopathy |
| `3` | Severe NPDR | Severe nonproliferative diabetic retinopathy |
| `4` | Proliferative DR (PDR) | Proliferative diabetic retinopathy |

`Ungradable` and `Needs Second Review` are project workflow states. They are not ICO DR severity grades and must not be encoded as 0-4.

---

## 1. ICO source hierarchy used by this reference

This reference is derived from the following parts of the supplied ICO 2017 guideline:

1. **International Classification of Diabetic Retinopathy and Diabetic Macular Edema** - printed page 2 (PDF page 7).
2. **Annex Table 1: Features of Diabetic Retinopathy** - printed page 16 (PDF page 21).
3. **Annex Table 2: Features of Proliferative Diabetic Retinopathy** - printed page 17 (PDF page 22).
4. **Annex clinical photographs** - printed pages 21-29 (PDF pages 26-34), including examples of mild NPDR, moderate NPDR, severe NPDR, IRMA, venous abnormalities, NVD/NVE, and preretinal hemorrhage.

The 0-4 mapping below is a software encoding of the five ICO severity categories. The source guideline itself names the categories; it does not assign the integers 0-4.

---

# 2. Grade 0 - No apparent DR

## ICO criterion

**No abnormalities attributable to diabetic retinopathy are identified.**

## Practical interpretation for M1

Use Grade 0 only when the image is sufficiently reviewable and the reviewer does not identify DR lesions that would place the eye in Grades 1-4.

Grade 0 must not be used merely because:

- AI returned no detections;
- the detector is unavailable;
- a mask failed;
- the image is poor quality;
- the reviewer has not completed the review;
- no annotation boxes were drawn.

Those conditions are workflow/evidence states, not proof of no apparent DR.

## UI help text

> **0 - No apparent DR**  
> No diabetic-retinopathy abnormality is identified on the reviewable image.

---

# 3. Grade 1 - Mild NPDR

## ICO criterion

**Microaneurysms only.**

This is the key boundary: if additional DR signs are present beyond microaneurysms alone, the case is no longer Mild NPDR under the ICO classification.

## Relevant ICO lesion description

ICO describes microaneurysms as isolated, spherical red dots of varying size. The Annex also notes that small dot hemorrhages may not always be distinguishable from microaneurysms on appearance alone.

## Practical interpretation for M1

Use Grade 1 when:

- one or more microaneurysms are identified; and
- there are no additional DR findings that move the case to Moderate NPDR or above; and
- there are no Severe NPDR or PDR signs.

Do not use Grade 1 when hemorrhages, hard exudates, cotton-wool spots, or other DR signs clearly make the case more than microaneurysms only.

## UI help text

> **1 - Mild NPDR**  
> Microaneurysms only. Additional DR signs move the case beyond Mild NPDR.

## ICO visual reference

- Annex Figure 1: mild nonproliferative diabetic retinopathy with microaneurysms.

---

# 4. Grade 2 - Moderate NPDR

## ICO criterion

**Microaneurysms with other DR signs, but less than Severe NPDR.**

ICO examples of the additional signs include:

- dot hemorrhages;
- blot hemorrhages;
- hard exudates;
- cotton-wool spots.

The decisive upper boundary is that the eye does **not** meet Severe NPDR criteria and does not have PDR signs.

## Practical interpretation for M1

Use Grade 2 when the retinopathy is clearly more than microaneurysms alone, but none of the ICO Severe NPDR threshold patterns is met and no PDR sign is present.

Common examples include combinations of:

- microaneurysms plus retinal hemorrhages;
- microaneurysms plus hard exudates;
- microaneurysms plus cotton-wool spots;
- other NPDR changes that remain below the Severe NPDR threshold.

### Important caution

Hard exudates may coexist with DME, but **DR severity grade and DME status are separate classifications**. Do not increase or decrease the 0-4 DR grade merely from DME status.

## UI help text

> **2 - Moderate NPDR**  
> More than microaneurysms alone (for example hemorrhages, hard exudates, or cotton-wool spots), but below Severe NPDR criteria.

## ICO visual references

- Annex Figure 2: moderate NPDR with hemorrhages, hard exudates, and microaneurysms.
- Annex Figures 3-7: additional examples of moderate NPDR, including examples with and without macular edema.

---

# 5. Grade 3 - Severe NPDR

## ICO criterion - the 4-2-1 severity pattern

ICO classifies Severe NPDR as Moderate NPDR with **any one or more** of the following findings, with **no signs of proliferative retinopathy**:

1. **Intraretinal hemorrhages:** at least 20 in **each of 4 quadrants**.
2. **Definite venous beading:** present in **2 quadrants**.
3. **Intraretinal microvascular abnormalities (IRMA):** present in **1 quadrant**.
4. **No signs of PDR.**

For software/UI wording, this can be summarized as the traditional **4-2-1 rule**, while retaining the actual criteria above in the Grade Guide.

## Important interpretation

Meeting **any one** of the three lesion-distribution thresholds is sufficient for the Severe NPDR category, provided proliferative signs are absent.

Do not require all three thresholds simultaneously.

Do not classify as Grade 3 if definite proliferative signs are present; the case belongs in the PDR category rather than Severe NPDR.

## Relevant ICO lesion descriptions

### Intraretinal hemorrhage

ICO distinguishes dot and blot hemorrhages and describes blot hemorrhages as intraretinal hemorrhages related to capillary occlusion.

### Venous beading

ICO lists venous beading among abnormalities associated with extensive capillary-network closure.

### IRMA

ICO describes IRMA as dilated capillary remnants following extensive capillary-network closure between an arteriole and venule.

## UI help text

> **3 - Severe NPDR**  
> No proliferative signs, plus at least one ICO 4-2-1 criterion: >=20 intraretinal hemorrhages in each of 4 quadrants, definite venous beading in 2 quadrants, or IRMA in 1 quadrant.

## ICO visual references

- Annex Figures 8-9: severe NPDR examples.
- Annex Figure 10: severe NPDR with venous loop.
- Annex Figure 11: severe NPDR with IRMA.

---

# 6. Grade 4 - Proliferative DR (PDR)

## ICO criterion

ICO defines Proliferative DR as Severe NPDR with **one or more proliferative findings**:

- **Neovascularization**; and/or
- **Vitreous hemorrhage or preretinal hemorrhage**.

These are proliferative findings and move the case beyond the NPDR scale.

## Relevant ICO proliferative features

### New vessels at the disc (NVD)

ICO describes NVD as new vessels arising from the venous circulation on the disc or within one disc diameter of the disc. The Annex notes that NVD should be distinguished from fine normal vessels; normal vessels taper, while NVD may loop back and form a chaotic vascular network.

### New vessels elsewhere (NVE)

ICO describes NVE as new vessels that commonly occur near the border between healthy retina and areas of capillary occlusion. The Annex specifically warns not to confuse NVE with IRMA, which occurs within areas of capillary occlusion.

### Other proliferative findings

The ICO Annex also describes:

- new vessels at other sites such as iris/anterior segment locations;
- fibrous proliferation associated with proliferative retinopathy.

The five-level project grade should still remain Grade 4; these features may be captured separately as detailed findings when the approved labeling taxonomy supports them.

## UI help text

> **4 - Proliferative DR (PDR)**  
> Proliferative disease with neovascularization and/or vitreous or preretinal hemorrhage.

## ICO visual references

- Annex Figure 12: PDR with venous beading and NVE.
- Annex Figures 13-14: high-risk PDR with new vessels at the disc and preretinal hemorrhage.
- Annex Figure 15: PDR with new vessels at the disc and elsewhere.

---

# 7. Grade boundary summary

| Grade | Name | ICO-defining boundary | Examples / key signs |
|---|---|---|---|
| `0` | No apparent DR | No DR abnormalities | No identifiable DR lesion on a reviewable image |
| `1` | Mild NPDR | Microaneurysms only | Microaneurysms; no additional DR sign |
| `2` | Moderate NPDR | More than microaneurysms only, but below Severe NPDR | Dot/blot hemorrhage, hard exudate, cotton-wool spot, other NPDR signs below severe threshold |
| `3` | Severe NPDR | At least one ICO 4-2-1 criterion and no PDR sign | >=20 intraretinal hemorrhages in each of 4 quadrants; venous beading in 2 quadrants; IRMA in 1 quadrant |
| `4` | PDR | Proliferative signs | Neovascularization; vitreous/preretinal hemorrhage |

---

# 8. Recommended UI decision order

This section is a **project operationalization of the ICO mutually exclusive categories**, not a new clinical classification.

```text
Can the image be graded reliably?
  No  -> Ungradable (separate workflow state; not 0-4)
  Yes -> continue

Are proliferative signs present?
  Yes -> Grade 4: PDR
  No  -> continue

Is any Severe NPDR 4-2-1 criterion met?
  Yes -> Grade 3: Severe NPDR
  No  -> continue

Are there DR signs beyond microaneurysms only?
  Yes -> Grade 2: Moderate NPDR
  No  -> continue

Are microaneurysms present?
  Yes -> Grade 1: Mild NPDR
  No  -> Grade 0: No apparent DR
```

If the reviewer cannot resolve a clinically meaningful ambiguity despite a reviewable image, use the project's **Needs Second Review** state rather than forcing a 0-4 grade.

---

# 9. DME is separate from DR grade

The ICO guideline classifies DME separately from the DR severity scale.

The supplied ICO document distinguishes:

- **No DME**;
- **Noncentral-involved DME**;
- **Central-involved DME**.

The defining concept is retinal thickening and whether the central subfield is involved. Hard exudates may be associated with current or previous edema but are not, by themselves, a substitute for the DME classification.

Therefore M1 must preserve:

```text
DR grade 0-4 != DME status
```

Do not infer referral, treatment, or DME status from the 0-4 DR grade alone.

---

# 10. Lesion notes for Grade Guide / tooltips

These descriptions are condensed from the ICO Annex and are intended for contextual help, not to replace clinician training.

| Finding | ICO-oriented recognition note | Grading relevance |
|---|---|---|
| Microaneurysm | Small isolated spherical red dot; may be difficult to distinguish from a small dot hemorrhage | Alone -> Mild NPDR |
| Dot hemorrhage | May resemble a microaneurysm; distinction may be difficult | Additional DR sign -> at least beyond Mild if clearly present with other NPDR findings |
| Blot hemorrhage | Intraretinal hemorrhage associated with capillary occlusion | Contributes to NPDR severity; distribution/count matters for Severe NPDR |
| Cotton-wool spot | Swollen nerve-fiber-layer axonal ends from interrupted axoplasmic flow; not exclusive to DR | Example of Moderate NPDR sign; not by itself a PDR sign |
| Venous beading | Venous abnormality associated with extensive capillary closure | Definite involvement in 2 quadrants is a Severe NPDR criterion |
| IRMA | Dilated capillary remnants after extensive capillary-network closure | In 1 quadrant is a Severe NPDR criterion |
| NVD | Neovascularization on/near optic disc | PDR sign |
| NVE | Neovascularization elsewhere, often near border of perfused/nonperfused retina | PDR sign; distinguish from IRMA |
| Preretinal hemorrhage | Hemorrhage anterior to retina | PDR sign in ICO classification |
| Vitreous hemorrhage | Hemorrhage into vitreous | PDR sign in ICO classification |

---

# 11. UWF-specific caution

The supplied ICO 2017 classification defines disease severity using retinal findings observable on clinical retinal examination and does **not** provide a separate UWF-specific 0-4 severity scale or a special peripheral-lesion weighting rule.

For M1:

- apply the approved ICO five-category rubric consistently;
- do not invent a UWF-specific severity modifier;
- do not change the 4-2-1 thresholds because the image has a wider field;
- record any future UWF-specific adaptation only after explicit clinical review and version it separately.

---

# 12. Treated / stable PDR and other unresolved edge cases

The ICO document contains treatment and post-treatment examples, but the five-category Table 1 does not define a dedicated sixth category for "treated PDR" or a project-specific rule for stable post-PRP images.

Therefore this reference does **not** invent one.

Until the project clinical owner freezes a treated/stable PDR rule:

- preserve visible treatment evidence and review history;
- do not silently downgrade a historically proliferative eye based only on a quiet post-treatment appearance;
- use `Needs Second Review` when the correct project grade cannot be determined under the approved rubric;
- record any future treated-PDR rule as a versioned clinical decision.

---

# 13. Software acceptance requirements

The clinician Grade Guide implemented from this reference should:

1. show all five grades with **number + name + concise criterion**;
2. make the Grade 3 4-2-1 criteria explicitly visible rather than hiding them behind "severe pattern" wording;
3. make Grade 4 proliferative signs explicit;
4. keep `Ungradable` and `Needs Second Review` outside the 0-4 values;
5. state that DME is a separate classification;
6. avoid referral/treatment recommendations in the grade chooser;
7. avoid auto-grading from lesion count, AI output, or empty annotations;
8. preserve clinician final authority;
9. keep the detailed reference available through a compact popover/drawer/help surface without making the normal expert workflow slower;
10. use the same terminology in UI, API presentation labels, tests, docs, and evidence receipts.

---

# 14. Reference labels for implementation

Recommended canonical display strings:

```text
0 - No apparent DR
1 - Mild NPDR
2 - Moderate NPDR
3 - Severe NPDR
4 - Proliferative DR (PDR)
```

Recommended compact help strings:

```text
0 - No DR abnormality identified
1 - Microaneurysms only
2 - More than microaneurysms only; below severe criteria
3 - ICO 4-2-1 severe NPDR criteria; no PDR sign
4 - Neovascularization and/or vitreous/preretinal hemorrhage
```

Do not replace the full Grade 3 detail with the compact string in the detailed Grade Guide.

---

# 15. Source note

Clinical source: International Council of Ophthalmology, *ICO Guidelines for Diabetic Eye Care*, Updated 2017. This project reference adapts the five-category DR severity classification, Annex lesion descriptions, and visual examples for a software Grade Guide. It does not claim that the ICO document defines this project's numeric encoding, UWF workflow, AI behavior, or project-specific exception states.

# End of ICO DR Grading Reference
