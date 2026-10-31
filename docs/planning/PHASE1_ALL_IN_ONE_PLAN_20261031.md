# Phase 1 All-in-one plan: screening, archive sorting and Gold-100 labelling

Status: PROPOSAL for owner approval, 31 October 2026. No code has been changed for
this plan. Clinical rules in section 4 need sign-off by the responsible physician
before any implementation. Not a diagnostic device; research and screening support
only.

Inputs: owner requirements (chat, 31 October 2026), ICO Guidelines for Diabetic
Eye Care (2017, Table 1, Table 2a, Table 2b), the owner's
`UWF_GOLD100_RESEARCH_PROTOCOL_V1.md`, the UWF ROI paper (Oh et al., J Imaging
Inform Med 2026, doi:10.1007/s10278-026-02259-6, CC BY 4.0), and the current code.

## 1. Users and the three jobs

| Job | Who | Output |
| --- | --- | --- |
| Screen new patients | Nurses, general physicians | DR grade (preliminary or confirmed), suggested referral, follow-up |
| Sort an image archive | Physicians | Copies of images in folders by grade |
| Collect research labels | Ophthalmologist (expert), AI research team | Gold-100 labels and a research dataset for phase 2 |

Phase 2 (after the Gold-100 is complete): train the hospital's own grading and ROI
models, then lesion and vein classification on CFP and UWF.

## 2. One program, two work areas

Screening and archive sorting are the same pipeline, so they become one work area
with two entry points:

```text
Screening work area
  Entry A: Screen new patients (one patient at a time)
  Entry B: Sort an image archive (a whole folder, as a batch)
        |
  import (copy, originals never changed) -> rim mask A2 -> AI grade (+ PRISM lesions)
        |
  person confirms or corrects the grade
        |
  outputs: suggested referral (only with a signed rule), grade folders, worklist
```

Research labelling stays a separate work area (section 6), because research labels
must not mix with screening decisions.

Grade folders keep two sets apart:

- `ai_predicted_unverified/grade_0..4, ungradable, low_confidence/` from AI only.
- `confirmed/grade_0..4, ungradable/` only after a person confirms (the existing
  grouped export already does this for confirmed grades).

AI folders say "unverified" in the name and in the manifest. They are never
counted as clinical grades or as training labels.

## 3. Roles (new)

Today the app has `admin` and `user`. Proposed:

| Role | Can do |
| --- | --- |
| Nurse | Import, run AI, give a preliminary screening grade, see the suggested referral (if the signed rule allows preliminary grades) |
| Physician | All of the above, confirm or correct grades, sort archives, export |
| Expert (ophthalmologist) | Research labelling work area, Gold-100 |
| Researcher | Research exports and dataset checks, no clinical decisions |
| Admin | Accounts, policy, read-only database view |

Every change records the signed-in user. Which role may finalise a grade used for
referral is a clinical decision (section 4).

## 4. Grading and referral: needs physician sign-off

### 4.1 Grade scale

ICO Table 1 is the International Clinical DR scale: 0 No apparent DR, 1 Mild NPDR
(microaneurysms only), 2 Moderate NPDR, 3 Severe NPDR (4-2-1 rule: haemorrhages in
4 quadrants, venous beading in 2, IRMA in 1), 4 PDR. DME is a separate axis (no,
non-central, central) and needs a 3-D exam to diagnose.

The deployed USPEC grader (NB01) outputs five classes 0 to 4 for UWF only
(`NOT_VALIDATED_FOR_CFP`, production rights `UNVERIFIED`). Owner answer
(31 October): NB01 was fine-tuned on MMRDR (Tang et al., Sci Data 2026), whose
UWF labels are five classes 0 to 4 (No DR, Mild, Moderate, Severe NPDR with the
4-2-1 rule, PDR) following Wilkinson 2003 and ICO, on Optos images (10,404 UWF
images, 6,109 patients). So the grade scale matches ICDR and the Thai DMS 2026
guideline. Limits: MMRDR grades DME only on OCT, so the grader does not predict
DME; poor-quality images were excluded from MMRDR, so the grader has not learned
"ungradable" and a person must judge gradability; the MMRDR article is
CC BY-NC-ND, so the model stays research and non-commercial.

### 4.2 Referral

The only referral rule in the code today is the owner-confirmed
`M1_DR_GRADE_4_REFERRAL` (refer only when a physician-confirmed grade is 4). The
owner's flow ("severe to ophthalmologist, any DR to a specialist") differs from it
and from ICO, so a new versioned rule needs a signed definition. ICO for
comparison:

