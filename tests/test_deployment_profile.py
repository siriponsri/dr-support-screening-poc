"""Offline Hospital M1 configuration boundaries, never inference evidence."""

import httpx
import pytest
from fastapi.testclient import TestClient

from dr_support.app import create_app
from dr_support.providers.remote import RemoteGlobalProvider
from dr_support.services.deployment_profile import (
    DeploymentProfileError,
    resolve_deployment_profile,
    validate_deployment_environment,
    validate_model_endpoint,
)
from dr_support.services.model_gateway import ModelConnection, probe_model_connection


def _settings(profile="QA_LOCAL", endpoint="http://127.0.0.1:17860"):
    return {
        "DR_SUPPORT_DEPLOYMENT_PROFILE": profile,
        "APP_PROFILE": "review",
        "MODEL_RUNTIME": "remote",
        "REMOTE_MODEL_URL": endpoint,
    }


def test_absent_profile_retains_legacy_external_configuration():
    assert resolve_deployment_profile({}) is None
    assert validate_model_endpoint("https://legacy.test/api/", environ={}) == "https://legacy.test/api"
    assert validate_deployment_environment({}).profile is None


@pytest.mark.parametrize("profile", ["full", "QA_CLOUD", "qa_local", "SERVER|LOCAL"])
def test_unknown_profile_fails_closed(profile):
    with pytest.raises(DeploymentProfileError, match="QA_SERVER or QA_LOCAL"):
        resolve_deployment_profile({"DR_SUPPORT_DEPLOYMENT_PROFILE": profile})


@pytest.mark.parametrize("profile", ["QA_LOCAL", "QA_SERVER"])
@pytest.mark.parametrize("field,value", [("APP_PROFILE", "full"), ("MODEL_RUNTIME", "local")])
def test_qa_preflight_preserves_review_runtime_invariants(profile, field, value):
    settings = _settings(profile)
    settings[field] = value
    with pytest.raises(DeploymentProfileError, match="review.*remote"):
        validate_deployment_environment(settings)


@pytest.mark.parametrize("profile", ["QA_LOCAL", "QA_SERVER"])
def test_qa_requires_operator_configured_endpoint(profile):
    settings = _settings(profile, "")
    with pytest.raises(DeploymentProfileError):
        validate_deployment_environment(settings)
    with pytest.raises(DeploymentProfileError, match="explicit REMOTE_MODEL_URL"):
        validate_model_endpoint("http://127.0.0.1:17860", environ=settings)


@pytest.mark.parametrize("endpoint", [
    "http://127.0.0.1:17860",
    "http://127.2.3.4:17860",
    "http://[::1]:17860",
    "http://localhost:17860",
    "http://model-gateway:8880",
])
def test_local_accepts_only_explicit_loopback_or_existing_compose_gateway(endpoint):
    settings = _settings(endpoint=endpoint)
    result = validate_deployment_environment(settings)
    assert result.profile == "QA_LOCAL"
    assert result.model_endpoint == endpoint


@pytest.mark.parametrize("endpoint", [
    "http://100.77.149.83:7861",
    "https://external.test",
    "http://127.0.0.1.external.test:17860",
    "http://model-gateway.external.test:8880",
    "http://localhost.:17860",
    "http://0.0.0.0:17860",
    "http://[::]:17860",
    "http://2130706433:17860",
    "http://0177.0.0.1:17860",
    "http://127.1:17860",
])
def test_local_rejects_external_wildcard_alias_and_ambiguous_hosts(endpoint):
    with pytest.raises(DeploymentProfileError):
        validate_deployment_environment(_settings(endpoint=endpoint))


@pytest.mark.parametrize("endpoint", [
    "ftp://localhost:17860",
    "//localhost:17860",
    "http:///localhost:17860",
    "http://user:never-print-secret@localhost:17860",
    "http://@localhost:17860",
    "http://localhost:99999",
    "http://localhost:0",
    "http://localhost:",
    "http://[::1",
    "http://local_host:17860",
    "http://localhost%2eexternal.test:17860",
    "http://localhost\\@external.test:17860",
    "http://local\thost:17860",
    "http://localhost:17860?token=never-print-secret",
    "http://localhost:17860#never-print-secret",
])
def test_invalid_endpoint_errors_never_echo_input_or_secrets(endpoint):
    with pytest.raises(DeploymentProfileError) as caught:
        validate_model_endpoint(endpoint, environ={})
    assert "never-print-secret" not in str(caught.value)
    assert endpoint not in str(caught.value)


