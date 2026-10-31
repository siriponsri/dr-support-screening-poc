"""Screening report: the grader chooses Refer / Not refer; a nurse prepares, a physician signs; print page is escaped."""
from fastapi.testclient import TestClient

from dr_support.api import create_app
from dr_support.services import pilot_auth
from dr_support.services.pilot_auth import UserStore

PASSWORD = "synthetic-test-pass-7"
FORM = {"patient_name": "Synthetic Patient <script>", "hn": "TEST-001", "camera": "UWF",
        "right": {"quality": "GRADABLE", "grade": 2, "dme": "NO", "signs": ["Microaneurysms", "Haemorrhages"]},
        "left": {"quality": "GRADABLE", "grade": 1}, "decision": "REFER", "refer_to": "OPHTHALMOLOGIST",
        "urgency": "WITHIN_3_MONTHS"}


def client(tmp_path, monkeypatch, *, signed_in_as=None):
    if signed_in_as:
        users = tmp_path / "users.json"
        store = UserStore(users)
        store.set_user("nurse1", PASSWORD, role="nurse", must_change=False, enforce_policy=False)
        store.set_user("doc1", PASSWORD, role="physician", must_change=False, enforce_policy=False)
        monkeypatch.setenv("DR_SUPPORT_AUTH_FILE", str(users))
    app = create_app(state_path=str(tmp_path / "state.sqlite3"))
    web = TestClient(app)
    if signed_in_as:
        assert web.post("/v1/auth/login", json={"username": signed_in_as, "password": PASSWORD}).status_code == 200
    return app, web


def first_case(web):
    cases = web.get("/v1/cases").json()
    return cases[0]["image_id"]


def test_a_saved_report_keeps_the_graders_choice_and_never_changes_the_clinical_grade(tmp_path, monkeypatch):
    app, web = client(tmp_path, monkeypatch)
    image_id = first_case(web)
    before = web.get(f"/v1/cases/{image_id}").json()
    reply = web.put(f"/v1/cases/{image_id}/screening-report",
                    json={"revision": before["revision"], "report": FORM, "reviewer": "Synthetic reviewer"})
    assert reply.status_code == 200
    record = reply.json()["screening_report"]
    assert record["form"]["decision"] == "REFER" and record["decision_source"] == "GRADER_SELECTED"
    assert record["status"] == "DRAFT"
    after = web.get(f"/v1/cases/{image_id}").json()
    assert after.get("clinician_review") == before.get("clinician_review")
    stale = web.put(f"/v1/cases/{image_id}/screening-report",
                    json={"revision": before["revision"], "report": FORM, "reviewer": "Synthetic reviewer"})
    assert stale.status_code == 409


def test_a_nurse_prepares_and_only_a_physician_signs(tmp_path, monkeypatch):
    app, nurse = client(tmp_path, monkeypatch, signed_in_as="nurse1")
    image_id = first_case(nurse)
    revision = nurse.get(f"/v1/cases/{image_id}/screening-report").json()["revision"]
    saved = nurse.put(f"/v1/cases/{image_id}/screening-report", json={"revision": revision, "report": FORM})
    assert saved.status_code == 200 and saved.json()["screening_report"]["status"] == "PRELIMINARY"
    refused = nurse.put(f"/v1/cases/{image_id}/screening-report",
                        json={"revision": saved.json()["revision"], "report": FORM, "sign": True})
    assert refused.status_code == 403 and "physician signs" in refused.json()["detail"]
    doctor = TestClient(app)
    assert doctor.post("/v1/auth/login", json={"username": "doc1", "password": PASSWORD}).status_code == 200
    signed = doctor.put(f"/v1/cases/{image_id}/screening-report",
                        json={"revision": saved.json()["revision"], "report": FORM, "sign": True})
    record = signed.json()["screening_report"]
    assert record["status"] == "SIGNED" and record["prepared_by"]["role"] == "nurse"
    assert record["signed_by"]["name"] == "doc1"


def test_signing_needs_a_decision_and_the_print_page_escapes_what_people_typed(tmp_path, monkeypatch):
    app, web = client(tmp_path, monkeypatch)
    image_id = first_case(web)
    revision = web.get(f"/v1/cases/{image_id}/screening-report").json()["revision"]
    undecided = {**FORM, "decision": None}
    assert web.put(f"/v1/cases/{image_id}/screening-report", json={
        "revision": revision, "report": undecided, "sign": True, "reviewer": "R"}).status_code == 422
    web.put(f"/v1/cases/{image_id}/screening-report", json={"revision": revision, "report": FORM, "reviewer": "R"})
    page = web.get(f"/v1/cases/{image_id}/screening-report/print")
    assert page.status_code == 200 and "Diabetic Retinopathy Screening Report" in page.text
    assert "<script>" not in page.text.split("<style>")[0] + page.text.split("</style>")[1]
    assert "Synthetic Patient &lt;script&gt;" in page.text and "never reported as normal" in page.text


def test_unknown_form_fields_are_refused(tmp_path, monkeypatch):
    app, web = client(tmp_path, monkeypatch)
    image_id = first_case(web)
    revision = web.get(f"/v1/cases/{image_id}/screening-report").json()["revision"]
    reply = web.put(f"/v1/cases/{image_id}/screening-report",
                    json={"revision": revision, "report": {**FORM, "auto_referral": True}, "reviewer": "R"})
    assert reply.status_code == 422


def test_roles_module_still_lists_signing_roles():
    assert {"physician", "expert", "admin"} <= pilot_auth.ROLES
