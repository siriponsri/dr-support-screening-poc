"""Offline consistency validation for a proposed candidate queue, not clinical authorization."""
import argparse
import json
import math
import re
from pathlib import Path

SHA = re.compile(r"^[a-f0-9]{64}$")


def validate(plan):
    if not isinstance(plan, dict) or plan.get("schema_version") != "gold-expansion-review-plan.v0-proposal":
        return ["Unknown proposal schema"]
    errors = []
    if plan.get("execution") != "NOT_RUN":
        errors.append("This proposal cannot authorize selection inference")
    seed = plan.get("gold_seed", {})
    evaluation = plan.get("independent_evaluation", {})
    if seed.get("provenance_class") != "PHYSICIAN_CONFIRMED_GOLD" or seed.get("snapshot_schema") != "s4.dataset-snapshot.v4":
        errors.append("Seed must reference the existing physician-confirmed canonical snapshot architecture")
    if not seed.get("snapshot_id") or not SHA.fullmatch(str(seed.get("source_state_digest", ""))):
        errors.append("Seed snapshot and source-state identity required")
    held_out = set(evaluation.get("patient_group_keys", []))
    if not evaluation.get("snapshot_id") or evaluation.get("snapshot_id") == seed.get("snapshot_id") or not held_out or evaluation.get("excluded_from_selection") is not True:
        errors.append("Separate independent evaluation snapshot/groups must be excluded from selection")
    if held_out.intersection(seed.get("patient_group_keys", [])):
        errors.append("Gold selection seed overlaps independent evaluation patients")
    seed_images = set(seed.get("source_sha256_inventory", []))
    evaluation_images = set(evaluation.get("source_sha256_inventory", []))
    if not seed_images or not evaluation_images or seed_images.intersection(evaluation_images):
        errors.append("Disjoint seed/evaluation source-image inventories are required")
    hashes = set()
    for row in plan.get("candidate_queue", []):
        if row.get("provenance_class") not in {"RETRIEVED_CANDIDATE", "PSEUDO_LABEL"} or row.get("include_in_gold") is not False:
            errors.append("Candidate/pseudo-label rows must never become gold through selection")
        digest = row.get("source_sha256")
        if not SHA.fullmatch(str(digest)) or digest in hashes or digest in seed_images or digest in evaluation_images:
            errors.append("Invalid or duplicate candidate image SHA256")
        hashes.add(digest)
        if row.get("source_origin") not in {"PUBLIC", "SYNTHETIC", "HOSPITAL_AUTHORIZED"}:
            errors.append("Candidate source lineage must be known; admission/export permission is separate")
        group = row.get("patient_group_key")
        if not group or group != row.get("queue_group_key") or group in held_out:
            errors.append("Candidate requires confirmed patient grouping outside independent evaluation")
        if row.get("seed_snapshot_id") != seed.get("snapshot_id"):
            errors.append("Candidate must retain its exact seed snapshot reference")
        selection = row.get("selection", {})
        score = selection.get("score")
        if type(score) not in {int, float} or not math.isfinite(score):
            errors.append("Selection score must be finite and retain its meaning")
        if not all(selection.get(key) for key in ["run_id", "model_id", "model_version", "score_kind"]) or not SHA.fullmatch(str(selection.get("checkpoint_sha256", ""))):
            errors.append("Selection model/version/checkpoint/run/score provenance required")
        if selection.get("source_sha256") != digest:
            errors.append("Selection provenance must bind to this exact candidate image")
        if row.get("lesion_geometry_transfer") != "PROHIBITED":
            errors.append("Lesion localization cannot be copied from a similar seed image")
        review = row.get("review", {})
        if review.get("status") not in {"PENDING", "ACCEPTED_FOR_REVIEW", "REJECTED", "CORRECTED", "CLINICIAN_CONFIRMED"}:
            errors.append("Unknown review queue status")
        if review.get("status") == "CLINICIAN_CONFIRMED" and (not review.get("canonical_case_id") or type(review.get("confirmed_revision")) is not int or review["confirmed_revision"] < 1):
            errors.append("Confirmed review requires an existing canonical case/revision reference")
    policy = plan.get("review_queue_policy", {})
    if policy.get("similarity_promotes_to_gold") is not False or policy.get("reuse_existing_worklist_and_snapshot") is not True:
        errors.append("Use existing human review/snapshot boundaries; no automatic gold promotion")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    args = parser.parse_args()
    try:
        errors = validate(json.loads(args.plan.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, AttributeError):
        errors = ["Invalid proposal structure"]
    for error in errors:
        print(error)
    print("INVALID PROPOSAL" if errors else "PROPOSAL CONSISTENT; SELECTION/TRAINING/CLINICAL ACCEPTANCE NOT RUN")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
