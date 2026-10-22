"""Synthetic fixtures only; never reads the authorized demo or imports a model.

Positive integration replaces ONLY the module's pinned test digest/dimensions
with generated PNG bytes. Production pin is separately asserted verbatim.
This does not verify real-image attachment, Linux resources or live transport.
"""

from copy import deepcopy
import itertools
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from dr_support.images import BridgeImage
from dr_support.store import new_case
from dr_support.providers.prism_remote_bound import (
    ExplicitHttpChannel,
    FixedSessionRemoteProvider,
)
from dr_support.services import case16_qualification as profile
from dr_support.services.prism_fixed_session import FixedQASession
from dr_support.services.prism_owned_runtime import (
    LoadedPrismExecutor,
    child_application,
)
from dr_support.services.prism_remote_transport import (
    BASE,
    BoundTransportHost,
    Principal,
    TransportError,
    sha,
)
from test_prism_owned_runtime import BoundProviderFake, fake_load_guard
from test_prism_remote_transport import FakeExecutor, png


def test_production_pin_and_owner_are_exact():
    assert (
        profile.SOURCE_SHA256
        == "07bc59b885de06bdd0260c771aabde195c26125e824269a691eb566a61a5cd19"
    )
    assert profile.OWNER_REFERENCE == "Sentinel_d7d1e493dbd88191a76fad54af3abf37"
    assert profile.RECORDED_ORIGIN == "PUBLIC"
    assert profile.EXPECTED_SIZE == (1920, 835)
    assert profile.RUN_REQUESTS == 1


@pytest.fixture
def metadata(monkeypatch):
    data = png(Image.new("RGB", (12, 8), (80, 40, 20)))
    digest = sha(data)
    monkeypatch.setattr(profile, "SOURCE_SHA256", digest)
    monkeypatch.setattr(profile, "EXPECTED_SIZE", (12, 8))
    image = BridgeImage(
        digest,
        data,
        "PUBLIC",
        "SYNTHETIC_BYTES_ONLY",
        modality="UWF",
        source_origin="PUBLIC",
        media_type="image/png",
    )
    admission = dict(
        image_id=digest,
        source_origin="PUBLIC",
        source_sha256=digest,
        integrity_status="OK",
        retinal_modality="UWF",
        modality_admission="FUNDUS_ACCEPTED",
        quality_state="GRADABLE",
        admission_method="MANUAL",
        admission_reason_code="SYNTHETIC_FIXTURE",
    )
    case = new_case(digest)
    case.update(
        image_sha256=digest,
        source_sha256=digest,
        admission=deepcopy(admission),
        resolver_state="RESOLVED",
        patient_key="SYNTHETIC_FIXTURE",
        laterality="LEFT",
    )
    return SimpleNamespace(
        image=image,
        admission=admission,
        case=case,
        authorization=profile.Case16Authorization(profile.OWNER_REFERENCE),
    )


