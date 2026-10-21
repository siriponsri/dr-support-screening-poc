"""Candidate provenance checks only; no similarity/model/training code."""
import copy
import json
from pathlib import Path

import pytest

from scripts.audit.validate_gold_expansion_plan import validate


def proposal():
    return json.loads((Path(__file__).resolve().parents[1] / "docs/audit/gold-expansion-plan.example.json").read_text())


def test_synthetic_proposal_is_consistent_without_authorizing_execution():
    assert not validate(proposal())


@pytest.mark.parametrize("failure", ["promotion", "pseudo_gold", "eval_candidate", "eval_seed", "duplicate_image", "missing_model", "wrong_image_provenance", "transferred_lesions", "unconfirmed_identity", "nonfinite_score", "missing_seed", "fake_confirmed_review", "seed_image", "evaluation_image", "unknown_origin", "execution"])
def test_blocks_contamination_and_missing_provenance(failure):
    plan = proposal()
    row = plan["candidate_queue"][0]
    if failure == "promotion":
        row["include_in_gold"] = True
    elif failure == "pseudo_gold":
        row["provenance_class"] = "PSEUDO_LABEL"
        row["include_in_gold"] = True
    elif failure == "eval_candidate":
        row["patient_group_key"] = row["queue_group_key"] = plan["independent_evaluation"]["patient_group_keys"][0]
    elif failure == "eval_seed":
        plan["gold_seed"]["patient_group_keys"] = plan["independent_evaluation"]["patient_group_keys"]
    elif failure == "duplicate_image":
        plan["candidate_queue"].append(copy.deepcopy(row))
    elif failure == "missing_model":
        row["selection"].pop("model_version")
    elif failure == "wrong_image_provenance":
        row["selection"]["source_sha256"] = "f" * 64
    elif failure == "transferred_lesions":
        row["lesion_geometry_transfer"] = "COPY_FROM_SIMILAR_SEED"
    elif failure == "unconfirmed_identity":
        row["patient_group_key"] = None
    elif failure == "nonfinite_score":
        row["selection"]["score"] = float("nan")
    elif failure == "missing_seed":
        row["seed_snapshot_id"] = "other"
    elif failure == "fake_confirmed_review":
        row["review"]["status"] = "CLINICIAN_CONFIRMED"
    elif failure == "seed_image":
        row["source_sha256"] = row["selection"]["source_sha256"] = plan["gold_seed"]["source_sha256_inventory"][0]
    elif failure == "evaluation_image":
        row["source_sha256"] = row["selection"]["source_sha256"] = plan["independent_evaluation"]["source_sha256_inventory"][0]
    elif failure == "unknown_origin":
        row["source_origin"] = "UNKNOWN"
    else:
        plan["execution"] = "RUN"
    assert validate(plan)


def test_pseudo_label_remains_non_gold_even_after_review_reference():
    plan = proposal()
    row = plan["candidate_queue"][0]
    row["provenance_class"] = "PSEUDO_LABEL"
    row["review"] = {"status": "CLINICIAN_CONFIRMED", "canonical_case_id": "synthetic-target", "confirmed_revision": 2}
    assert not validate(plan)
    assert row["include_in_gold"] is False
