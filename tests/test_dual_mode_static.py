"""Static safety checks for the portable dual-mode deployment definition."""
from pathlib import Path


ROOT = Path(__file__).parents[1]
COMPOSE = (ROOT / "deployment/dual-mode/compose.yml").read_text()


def test_dual_mode_binds_only_loopback_and_requires_gpu():
    assert '127.0.0.1:${' in COMPOSE
    assert 'capabilities: [gpu]' in COMPOSE
    assert 'INFERENCE_DEVICE: cuda:0' in COMPOSE
    assert 'DR_SUPPORT_RELAX_DEVICE: "0"' in COMPOSE
    assert 'portable_postgres_data' in COMPOSE


def test_dual_mode_keeps_assets_external_and_read_only():
    assert ':ro' in COMPOSE
    assert 'hospital' not in COMPOSE.lower() or 'hospital-3090' in COMPOSE
    assert 'REMOTE_MODEL_TOKEN' in COMPOSE
    assert 'weights_only=False' not in COMPOSE
