"""The manual screenshot script captures only the exact pinned public samples. Offline, synthetic bytes."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("capture_manual_screenshots",
                                              ROOT / "scripts/docs/capture_manual_screenshots.py")
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


@pytest.fixture
def pinned(tmp_path, monkeypatch):
    samples = tmp_path / "samples"
    samples.mkdir()
    rows = []
    for index in range(1, 11):
        data = f"synthetic public sample {index}".encode()
        (samples / f"{index:02}_dr.jpg").write_bytes(data)
        rows.append({"image_id": f"{index:02}_dr", "filename": f"{index:02}_dr.jpg",
                     "sha256": hashlib.sha256(data).hexdigest(), "source_type": "PUBLIC"})
    manifest = tmp_path / "SAMPLE_SOURCE_MANIFEST.json"
    manifest.write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setattr(capture, "SAMPLE_MANIFEST", manifest)
    return samples


def test_exact_pinned_samples_are_approved_with_their_verified_bytes(pinned):
    approved = capture.approved_samples(pinned)
    assert len(approved) == 10 and approved["03_dr.jpg"] == b"synthetic public sample 3"


def test_an_extra_unapproved_image_stops_before_any_copy(pinned):
    (pinned / "patient.jpg").write_bytes(b"not approved")
    with pytest.raises(SystemExit, match="UNAPPROVED_OR_MISSING_SAMPLE"):
        capture.approved_samples(pinned)


def test_a_missing_sample_stops(pinned):
    (pinned / "07_dr.jpg").unlink()
    with pytest.raises(SystemExit, match="UNAPPROVED_OR_MISSING_SAMPLE"):
        capture.approved_samples(pinned)


def test_changed_bytes_with_the_right_name_stop(pinned):
    (pinned / "05_dr.jpg").write_bytes(b"a different image under an approved name")
    with pytest.raises(SystemExit, match="CHANGED_SAMPLE"):
        capture.approved_samples(pinned)


def test_a_symlinked_sample_stops(pinned, tmp_path):
    outside = tmp_path / "outside.jpg"
    outside.write_bytes((pinned / "02_dr.jpg").read_bytes())
    (pinned / "02_dr.jpg").unlink()
    try:
        (pinned / "02_dr.jpg").symlink_to(outside)
    except OSError:
        pytest.skip("Symlink creation needs a privilege this Windows account does not hold")
    with pytest.raises(SystemExit, match="UNAPPROVED_OR_MISSING_SAMPLE"):
        capture.approved_samples(pinned)


def test_the_app_is_started_with_no_model_runtime_that_could_load_or_call_a_model():
    source = (ROOT / "scripts/docs/capture_manual_screenshots.py").read_text(encoding="utf-8")
    assert 'MODEL_RUNTIME="remote"' in source and "REMOTE_MODEL_URL=" not in source and '"REMOTE_MODEL"' in source
