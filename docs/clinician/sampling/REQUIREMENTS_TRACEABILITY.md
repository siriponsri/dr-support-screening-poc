# Image sampling requirements traceability

This file is the source of truth for every `IMG-SAMP-*` requirement. The Team Image Sampling Requirements PDF, the Clinician Image Selection Guide, the product presentation, and the technical briefing cite these IDs and do not restate them with different wording.

Changing a requirement here does **not** change Workbench admission, review, or export behaviour. Software behaviour changes need a separate owner-approved spec (see `AGENTS.md`).

## How to read the columns

- **Level**
  - `SW`: implemented software behaviour on `main`, verified in code and tests.
  - `OWN`: explicit owner/team decision (V4 handoff).
  - `TGT`: internal POC sampling target. This is not a clinical requirement, not a prevalence claim, and not a powered sample-size calculation.
  - `EXT`: external best-practice recommendation. It is adopted only as guidance.
  - `OPEN`: proposed; needs owner or clinical approval before it is used.
- **Audience**
  - `C`: clinician or authorized hospital user.
  - `T`: project team or dataset coordinator.
  - `D`: developer.
  - `H`: hospital coordinator or IT.
- **Software-enforced?** says whether the Workbench itself enforces the requirement:
  - `Yes`: it enforces it.
  - `Partial`: it gives evidence but does not enforce it.
  - `No`: it plays no part.
- **Clinician action?** and **Team action?** name what each role actually does. `None` means nothing.

## Requirements