| ICDR grade | ICO high resource (Table 2a) | ICO low/intermediate (Table 2b) |
| --- | --- | --- |
| 0 No apparent DR | rescreen 1-2 years, no referral | rescreen 1-2 years, no referral |
| 1 Mild NPDR | 6-12 months, no referral | 1-2 years, no referral |
| 2 Moderate NPDR | 3-6 months, refer | 6-12 months, refer |
| 3 Severe NPDR | under 3 months, refer | under 3 months, refer |
| 4 PDR | under 1 month, refer | under 1 month, refer |
| Central-involved DME | 1 month, refer | 1 month, refer |

Decision table for the physician to fill in and sign:

| Question | Answer |
| --- | --- |
| Grade scale | ICDR 0-4 (ICO Table 1)? |
| "Refer to ophthalmologist" from which grade, how soon | |
| "Refer to specialist" from which grade, how soon | |
| Ungradable image | refer / repeat photo / physician review |
| Suspected DME (hard exudates near the fovea) | |
| Same rule for UWF and CFP | |
| May a nurse's preliminary grade trigger the suggestion, or only a physician-confirmed grade | |

Until signed, the app keeps showing only the existing rule.

## 5. Hospital server and deployment

### 5.1 Two packages from one codebase

| Package | Where | Purpose |
| --- | --- | --- |
| Hospital local (VLAN) | Linux server inside the hospital | Real use; images never leave the hospital |
| Team server (dr-train) | Team GPU host | AI demo for the hospital, and the AI service for option A below |

Plus the existing Windows one-click workstation for a single PC or a laptop demo.

### 5.2 Docker: recommended for the servers, done by us

Recommendation: yes for the hospital server package, prepared by the engineering
team; IT runs one install script; physicians and nurses only open a browser link
(or a desktop shortcut). Nobody clinical touches Docker.

Why: the same image runs on the demo and in the hospital; installs offline in a
closed VLAN (`docker load` from a file); update and rollback are a version tag;
hospital IT usually knows it.

Conditions:

- Linux with Docker Engine (free). Not Docker Desktop on Windows Server (licence
  for large organisations, GPU passthrough issues).
- GPU needs the NVIDIA driver and NVIDIA Container Toolkit on the host.
- Three services: `app` (web + API), `postgres`, `model-api` (GPU). Data on host
  folders with nightly backup.
- Model weights are not baked into images. They live in a read-only folder and are
  checked against pinned hashes at start (as today). RETFound official weights are
  CC BY-NC 4.0 and USPEC rights are UNVERIFIED, so images and weights are not
  redistributed outside the project.
- dr-train is shared with other teams (Ollama, GPU1). Changing it to Docker needs
  team agreement; it can stay native at first.

### 5.3 Server specification

Measured today: the GPU child with the graders and PRISM loaded uses about 2.8 GB
of GPU memory; the app and PostgreSQL are light for 3 to 5 users.

**Option A: app and database in the hospital, AI on the team server**

| Item | Size |
| --- | --- |
| CPU | 8 cores |
| RAM | 16 GB (32 GB if archives over 20,000 images) |
| System disk | 512 GB SSD |
| Data disk (separate) | 2-4 TB for originals, analysis copies, grade-folder copies |
| Backup | separate disk or NAS, at least the data disk size |
| GPU | none |
| Network | IT-approved route to the team Model API, plus approval to send image bytes out of the hospital |

**Option B: everything inside the hospital, including AI**

| Item | Size |
| --- | --- |
| CPU | 12-16 cores |
| RAM | 64 GB |
| GPU | one card with 24 GB (16 GB is enough for inference; 24 GB leaves room for phase 2 training). Server-friendly examples: NVIDIA L4, RTX 4500 Ada, RTX A5000 |
| System disk | 1 TB SSD (RAID 1 if possible) |
| Data disk (separate) | 4 TB or more |
| Backup | separate disk or NAS |
| OS | Ubuntu Server 22.04 or 24.04 LTS |
| Power | UPS |

Storage note: an Optos JPEG is a few MB, an Optos DICOM can be 20-35 MB. 10,000
DICOM images is about 350 GB before analysis copies and grade-folder copies.

### 5.4 Backup server and demo: privacy limits

- If the hospital server fails, switching to dr-train sends patient images outside
  the hospital. That needs explicit hospital data-transfer approval. Without it,
  the backup is a second local machine or a restore onto spare hardware.
- The demo on dr-train uses public or consented demo images only and needs an
  approved network route (no open internet port).

## 6. UI language

English by default with an EN/TH switch. In Thai mode, headings and technical
terms stay English (DR grade, ROI, Refer, PRISM, Confirm Image). Translations are
reviewed with the `thai-natural-writing` skill. The choice is a per-user setting.

## 7. Gold-100 labelling (ideas for the research protocol)

The ophthalmologist selects the 100 images; the program supports and records, and
never second-guesses the expert.

