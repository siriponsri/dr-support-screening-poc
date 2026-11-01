"""Referral list and connectors: only signed grader-chosen referrals; FHIR export; nothing leaves unless configured."""
import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from dr_support.api import create_app
from dr_support.services import referral_outbox
from dr_support.services.pilot_auth import UserStore

PASSWORD = "synthetic-test-pass-7"
FORM = {"patient_name": "Synthetic Patient", "hn": "TEST-001", "right": {"quality": "GRADABLE", "grade": 3},
        "left": {"quality": "GRADABLE", "grade": 1}, "decision": "REFER", "refer_to": "RETINA_SPECIALIST",
        "urgency": "WITHIN_1_MONTH", "remarks": "=HYPERLINK(\"x\")"}


def setup(tmp_path, monkeypatch):
    users = tmp_path / "config" / "users.json"
    users.parent.mkdir()
    store = UserStore(users)
    for name, role in (("doc1", "physician"), ("nurse1", "nurse"), ("admin1", "admin")):
        store.set_user(name, PASSWORD, role=role, must_change=False, enforce_policy=False)
    monkeypatch.setenv("DR_SUPPORT_AUTH_FILE", str(users))
    app = create_app(state_path=str(tmp_path / "state.sqlite3"))
    clients = {}
    for name in ("doc1", "nurse1", "admin1"):
        client = TestClient(app)
        assert client.post("/v1/auth/login", json={"username": name, "password": PASSWORD}).status_code == 200
        clients[name] = client
    image_id = clients["doc1"].get("/v1/cases").json()[0]["image_id"]
    return app, clients, image_id


def sign(client, image_id, form=FORM):
    revision = client.get(f"/v1/cases/{image_id}/screening-report").json()["revision"]
    reply = client.put(f"/v1/cases/{image_id}/screening-report", json={"revision": revision, "report": form, "sign": True})
    assert reply.status_code == 200


def test_only_signed_reports_where_the_grader_chose_refer_become_referrals(tmp_path, monkeypatch):
    app, clients, image_id = setup(tmp_path, monkeypatch)
    doctor = clients["doc1"]
    assert doctor.get("/v1/referrals").json()["items"] == []
    revision = doctor.get(f"/v1/cases/{image_id}/screening-report").json()["revision"]
    doctor.put(f"/v1/cases/{image_id}/screening-report", json={"revision": revision, "report": FORM})  # Draft only.
    assert doctor.get("/v1/referrals").json()["items"] == []
    sign(doctor, image_id)
    items = doctor.get("/v1/referrals").json()["items"]
    assert len(items) == 1 and items[0]["decision_source"] == "GRADER_SELECTED" and items[0]["refer_to"] == "RETINA_SPECIALIST"


def test_fhir_export_is_a_service_request_bundle_with_per_eye_grades(tmp_path, monkeypatch):
    app, clients, image_id = setup(tmp_path, monkeypatch)
    sign(clients["doc1"], image_id)
    bundle = json.loads(clients["doc1"].get(f"/v1/referrals/{image_id}/fhir").text)
    kinds = [entry["resource"]["resourceType"] for entry in bundle["entry"]]
    assert bundle["resourceType"] == "Bundle" and kinds == ["Patient", "Observation", "Observation", "ServiceRequest"]
    service = bundle["entry"][-1]["resource"]
    assert service["priority"] == "asap" and service["code"]["text"] == "Referral to retina specialist"
    assert "chosen by the grader" in service["note"][0]["text"]


def test_csv_export_neutralises_spreadsheet_formulas(tmp_path, monkeypatch):
    app, clients, image_id = setup(tmp_path, monkeypatch)
    sign(clients["doc1"], image_id)
    text = clients["doc1"].get("/v1/referrals.csv").text
    assert "'=HYPERLINK" in text and ",=HYPERLINK" not in text


