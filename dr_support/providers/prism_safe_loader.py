"""Restricted checkpoint loading for the locked PRISM-DR YOLO artifacts.

The PRISM release checkpoints contain serialized Ultralytics ``DetectionModel``
objects. This module permits only the concrete Torch/Ultralytics classes found
in the statically inspected, repository-locked files, and always uses
``weights_only=True``. It never invokes ``YOLO(path)`` or another path-based
checkpoint loader.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any


class SafeCheckpointError(RuntimeError):
    """A checkpoint could not be represented by the reviewed safe allowlist."""


# Exact classes found by static ``get_unsafe_globals_in_checkpoint`` inspection
# of all 21 locked PRISM files. Mapping paths are intentionally literal; no
# module name supplied by a checkpoint is imported dynamically.
_SAFE_GLOBAL_PATHS = (
    "torch.nn.modules.activation.SiLU",
    "torch.nn.modules.batchnorm.BatchNorm2d",
    "torch.nn.modules.container.ModuleList",
    "torch.nn.modules.container.Sequential",
    "torch.nn.modules.conv.Conv2d",
    "torch.nn.modules.linear.Identity",
    "torch.nn.modules.pooling.MaxPool2d",
    "torch.nn.modules.upsampling.Upsample",
    "ultralytics.nn.modules.block.A2C2f",
    "ultralytics.nn.modules.block.AAttn",
    "ultralytics.nn.modules.block.ABlock",
    "ultralytics.nn.modules.block.Attention",
    "ultralytics.nn.modules.block.Bottleneck",
    "ultralytics.nn.modules.block.C2PSA",
    "ultralytics.nn.modules.block.C2f",
    "ultralytics.nn.modules.block.C3",
    "ultralytics.nn.modules.block.C3k",
    "ultralytics.nn.modules.block.C3k2",
    "ultralytics.nn.modules.block.DFL",
    "ultralytics.nn.modules.block.PSABlock",
    "ultralytics.nn.modules.block.SPPF",
    "ultralytics.nn.modules.conv.Concat",
    "ultralytics.nn.modules.conv.Conv",
    "ultralytics.nn.modules.conv.DWConv",
    "ultralytics.nn.modules.head.Detect",
    "ultralytics.nn.tasks.DetectionModel",
)


def _safe_global_registry() -> dict[str, type[Any]]:
    registry: dict[str, type[Any]] = {}
    for qualified_name in _SAFE_GLOBAL_PATHS:
        module_name, attribute = qualified_name.rsplit(".", 1)
        module = importlib.import_module(module_name)
        value = getattr(module, attribute)
        actual_name = f"{value.__module__}.{value.__qualname__}"
        if actual_name != qualified_name or not isinstance(value, type):
            raise SafeCheckpointError(f"Reviewed safe-global identity changed: {qualified_name}")
        registry[qualified_name] = value
    return registry


def inspect_checkpoint_globals(checkpoint_path: str | Path) -> tuple[str, ...]:
    """Statically list non-default globals without unpickling checkpoint data."""
    import torch

    inspector = getattr(torch.serialization, "get_unsafe_globals_in_checkpoint", None)
    if inspector is None:
        raise SafeCheckpointError("This PyTorch build has no static checkpoint-global inspector")
    return tuple(sorted(inspector(str(checkpoint_path))))


def safe_load_detection_model(checkpoint_path: str | Path):
    """Load one verified PRISM checkpoint as an Ultralytics DetectionModel.

    The caller must verify its locked SHA-256 before this function. Static
    globals outside the reviewed allowlist fail closed. The returned module is
    already loaded in memory and must be supplied to predictors/adapters;
    callers must never reopen ``checkpoint_path`` through Ultralytics or SAHI.
    """
    import torch
    from torch import nn
    from ultralytics.nn.tasks import DetectionModel

    path = Path(checkpoint_path)
    if not path.is_file() or path.is_symlink():
        raise SafeCheckpointError("Checkpoint must be a regular, non-symlink file")

    inventory = inspect_checkpoint_globals(path)
    registry = _safe_global_registry()
    unsupported = sorted(set(inventory) - registry.keys())
    if unsupported:
        raise SafeCheckpointError(
            "Checkpoint contains globals outside the explicit PRISM safe allowlist: "
            + ", ".join(unsupported)
        )

    allowlist = [registry[name] for name in inventory]
    try:
        with torch.serialization.safe_globals(allowlist):
            checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    except Exception as exc:
        # Do not retry or fall back to unrestricted pickle loading.
        raise SafeCheckpointError(
            f"Restricted weights_only=True load failed ({type(exc).__name__})"
        ) from None

    if not isinstance(checkpoint, dict):
        raise SafeCheckpointError("Safe-loaded PRISM checkpoint is not a mapping")
    model = checkpoint.get("ema") or checkpoint.get("model")
    if not isinstance(model, nn.Module) or not isinstance(model, DetectionModel):
        raise SafeCheckpointError("Safe-loaded PRISM checkpoint has no expected DetectionModel")
    names = getattr(model, "names", None)
    if not isinstance(names, dict) or len(names) != 1 or not all(
        isinstance(key, (int, str)) and isinstance(value, str) and value.strip()
        for key, value in names.items()
    ):
        raise SafeCheckpointError("Safe-loaded PRISM DetectionModel class metadata is invalid")
    if not isinstance(model.state_dict(), dict) or not model.state_dict():
        raise SafeCheckpointError("Safe-loaded PRISM DetectionModel has no state tensors")

    # Ultralytics 8.4.8's load_checkpoint normalization calls .float() on the
    # selected module before inference. Mirror that normalization exactly.
    model.float()
    model.eval()
    return model, {
        "static_unsafe_globals": inventory,
        "explicit_allowlist": inventory,
        "checkpoint_keys": tuple(sorted(checkpoint)),
        "model_type": f"{type(model).__module__}.{type(model).__qualname__}",
        "class_names": dict(names),
        "state_dict_tensor_count": len(model.state_dict()),
        "weights_only": True,
    }