| ID | Requirement | Audience | Level | Source type | Software-enforced? | Clinician action? | Team action? | Owner approval needed? |
|:--------|:----------------------------|:---|:----|:-------|:--------|:--------|:---------|:------|
| IMG-SAMP-001 | The project team and the Workbench do not browse, query, or harvest hospital-controlled storage, and do not pre-select images for clinicians. | T, H, D | OWN | Owner decision | Partial: the Workbench only scans its configured Workspace input folder | None | Do not request storage access; do not propose automatic PACS/storage queries | No (decided) |
| IMG-SAMP-002 | A clinician or authorized hospital user chooses each candidate retinal image from hospital-controlled storage during normal work. | C | OWN | Owner decision | No | Choose the image | None | No (decided) |
| IMG-SAMP-003 | Only selected images reach the Workbench, and only through the hospital-approved staging/transfer process into the Workspace input folder. | C, H | OWN | Owner decision | Partial: admission reads only the Workspace input folder, top level, no sub-folders | Stage through the approved process | Confirm the approved process exists before collection starts | Yes: the approved staging process itself |
| IMG-SAMP-004 | Stage the original image file. Do not crop, annotate, recompress, convert, or screenshot it before staging. | C, H | OWN + SW | Owner decision; repository immutability rule | Partial: SHA-256 source identity, format/extension checks, source-change detection | Copy the original file | Investigate `Source changed` or format-mismatch cases | No |
| IMG-SAMP-005 | Staged filenames and folders must not carry direct identifiers. Any pseudonymous naming is done by the approved hospital process, not invented per image by the clinician. | H, T | OPEN | Privacy boundary; export includes `filename` | No | None beyond the approved process | Agree a naming convention with the hospital | Yes |
| IMG-SAMP-010 | The only source classification is `Refer` / `Not-refer`, as already held by the source hospital workflow. It is the primary sampling axis. | T, C | OWN | Owner decision | No: the Workbench stores no source class | None: the class already exists in the source workflow | Record the class for each staged image in the team tracking record | No (decided) |
| IMG-SAMP-011 | Source class (`Refer`/`Not-refer`) is a separate concept from the Workbench clinician DR grade (0–4) and annotations. Neither is mapped onto, overwritten by, or derived from the other. | T, D | OWN + SW | Owner decision; code | Yes: grade values are 0–4 and grade sources are `AI_ACCEPTED` / `AI_CORRECTED` / `MANUAL`; no source-class field exists | None | Keep source class in the team record only | No |
| IMG-SAMP-012 | During pre-selection the clinician is not asked for a DR grade, lesion labels, an image-quality score, a research cohort, a train/validation/test group, or demographic data. | C | OWN | Owner decision (minimum burden) | No | None | Keep forms and requests free of these fields | No (decided) |
| IMG-SAMP-013 | How the source class (and sex, where used) is linked to each staged image is decided before collection, without adding per-image clinician data entry. Options: one Workspace per class, a hospital-supplied pseudonymous list, or coordinator batch logs. | T, H | OPEN | Gap: the Workbench has no source-class field | No | At most, stage into the folder for that class (only if that option is chosen) | Propose and run the chosen mechanism | Yes |
| IMG-SAMP-020 | For the current POC annotation batch, aim for approximately balanced `Refer` / `Not-refer` collection (planning band 40–60 % per class). | T | TGT | POC / annotation-coverage planning target | No | None | Monitor counts; ask the coordinator for more of the under-represented class | Yes: target N and band |
| IMG-SAMP-021 | A balanced collection is not hospital prevalence. Do not report prevalence, sensitivity/specificity, or clinical performance from this set without a new, purpose-specific sampling design. | T | EXT + OWN | FDA AI-enabled device draft guidance; TRIPOD+AI | No | None | Label every report "POC annotation-coverage sample" | No |
| IMG-SAMP-022 | Stop collecting for the current batch when the owner-approved total N is reached, each class has at least its floor (default proposal: 40 % of N), and the Unknown-laterality share is at most 20 %, or when the owner decides to stop. | T | TGT + OPEN | Internal planning | No | None | Check the stopping rule at each monitoring update | Yes |
| IMG-SAMP-030 | Sex is recorded only when it is already available from approved source metadata or the approved workflow. Clinicians never re-enter it per image. | T, C | OWN | Owner decision | No: the Workbench stores no sex field | None | Take sex from approved metadata only, or leave it `Unknown` | No (decided) |
| IMG-SAMP-031 | Both sexes should be represented where data are available. Counts of Male / Female / Unknown are reported by source class. | T | OWN | Team requirement | No | None | Produce the sex × source-class table | No |
| IMG-SAMP-032 | Soft monitoring flag: raise a note to the owner if either known sex is below 30 % of known-sex images. This is a flag, not a quota and not a reason to exclude an image. | T | TGT | Internal POC target | No | None | Flag it in the monitoring update | Yes: threshold |
| IMG-SAMP-033 | `Unknown` / not available is an acceptable value for sex, laterality, and optional metadata. A useful retinal image is not excluded only because demographic metadata is missing. | T, C | OWN | Owner decision | Partial: laterality `UNKNOWN` is a valid Confirm Image value | Choose Unknown instead of guessing | Report Unknown rates | No |
| IMG-SAMP-040 | Both left and right eyes should be represented. The laterality distribution is reported by source class. There is no fixed 50/50 quota. | T | OWN | Team requirement | No | None | Produce the laterality × source-class table | No |
| IMG-SAMP-041 | Team laterality counts use the clinician-confirmed value from **Confirm Image** (`laterality_resolution_method = MANUAL` in `images.csv`). Filename, OCR, or DICOM candidates are evidence only. | T, D | SW + OWN | Code: Confirm Image contract and export columns | Yes: Confirm Image stores `LEFT` / `RIGHT` / `UNKNOWN` with method `MANUAL` | Set the eye in Confirm Image (the existing workflow step) | Count only confirmed values; treat others as Unknown | No |
| IMG-SAMP-042 | Laterality is never guessed from a filename for team statistics. Unconfirmed or unsafe laterality stays `Unknown`. | T, C | OWN + EXT | Owner decision; DICOM Image Laterality is the standard attribute | Partial: resolver candidates need confirmation in the workflow | Choose Unknown when not sure | Do not back-fill from filenames | No |
| IMG-SAMP-043 | Soft monitoring flag: note it if either known eye is below 30 % of known-laterality images. | T | TGT | Internal POC target | No | None | Flag it in the monitoring update | Yes: threshold |
| IMG-SAMP-050 | Several images from one patient, including both eyes, are allowed. They are not independent patients: the pseudonymous patient key is preserved and the team reports distinct patients as well as images. | T, D | SW + EXT | Code: `patient_key`, `training_group_key`; Tampu 2022 | Partial: grouping key exported; no automatic split | Link the patient key in Confirm Image (existing step) | Report distinct-patient count and images per patient | No |
| IMG-SAMP-051 | Any future ML train/validation/test experiment splits at patient/group level where identity is available. This POC creates no split. | T, D | EXT + SW | GMLP principles; Tampu 2022; export `grouping_policy` | Yes: export states "no automatic train-validation-test split" | None | Apply this only in future experiment designs | No |
| IMG-SAMP-052 | Soft monitoring flag: note any patient who contributes more than 4 images to a batch. | T | TGT + OPEN | Internal POC target | No | None | Flag it in the monitoring update | Yes: cap value |
| IMG-SAMP-060 | Byte-identical files are detected by SHA-256 and shown as one case with aliases (`Duplicate content`). | T, D | SW | Code: admission integrity | Yes | None | Review duplicate aliases before counting | No |
| IMG-SAMP-061 | Near-duplicates (repeat captures, re-exported or resized copies) are not detected automatically. The team reviews repeated patient + eye combinations. Clinicians avoid knowingly staging the same image twice. | T, C | SW + OWN | Code gap; team policy | No | Skip an image you know was already staged | Review repeated patient/eye combinations | No |
| IMG-SAMP-070 | The clinician uses a three-way decision for each candidate: **Use**, **Review first**, or **Skip**. There is no score and no form. | C | OWN + EXT | Owner decision; NHS DESP adequacy concept; EyeQ Good/Usable/Reject | No | A glance-level decision | Maintain the guide | Yes: clinical sign-off of wording |
| IMG-SAMP-071 | **Use**: a colour fundus/retinal photograph that already has a `Refer`/`Not-refer` class, in which the retina (optic disc, macula, vessels) is visible enough for normal reading, and which is the original file in a supported format. | C | EXT + SW | NHS DESP image-adequacy definitions; supported formats in code | Partial: format support and admission checks | Pick images like this | None | Yes: clinical sign-off |
| IMG-SAMP-072 | **Review first**: borderline blur or exposure, uncertain field or laterality, a possible duplicate, or not sure enough retina is visible. Take a second look. If you would still use it clinically, stage it without inventing metadata. Otherwise skip it or ask the coordinator. | C | OWN | Owner decision | Partial: admission may flag `Needs review` / `Image quality review` | Second look only | Answer questions; track borderline outcomes | Yes: clinical sign-off |
| IMG-SAMP-073 | **Skip**: wrong modality (for example OCT or an external-eye photo), corrupt or unreadable files, screenshots or edited/annotated derivatives, non-retinal images, and objects the Workbench cannot admit (for example multi-frame or non-ophthalmic DICOM). | C | SW + OWN | Code: unsupported modality/format handling | Partial: unsupported inputs are rejected or flagged | Do not stage | None | No |
| IMG-SAMP-074 | Image suitability or gradability is a separate concept from source class. A poor-quality or ungradable image is never relabelled `Refer` or `Not-refer` to fit a target. | C, T | OWN + EXT | Owner decision; NHS DESP ungradable outcome; FDA DEN180001 "insufficient quality" output | Yes: admission `quality_state` is independent of grade; `UNGRADABLE` blocks DR-ready | None | Report suitability outcomes separately | No |
| IMG-SAMP-075 | Staged images later found ungradable keep the existing Workbench quality state (`Image quality issue` / `UNGRADABLE`). No new clinical label is created. The team reports how many there are. | T, D | SW + OWN | Code: admission review actions | Yes | Existing admission action only if needed | Count them; decide with the owner whether they count toward N | Yes: counting rule |
| IMG-SAMP-076 | Workbench automatic admission checks (size, aspect ratio, near-uniformity, extreme brightness, colour/field signals) are coarse safety screens, not a gradability assessment. | T, D | SW | Code: `_classify_decoded` | Yes (as a screen only) | None | Do not report them as quality grading | No |
| IMG-SAMP-080 | Optional dimensions (age band, camera/device, site, capture period) are team-only. Collect them from approved metadata when this is feasible; otherwise defer them. They never become per-image clinician entry. | T | EXT + OWN | FDA AI-enabled device draft guidance; STANDING Together | No | None | Record them when available, or state them as not collected | Yes: which dimensions |
| IMG-SAMP-090 | The team keeps two simple monitoring summaries: sex × source class and laterality × source class. Each update also reports Unknown rates, distinct patients, duplicates, and suitability outcomes. | T | OWN | Team requirement | No | None | Update after each staged batch | No |
| IMG-SAMP-091 | Monitoring tables are produced by the team from the Workbench export (`images.csv`) joined to the team source-class record by `image_id` / `image_sha256`. They contain no direct identifiers and are not committed to this repository. | T, D | OWN + OPEN | Team process; export schema | No | None | Run the join; store the output per hospital policy | Yes: storage location |
| IMG-SAMP-092 | Coverage gaps go back to the hospital coordinator only as aggregate requests (for example "more `Not-refer` images this week"), never as per-patient pull lists. | T, H | OWN | Owner decision | No | Occasional aggregate request, at batch level | Send aggregate requests only | No |
| IMG-SAMP-100 | Clinicians are not required to calculate quotas, balance subgroups, count sex or eyes, enter demographics, assign a DR grade or lesions before review, score quality, choose research splits, or complete per-image forms. | C | OWN | Owner decision (acceptance criterion) | No | None | Reject any process change that adds these | No (decided) |
| IMG-SAMP-101 | The clinician-facing guide stays at one page (two at most), has no form, calculator, or data entry, and states that the team monitors coverage. | C, T | OWN | Owner decision | No | Read it once | Keep it minimal; send proposed additions to the owner | Yes: for any added field |
| IMG-SAMP-110 | Guides, presentations, monitoring tables, screenshots, and this repository never contain PHI, raw DICOM identifiers, or hospital storage paths. | All | OWN + SW | Security and privacy rules; export uses pseudonymous keys | Partial: pseudonymous `patient_key` validation; export has no absolute paths | None | Check before sharing | No |