def test_nothing_is_sent_until_the_admin_configures_a_connector_then_one_recorded_attempt(tmp_path, monkeypatch):
    app, clients, image_id = setup(tmp_path, monkeypatch)
    sign(clients["doc1"], image_id)
    assert clients["doc1"].post(f"/v1/referrals/{image_id}/send").status_code == 409
    drop = tmp_path / "drop"
    monkeypatch.setenv("DR_SUPPORT_REFERRAL_DROP_ROOT", str(tmp_path))
    assert clients["doc1"].put("/v1/admin/referral-connector", json={"kind": "file_drop", "folder": str(drop)}).status_code == 403
    assert clients["admin1"].put("/v1/admin/referral-connector", json={"kind": "file_drop", "folder": str(drop)}).status_code == 200
    assert clients["nurse1"].post(f"/v1/referrals/{image_id}/send").status_code == 403
    attempt = clients["doc1"].post(f"/v1/referrals/{image_id}/send").json()
    assert attempt["status"] == "WRITTEN" and len(list(drop.glob("referral-*.json"))) == 1
    assert len(clients["doc1"].get("/v1/referrals").json()["items"][0]["deliveries"]) == 1


def test_webhook_setting_needs_https_and_a_token_variable_name_not_a_token(tmp_path, monkeypatch):
    monkeypatch.setenv("DR_SUPPORT_REFERRAL_HOSTS", "his.example")
    app, clients, _ = setup(tmp_path, monkeypatch)
    admin = clients["admin1"]
    assert admin.put("/v1/admin/referral-connector", json={"kind": "webhook", "url": "http://his.example/fhir"}).status_code == 422
    assert admin.put("/v1/admin/referral-connector", json={"kind": "webhook", "url": "https://his.example/fhir",
                                                            "token_env": "abc secret value"}).status_code == 422
    ok = admin.put("/v1/admin/referral-connector", json={"kind": "webhook", "url": "https://his.example/fhir", "token_env": "REFERRAL_TOKEN"})
    assert ok.status_code == 200 and ok.json()["token_env"] == "REFERRAL_TOKEN"


def test_a_failed_webhook_is_recorded_and_not_retried():
    referral = {"image_id": "a" * 64, "decision": "REFER", "refer_to": None, "urgency": None, "patient_name": "",
                "hn": "", "right_grade": 2, "left_grade": None, "signed_by": "doc1", "signed_at": "2026-10-31", "remarks": ""}
    calls = []

    def post(url, content, headers):
        calls.append(url)
        raise ConnectionError("down")
    attempt = referral_outbox.deliver({"kind": "webhook", "url": "https://his.example/fhir", "token_env": ""}, referral, post=post)
    assert attempt["status"] == "FAILED" and calls == ["https://his.example/fhir"]



def test_operator_lists_where_referrals_may_go_and_tokens_must_be_referral_tokens(tmp_path, monkeypatch):
    monkeypatch.setenv("DR_SUPPORT_REFERRAL_HOSTS", "his.example")
    monkeypatch.setenv("DR_SUPPORT_REFERRAL_DROP_ROOT", str(tmp_path / "drops"))
    check = referral_outbox.validate_connector
    for refused in ({"kind": "webhook", "url": "https://elsewhere.example/fhir"},
                    {"kind": "webhook", "url": "https://his.example/fhir", "token_env": "REMOTE_MODEL_TOKEN"},
                    {"kind": "file_drop", "folder": str(tmp_path / "other")}):
        with pytest.raises(HTTPException):
            check(refused)
    assert check({"kind": "file_drop", "folder": str(tmp_path / "drops" / "his")})["kind"] == "file_drop"
    monkeypatch.setenv("SECRET_VALUE", "do-not-send")
    seen = {}

    class Reply:
        status_code = 200

    def post(url, content, headers):
        seen.update(headers)
        return Reply()

    referral_outbox.deliver({"kind": "webhook", "url": "https://his.example/fhir", "token_env": "SECRET_VALUE"},
                            {"image_id": "x" * 64, "decision": "REFER", "refer_to": None, "urgency": None,
                             "patient_name": "", "hn": "", "right_grade": 2, "left_grade": None, "signed_by": "doc1",
                             "signed_at": "2026-10-31", "remarks": ""}, post=post)
    assert "Authorization" not in seen
