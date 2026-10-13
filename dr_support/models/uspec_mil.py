"""Lazy USPEC ViT-L/RetinaMIL construction and restricted checkpoint loading."""

from __future__ import annotations

from functools import partial
from types import SimpleNamespace
from typing import Callable

from .uspec_artifact import EXPECTED, ArtifactContract, verified_artifact, verify_stream


def build_model():
    """Construct the reviewed architecture only when a verified load is requested."""
    import torch
    from torch import nn
    import timm

    class USPECEncoder(nn.Module):
        def __init__(self):
            super().__init__()
            self.model = timm.create_model(
                "vit_large_patch16_224",
                pretrained=False,
                num_classes=0,
                global_pool="token",
                norm_layer=partial(nn.LayerNorm, eps=1e-6),
            )
            self.config = SimpleNamespace(hidden_size=1024)

        def forward(self, pixel_values):
            tokens = self.model.forward_features(pixel_values)
            pooled = tokens[:, 1:, :].mean(1, keepdim=True)
            return SimpleNamespace(last_hidden_state=pooled)

    class RetinaMIL(nn.Module):
        def __init__(self, encoder):
            super().__init__()
            self.encoder = encoder
            dimension = encoder.config.hidden_size
            self.pos = nn.Embedding(49, dimension)
            self.attn = nn.Linear(dimension, 1)
            self.head = nn.Sequential(nn.LayerNorm(dimension), nn.Linear(dimension, 5))

        def aggregate(self, features):
            positions = torch.arange(49, device=features.device)
            features = features + self.pos(positions)[None]
            attention = self.attn(features).softmax(dim=1)
            return self.head((attention * features).sum(dim=1))

    return RetinaMIL(USPECEncoder())


def load_verified_model(
    directory,
    *,
    device="cpu",
    contract: ArtifactContract = EXPECTED,
    factory: Callable | None = None,
):
    """Load one tensor-only state dict; never retry with unrestricted pickle."""
    import torch

    with verified_artifact(directory, contract) as (stream, observed):
        model = factory() if factory is not None else build_model()
        state = torch.load(stream, map_location="cpu", weights_only=True)
        expected_state = model.state_dict()
        if not isinstance(state, dict) or not state or set(state) != set(expected_state):
            raise ValueError("USPEC checkpoint must be a nonempty tensor state dictionary")
        for key, value in state.items():
            expected = expected_state[key]
            if (
                not isinstance(key, str)
                or type(value) is not torch.Tensor
                or value.is_quantized
                or value.layout != torch.strided
                or value.device.type != "cpu"
                or value.dtype != expected.dtype
                or value.shape != expected.shape
                or not value.is_contiguous()
            ):
                raise ValueError("USPEC checkpoint tensor does not match the reviewed dense state dictionary")
        model.load_state_dict(state, strict=True)
        verify_stream(stream, contract)
        model = model.float().eval().to(device)
        for parameter in model.parameters():
            parameter.requires_grad_(False)
    return model, observed