## Evidence

| ID | Repository evidence | External source |
|:-------|:------------------------|:--------------|
| IMG-SAMP-001 | `dr_support/services/admission.py` `scan_input_folder` (configured folder only); `dr_support/services/workspaces.py` | Owner decision (V4) |
| IMG-SAMP-002 | None: happens outside the software | Owner decision (V4) |
| IMG-SAMP-003 | `scan_input_folder`: top-level files only, symlinks and ancillary `.csv/.json/.md/.txt` skipped | Owner decision (V4) |
| IMG-SAMP-004 | `dr_support/imaging/contracts.py` `IntegrityStatus`; `tests/test_integrity.py`; `AGENTS.md` immutability rule | None |
| IMG-SAMP-005 | `docs/reference/DATASET_MANIFEST.md` (`filename` column); `docs/operations/SECURITY_PRIVACY.md` | None |
| IMG-SAMP-010 | No `Refer`/`Not-refer` field in `dr_support/**` or `frontend/src/**` | Owner decision (V4) |
| IMG-SAMP-011 | `dr_support/workflow.py` `Review` (grade 0–4), `grade_review_source`; `docs/reference/DATASET_MANIFEST.md` | NHS DESP grading definitions [E2] (grading and referral are separate schemes) |
| IMG-SAMP-012 | None | Owner decision (V4) |
| IMG-SAMP-013 | `dr_support/services/workspaces.py` (several Workspace profiles are supported) | Datasheets for Datasets [E10] (record the collection process) |
| IMG-SAMP-020 | None | FDA AI-enabled device draft guidance [E7] (characterise the data); owner decision |
| IMG-SAMP-021 | None | [E7]; TRIPOD+AI [E9] |
| IMG-SAMP-022 | `images.csv` `laterality` column | Internal planning |
| IMG-SAMP-030 | No sex field in contracts | [E7] and STANDING Together [E8] (report demographics when available) |
| IMG-SAMP-031 | None | [E7]; [E8] |
| IMG-SAMP-032 | None | Internal |
| IMG-SAMP-033 | `ConfirmImage.laterality` accepts `UNKNOWN` (`dr_support/workflow.py`) | [E8] (state missing data openly) |
| IMG-SAMP-040 | `images.csv` `laterality` | DICOM PS3.3 C.8.17.5 Image Laterality [E5] |
| IMG-SAMP-041 | `dr_support/workflow.py` `confirm_image`; `dr_support/services/dataset.py` `IMAGE_FIELDS` | [E5] |
| IMG-SAMP-042 | `dr_support/services/resolver.py` (filename/OCR candidates); `dr_support/imaging/dicom.py` `_laterality_candidate` (extracted as a metadata candidate; not used by the resolver) | [E5] |
| IMG-SAMP-043 | None | Internal |
| IMG-SAMP-050 | `dr_support/services/dataset.py` `training_group_key`, `grouping_policy` | Tampu et al. 2022 [E11] |
| IMG-SAMP-051 | `manifest.json` `grouping_policy` | GMLP guiding principles [E6]; [E11] |
| IMG-SAMP-052 | None | Internal |
| IMG-SAMP-060 | `dr_support/services/admission.py` `_apply_integrity` (`DUPLICATE_CONTENT`) | None |
| IMG-SAMP-061 | None: no perceptual-hash detection is implemented | None |
| IMG-SAMP-070 | None | NHS DESP image-quality guidance [E1]; EyeQ [E4] |
| IMG-SAMP-071 | `SUPPORTED_INPUT_TYPES` in `dr_support/services/admission.py` | [E1] (macula- and disc-centred field adequacy) |
| IMG-SAMP-072 | `clinician_view` labels in `dr_support/services/admission.py` | [E1]; [E4] ("Usable" category) |
| IMG-SAMP-073 | `DICOM_UNSUPPORTED_MODALITY`, `REJECTED_INVALID` handling | DICOM Ophthalmic Photography IOD [E5] |
| IMG-SAMP-074 | `AdmissionMetadata.quality_state`; dataset `_case_eligibility` (`UNGRADABLE`) | [E1] (ungradable outcome); FDA DEN180001 [E3] |
| IMG-SAMP-075 | `AdmissionReviewAction` `QUALITY_INADEQUATE` (`dr_support/contracts/admission.py`) | [E1] |
| IMG-SAMP-076 | `_classify_decoded` in `dr_support/services/admission.py` | [E4] (automated quality assessment is a separate problem) |
| IMG-SAMP-080 | None | [E7]; [E8] |
| IMG-SAMP-090 | None | [E8]; [E10] |
| IMG-SAMP-091 | `docs/reference/DATASET_MANIFEST.md` (`image_id`, `image_sha256`) | [E10] |
| IMG-SAMP-092 | None | Owner decision (V4) |
| IMG-SAMP-100 | None | Owner decision (V4 acceptance) |
| IMG-SAMP-101 | `docs/clinician/IMAGE_SELECTION_GUIDE.html` | Nielsen Norman Group, *Progressive Disclosure* |
| IMG-SAMP-110 | `docs/operations/SECURITY_PRIVACY.md`; `normalize_patient_key` in `dr_support/services/resolver.py` | None |

