"""Generate a sanitized manifest example through the real export endpoint."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from dr_support.api import create_app


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "docs" / "DATASET_MANIFEST_V2_EXAMPLE.json"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="rrw-manifest-example-") as directory:
        root = Path(directory)
        input_folder = root / "input"
        output_folder = root / "output"
        input_folder.mkdir()
        output_folder.mkdir()
        app = create_app(root / "fallback.sqlite", include_samples=False)
        fallback_store = app.state.store
        client = TestClient(app)
        response = client.post("/v1/workspaces", json={
            "name": "Manifest example",
            "input_folder": str(input_folder),
            "output_folder": str(output_folder),
            "database_path": str(root / "workspace.sqlite"),
        })
        response.raise_for_status()
        app.state.workspace_image_ids.add("SYNTH_001")
        app.state.workspace_admission_ids.add("SYNTH_001")
        client.post("/v1/infer/global", json={"image_id": "SYNTH_001", "model_id": "mock-global"}).raise_for_status()
        client.post("/v1/infer/lesion-roi", json={"image_id": "SYNTH_001", "model_id": "mock-lesion"}).raise_for_status()
        case = client.get("/v1/cases/SYNTH_001").json()
        annotations = client.put("/v1/cases/SYNTH_001/annotations", json={
            "revision": case["revision"],
            "reviewer": "Example reviewer",
            "annotations": [{
                "type": "rectangle",
                "label": "MICROANEURYSM",
                "geometry": {"x": 10, "y": 20, "width": 30, "height": 25},
            }],
        })
        annotations.raise_for_status()
        case = annotations.json()
        graded = client.post("/v1/cases/SYNTH_001/review", json={
            "revision": case["revision"],
            "action": "CORRECT_GRADE",
            "reviewer": "Example reviewer",
            "grade": 3,
        })
        graded.raise_for_status()
        confirmed = client.post("/v1/cases/SYNTH_001/review", json={
            "revision": graded.json()["revision"],
            "action": "CONFIRM_ANNOTATIONS",
            "reviewer": "Example reviewer",
        })
        confirmed.raise_for_status()
        exported = client.post("/v1/dataset/export")
        exported.raise_for_status()
        export_dir = output_folder / exported.json()["directory_name"]
        manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
        manifest["created_at"] = "2026-09-23T00:00:00+00:00"
        manifest["export_id"] = "example-export"
        manifest["workspace_id"] = "ws_example"
        app.state.store.db.close()
        if app.state.store is not fallback_store:
            fallback_store.db.close()
        workspace_manager = getattr(app.state, "workspace_manager", None)
        if workspace_manager is not None:
            workspace_manager.catalog.db.close()
    TARGET.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {TARGET}")


if __name__ == "__main__":
    main()
