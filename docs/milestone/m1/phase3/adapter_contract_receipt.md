# Phase 3 Adapter Contract Receipt

Status: `CONTRACT_VERIFIED / RUNTIME_NOT_RUN` for the repository adapters.

| Adapter | Identity | Input / preprocessing | Output / explanation | Qualification state |
| --- | --- | --- | --- | --- |
| USPEC candidate | `uspec-uwf-grading`, `grading_state.pt-candidate` | Phase 2 selected UWF analysis representation; exact research adapter and observed checkpoint are unavailable in this execution | Grade 0-4 candidate; attention would be model evidence only and must carry `MODEL_ATTENTION_NOT_LESION_LOCALIZATION` | `BLOCKED_ARTIFACT` |
| RETFound | `retfound-aptos5`, revision `ae9a9ecf...` | CFP RGB resize/center-crop/ImageNet normalization; legacy provider path | Five-class raw model scores; no explanation payload | `CFP_DOMAIN / RESEARCH_ONLY` |
| PRISM | `prism-dr-5fold`, revision `79637440...` | CFP ROI cropper, green median/CLAHE, class-specific tiles/fusion; repository adapter kept separate from research-package adapter | Original-pixel lesion proposals; empty output is not negative; no attention/localization conflation | `CFP_DOMAIN / COMPARATOR_ONLY` |

No extra UWF mask, ROI cropper, research-package fusion, or model transform was
silently combined with another adapter. Any future representation or
preprocessing change requires a new adapter/version receipt and measured
comparison under the same fixture identity.