### 7.1 Respect and bias control

- Grade first without AI. The expert's grade is entered before any AI suggestion is
  shown. Then the AI suggestion can be shown as a second opinion; any change is
  saved as a separate field (grade before AI, grade after AI). This keeps the Gold
  clean of anchoring and gives a small AI-influence result for the paper.
- Wording: "Your grade is the reference", "AI suggestion (optional)". No warnings
  such as "AI disagrees". Only the grade and gradability are required.
- Selection: record who selected and a short reason category (typical, hard,
  severe, rare). The protocol's TypiClust section becomes "expert-selected", with
  selection bias stated. A coverage helper (counts by AI-predicted grade and image
  quality) is offered as information only.
- Optional, only if the expert agrees: 10-20 consecutive archive images to estimate
  real-world mix.

### 7.2 What to record per image (fast fields)

| Field | Cost |
| --- | --- |
| ICDR grade 0-4, gradable, main quality issue, laterality | required, about 20 s |
| Expert confidence (sure / unsure) | 1 click |
| Signs per quadrant (superior, inferior, nasal, temporal): haemorrhages, venous beading, IRMA, neovascularisation, hard exudates near the fovea | a few checkboxes; matches the ICO 4-2-1 rule and gives weak location labels for MIL |
| Suspected DME (not a diagnosis) | 1 click |
| Referral by the signed rule | automatic |
| Time spent | automatic |

Optional, after the grade: PRISM lesion boxes accept or reject (provenance kept as
AI-suggested versus expert-drawn); ROI mask from A2 corrected by the research
team and only spot-checked by the expert, to save expert time.

### 7.3 Cheap extra evidence

- Intra-rater check: 10-15 images shown again, blinded, after about two weeks.
- Second expert on a subset if one is available (inter-rater agreement).
- Nurses and general physicians grade the same 100 images blind: screening
  accuracy of non-specialists against Gold, which is the product question.
- The protocol's split stays: about 80 development and 20 untouched test, by
  patient.

### 7.4 "Vein"

Clarify: venous beading (an ICO severe NPDR sign, collected in 7.2), retinal vein
occlusion (a separate disease label), or vessel segmentation (pixel masks, a
different and costly task).

## 8. Phase 1 delivery order (proposed)

1. Sign-off: referral table (4.2), roles (3), "vein" meaning (7.4).
2. Roles and EN/TH switch.
3. Combined screening work area with archive sorting and the two folder sets.
4. Research labelling work area for Gold-100 (7.1, 7.2).
5. Server package (Docker for the hospital VLAN) with install, backup and rollback
   scripts, tested first on a spare machine.
6. Pilot on the hospital server after IT confirms option A or B.

## 8a. Owner answers, 31 October 2026 (second round)

1. Input: the program must take both new patients and archive folders (section 2).
   Servers: both team designs. A: QA inside the hospital (VLAN) plus production;
   B: QA in the cloud with an import that hospital IT approves. Either way
   production (app, database, model server, images) stays in the hospital
   network with no general internet.
2. NB01 training data: MMRDR (section 4.1).
3. Phase 1 has no referral system. Output is a PDF report that states Refer or
   Not refer, chosen by the person who grades, on a form the physician team
   reviews first. Draft form (A4, synthetic and blank, built from ICO 2017, Thai
   DMS 2026 and MOH Singapore Advisory 04/2023):
   https://claude.ai/artifact/6MsbQJ9J1NFdGzytrRkUMD (private until shared).
   Automatic referral suggestions wait for the signed table in section 4.2.
   The Thai DMS guideline gives two thresholds to settle: its AI chapter treats
   moderate NPDR or worse, suspected DME, other significant retinal disease and
   ungradable images as "referable", while its urgency section lists severe
   NPDR or worse and DME; ungradable images must never be reported as normal.
4. The hospital allows no patient image to leave, except consented images (such
   as the consented UWF demo set). dr-train is for development and emergencies
   only; real use runs on the hospital-local package. The backup-to-dr-train idea
   in 5.4 is therefore out for real patients.
5. Ethics approval: later, after the team agrees the program is worth taking further.
6. "Vein" means vessel segmentation (vascular structure). This is phase 2 and
   needs pixel masks, the most expensive label type. Ideas for later: draft
   vessel maps from a classic filter or a public model for experts to correct
   only on a small set, and agree a target with the physicians first.

## 9. Open questions for the owner

1. Option A or B for the hospital server, and whether IT allows Docker on Linux.
2. Which dataset and label guide the NB01 USPEC head was trained on.
3. The referral decision table (4.2), signed by the responsible physician.
4. Hospital approval for any image leaving the hospital (backup, option A).
5. Ethics approval for the Gold-100 study and later publication.
