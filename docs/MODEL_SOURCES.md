# Model and sample sources

## RETFound

Official source: https://github.com/rmaphoh/RETFound
Pinned revision: `ae9a9ecf37857cf47b8aa9f87cd6f710d75db287`.
Benchmark checkpoint listing: https://github.com/rmaphoh/RETFound/blob/ae9a9ecf37857cf47b8aa9f87cd6f710d75db287/BENCHMARK.md
APTOS checkpoint folder: https://drive.google.com/drive/folders/16kL5V-1U7ACc-68PSHjAq6vyXRJvUoq3
Checkpoint file ID: `1Ujzb6Xd1naWC0NngHah-DbHSgqxOiyJX`, `checkpoint-best.pth`.
SHA256: `a96b9dbcb78eff373912fb0a48d316dc35ffb0715bb2a1b9128b096d780edbbf`.

Architecture: MAE ViT-L/16, global pooling, five-class fine-tuned head (5 × 1024).
Class order frozen as APTOS grades `[0,1,2,3,4]`, using the official benchmark task and
ImageFolder label order. Checkpoint alone is not a clinical protocol authority.
Input: RGB, shorter side 256 bicubic, center crop 224, ImageNet mean/std.
Strict state-dict loading rejects pretrained-encoder-only weights. No training.
Pinned upstream returns singleton pooled token features; adapter applies the trained head
and reshapes to five logits before softmax. Evaluation mode only.
CFP only; UWF returns UNSUPPORTED. No calibration fitted and no gradability detector claimed.
License: CC-BY-NC-4.0, non-commercial research POC only.

## PRISM-DR

Official source: https://github.com/zubeyrozeren/PRISM-DR
Pinned revision: `79637440a535e4f8118e939d3787121f82180125`.
Release: https://github.com/zubeyrozeren/PRISM-DR/releases/tag/v1.0
Asset: https://github.com/zubeyrozeren/PRISM-DR/releases/download/v1.0/weights.zip
Archive SHA256: `966a38bade7ed9049d5bc4b91a3adebb8f4c92afba64386abf6ab13a537c3b49`.
All 21 individual hashes: `dr_support/providers/prism_assets.json`.

Pipeline: released ROI cropper → green channel/median5/CLAHE2 → per-lesion five-fold inference.
MA/HE/EX: 1280 tiles with 0.25 overlap, upstream tiled inference, majority vote 3/5.
SE: full crop inference at 1280, weighted box fusion. Upstream validation fold thresholds.
Inter-lesion suppression uses upstream size/priority rules in non-delta ensemble mode.
Coordinates are mapped back to original pixels by adding the crop offset. No resizing is
silently reinterpreted as original-image geometry. Empty detections are not confirmed absence.
A missing ROI crop causes an explicit failure, not a silent alternative preprocessing path.

| Source label | API / CVAT canonical label |
|---|---|
| MA | MICROANEURYSM |
| HE | HEMORRHAGE |
| EX | HARD_EXUDATE |
| SE | SOFT_EXUDATE |

Optional `PRISM_THRESHOLDS` is a JSON object keyed by MA/HE/EX/SE with scores in [0,1].
Overrides are recorded in prediction provenance; defaults come from the pinned upstream config.
The upstream 38-pixel size rule is calibrated to its source scale, not validated on HRF.
This POC makes no transfer-accuracy claim.

Licensing: PRISM authored code MIT; Ultralytics dependency AGPL-3.0. Source release describes
weights for academic use. See upstream THIRD_PARTY_NOTICES.md. No commercial clearance asserted.
Provider source remains available via the pinned upstream references; no closed-source
network service is published by this delivery.

## Ten HRF samples

Authorized by owner in this session: `01_dr` through `10_dr`.
Mirror: https://huggingface.co/datasets/MedOtter/HRF
Viewer revision observed: `e7da6e866850e54054a4c808f2edec206bec4765`.
Mirror card states CC-BY-4.0. Attribution: HRF / High-Resolution Fundus Image Database,
Budai et al.; MedOtter mirror. Original project: https://www5.cs.fau.de/research/data/fundus-images/
Images here are viewer JPEG derivatives, not asserted byte-identical to original archives.
Individual image hashes/dimensions: docs/SAMPLE_MANIFEST.json.

HRF vessel segmentation ground truth does not provide lesion bounding boxes or adjudicated
ordinal DR grades for this workflow. No dataset masks are used. These samples are exclusively
integration smoke examples, not scientific R1/R2/R3 datasets or benchmark results.

Recorded results for `01_dr` are in examples/. They are real model outputs, still AI suggestions.
The static PREVIEW.html uses those recorded outputs and disables inference/review mutations.

## Clinician review display policy

PRISM inference output is retained intact in the local case record. A separate deterministic review
selection derives the overlay and CVAT pre-label set using optional `REVIEW_THRESHOLDS` plus
`REVIEW_MAX_PER_CLASS` and `REVIEW_MAX_TOTAL`. This is a usability/safety cap only; it is not a
scientific threshold claim and does not change recorded provider provenance.

Repository-level notices are in `../THIRD_PARTY_NOTICES.md`.
