# Where to change what

Practical recipes for common changes. Each one lists where to start, what must change with it, and what is protected.

Before any change, follow the `AGENTS.md` lifecycle:

- use a bounded branch;
- no implementation directly on `main`;
- run focused tests, then full validation;
- merge, then rebuild `frontend/dist` on `main` if the frontend changed.

Protected areas need an owner-approved spec under `docs/` **before** implementation.

## Workflow and clinical semantics

| I want to change... | Start here | Also update | Protected? |
|:--|:--|:--|:--|
| A clinician-facing label or message | The component under `frontend/src/components/**` or `pages/**`; backend plain-language text in `services/admission.py` `clinician_view` or `services/resolver.py` `resolver_clinician_view` | Frontend tests that assert text; the Clinician User Manual (`docs/manuals/clinician/*.qmd`) and screenshots; the demo deck if the label is shown | Wording rules in `AGENTS.md` (no raw enums) and `DESIGN.md` |
| What counts as a supported input | `services/admission.py` `SUPPORTED_INPUT_TYPES`, `imaging/registry.py`, `imaging/dicom.py` | `tests/test_admission.py`, `test_dicom_ingest.py`; README "Supported input intent"; CUM §1; IMG-SAMP-073 in the sampling register | **Yes** |
| Automatic admission thresholds | `services/admission.py` `_classify_decoded`, `MIN_*` / `MAX_*` constants | `tests/test_admission.py`; IMG-SAMP-076 | **Yes** |
| Resolver filename patterns | `services/resolver.py` `_FILENAME_WITH_EYE`, `_PATIENT_ONLY` | `tests/test_resolver.py`; CUM §2 | **Yes** |
| Grade actions or provenance categories | `workflow.py` `Review`, `review()` | `ClinicianReviewPage.tsx`; `services/dataset.py` (`grade_review_source`); `DATASET_MANIFEST.md`; `test_workflow.py`, `test_dataset.py` | **Yes** |
| Annotation labels or shapes | `workflow.py` `HumanAnnotationDraft`, `clean_geometry`; `contracts/__init__.py` `LABELS` | `RetinalCanvas.tsx`, `lesionPresentation.ts`, `cvat.py` label map, dataset `CANONICAL_LABELS`, `DATASET_MANIFEST.md`, tests | **Yes** |
| AI ROI correction behaviour | `workflow.py` `lesion_review`; `AiRoiPopover.tsx`; `AnnotationEditorPage.tsx` (`confirmRoi`, `removeRoi`); `lesionPresentation.ts` | `frontend/tests/lesionCorrection.test.tsx`, `singleLineFlow.test.tsx`; CUM §5 | **Yes** (provenance) |
| Single-line flow order, Previous/Next or leave-case warnings, re-edit warnings | `lib/caseProgress.ts`, `lib/caseNavigation.ts`, `components/common/CaseNavigation.tsx`, `components/common/ConfirmDialog.tsx`, page components | `frontend/tests/singleLineFlow.test.tsx`; CUM §4, §6, §7 | **Yes** (clinician workflow) |
| Autosave delay or unsaved-changes guard | `pages/AnnotationEditorPage.tsx` | `frontend/tests/annotationEditor.test.tsx`; CUM §6 | No, but it must never confirm |
| Readiness rules | `services/dataset.py` `_task_reason`, `_case_eligibility` | `eligibility_policy_version`; `DATASET_MANIFEST.md`; `test_dataset.py`; CUM §8 | **Yes** |
| Export columns | `services/dataset.py` `IMAGE_FIELDS`, `ANNOTATION_FIELDS`, `export()` | `DATASET_MANIFEST.md`; `docs/reference/DATASET_MANIFEST_V2_EXAMPLE.json` (`scripts/docs/generate_manifest_example.py`); `test_dataset.py`; team monitoring scripts | **Yes** (schema) |

## Models and runtime

| I want to change... | Start here | Also update | Protected? |
|:--|:--|:--|:--|
| Model API URL, token, or timeout | Environment `REMOTE_MODEL_URL` / `REMOTE_MODEL_TOKEN`; `providers/remote.py` `INFERENCE_TIMEOUT_SECONDS` | `docs/operations/CONFIGURATION.md`; `test_remote.py` | Timeout: no. Contract: **yes** |
| A model checkpoint or revision | `providers/retfound.py` / `prism.py` constants, `prism_assets.json`, `setup_models.py` | `THIRD_PARTY_NOTICES.md`; `MODEL_SERVER.md`; operator manual | **Yes** (model identity and provenance) |
| Profile rules or ports | `dr_support/app.py`, `run.py`, `START.cmd`, `scripts/model-server/start.sh` | `test_profiles.py`, `test_startup.py`; `CONFIGURATION.md`; operator manual | **Yes** |
| UI theme or tokens | `frontend/src/theme/**` | `DESIGN.md` first, then the components | DESIGN.md is the source of truth |

## Sampling, guides, and documents

| I want to change... | Start here | Also update | Protected? |
|:--|:--|:--|:--|
| **Team sampling requirements** | `docs/clinician/sampling/REQUIREMENTS_TRACEABILITY.md` (the register) and the related `*.qmd` chapter | Rebuild `docs/pdfs/IMAGE_SAMPLING_REQUIREMENTS.pdf`; `docs/presentation/PRESENTATION_SOURCE_MAP.md` and the technical briefing if a cited ID changes. **This does not change Workbench admission rules.** Clinical or owner approval may be required (see the "Owner approval needed?" column). | Owner-approved items: yes |
| **Clinician image-selection guide** | `docs/clinician/IMAGE_SELECTION_GUIDE.html` (the single source for HTML and PDF) | Rebuild with `build_docs.py image-guide`; keep it to 1 page (2 at most); IMG-SAMP-100 and 101. **It must stay minimal-burden. Do not add per-image fields without explicit approval.** | Yes, for any new clinician action |
| Adding source class or sex *inside* the Workbench | Write a normative spec first (admission contract, case schema, export columns, UI, tests) | `DATASET_MANIFEST.md`; the sampling register (IMG-SAMP-010, 013, 030); an ADR | **Yes**: a contract change |
| Clinician User Manual | `docs/manuals/clinician/*.qmd` | `build_docs.py clinician-manual`; inspect every page | No |
| Deployment and Operations Manual | `docs/manuals/operator/*.qmd` | `build_docs.py operator-manual` | No |
| Developer Technical Guide | `docs/manuals/developer/*.qmd` | `build_docs.py developer`; this file and `FEATURE_IMPLEMENTATION_MAP.md` if paths move | No |
| Product demo scenes | `docs/presentation/hyperframes/index.html` (HyperFrames slideshow manifest and scenes) | `PRESENTATION_SCRIPT_TH.md`, `PRESENTATION_SOURCE_MAP.md`; `build_docs.py demo`; `check_docs.py` | No |
| Technical briefing | `docs/presentation/src/TECHNICAL_BRIEFING.source.html` | `TECHNICAL_PRESENTATION_SCRIPT_TH.md`; `build_docs.py briefing` | No |
| Architecture diagrams | `docs/adr/architecture/*.mmd` | `build_docs.py diagrams`; any guide figure that uses them | No |
| Record an architecture decision | `docs/adr/NNNN-title.md` (MADR format) | `docs/adr/README.md` index | No |
