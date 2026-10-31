"""Gold-100: blind grade first, AI shown only after, both kept; only the expert writes; export keeps provenance apart."""
from fastapi.testclient import TestClient

from dr_support.api import create_app
from dr_support.services.pilot_auth import UserStore

PASSWORD = "synthetic-test-pass-7"
BLIND = {"gradable": True, "grade": 2, "confidence": "UNSURE", "laterality": "RIGHT",
         "quadrant_signs": {"superior": ["HAEMORRHAGES"], "temporal": ["VENOUS_BEADING"]}, "selection_reason": "HARD"}


def setup(tmp_path, monkeypatch):
    users = tmp_path / "users.json"
    store = UserStore(users)
    for name, role in (("expert1", "expert"), ("doc1", "physician"), ("research1", "researcher")):
        store.set_user(name, PASSWORD, role=role, must_change=False, enforce_policy=False)
    monkeypatch.setenv("DR_SUPPORT_AUTH_FILE", str(users))
    app = create_app(state_path=str(tmp_path / "state.sqlite3"))
    clients = {}
    for name in ("expert1", "doc1", "research1"):
        client = TestClient(app)
        assert client.post("/v1/auth/login", json={"username": name, "password": PASSWORD}).status_code == 200
        clients[name] = client
    image_id = clients["expert1"].get("/v1/cases").json()[0]["image_id"]
    case = app.state.store.get(image_id)
    case["global"] = {"grade": 3, "model_id": "uspec-uwf-grading"}
    app.state.store.put(case)
    return app, clients, image_id


def revision(client, image_id):
    return client.get(f"/v1/cases/{image_id}/gold-label").json()["revision"]


def test_ai_stays_hidden_until_the_blind_grade_is_saved_and_then_the_blind_grade_is_locked(tmp_path, monkeypatch):
    app, clients, image_id = setup(tmp_path, monkeypatch)
    expert = clients["expert1"]
    early = expert.post(f"/v1/cases/{image_id}/gold-label/reveal-ai", json={"revision": revision(expert, image_id)})
    assert early.status_code == 409
    assert "ai_grade" not in expert.get(f"/v1/cases/{image_id}/gold-label").json()
    saved = expert.put(f"/v1/cases/{image_id}/gold-label/blind",
                       json={"revision": revision(expert, image_id), "label": BLIND, "seconds_spent": 40})
    assert saved.status_code == 200 and saved.json()["gold_label"]["blind"]["grade"] == 2
    shown = expert.post(f"/v1/cases/{image_id}/gold-label/reveal-ai", json={"revision": saved.json()["revision"]})
    assert shown.json()["ai_grade"] == {"grade": 3, "model_id": "uspec-uwf-grading", "provenance": "model_suggestion"}
    relabel = expert.put(f"/v1/cases/{image_id}/gold-label/blind",
                         json={"revision": shown.json()["revision"], "label": {**BLIND, "grade": 3}})
    assert relabel.status_code == 409
    final = expert.put(f"/v1/cases/{image_id}/gold-label/final", json={"revision": shown.json()["revision"], "grade": 3})
    after = final.json()["gold_label"]
    assert after["blind"]["grade"] == 2 and after["after_ai"] == {**after["after_ai"], "grade": 3, "changed": True, "ai_seen": True}
    assert app.state.store.get(image_id).get("clinician_review") is None   # Never touches the clinical review.


def test_only_the_expert_writes_and_the_export_keeps_gold_and_ai_apart(tmp_path, monkeypatch):
    app, clients, image_id = setup(tmp_path, monkeypatch)
    for name in ("doc1", "research1"):
        refused = clients[name].put(f"/v1/cases/{image_id}/gold-label/blind",
                                    json={"revision": revision(clients[name], image_id), "label": BLIND})
        assert refused.status_code == 403
    expert = clients["expert1"]
    expert.put(f"/v1/cases/{image_id}/gold-label/blind", json={"revision": revision(expert, image_id), "label": BLIND})
    assert clients["doc1"].get("/v1/research/gold-labels").status_code == 403
    export = clients["research1"].get("/v1/research/gold-labels").json()
    assert export["count"] == 1 and export["items"][0]["provenance"] == "clinician_verified"
    assert "ai_at_reveal" not in export["items"][0]


def test_a_gradable_blind_label_needs_a_grade_and_unknown_fields_are_refused(tmp_path, monkeypatch):
    app, clients, image_id = setup(tmp_path, monkeypatch)
    expert = clients["expert1"]
    assert expert.put(f"/v1/cases/{image_id}/gold-label/blind", json={
        "revision": revision(expert, image_id), "label": {**BLIND, "grade": None}}).status_code == 422
    assert expert.put(f"/v1/cases/{image_id}/gold-label/blind", json={
        "revision": revision(expert, image_id), "label": {**BLIND, "ai_grade": 3}}).status_code == 422