@pytest.fixture
def app(metadata, tmp_path, monkeypatch):
    # SQL construction fails the test, as does any attempted model/CV import.
    import builtins

    original_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"torch", "cv2", "ultralytics", "sahi"}:
            pytest.fail("REAL_MODEL_IMPORT_FORBIDDEN")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    from dr_support.api import _factory

    monkeypatch.setattr(
        _factory, "_build_case_store", lambda *a, **k: pytest.fail("DB_FORBIDDEN")
    )
    fake = FakeExecutor()

    class ProvenanceFixture(BoundProviderFake):
        def prepare_prism_preview_candidate(self, image):
            value = super().prepare_prism_preview_candidate(image)
            if value["status"] == "UNCERTAIN":
                value["reason_code"] = profile.BASELINE_REASON
            return value

        def infer_remote_fenced_prism(self, request, image, **kwargs):
            authorization = kwargs.pop("demo_authorization")
            assert authorization is metadata.authorization
            authorization.wire(image.data)
            authorization.binding(kwargs["binding"])
            value = super().infer_remote_fenced_prism(request, image, **kwargs)
            # A fake result must report its input's simulated recorded origin.
            value["result"]["provenance"]["source_type"] = image.source_origin
            return value

    raw = ProvenanceFixture(fake)
    executor = LoadedPrismExecutor(
        raw,
        expected_pins=fake.pins,
        load_guard=fake_load_guard,
        demo_authorization=metadata.authorization,
    )
    executor.load_until(executor.clock() + 1, lambda: False)
    counter = itertools.count()
    principal = Principal(
        "PUBLIC_TEST_FIXTURE",
        frozenset({"review-client", "prepare-source", "forward-authority"}),
    )
    host = BoundTransportHost(
        executor,
        authenticate=lambda headers: principal,
        epoch="test_demo_epoch",
        issue_id=lambda: f"test_demo_{next(counter):08}",
        allowed_origins={"PUBLIC"},
    )

    def endpoint(request):
        assert (
            request.headers["authorization"]
            == "Bearer PUBLIC_TEST_FIXTURE_NOT_A_SECRET"
        )
        status, body = host.handle(
            request.method, request.url.path, request.headers, request.content
        )
        return httpx.Response(status, json=body)

    channel = ExplicitHttpChannel(
        "https://fixture.invalid",
        transport=httpx.MockTransport(endpoint),
        auth_headers=lambda authority=False: {
            "Authorization": "Bearer PUBLIC_TEST_FIXTURE_NOT_A_SECRET"
        },
    )
    provider = FixedSessionRemoteProvider(channel, wait_seconds=0.5, poll_seconds=0.002)
    provider.negotiate()
    directory = tmp_path / "case16-owned-qualification-q01"
    session = profile.authorized_case16_session(
        directory,
        authorization=metadata.authorization,
        image=metadata.image,
        case=metadata.case,
        admission=metadata.admission,
        provider=provider,
        authenticated_status_reader=lambda fence: channel.request(
            "GET", BASE + "/jobs/" + fence["job_id"], epoch=fence["epoch"]
        ),
    )
    actual = _factory.create_app(
        include_samples=False, include_demo_fixtures=False, qa_fixed_session=session
    )
    rig = SimpleNamespace(
        **vars(metadata),
        client=TestClient(actual, raise_server_exceptions=False),
        session=session,
        executor=executor,
        fake=fake,
        raw=raw,
        host=host,
        directory=directory,
    )
    yield rig
    for job in host.jobs.values():
        if job.thread:
            job.thread.join(timeout=2)
            assert not job.thread.is_alive()
    channel.close()
    session.close()


def prepare(app):
    case = app.client.get("/v1/cases/" + app.image.image_id).json()
    return app.client.post(
        "/v1/cases/" + app.image.image_id + "/prism-input-preview",
        json={"revision": case["revision"]},
    )


def submit(app, plan):
    return app.client.post(
        "/v1/cases/"
        + app.image.image_id
        + "/prism-input-preview/"
        + plan["plan_id"]
        + "/infer",
        json={
            "revision": plan["case_revision"],
            "source_sha256": plan["source_sha256"],
            "wire_sha256": plan["wire_sha256"],
            "plan_sha256": plan["plan_sha256"],
            "mask_sha256": plan["mask"]["sha256"],
            "transform_sha256": plan["transform"]["sha256"],
            "model_version": plan["model_version"],
        },
    )