def test_local_manual_override_rejected_even_to_another_loopback_port(monkeypatch):
    for name, value in _settings().items():
        monkeypatch.setenv(name, value)
    connection = ModelConnection("Local", "http://127.0.0.1:17860/", "private-token")
    assert connection.url == "http://127.0.0.1:17860"
    with pytest.raises(DeploymentProfileError, match="private deployment configuration"):
        ModelConnection("Changed", "http://127.0.0.1:17861", "private-token")
    with pytest.raises(DeploymentProfileError, match="QA_LOCAL requires"):
        ModelConnection("Changed", "https://external.test", "private-token")


def test_server_configuration_does_not_claim_network_approval_or_inference():
    settings = _settings("QA_SERVER", "http://127.0.0.1:17860")
    result = validate_deployment_environment(settings)
    assert result.profile == "QA_SERVER"
    assert result.model_endpoint == settings["REMOTE_MODEL_URL"]
    assert not hasattr(result, "ready")
    assert not hasattr(result, "inference_pass")


@pytest.mark.parametrize("method,path", [
    ("post", "/v1/model-connection/test"),
    ("put", "/v1/model-connection"),
])
@pytest.mark.parametrize("endpoint", ["https://external.test", "http://127.0.0.1:17861"])
def test_local_ui_override_is_blocked_before_probe_and_preserves_connection(
    monkeypatch, method, path, endpoint,
):
    for name, value in _settings().items():
        monkeypatch.setenv(name, value)
    app = create_app()
    previous = app.state.model_connection
    previous_providers = app.state.providers
    calls = []

    def unexpected_probe(request):
        calls.append(request)
        raise AssertionError("A blocked local override must not probe any endpoint")

    app.state.model_gateway_transport = httpx.MockTransport(unexpected_probe)
    response = getattr(TestClient(app), method)(
        path,
        json={"name": "Changed", "url": endpoint, "token": "never-print-secret"},
    )
    assert response.status_code == 422
    assert "never-print-secret" not in response.text
    assert calls == []
    assert app.state.model_connection is previous
    assert app.state.providers is previous_providers


def test_local_probe_does_not_follow_redirect_to_external_host(monkeypatch):
    for name, value in _settings().items():
        monkeypatch.setenv(name, value)
    calls = []

    def redirect(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://external.test/health"})

    connection = ModelConnection("Local", "http://127.0.0.1:17860")
    probe = probe_model_connection(connection.url, transport=httpx.MockTransport(redirect))
    assert probe.connection_verified is False
    assert calls == ["http://127.0.0.1:17860/health"]
    provider = RemoteGlobalProvider(
        base_url=connection.url, transport=httpx.MockTransport(redirect),
    )
    response = provider._send("POST", "/v1/predict/dr", json={})
    assert response.status_code == 302
    assert calls == [
        "http://127.0.0.1:17860/health",
        "http://127.0.0.1:17860/v1/predict/dr",
    ]


@pytest.mark.parametrize("profile,trust_env", [("QA_LOCAL", False), ("QA_SERVER", True), (None, True)])
def test_proxy_environment_is_ignored_only_for_local_metadata_and_inference(
    monkeypatch, profile, trust_env,
):
    # An inherited proxy must not redirect hospital-local images or metadata.
    monkeypatch.setenv("HTTP_PROXY", "http://unapproved-proxy.invalid:9999")
    monkeypatch.setenv("HTTPS_PROXY", "http://unapproved-proxy.invalid:9999")
    monkeypatch.setenv("NO_PROXY", "")
    if profile is None:
        monkeypatch.delenv("DR_SUPPORT_DEPLOYMENT_PROFILE", raising=False)
    else:
        for name, value in _settings(profile).items():
            monkeypatch.setenv(name, value)
    clients = []
    real_client = httpx.Client

    def record_client(**kwargs):
        client = real_client(**kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(httpx, "Client", record_client)
    transport = httpx.MockTransport(lambda request: httpx.Response(503))
    probe = probe_model_connection("http://127.0.0.1:17860", transport=transport)
    assert probe.connection_verified is False
    provider = RemoteGlobalProvider(base_url="http://127.0.0.1:17860", transport=transport)
    with provider._client(1.0) as client:
        assert client.follow_redirects is False
        assert client.get("http://127.0.0.1:17860/health").status_code == 503
    assert len(clients) == 2
    assert all(client.trust_env is trust_env for client in clients)
