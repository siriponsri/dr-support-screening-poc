"""Focused PRE-S3 isolation, queue, and Model Gateway contract coverage."""

import httpx
import pytest
from fastapi.testclient import TestClient

from dr_support.api import create_app as create_review_app
from dr_support.grade import DR_GRADE_LABELS, grade_label
from dr_support.app import create_app


def test_review_profile_starts_without_legacy_demo_fixtures(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_PROFILE", "review")
    monkeypatch.setenv("MODEL_RUNTIME", "remote")
    monkeypatch.delenv("DR_DEMO_FOLDER", raising=False)
    monkeypatch.setenv("DR_SUPPORT_STATE", str(tmp_path / "review.sqlite"))

    app = create_app()

    assert app.state.images == {}
    assert TestClient(app).get("/v1/cases").json() == []


def test_queue_exclusion_is_reversible_and_keeps_case_data(monkeypatch, tmp_path):
    monkeypatch.setenv("DR_SUPPORT_STATE", str(tmp_path / "review.sqlite"))
    app = create_review_app()
    client = TestClient(app)

    original = client.get("/v1/cases/SYNTH_001").json()
    excluded = client.post(
        "/v1/cases/SYNTH_001/queue",
        json={"revision": original["revision"], "action": "EXCLUDE"},
    )

    assert excluded.status_code == 200
    excluded_body = excluded.json()
    assert excluded_body["queue_state"] == "EXCLUDED"
    assert excluded_body["image_id"] == original["image_id"]
    assert excluded_body["image_sha256"] == original["image_sha256"]
    assert excluded_body["queue_history"][-1]["previous_state"] == "INCLUDED"

    restored = client.post(
        "/v1/cases/SYNTH_001/queue",
        json={"revision": excluded_body["revision"], "action": "RESTORE"},
    )

    assert restored.status_code == 200
    restored_body = restored.json()
    assert restored_body["queue_state"] == "INCLUDED"
    assert restored_body["queue_history"][-1]["previous_state"] == "EXCLUDED"
    assert len(restored_body["queue_history"]) == 2


def test_model_connection_never_returns_token_and_failed_save_preserves_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_PROFILE", "review")
    monkeypatch.setenv("MODEL_RUNTIME", "remote")
    monkeypatch.setenv("DR_SUPPORT_STATE", str(tmp_path / "review.sqlite"))
    app = create_app()
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "PASS", "assets_verified": True})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=[
                {"model_id": "retfound-aptos5", "status": "LOADED"},
                {"model_id": "prism-dr-5fold", "status": "LOADED"},
            ])
        return httpx.Response(404)

    app.state.model_gateway_transport = httpx.MockTransport(handler)
    client = TestClient(app)

    tested = client.post(
        "/v1/model-connection/test",
        json={"name": "Hospital GPU", "url": "https://gateway.test", "token": "do-not-return"},
    )
    assert tested.status_code == 200
    assert tested.json()["status"] == "CONNECTED"
    assert tested.json()["token_configured"] is True
    assert "do-not-return" not in tested.text
    assert all(request.headers.get("authorization") == "Bearer do-not-return" for request in calls)

    saved = client.put(
        "/v1/model-connection",
        json={"name": "Hospital GPU", "url": "https://gateway.test", "token": "keep-server-side"},
    )
    assert saved.status_code == 200
    assert app.state.providers["retfound-aptos5"].base_url == "https://gateway.test"
    assert app.state.providers["retfound-aptos5"]._explicit_token == "keep-server-side"
    assert "keep-server-side" not in saved.text

    def unavailable(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    app.state.model_gateway_transport = httpx.MockTransport(unavailable)
    connection_state = client.get('/v1/model-connection')
    assert connection_state.status_code == 200
    assert connection_state.json()['status'] == 'UNAVAILABLE'
    assert connection_state.json()['connection_verified'] is False
    assert connection_state.json()['models'] == []
    failed = client.put(
        "/v1/model-connection",
        json={"name": "Broken", "url": "https://broken.test", "token": "failed-secret"},
    )
    assert failed.status_code == 502
    assert "failed-secret" not in failed.text
    assert app.state.model_connection.url == "https://gateway.test"
    assert app.state.providers["retfound-aptos5"].base_url == "https://gateway.test"


@pytest.mark.parametrize("status_code", [401, 403])
def test_model_connection_probe_handles_unauthorized_without_echoing_token(monkeypatch, tmp_path, status_code):
    monkeypatch.setenv("APP_PROFILE", "review")
    monkeypatch.setenv("MODEL_RUNTIME", "remote")
    monkeypatch.setenv("DR_SUPPORT_STATE", str(tmp_path / "review.sqlite"))
    app = create_app()
    app.state.model_gateway_transport = httpx.MockTransport(
        lambda _request: httpx.Response(status_code)
    )

    response = TestClient(app).post(
        "/v1/model-connection/test",
        json={"name": "Hospital GPU", "url": "https://gateway.test", "token": "unauthorized-secret"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "UNAVAILABLE"
    assert "unauthorized-secret" not in response.text
    assert "Bearer" not in response.text


def test_model_connection_probe_handles_timeout_as_bounded_unavailable_state(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_PROFILE", "review")
    monkeypatch.setenv("MODEL_RUNTIME", "remote")
    monkeypatch.setenv("DR_SUPPORT_STATE", str(tmp_path / "review.sqlite"))
    app = create_app()

    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("test timeout")

    app.state.model_gateway_transport = httpx.MockTransport(timeout)
    response = TestClient(app).post(
        "/v1/model-connection/test",
        json={"name": "Hospital GPU", "url": "https://gateway.test", "token": "timeout-secret"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "UNAVAILABLE"
    assert "timeout-secret" not in response.text


def test_ico_grade_labels_keep_the_numeric_contract_and_canonical_pdr_name():
    assert list(DR_GRADE_LABELS) == [0, 1, 2, 3, 4]
    assert grade_label(4) == "Proliferative DR (PDR)"
    assert grade_label(5) is None