def test_one_authorized_app_plan_preserves_origin_and_copied_human_state(app):
    original_case, original_admission = deepcopy(app.case), deepcopy(app.admission)
    plans = []
    for _ in range(profile.RUN_REQUESTS):
        response = prepare(app)
        assert response.status_code == 200, response.text
        plan = response.json()
        plans.append(plan)
        assert plan["mask"]["sha256"] is None
        result = submit(app, plan)
        assert result.status_code == 200, (
            result.text,
            [(job.state, job.error) for job in app.host.jobs.values()],
        )
        assert result.json()["status"] == "APPLIED"
        after_save = app.session.store.get(app.image.image_id)
        assert all(
            after_save.get(key) == original_case.get(key)
            for key in profile.CLINICAL_FIELDS
        )
    assert app.raw.loads == app.executor.load_attempts == 1
    assert app.fake.roi == len(app.raw.calls) == 1
    assert (
        app.image.source_origin
        == app.image.source_type
        == app.admission["source_origin"]
        == "PUBLIC"
    )
    assert all(
        call[2]["recorded_source_identity"]["source_origin"] == "PUBLIC"
        for call in app.raw.calls
    )
    assert all(
        call[2]["admission"]["source_origin"] == "PUBLIC" and call[0] == app.image.data
        for call in app.raw.calls
    )
    assert app.case == original_case and app.admission == original_admission
    copied = app.session.store.get(app.image.image_id)
    assert all(
        copied.get(key) == original_case.get(key) for key in profile.CLINICAL_FIELDS
    )
    assert len(list((app.directory / "testdata").glob("output-*.json"))) == 1
    assert submit(app, plans[0]).status_code == 409
    assert prepare(app).status_code != 200
    assert app.fake.roi == 1


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("case", "image_id", "another-case"),
        ("case", "source_sha256", "f" * 64),
        ("case", "image_sha256", "f" * 64),
        ("admission", "source_sha256", "f" * 64),
        ("admission", "integrity_status", "SOURCE_CHANGED"),
        ("admission", "quality_state", "NEEDS_REVIEW"),
        ("admission", "modality_admission", "NEEDS_REVIEW"),
        ("admission", "retinal_modality", "CFP"),
        ("admission", "source_origin", "SYNTHETIC"),
        ("admission", "source_origin", "HOSPITAL_AUTHORIZED"),
        ("admission", "integrity", {"changed_sources": ["fixture"]}),
    ],
)
def test_wrong_case_recorded_hash_or_review_state_rejected(
    metadata, section, key, value
):
    getattr(metadata, section)[key] = value
    with pytest.raises(TransportError):
        metadata.authorization.input(metadata.image, metadata.case, metadata.admission)


@pytest.mark.parametrize("value", ["", "approved", "Sentinel_other", None])
def test_wrong_authorization_rejected(value):
    with pytest.raises(TransportError):
        profile.Case16Authorization(value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("lesion_review_state", "REVIEWED"),
        ("annotation_completeness", {"MA": True, "HE": True, "EX": True, "SE": True}),
        ("annotations", {"human_confirmed": True, "lesions": []}),
    ],
)
def test_appended_inference_cannot_promote_clinical_fields(
    metadata, tmp_path, field, value
):
    original = deepcopy(metadata.case)
    store = profile.QualificationMemoryStore(original, evidence=tmp_path / "testdata")
    changed = store.get(metadata.image.image_id)
    changed[field] = value
    changed["inference_history"].append({"synthetic_fixture": "not real inference"})
    with pytest.raises(TransportError, match="CLINICAL_MUTATION"):
        store.put(changed)
    assert store.get(metadata.image.image_id) == original
    assert not (tmp_path / "testdata").exists()


def test_untyped_authorization_rejected_before_source_files(tmp_path, metadata):
    root = tmp_path / "case16-owned-qualification-q01"
    with pytest.raises(TransportError):
        profile.authorized_case16_session(
            root,
            authorization=True,
            image=metadata.image,
            case=metadata.case,
            admission=metadata.admission,
            provider=None,
            authenticated_status_reader=None,
        )
    assert not root.exists()


def test_actual_wrong_bytes_never_replace_recorded_pin(metadata):
    with pytest.raises(TransportError):
        metadata.authorization.wire(b"wrong immutable bytes")


def test_applied_mask_rejected_before_ticket_or_roi(app):
    app.fake.ready_mask = True
    response = prepare(app)
    assert response.status_code != 200
    assert app.fake.roi == 0 and not app.host.tickets


def test_public_source_without_attestation_still_rejected_by_fixed_profile(
    tmp_path, metadata
):
    store = profile.QualificationMemoryStore(
        metadata.case, evidence=tmp_path / "testdata"
    )
    # Provider type guard occurs first; reuse a synthetic app's provider in a separate test below.
    with pytest.raises(TransportError):
        FixedQASession(
            tmp_path / "journal",
            store=store,
            images={metadata.image.image_id: metadata.image},
            admissions={metadata.image.image_id: metadata.admission},
            provider=None,
            authenticated_status_reader=lambda fence: None,
        )
    assert not (tmp_path / "journal").exists()


def test_fresh_scope_not_reopened_or_backed_by_external_store(app, tmp_path):
    with pytest.raises(TransportError):
        profile.authorized_case16_session(
            app.directory,
            authorization=app.authorization,
            image=app.image,
            case=app.case,
            admission=app.admission,
            provider=app.session.provider,
            authenticated_status_reader=lambda fence: None,
        )
    with pytest.raises(TransportError, match="COPIED_MEMORY_STORE"):
        FixedQASession(
            tmp_path / "new-journal",
            store=SimpleNamespace(),
            images={app.image.image_id: app.image},
            admissions={app.image.image_id: app.admission},
            provider=app.session.provider,
            authenticated_status_reader=lambda fence: None,
            demo_authorization=app.authorization,
        )


