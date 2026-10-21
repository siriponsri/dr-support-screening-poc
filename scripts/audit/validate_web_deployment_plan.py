"""Validate review-only templates offline; never read env, connect or deploy."""
import argparse
import ast
import json
from pathlib import Path


def validate(plan):
    if not isinstance(plan, dict):
        return ["Plan must be an object"]
    errors = []
    if plan.get("schema_version") != "web-deployment-review-plan.v1":
        errors.append("Unknown plan schema")
    if plan.get("execution") != "NOT_RUN":
        errors.append("A plan cannot claim executed deployment")
    profiles = plan.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        return errors + ["At least one review profile is required"]
    for profile in profiles:
        if not isinstance(profile, dict):
            errors.append("Profile must be an object")
            continue
        expected_fields = {
            "app_profile": "review", "model_runtime": "remote",
            "case_store": "postgres", "workers": 1, "bind": "127.0.0.1",
            "local_weights": False, "source_mount_read_only": True,
            "secrets": "operator-managed",
        }
        for field, expected in expected_fields.items():
            if type(profile.get(field)) is not type(expected) or profile[field] != expected:
                errors.append(f"{profile.get('name', 'unnamed')}: invalid {field}")
        port = profile.get("port")
        if type(port) is not int or not 1024 <= port <= 65535:
            errors.append("Invalid review port")
    required = {
        "exact-source-commit", "frontend-source-digest", "frontend-output-set-sha256",
        "locked-dependency-receipt", "backup-restore-rehearsal", "operator-approval",
        "synthetic-manual-review-smoke",
    }
    if not required.issubset(set(plan.get("required_release_evidence", []))):
        errors.append("Missing release evidence gate")
    if plan.get("separate_model_service", {}).get("weights_mount") != "read-only":
        errors.append("Model weights must be read-only")
    if plan.get("image_reference_policy") != "sha256-digest-required":
        errors.append("Immutable image identity is required")
    if "immutable-original-images-with-sha256-inventory" not in plan.get("backup_scope", []):
        errors.append("Database backup alone does not preserve original images")
    return errors


def validate_compose_template(template):
    """Static policy check, not Docker Compose/runtime/ingress qualification."""
    if not isinstance(template, dict):
        return ["Compose template must be an object"]
    errors = []
    if template.get("x-audit-status") != "TEMPLATE_ONLY_NOT_RUN":
        errors.append("Template must not claim execution")
    services = template.get("services", {})
    if set(services) != {"review"}:
        return errors + ["Review template must not create model or database services"]
    review = services["review"]
    env = review.get("environment", {})
    for key, expected in {"APP_PROFILE": "review", "MODEL_RUNTIME": "remote", "DR_SUPPORT_CASE_STORE": "postgres", "WORKERS": "1"}.items():
        if env.get(key) != expected:
            errors.append(f"Invalid review environment {key}")
    if not str(review.get("image", "")).startswith("${DR_REVIEW_IMAGE:?"):
        errors.append("Approved immutable image must be provided by the operator")
    if not str(env.get("DR_SUPPORT_DATABASE_URL", "")).startswith("${DR_SUPPORT_DATABASE_URL:?"):
        errors.append("Database credentials must remain operator supplied")
    if review.get("read_only") is not True:
        errors.append("Review root filesystem must be read-only")
    if review.get("devices") or review.get("privileged") or review.get("network_mode"):
        errors.append("No GPU, privileged or host-network service in review template")
    if not review.get("ports") or any(not value.startswith("127.0.0.1:") for value in review["ports"]):
        errors.append("Review ports must bind to loopback")
    mounts = review.get("volumes", [])
    source = [mount for mount in mounts if mount.get("target") == "/data/source"]
    if len(source) != 1 or source[0].get("read_only") is not True:
        errors.append("Original images must have one read-only source mount")
    targets = [mount.get("target") for mount in mounts]
    if len(targets) != len(set(targets)) or "/app/local-state" not in targets or "/data/output" not in targets:
        errors.append("Source, writable state and output mounts must be distinct")
    if any("weight" in str(mount).lower() for mount in mounts):
        errors.append("Model weights do not belong on the Review service")
    health = review.get("healthcheck", {}).get("test", [])
    if len(health) != 4 or health[:3] != ["CMD", "python", "-c"]:
        errors.append("Recognized health payload check is required")
    else:
        try:
            ast.parse(health[3])
        except SyntaxError:
            errors.append("Invalid healthcheck Python syntax")
        if "PASS_WITH_WARNINGS" not in health[3] or "json.load" not in health[3]:
            errors.append("HTTP status alone is not semantic liveness")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--compose-template", type=Path)
    args = parser.parse_args()
    try:
        errors = validate(json.loads(args.plan.read_text(encoding="utf-8")))
        if args.compose_template:
            errors.extend(validate_compose_template(json.loads(args.compose_template.read_text(encoding="utf-8"))))
    except (OSError, ValueError, TypeError, AttributeError) as error:
        print(f"INVALID PLAN: {type(error).__name__}")
        return 1
    for error in errors:
        print(error)
    print("INVALID PLAN" if errors else "PLAN STRUCTURE VALID; DEPLOYMENT NOT RUN; RELEASE EVIDENCE STILL REQUIRED")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
