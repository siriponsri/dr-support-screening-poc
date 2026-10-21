"""Offline negative cases for review deployment templates; never run Compose."""
import copy
import json
from pathlib import Path

import pytest

from scripts.audit.validate_web_deployment_plan import validate, validate_compose_template

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / "docs/audit" / name).read_text())


def test_review_templates_are_structurally_valid_only():
    assert not validate(load("deployment-review-plan.json"))
    assert not validate_compose_template(load("review.compose.template.json"))


@pytest.mark.parametrize("field,value", [("app_profile", "full"), ("model_runtime", "local"), ("case_store", "sqlite"), ("workers", 2), ("bind", "0.0.0.0"), ("local_weights", True), ("source_mount_read_only", False), ("secrets", "inline")])
def test_rejects_unsafe_review_profile(field, value):
    plan = load("deployment-review-plan.json")
    plan["profiles"][0][field] = value
    assert validate(plan)


def test_original_images_are_required_in_backup_inventory():
    plan = load("deployment-review-plan.json")
    plan["backup_scope"] = ["postgres-consistent-dump"]
    assert validate(plan)


@pytest.mark.parametrize("mutation", ["gpu", "public_port", "writable_source", "mixed_state", "inline_secret", "http_only_health", "mutable_image"])
def test_rejects_unsafe_compose_template(mutation):
    template = copy.deepcopy(load("review.compose.template.json"))
    service = template["services"]["review"]
    if mutation == "gpu":
        service["devices"] = ["/dev/nvidia0"]
    elif mutation == "public_port":
        service["ports"] = ["0.0.0.0:8000:8000"]
    elif mutation == "writable_source":
        service["volumes"][0]["read_only"] = False
    elif mutation == "mixed_state":
        service["volumes"][1]["target"] = "/data/source"
    elif mutation == "inline_secret":
        service["environment"]["DR_SUPPORT_DATABASE_URL"] = "synthetic-inline-secret-placeholder"
    elif mutation == "http_only_health":
        service["healthcheck"]["test"] = ["CMD", "curl", "--fail", "http://localhost/health"]
    else:
        service["image"] = "example:latest"
    assert validate_compose_template(template)
