# Third-Party Notices

This file records the principal third-party materials used or referenced by the product.
It is not legal advice and does not replace the upstream license texts.

## RETFound

- Upstream: https://github.com/rmaphoh/RETFound
- Pinned source revision: `ae9a9ecf37857cf47b8aa9f87cd6f710d75db287`
- Repository license: Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0).
- Product use: research/non-commercial only; no commercial clearance is asserted.
- The product does not redistribute the checkpoint. Setup retrieves the approved upstream checkpoint and verifies its SHA-256.

## PRISM-DR

- Upstream: https://github.com/zubeyrozeren/PRISM-DR
- Pinned source revision: `79637440a535e4f8118e939d3787121f82180125`
- Repository code license: MIT.
- The v1.0 release states that the trained weights were produced with Ultralytics YOLO and describes them for academic use.
- The PRISM-DR runtime depends on Ultralytics components licensed under AGPL-3.0 in the referenced upstream ecosystem. No commercial deployment clearance is asserted by this product.
- The product does not redistribute the PRISM weights in Git history; setup verifies the released assets by SHA-256.

## HRF / MedOtter mirror

- Mirror: https://huggingface.co/datasets/MedOtter/HRF
- Dataset card observed by the project states CC BY 4.0.
- Attribution in this delivery: HRF / High-Resolution Fundus Image Database, Budai et al.; MedOtter mirror.
- Included viewer JPEG derivatives are public smoke examples only. They are not treated as lesion ground truth or ordinal DR ground truth.

## Runtime libraries

Python and JavaScript dependencies retain their own upstream licenses. Important examples include FastAPI, Uvicorn, HTTPX, Pydantic, Pillow, PyTorch, torchvision, timm, SAHI, ensemble-boxes, and jsdom. Dependency installation does not change their upstream terms.

## Product boundary

No third-party license listed here should be interpreted as authorization for clinical deployment, commercial resale, patient-data processing, or regulated medical-device use. Those decisions require separate legal, governance, security, and clinical review.
