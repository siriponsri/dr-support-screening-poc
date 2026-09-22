# Troubleshooting — Draft for S8 Rewrite

Keep only issues reproducible on the final release.

Suggested sections:
- review app cannot reach Model API;
- `/health` not ready;
- model asset missing/hash mismatch;
- GPU/CUDA unavailable;
- DICOM codec required;
- unsupported DICOM modality;
- Worklist scan/admission errors;
- CVAT optional integration unavailable;
- frontend build/start failure;
- Windows file-lock/worktree remnants should not appear in production docs unless still relevant.

Each entry should include: symptom, likely cause, safe check, fix, and when to escalate.
