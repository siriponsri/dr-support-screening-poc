"""Hospital M1 operation identity shared by proposal drafting and the host session.

Pure functions: no model load, network, GPU or credentials. The approved
continuation proposal binds each operation to one source image, model,
modality, reviewed model pins and route parameters. The host child derives the
same facts from a prepared request; the parent admits only an exactly matching,
not yet attempted frozen operation. A mismatch is refused before any charge.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re

# Reviewed batch identities (HANDOFF anchor). Only the two global graders are
# taken from it: PRISM's workspace identity differs from its batch-bound config
# and is supplied separately from BoundLocalPRISM._runtime_identity().
EXPECTED_MODELS_SHA256 = "ac399bfb9d4b5a3a397d18677efe37b30701a35bd1af71657d676aa7ded6ba1a"
PRISM = "prism-dr-5fold"
GLOBAL_MODELS = {"uspec-uwf-grading": "UWF", "retfound-aptos5": "CFP"}
SUPPORTED = {("uspec-uwf-grading", "UWF"), ("retfound-aptos5", "CFP"), (PRISM, "UWF"), (PRISM, "CFP")}
GLOBAL_ROUTE = "/v1/predict/dr"
PRISM_ROUTE = "/v1/prism-bound/execute"  # prism_remote_transport.BASE + "/execute"
PRISM_PROTOCOL = "prism-wire-binding.source-attested.v2"  # prism_remote_transport.PROTOCOL
GLOBAL_PIN_KEYS = {"model_id", "source_revision", "checkpoint_sha256", "preprocessing", "provider_source_sha256"}
PRISM_PIN_KEYS = {"model_id", "source_revision", "preprocessing", "config_sha256", "checkpoint_sha256"}
FACT_KEYS = ("source_sha256", "model_id", "modality", "model_pins_sha256", "parameters_sha256", "preprocessing_id")
OPERATION_KEYS = {"job_id", "operation_id", "purpose", "window_id", *FACT_KEYS}


class OperationError(ValueError):
    """Fixed secret-free refusal codes only."""


def require(condition, code):
    if not condition:
        raise OperationError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _sha(value):
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _checkpoints(value):
    return (type(value) is dict and 0 < len(value) <= 64
            and all(type(name) is str and 0 < len(name) <= 512 and name.isprintable() and _sha(item)
                    for name, item in value.items()))


def reviewed_models(expected_raw, prism_pins):
    """Exact reviewed global pins plus the separately computed PRISM workspace pins."""
    require(digest(expected_raw) == EXPECTED_MODELS_SHA256, "M1_REVIEWED_MODEL_PINS_CHANGED")
    expected = json.loads(expected_raw)
    models = {}
    for model_id in GLOBAL_MODELS:
        entry = expected[model_id]
        pins = entry["pins"]
        require(type(pins) is dict and set(pins) == GLOBAL_PIN_KEYS and pins["model_id"] == model_id
                and _checkpoints(pins["checkpoint_sha256"]) and _sha(pins["provider_source_sha256"])
                and all(type(pins[key]) is str and pins[key] for key in ("source_revision", "preprocessing")),
                "M1_REVIEWED_GLOBAL_PINS_REQUIRED")
        models[model_id] = {"pins": deepcopy(pins), "capability_id": entry["capability_id"]}
    require(type(prism_pins) is dict and set(prism_pins) == PRISM_PIN_KEYS and prism_pins["model_id"] == PRISM
            and _sha(prism_pins["config_sha256"]) and _checkpoints(prism_pins["checkpoint_sha256"])
            and len(prism_pins["checkpoint_sha256"]) == 21
            and prism_pins["source_revision"] == expected[PRISM]["pins"]["source_revision"]
            and prism_pins["checkpoint_sha256"] == expected[PRISM]["pins"]["checkpoint_sha256"]
            and type(prism_pins["preprocessing"]) is str and prism_pins["preprocessing"],
            "M1_PRISM_WORKSPACE_PINS_REQUIRED")
    models[PRISM] = {"pins": deepcopy(prism_pins), "capability_id": expected[PRISM]["capability_id"]}
    return models


def parameters(models, model_id):
    """Route-level parameters only; image-specific masks are covered by the plan."""
    capability = models[model_id]["capability_id"]
    if model_id == PRISM:
        return {"route": PRISM_ROUTE, "binding_protocol": PRISM_PROTOCOL, "capability_id": capability}
    return {"route": GLOBAL_ROUTE, "task": "global", "capability_id": capability}


def facts(models, *, source_sha256, model_id, modality):
    require(_sha(source_sha256) and (model_id, modality) in SUPPORTED and model_id in models,
            "M1_SUPPORTED_SOURCE_MODEL_MODALITY_REQUIRED")
    pins = models[model_id]["pins"]
    return {"source_sha256": source_sha256, "model_id": model_id, "modality": modality,
            "model_pins_sha256": digest(canonical(pins)),
            "parameters_sha256": digest(canonical(parameters(models, model_id))),
            "preprocessing_id": f"{model_id}:{digest(pins['preprocessing'].encode())[:32]}"}


def operation(models, *, operation_id, purpose, window_id, **fact_arguments):
    require(type(operation_id) is str and re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", operation_id) is not None,
            "M1_OPERATION_ID_REQUIRED")
    body = {"operation_id": operation_id, "purpose": purpose, "window_id": window_id,
            **facts(models, **fact_arguments)}
    return {**body, "job_id": digest(canonical(body))}


def global_result_digest(value):
    """Digest of the raw global result fields the review app persists unchanged.

    Computed by the host child from the HTTP response and by the Windows
    readback from PostgreSQL, so the readback is bound to this request's result.
    """
    require(type(value) is dict and type(value.get('provenance')) is dict, 'M1_GLOBAL_RESULT_REQUIRED')
    provenance = value['provenance']
    return digest(canonical({
        **{key: value.get(key) for key in ('model_id', 'model_version', 'modality', 'state', 'grade', 'probabilities')},
        'provenance': {key: provenance.get(key) for key in ('checkpoint_sha256', 'source_revision', 'image_sha256')},
    }))


def match_operation(jobs, observed, *, window_id, states):
    """Lowest-ID unattempted operation whose frozen facts equal the observed request."""
    require(type(observed) is dict and set(observed) == set(FACT_KEYS), "M1_EXACT_REQUEST_FACTS_REQUIRED")
    candidates = sorted((job for job in jobs.values()
                         if job["window_id"] == window_id and states.get(job["job_id"]) is None
                         and all(job[key] == observed[key] for key in FACT_KEYS)),
                        key=lambda job: job["operation_id"])
    return deepcopy(candidates[0]) if candidates else None
