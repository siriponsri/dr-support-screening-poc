"""Source-bound cached postfilter replay; no segmenter, model or clinical label."""
import base64
from copy import deepcopy
import hashlib
import io
import json
import math
from pathlib import Path

from PIL import Image

from ..contracts import LesionResult
from ..presentation import lesion_detection_id
from .artifact_roi_assist import digest, input_binding

CONFIG = "DR_SUPPORT_ARTIFACT_ROI_REPLAY_MANIFEST"
SCHEMA = "annotation-artifact-cached-replay.v1"


def p4_cache_manifest(profile, results, guarded_pngs, saved_response_bytes):
    """Convert reviewed cached decisions, never recompute SAM/color/margins.

    Bytes are injected by the host, keyed by source hash. No profile path is
    followed and no original image is loaded. All aliases/indices are data.
    """
    if (profile.get("mode") != "OFFLINE_POSTFILTER_NOT_RERUN"
            or profile.get("recommendation_scope") != "EXACT_SOURCE_BOUND_DEMO_REPLAY_ONLY"
            or profile.get("live_enabled") is not False or profile.get("raw_to_confirmed_negative") is not False
            or profile.get("margin_counted_once") is not True or profile.get("containment_fraction") != 1.0
            or results.get("profile") != profile.get("id")):
        raise ValueError("Unsupported cached postfilter policy")
    records = []
    for source in profile["sources"]:
        matches = [row for row in results["records"] if row["source_sha256"] == source["source_sha256"]]
        if len(matches) != 1 or any(row["source_sha256"] == source["source_sha256"] for row in records):
            raise ValueError("Ambiguous cached source")
        saved = matches[0]
        if saved["saved_response_sha256"] != source["result_sha256"]:
            raise ValueError("Cached result identity changed")
        response_bytes = saved_response_bytes[source["source_sha256"]]
        if hashlib.sha256(response_bytes).hexdigest() != source["result_sha256"]:
            raise ValueError("Saved response bytes changed")
        original_result = json.loads(response_bytes)["result"]
        assessment = saved["assessment"]["records"]
        if [row["raw_index"] for row in assessment] != list(range(saved["raw_count"])):
            raise ValueError("Incomplete raw detection lineage")
        indexes = [row["raw_index"] for row in assessment if row["would_hide"]]
        if indexes != source["would_hide_raw_indexes"]:
            raise ValueError("Cached selection changed")
        png = guarded_pngs[source["source_sha256"]]
        with Image.open(io.BytesIO(png)) as mask:
            mask.load()
            if mask.format != "PNG" or mask.mode != "L" or not set(mask.tobytes()) <= {0, 255}:
                raise ValueError("Invalid guarded mask")
            pixels = bytes(value != 0 for value in mask.tobytes())
            if hashlib.sha256(pixels).hexdigest() != source["guarded_core_pixel_sha256"]:
                raise ValueError("Guarded mask identity changed")
            for index in indexes:
                box = assessment[index]["raw_detection"]["rectangle"]
                left, top, right, bottom = math.floor(box[0]), math.floor(box[1]), math.ceil(box[2]), math.ceil(box[3])
                if (not (0 <= left < right <= mask.width and 0 <= top < bottom <= mask.height)
                        or mask.crop((left, top, right, bottom)).getextrema() != (255, 255)):
                    raise ValueError("Cached box does not fit guarded mask")
            size = list(mask.size)
        raw = [deepcopy(row["raw_detection"]) for row in assessment]
        if original_result.get("lesions") != raw:
            raise ValueError("Saved raw detections changed")
        records.append({"source_sha256": source["source_sha256"], "size": size,
                        "raw_result_sha256": digest(original_result),
                        "raw_detections_sha256": digest(raw), "raw_count": len(raw),
                        "saved_response_sha256": source["result_sha256"],
                        "proposed_raw_indexes": indexes, "mask_png_sha256": hashlib.sha256(png).hexdigest(),
                        "mask_png_base64": base64.b64encode(png).decode()})
    return {"schema": SCHEMA, "profile_id": profile["id"], "live_enabled": False,
            "policy": {key: deepcopy(profile[key]) for key in (
                "seed_rule", "margin_normalized_long_side", "margin_counted_once", "containment_fraction")},
            "profile_sha256": digest(profile), "results_sha256": digest(results), "records": records}


class CachedArtifactReplayProvider:
    def __init__(self, manifest):
        self.manifest = deepcopy(manifest)

    @classmethod
    def from_path(cls, path):
        try:
            with Path(path).open("rb") as stream:
                raw = stream.read(8_000_001)
            if len(raw) > 8_000_000:
                raise ValueError("Replay manifest too large")
            return cls(json.loads(raw))
        except (OSError, ValueError):
            return cls({"schema": SCHEMA, "invalid": True})

    def identity(self):
        return {"method_version": "cached-artifact-postfilter-replay.v1",
                "mask_version": "cached-guarded-original-pixels.v1",
                "evidence_kind": "CACHED_OFFLINE_ARTIFACT_REPLAY_NOT_CERTIFIED",
                "config_sha256": digest(self.manifest)}

    def derive_bound(self, case, image, rows):
        unavailable = {"status": "CACHED_REPLAY_UNAVAILABLE_RETAINED_ALL"}
        manifest = self.manifest
        if manifest.get("schema") != SCHEMA or manifest.get("live_enabled") is not False:
            return unavailable
        matches = [row for row in manifest.get("records", []) if row.get("source_sha256") == image.sha256]
        if len(matches) != 1:
            return unavailable
        record = matches[0]
        raw = (case.get("lesion") or {}).get("lesions", [])
        if (record["size"] != list(image.size) or record["raw_detections_sha256"] != digest(raw)
                or record["raw_result_sha256"] != digest(case.get("lesion"))
                or record["raw_count"] != len(raw)):
            return unavailable
        indexes = record["proposed_raw_indexes"]
        if (len(set(indexes)) != len(indexes)
                or any(type(index) is not int or not 0 <= index < len(raw) for index in indexes)):
            return unavailable
        png = base64.b64decode(record["mask_png_base64"], validate=True)
        if hashlib.sha256(png).hexdigest() != record["mask_png_sha256"]:
            return unavailable
        displayed = {row["detection_id"] for row in rows}
        normalized = LesionResult.model_validate(case["lesion"]).lesions
        return {"status": "SHADOW_ONLY", "input_binding": input_binding(case, image),
                "provider_identity": self.identity(), "exclude_mask_png": png,
                "mask_png_sha256": record["mask_png_sha256"],
                "suppressed": [{"detection_id": key, "reason": "EMPIRICAL_ARTIFACT_PROPOSAL"}
                               for key in (lesion_detection_id(normalized[index]) for index in indexes) if key in displayed],
                "proposal_metadata": {"mode": "OFFLINE_POSTFILTER_NOT_RERUN",
                    "live_suppression_allowed": False, "profile_id": manifest["profile_id"],
                    "saved_response_sha256": record["saved_response_sha256"],
                    "raw_detections_sha256": record["raw_detections_sha256"],
                    "raw_result_sha256": record["raw_result_sha256"],
                    "policy": deepcopy(manifest["policy"]),
                    "clinical_validation": "NOT_EVALUATED", "new_image_support": False}}
