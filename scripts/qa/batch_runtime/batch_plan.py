"""Pure grouping from the existing finite QA planner; no process or model calls."""
from copy import deepcopy
from batch_ledger import canonical, digest, require

MODEL_ORDER = ("retfound-aptos5", "uspec-uwf-grading", "prism-dr-5fold")

def planned_leases(jobs, *, completed=()):
    """Only not-sent pinned jobs, at most8 per one-role worker, browser included."""
    require(
        len({job["job_id"] for job in jobs}) == len(jobs) <= 480,
        "UNIQUE_BOUNDED_MANIFEST_REQUIRED",
    )
    done = set(completed)
    groups = []
    for model in MODEL_ORDER:
        pending = [
            deepcopy(job)
            for job in jobs
            if job["model_id"] == model and job["job_id"] not in done
        ]
        # Preserve manifest ordering inside the role; no resampling/discovery.
        # A real four-job lease reached270s after three returned predictions.
        # Reduce grouping below the approved maximum4; retain native parameters,
        # all deadlines, original job order/count, and zero inference retries.
        per_lease = 2 if model == "prism-dr-5fold" else 8
        for start in range(0, len(pending), per_lease):
            rows = pending[start : start + per_lease]
            lease_id = (
                "batch_"
                + model.replace("-", "_")
                + "_"
                + digest(canonical([row["job_id"] for row in rows]))[:20]
            )
            groups.append({"lease_id": lease_id, "model_id": model, "jobs": rows})
    require(
        sum(len(group["jobs"]) for group in groups)
        == len([job for job in jobs if job["job_id"] not in done]),
        "UNKNOWN_MODEL_ROUTE",
    )
    return groups
