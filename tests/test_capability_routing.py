import pytest

from dr_support.services.capability_routing import CapabilityRoutingError, route_capability


def _capability(*, model_id="retfound-aptos5", task="global", modalities=None, status="LOADED", release_status="QUALIFIED"):
    return {
        "model_id": model_id,
        "task": task,
        "modalities": modalities if modalities is not None else ["CFP"],
        "status": status,
        "capability_id": "fixture-capability",
        "revision": "fixture-revision",
        "preprocessing": "fixture-preprocessing",
        "release_status": release_status,
    }


def test_cfp_global_capability_is_actionable():
    route = route_capability(
        _capability(), model_id="retfound-aptos5", task="global", modality="CFP"
    )
    assert route.supported_modalities == ("CFP",)


def _qualified_uspec(*, modalities=None):
    return {
        "model_id": "uspec-uwf-grading",
        "task": "global",
        "modalities": modalities or ["UWF"],
        "status": "QUALIFIED_NOT_LOADED",
        "ready": True,
        "capability_id": "dr_grade",
        "revision": "grading_state.pt-sha256:locked",
        "preprocessing": "uspec-source-rgb-v1",
        "release_status": "RESEARCH_ONLY",
        "runtime_qualification": "ENGINEERING_QUALIFIED",
        "rights_status": "UNVERIFIED",
        "clinical_validation_status": "NOT_ESTABLISHED",
        "production_authorization": "NOT_AUTHORIZED",
    }


def _qualified_prism(*, modality="CFP"):
    return {
        "model_id": "prism-dr-5fold",
        "task": "lesion-roi",
        "modalities": ["CFP", "UWF"],
        "status": "LOADED",
        "ready": True,
        "capability_id": "core_lesion_localization",
        "revision": "79637440a535e4f8118e939d3787121f82180125",
        "preprocessing": "prism-legacy-cfp-plus-experimental-uwf-v1",
        "release_status": "RESEARCH_ONLY",
        "trained_domain": "CFP",
        "uwf_use": "EXPERIMENTAL",
        "clinical_validation_status": "NOT_VALIDATED_FOR_UWF",
    }


def test_locked_global_grading_routes_are_modality_bound():
    cfp_route = route_capability(
        _capability(), model_id="retfound-aptos5", task="global", modality="CFP",
    )
    uwf_route = route_capability(
        _qualified_uspec(), model_id="uspec-uwf-grading", task="global", modality="UWF",
    )
    assert cfp_route.model_id == "retfound-aptos5"
    assert uwf_route.model_id == "uspec-uwf-grading"

    with pytest.raises(CapabilityRoutingError, match="UWF images only"):
        route_capability(
            _qualified_uspec(), model_id="uspec-uwf-grading", task="global", modality="CFP",
        )
    with pytest.raises(CapabilityRoutingError, match="CFP images only"):
        route_capability(
            _capability(modalities=["CFP", "UWF"]),
            model_id="retfound-aptos5", task="global", modality="UWF",
        )
    with pytest.raises(CapabilityRoutingError, match="UWF images only"):
        route_capability(
            _qualified_uspec(modalities=["CFP", "UWF"]),
            model_id="uspec-uwf-grading", task="global", modality="CFP",
        )


def test_known_uspec_identity_cannot_advertise_non_global_task():
    descriptor = _qualified_uspec()
    descriptor['task'] = 'lesion-roi'
    with pytest.raises(CapabilityRoutingError, match="does not provide the requested"):
        route_capability(
            descriptor, model_id="uspec-uwf-grading", task="global", modality="UWF",
        )


@pytest.mark.parametrize("modality", ["CFP", "UWF"])
def test_prism_lesion_assistance_keeps_both_advertised_modalities(modality):
    descriptor = _qualified_prism()
    if modality == "UWF":
        descriptor["trained_domain"] = "CFP"
        descriptor["uwf_use"] = "EXPERIMENTAL"
        descriptor["clinical_validation_status"] = "NOT_VALIDATED_FOR_UWF"
    route = route_capability(
        descriptor, model_id="prism-dr-5fold", task="lesion-roi", modality=modality,
    )
    assert route.model_id == "prism-dr-5fold"
    assert route.modality == modality


