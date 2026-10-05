import pytest

from dr_support.services.capability_routing import CapabilityRoutingError, route_capability


def _capability(*, model_id="retfound-aptos5", task="global", modalities=None, status="LOADED"):
    return {
        "model_id": model_id,
        "task": task,
        "modalities": modalities if modalities is not None else ["CFP"],
        "status": status,
    }


def test_cfp_global_capability_is_actionable():
    route = route_capability(
        _capability(), model_id="retfound-aptos5", task="global", modality="CFP"
    )
    assert route.supported_modalities == ("CFP",)


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


def test_unready_capability_stays_manual_only():
    with pytest.raises(CapabilityRoutingError, match="No ready model"):
        route_capability(
            _capability(status="BLOCKED_ARTIFACT"),
            model_id="retfound-aptos5",
            task="global",
            modality="CFP",
        )