## External sources

The sources below were opened and checked in September 2026. Two sources could not be verified in this pass and are not cited as evidence: the full text of the ICO *Guidelines for Diabetic Eye Care* (2017) and the current AAO *Diabetic Retinopathy Preferred Practice Pattern*.

- **[E1]** NHS England. *Diabetic eye screening: guidance on fundus image quality and when adequate images cannot be taken.* GOV.UK, updated 11 March 2026. <https://www.gov.uk/government/publications/diabetic-eye-screening-pathway-for-images-and-where-images-cannot-be-taken/diabetic-eye-screening-guidance-when-adequate-images-cannot-be-taken>
- **[E2]** NHS England. *NHS Diabetic Eye Screening Programme: grading definitions for referable disease.* GOV.UK, updated 4 December 2025. <https://www.gov.uk/government/publications/diabetic-eye-screening-retinal-image-grading-criteria>
- **[E3]** U.S. FDA. *De Novo decision summary DEN180001 (IDx-DR).* 2018. <https://www.accessdata.fda.gov/cdrh_docs/reviews/DEN180001.pdf>
- **[E4]** Fu H. et al. *Evaluation of Retinal Image Quality Assessment Networks in Different Color-Spaces* (EyeQ). MICCAI 2019. <https://arxiv.org/abs/1907.05345>
- **[E5]** NEMA. *DICOM PS3.3*, C.8.17.5 Ocular Region Imaged Module and A.41 Ophthalmic Photography 8 Bit Image IOD. <https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.8.17.5.html>
- **[E6]** U.S. FDA, Health Canada, and MHRA. *Good Machine Learning Practice for Medical Device Development: Guiding Principles.* 2021. <https://www.fda.gov/medical-devices/software-medical-device-samd/good-machine-learning-practice-medical-device-development-guiding-principles>
- **[E7]** U.S. FDA. *Artificial Intelligence-Enabled Device Software Functions: Lifecycle Management and Marketing Submission Recommendations.* Draft guidance, January 2025. <https://www.fda.gov/regulatory-information/search-fda-guidance-documents/artificial-intelligence-enabled-device-software-functions-lifecycle-management-and-marketing>
- **[E8]** Alderman J.E. et al. *Tackling algorithmic bias and promoting transparency in health datasets: the STANDING Together consensus recommendations.* Lancet Digital Health 2025;7(1):e64–e88. <https://www.datadiversity.org/recommendations>
- **[E9]** Collins G.S. et al. *TRIPOD+AI statement.* BMJ 2024;385:e078378. <https://www.bmj.com/content/385/bmj-2023-078378>
- **[E10]** Gebru T. et al. *Datasheets for Datasets.* Communications of the ACM, 2021. <https://arxiv.org/abs/1803.09010>
- **[E11]** Tampu I.E., Eklund A., Haj-Hosseini N. *Inflation of test accuracy due to data leakage in deep learning-based classification of OCT images.* Scientific Data 2022. <https://www.nature.com/articles/s41597-022-01618-6>
