"""Restricted PRISM checkpoint loading invariants.

These tests use tiny in-memory modules and never execute a real checkpoint
pickle. The separate runtime evidence records the locked-artifact smoke.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _runtime_modules():
    torch = pytest.importorskip("torch")
    tasks = pytest.importorskip("ultralytics.nn.tasks")
    from dr_support.providers import prism_safe_loader

    return torch, tasks, prism_safe_loader


def test_safe_loader_requests_weights_only_and_checks_model_structure(monkeypatch, tmp_path):
    torch, tasks, safe_loader = _runtime_modules()
    checkpoint_path = tmp_path / "locked.pt"
    checkpoint_path.write_bytes(b"test fixture; torch.load is patched")

    class FixtureDetectionModel(torch.nn.Module):
        names = {0: "lesion"}

        def __init__(self):
            super().__init__()
            self.weight = torch.nn.Parameter(torch.ones(1))

    monkeypatch.setattr(tasks, "DetectionModel", FixtureDetectionModel)
    monkeypatch.setattr(safe_loader, "inspect_checkpoint_globals", lambda _path: ("torch.nn.Identity",))
    monkeypatch.setattr(
        safe_loader,
        "_safe_global_registry",
        lambda: {"torch.nn.Identity": torch.nn.Identity},
    )
    calls = []

    def restricted_load(path, *, map_location, weights_only):
        calls.append((Path(path), map_location, weights_only))
        return {"model": FixtureDetectionModel(), "ema": None, "epoch": 0}

    monkeypatch.setattr(torch, "load", restricted_load)

    model, report = safe_loader.safe_load_detection_model(checkpoint_path)

    assert calls == [(checkpoint_path, "cpu", True)]
    assert isinstance(model, FixtureDetectionModel)
    assert report["weights_only"] is True
    assert report["explicit_allowlist"] == ("torch.nn.Identity",)
    assert report["state_dict_tensor_count"] == 1


def test_unsupported_static_global_fails_before_checkpoint_load(monkeypatch, tmp_path):
    torch, _tasks, safe_loader = _runtime_modules()
    checkpoint_path = tmp_path / "locked.pt"
    checkpoint_path.write_bytes(b"test fixture; torch.load is patched")
    monkeypatch.setattr(
        safe_loader,
        "inspect_checkpoint_globals",
        lambda _path: ("untrusted.module.CheckpointHook",),
    )
    monkeypatch.setattr(safe_loader, "_safe_global_registry", lambda: {})
    monkeypatch.setattr(
        torch,
        "load",
        lambda *_args, **_kwargs: pytest.fail("unsupported globals must block load"),
    )

    with pytest.raises(safe_loader.SafeCheckpointError, match="outside the explicit PRISM safe allowlist"):
        safe_loader.safe_load_detection_model(checkpoint_path)