def test_clinical_or_gold_style_write_never_permitted(app):
    copied = app.session.raw_store.get(app.image.image_id)
    copied["reviewed_grade"] = 4
    with pytest.raises(TransportError, match="CLINICAL_MUTATION"):
        app.session.raw_store.put(copied)
    response = app.client.post(
        "/v1/cases/" + app.image.image_id + "/review", json={"grade": 4}
    )
    assert response.status_code == 423
    assert app.fake.roi == 0 and app.case["reviewed_grade"] is None


def test_worker_scope_uses_same_preserved_origin(app):
    _, host = child_application(
        app.executor,
        token="PUBLIC_TEST_FIXTURE_NOT_A_SECRET",
        issue_id=lambda: "fixture",
        epoch="fixture_epoch",
    )
    assert host.allowed_origins == {"PUBLIC"}


def test_first_evidence_save_failure_closes_profile_without_second_model_call(
    app, monkeypatch
):
    plan = prepare(app).json()

    def fail_write(case):
        raise OSError("SYNTHETIC_EVIDENCE_WRITE_FAILURE")

    monkeypatch.setattr(app.session.raw_store, "put", fail_write)
    assert submit(app, plan).status_code == 502
    assert app.session.poisoned is True and app.fake.roi == 1
    assert (
        app.client.post(
            "/v1/cases/" + app.image.image_id + "/prism-input-preview",
            json={"revision": plan["case_revision"]},
        ).status_code
        == 423
    )
    assert app.fake.roi == 1 and app.case["reviewed_grade"] is None


def test_ordinary_fixed_profile_still_rejects_public_even_with_valid_provider(
    app, tmp_path
):
    with pytest.raises(TransportError, match="FIXED_QA_SYNTHETIC_ONLY"):
        FixedQASession(
            tmp_path / "ordinary-journal",
            store=app.session.raw_store,
            images={app.image.image_id: app.image},
            admissions={app.image.image_id: app.admission},
            provider=app.session.provider,
            authenticated_status_reader=lambda fence: None,
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("case_source_sha256", "f" * 64),
        ("admission_source_sha256", "f" * 64),
        ("image_recorded_sha256", "f" * 64),
        ("integrity_status", "SOURCE_CHANGED"),
        ("source_origin", "SYNTHETIC"),
    ],
)
def test_binding_never_replaces_conflicting_recorded_identity(metadata, field, value):
    digest = metadata.image.sha256
    binding = dict(
        image_id=digest,
        source_sha256=digest,
        case_revision=1,
        admission_sha256="a" * 64,
        admission=metadata.admission,
        modality="UWF",
        model_id="prism-dr-5fold",
        wire_sha256=digest,
        external_fov_status="UNCERTAIN",
        external_fov_reason_code=profile.BASELINE_REASON,
        mask_sha256=None,
        mask_png_sha256=None,
        mask_version=None,
        recorded_source_identity=dict(
            source_origin="PUBLIC",
            integrity_status="OK",
            case_revision=1,
            admission_sha256="a" * 64,
            case_source_sha256=digest,
            admission_source_sha256=digest,
            image_recorded_sha256=digest,
        ),
    )
    metadata.authorization.binding(binding)
    binding["recorded_source_identity"][field] = value
    with pytest.raises(TransportError):
        metadata.authorization.binding(binding)


@pytest.mark.parametrize(
    "changed",
    [
        {"max_jobs": 3},
        {"max_seconds": 599},
        {"max_vram_mib": 10241},
        {"max_rss_bytes": 24 * 1024**3 + 1},
    ],
)
def test_budgets_cannot_expand(metadata, changed):
    values = dict(
        model_id="prism-dr-5fold",
        max_jobs=2,
        max_seconds=270,
        drain_seconds=25,
        max_vram_mib=10240,
        max_rss_bytes=24 * 1024**3,
    )
    values.update(changed)
    with pytest.raises(TransportError):
        metadata.authorization.worker_policy(
            SimpleNamespace(**values), whole_session_seconds=1800
        )
