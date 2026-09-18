# Runbook

This is a standalone public/synthetic POC. It never needs WSL, Docker, or local CVAT.
No OcuForge installation is required. Do not extract this project over OcuForge.

## Owner on the restricted Windows workstation

Your browser can use CVAT Online. Running this API and the model weights requires a separate
Python-capable developer host, or a future authorized authenticated web deployment.
This delivery does not claim that a hosted service already exists.
Do not change IT restrictions to run it. Give this ZIP to the developer host if Python is unavailable.

## Developer host: quick start

Use Python 3.11/3.12 (3.12 recommended) and Git. Extract the project to a new directory.
On Windows with Python 3.12 available, double-click `START.cmd`.
It creates a project-only virtual environment and installs the lightweight API dependencies.
Open http://127.0.0.1:8000 after startup. Keep the console open.

Equivalent commands on Linux/macOS:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m dr_support.run
```

The release ZIP includes ten public HRF JPEG examples under `local-state/bridge/samples`.
A Git-only clone needs `python -m dr_support.fetch_samples`. Downloaded bytes must match the
tracked `docs/SAMPLE_MANIFEST.json`; changed mirror bytes are rejected at admission.
The generated synthetic fixture always works without model weights or internet.
The source registry admits these samples only. There is no arbitrary image-upload endpoint.

## One-time real model setup

On the developer host, after reading MODEL_SOURCES.md (research/non-commercial use):

```bash
python -m pip install -e ".[models]"
python -m dr_support.setup_models
python -m dr_support.run
```

Windows equivalents use `.venv\Scripts\python.exe` instead of `python`.
Allow roughly 4 GB for weights plus the Python environment; 16 GB system RAM is recommended
for this CPU POC. No GPU provisioning, paid API, or training is performed.
Downloads use official sources. File/revision hashes are checked; no substitute checkpoint
is silently accepted. RETFound's 3.64 GB release contains optimizer state but inference loads only its model state.
The ZIP/bundle does not redistribute model checkpoints. They are reproducibly downloadable.

Default sources/weights are found under `local-state/bridge` by `dr_support.run`.

Clinician display/CVAT pre-label filtering is separate from raw PRISM inference. Optional runtime controls:

```text
REVIEW_THRESHOLDS={"MA":0.70,"HE":0.50}
REVIEW_MAX_PER_CLASS=25
REVIEW_MAX_TOTAL=80
```

`REVIEW_THRESHOLDS` is keyed by MA/HE/EX/SE. Raw `case.lesion.lesions` remains unchanged for provenance; the derived `case.lesion_review` view is the bounded subset shown and pushed to CVAT.
To use a separately prepared cache, set RETFOUND_SOURCE, RETFOUND_WEIGHTS, PRISM_SOURCE,
and PRISM_WEIGHTS to those verified locations. Source paths must be the pinned clean Git checkouts.
The API does not load `.env` files. Runtime environment variables are authoritative.

## Review workflow

1. Review Queue → select a public image or SYNTH_001.
2. Case Review → Run grading. Public images use RETFound; SYNTH_001 uses an explicit fixture.
3. Inspect the image. Enter reviewer name; Accept, Mark Incorrect, Correct Grade, or Escalate.
4. Annotation → Run pre-label. Public images use PRISM-DR, synthetic uses an explicit fixture.
5. Prepare CVAT task → Open in CVAT → correct shapes and save in CVAT → Sync corrections.
6. Inspect the imported coordinates and the saved CVAT image; Confirm imported annotations.

The overlay shows original AI suggestions. Imported corrections are listed separately.
A sync by itself never makes annotations reviewed. Editing the annotation snapshot invalidates
its prior confirmation. Global-grade review and lesion review have separate states.
No lesion ground truth or adjudicated HRF ordinal grades are included.

SQLite persists case history and task mapping. Keep one runtime worker and one instance per
state file. Back up `local-state/bridge/reviews.sqlite` with the server stopped. No reset/migration
command deletes review records. Do not edit the database to force a failed sync to pass.

Reviewer names are self-declared POC audit labels, not authenticated clinical signatures.
The bundled server binds localhost. A remotely hosted service needs HTTPS, authentication,
request-size limits, network access control, and a trusted reverse proxy before exposure.
The HTML UI contains no tokens. Inject CVAT_TOKEN on the server only; see CVAT_ONLINE_SETUP.md.

## Validation

```bash
python -m pip install -e ".[test]"
python -m pytest -q
python -m ruff check dr_support tests
npm ci
npm test

# Optional real-browser preview smoke
python -m pip install -e ".[browser-test]"
# install/point Playwright to a permitted Chromium if your environment requires it
python -m pytest -q tests/test_browser_ui.py
```

Python tests block external network. DOM tests use a disposable local SQLite file and a local
API subprocess. They do not simulate real clinical correctness or substitute for pixel QA.
Live model tests are recorded in RETFOUND_SMOKE.json and PRISM_SMOKE.json.
Live CVAT remains a separate credential-dependent acceptance step.

## Manual annotation sync

If automated sync is unavailable, use CVAT's UI to save and inspect the annotations.
Obtain the CVAT single-image annotations JSON plus the actual project label IDs (never assume IDs).
In Annotation → Export case & suggestion JSON, obtain `image_sha256`.
Prepare this JSON envelope and choose it in Manual sync fallback:

```json
{
  "image_sha256": "EXACT_HASH_FROM_CASE_EXPORT",
  "label_ids": {
    "MICROANEURYSM": 1,
    "HEMORRHAGE": 2,
    "HARD_EXUDATE": 3,
    "SOFT_EXUDATE": 4
  },
  "annotations": {
    "version": 0,
    "tags": [],
    "tracks": [],
    "shapes": [{"id": 1, "frame": 0, "type": "rectangle", "label_id": 1,
                "points": [100, 100, 130, 140], "source": "manual"}]
  }
}
```

The IDs and coordinates above are examples only. Use actual project IDs and image geometry.
The UI supplies the current case revision. The server rejects changed image hashes, unknown
labels, unsupported geometries, out-of-bounds shapes, and stale revisions. Supported imported shape types are rectangle, ellipse, polygon, polyline, and points. **Mask sync is intentionally unsupported in v0.1.2** and is rejected explicitly rather than dropped. This route records
remote identity as unverified; it does not claim that CVAT authentication succeeded.

## Recovery and rollback

The new repository has independent history. Restore the standalone bundle in a new directory:
`git clone dr-support-screening-poc.bundle dr-support-screening-poc` then switch to `feat/bridge-poc`.
To undo a gate, use an ordinary revert on the standalone feature branch after saving runtime state.
Never reset or merge the preserved OcuForge audit branch. OcuForge remains read-only.