def test_prism_uwf_route_requires_experimental_validation_metadata():
    descriptor = _qualified_prism()
    descriptor.update(uwf_use="NOT_SUPPORTED", clinical_validation_status="VALIDATED")
    with pytest.raises(CapabilityRoutingError, match="explicit experimental"):
        route_capability(
            descriptor, model_id="prism-dr-5fold", task="lesion-roi", modality="UWF",
        )


def test_uwf_global_capability_requires_uwf_advertisement():
    route = route_capability(
        _capability(model_id="uspec-like", modalities=["UWF"]),
        model_id="uspec-like",
        task="global",
        modality="UWF",
    )
    assert route.modality == "UWF"


@pytest.mark.parametrize(
    ("task", "modality"),
    [("global", "UWF"), ("global", "OTHER"), ("lesion-roi", "UWF")],
)
def test_incompatible_modality_is_rejected(task, modality):
    descriptor = _capability(
        model_id="prism-dr-5fold" if task == "lesion-roi" else "retfound-aptos5",
        task=task,
        modalities=["CFP"],
    )
    with pytest.raises(CapabilityRoutingError, match="image type|CFP images only"):
        route_capability(
            descriptor,
            model_id=descriptor["model_id"],
            task=task,
            modality=modality,
        )


def test_unknown_modality_is_manual_only():
    with pytest.raises(CapabilityRoutingError, match="image type"):
        route_capability(
            _capability(),
            model_id="retfound-aptos5",
            task="global",
            modality="UNKNOWN",
        )


def test_prism_cannot_be_used_as_dr_grader():
    with pytest.raises(CapabilityRoutingError, match="requested review task"):
        route_capability(
            _capability(model_id="prism-dr-5fold", task="lesion-roi"),
            model_id="prism-dr-5fold",
            task="global",
            modality="CFP",
        )


def test_known_cfp_model_identity_cannot_route_to_uwf_even_when_advertised():
    with pytest.raises(CapabilityRoutingError, match="CFP images only"):
        route_capability(
            _capability(modalities=["CFP", "UWF"]),
            model_id="retfound-aptos5",
            task="global",
            modality="UWF",
        )


def test_generic_capability_requires_qualification_metadata_before_routing():
    descriptor = _capability(model_id="uspec-like", modalities=["UWF"])
    descriptor.pop("capability_id")
    descriptor.pop("revision")
    descriptor.pop("preprocessing")
    with pytest.raises(CapabilityRoutingError, match="incomplete"):
        route_capability(
            descriptor,
            model_id="uspec-like",
            task="global",
            modality="UWF",
        )


def test_generic_capability_with_only_unsupported_modality_stays_manual_only():
    with pytest.raises(CapabilityRoutingError, match="incomplete"):
        route_capability(
            _capability(model_id="generic-capability", modalities=["MRI"]),
            model_id="generic-capability",
            task="global",
            modality="CFP",
        )


def test_generic_uwf_capability_requires_known_release_status():
    descriptor = _capability(model_id="generic-capability", modalities=["UWF"])
    descriptor.pop("release_status")
    with pytest.raises(CapabilityRoutingError, match="incomplete"):
        route_capability(
            descriptor,
            model_id="generic-capability",
            task="global",
            modality="UWF",
        )


def test_generic_cfp_capability_requires_known_release_status():
    descriptor = _capability(model_id="generic-capability", modalities=["CFP"])
    descriptor.pop("release_status")
    with pytest.raises(CapabilityRoutingError, match="incomplete"):
        route_capability(
            descriptor,
            model_id="generic-capability",
            task="global",
            modality="CFP",
        )


def test_non_boolean_ready_value_stays_manual_only():
    descriptor = _capability()
    descriptor["ready"] = "false"
    with pytest.raises(CapabilityRoutingError, match="readiness value is invalid"):
        route_capability(
            descriptor,
            model_id="retfound-aptos5",
            task="global",
            modality="CFP",
        )


def test_unready_capability_stays_manual_only():
    with pytest.raises(CapabilityRoutingError, match="No ready model"):
        route_capability(
            _capability(status="BLOCKED_ARTIFACT"),
            model_id="retfound-aptos5",
            task="global",
            modality="CFP",
        )
