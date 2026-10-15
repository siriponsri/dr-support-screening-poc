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


def test_dual_mode_healthchecks_have_no_invalid_yaml_escapes():
    assert "\\'" not in COMPOSE
    assert "urlopen('http://127.0.0.1:8880/health'" in COMPOSE
    assert "urlopen('http://127.0.0.1:8000/health'" in COMPOSE


def test_gpu_profiles_supply_source_identity_and_bound_unqualified_targets():
    profiles = ROOT / "deployment" / "dual-mode" / "profiles"
    for name in ("ceo-p40.env.example", "hospital-3090.env.example"):
        text = (profiles / name).read_text()
        assert "DR_SCREENING_SOURCE_COMMIT=REPLACE_IN_PRIVATE_ENV" in text
        assert "NOT_RUN" in text
    p40 = (profiles / "ceo-p40.env.example").read_text()
    assert "pytorch/pytorch:2.11.0-cuda12.6-cudnn9-runtime" in p40
    assert "qualification is NOT_RUN" in p40
