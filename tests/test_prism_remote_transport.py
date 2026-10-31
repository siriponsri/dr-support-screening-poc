"""Fake HTTP, fake model port, synthetic bytes only; never a live runtime proof."""
import dr_support.services.prism_remote_transport as transport_module
import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import itertools
from threading import Event, Lock
from concurrent.futures import ThreadPoolExecutor
import time
from types import SimpleNamespace

import httpx
from PIL import Image
import pytest

from dr_support.images import BridgeImage
from dr_support.providers.prism_remote_bound import ExplicitHttpChannel, RemoteBoundTransportCandidate, RemoteExecutionUncertain
from dr_support.services.prism_remote_transport import BASE, PROTOCOL, BoundTransportHost, Principal, TransportError, canonical, pixels, sha
from dr_support.services.prism_remote_profile import QUALIFIED, register_isolated_remote_profile


def png(image):
    output = io.BytesIO();image.save(output, format="PNG");return output.getvalue()


class FakeAuthority:
    def __init__(self):
        self.lock = Lock();self.held = self.quarantined = False
        self.released = Event();self.calls = 0
        self.current = {}
        self.original_store = object();self.original_provider = object()

    def authorize_prepare(self, wire):
        if wire.source_type != "SYNTHETIC":raise TransportError("FIXTURE_SOURCE_NOT_AUTHORIZED")

    def mutate(self, name, value):
        with self.lock:
            if self.held:
                raise TransportError("MUTATION_FENCED")
            self.current[name] = value

    def acquire(self, binding, challenge, revalidate):
        with self.lock:
            if self.held or self.quarantined:
                raise TransportError("AUTHORITY_ALREADY_FENCED")
            self.calls += 1
            revalidate()  # Under the SAME fence that covers every mutation.
            expected = {"source": binding["source_sha256"], "revision": binding["case_revision"],
                        "workspace": binding["scope"], "provider": binding["model_pins"]["config_sha256"],
                        "admission": binding["admission_sha256"], "preparation": binding["preparation_context"],
                        "store_handle": self.original_store, "provider_handle": self.original_provider}
            if self.current != expected:
                raise TransportError("LOCAL_SOURCE_SCOPE_STALE")
            self.held = True
        authority = self
        class Lease:
            fence_id = "fixture_fence_001"
            def release(self, proof):
                with authority.lock:
                    assert authority.held
                    authority.held = False;authority.released.set()
            def quarantine(self, reason):
                with authority.lock:
                    authority.quarantined = True
        return Lease()


class FakeExecutor:
    entry_fence_port = True  # Test port only, never qualification.
    def __init__(self):
        self.pins = {"model_id": "prism-dr-5fold", "source_revision": "a" * 40, "preprocessing": "fixture-pipeline",
                     "config_sha256": "c" * 64, "checkpoint_sha256": {"fixture.pt": "b" * 64}}
        self.loads = self.roi = self.prepares = 0;self.loaded = False
        self.load_entered = Event();self.allow_load = Event();self.allow_load.set()
        self.allow_entry = Event();self.allow_entry.set()
        self.on_load = self.after_gate = self.after_entry = None
        self.ready_mask = False;self.skip_entry = False;self.fail = False
    def identity(self):return deepcopy(self.pins)
    def loaded_identity(self):
        assert self.loaded
        return deepcopy(self.pins)
    def prepare(self, wire, modality):
        self.prepares += 1
        if self.ready_mask:
            image = pixels(wire);mask = Image.new("L", image.size, 255);mask.putpixel((0, 0), 0)
            return {"status": "READY", "mask_png": png(mask), "mask_version": transport_module.MASK_VERSION, "reason_code": None}
        return {"status": "UNCERTAIN", "mask_png": None, "mask_version": None, "reason_code": "FIXTURE_UNCERTAIN"}
    def load_until(self, deadline, cancelled):
        self.loads += 1;self.load_entered.set()
        while not self.allow_load.wait(.005):
            if cancelled() or time.monotonic() >= deadline:raise TransportError("FAKE_LOAD_CANCELLED")
        if self.on_load:self.on_load()
        self.loaded = True
    def execute(self, wire, mask, binding, plan_hash, *, before_forward, on_roi_entry):
        assert self.loaded
        before_forward()
        if self.after_gate:self.after_gate()
        assert self.allow_entry.wait(2)
        if not self.skip_entry:on_roi_entry()
        else:return {}
        self.roi += 1
        if self.after_entry:self.after_entry()
        if self.fail:raise RuntimeError("FIXTURE_MODEL_FAILURE")
        width, height = pixels(wire).size
        processing = {"input_image_sha256": sha(wire), "processing_mode": "PREPARED" if mask else "FALLBACK",
            "native_roi_status": "SUCCEEDED", "native_roi_bbox": [0, 0, width, height], "external_fov_status": binding["external_fov_status"],
            "external_fov_reason_code": binding["external_fov_reason_code"], "fov_used_for_model_input": mask is not None,
            "analysis_field": None, "raw_boundary_classes": []}
        if mask:
            processing["analysis_field"] = {"status": "READY", "mask_version": binding["mask_version"], "mask_sha256": binding["mask_sha256"],
                "source_rgb_sha256": binding["wire_rgb_sha256"], "image_width": width, "image_height": height,
                "boundary_confidence": .9, "excluded_fraction": 1 / (width * height), "boundary": [[0, 0], [width, 0], [width, height]],
                "used_for_model_input": True, "field_mask_png_base64": base64.b64encode(mask).decode()}
        return {"preview_receipt": {"plan_sha256": plan_hash, "wire_sha256": sha(wire), "mask_sha256": binding["mask_sha256"], "transform_sha256": binding["transform"]["sha256"]},
            "result": {"model_id": "prism-dr-5fold", "model_version": self.pins["source_revision"], "modality": "UWF", "state": "AI_SUGGESTION",
                "width": width, "height": height, "lesions": [], "warnings": ["FAKE_INTERNALS_NOT_REAL_INFERENCE", "Empty output is not clinician normal"],
                "provenance": {"image_sha256": sha(wire), "source_type": "SYNTHETIC", "source_revision": self.pins["source_revision"],
                               "checkpoint_sha256": self.pins["checkpoint_sha256"], "preprocessing": self.pins["preprocessing"]}}, "processing_evidence": processing}


@pytest.fixture
def rig(monkeypatch):
    import builtins
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"torch", "cv2"}:pytest.fail("Real model/CV import forbidden")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    import socket, sqlite3, psycopg
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("Socket/listener forbidden"))
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: pytest.fail("SQL forbidden"))
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: pytest.fail("SQL forbidden"))
    executor, authority = FakeExecutor(), FakeAuthority();ids = itertools.count()
    def authenticate(headers):
        value = headers.get("authorization")
        if value == "Bearer FIXTURE_REVIEW":return Principal("fixture_server", frozenset({"review-client", "prepare-source"}))
        if value == "Bearer FIXTURE_AUTHORITY":return Principal("fixture_server", frozenset({"review-client", "prepare-source", "forward-authority"}))
        if value == "Bearer FIXTURE_OTHER":return Principal("other_server", frozenset({"review-client", "prepare-source", "forward-authority"}))
        return None
    host = BoundTransportHost(executor, authenticate=authenticate, issue_id=lambda: f"fixture_{next(ids):08d}", epoch="fixture_epoch_01", job_seconds=.8)
    state = {"fault": None, "requests": [], "grant_hook": None}
    def endpoint(request):
        state["requests"].append((request.method, request.url.path))
        headers = {k.lower(): v for k, v in request.headers.items()}
        if state["fault"] == "offline":raise httpx.ReadError("FIXTURE_OFFLINE")
        if request.url.path.endswith("/grant") and state["grant_hook"]:state["grant_hook"]()
        status, value = host.handle(request.method, request.url.path, headers, request.content)
        if state["fault"] == "drop_execute" and request.url.path == BASE + "/execute":
            raise httpx.ReadError("FIXTURE_LOST_EXECUTE_ACK")
        if state["fault"] == "drop_grant" and request.url.path.endswith("/grant"):
            state["fault"] = "offline";raise httpx.ReadError("FIXTURE_LOST_GRANT_ACK")
        return httpx.Response(status, json=value)
    channel = ExplicitHttpChannel("https://fixture.invalid", transport=httpx.MockTransport(endpoint),
        auth_headers=lambda authority=False: {"Authorization": "Bearer FIXTURE_AUTHORITY" if authority else "Bearer FIXTURE_REVIEW"})
    client = RemoteBoundTransportCandidate(channel, source_authority=authority, wait_seconds=1.2, poll_seconds=.002)
    client.negotiate()
    wire = BridgeImage("fixture_image", png(Image.new("RGB", (12, 8), (80, 40, 20))), "SYNTHETIC", "synthetic",
                       modality="UWF", media_type="image/png", source_origin="SYNTHETIC")
    request = SimpleNamespace(image_id=wire.image_id, model_id="prism-dr-5fold", modality="UWF")
    def prepare():
        candidate = client.prepare_prism_preview_candidate(wire)
        ticket = client.tickets[(wire.sha256, wire.modality)]
        image = pixels(wire.data);rgb = sha(__import__('struct').pack(">II", *image.size) + image.tobytes())
        transform = {"version": "1", "original_width": 12, "original_height": 8, "input_width": 12, "input_height": 8,
            "original_to_input": [1, 0, 0, 1, 0, 0], "coordinate_mapping": {"scale_x": 1, "scale_y": 1},
            "transform_id": "analysis-uwf-unmasked-source-v1", "representation_version": "uwf-source-analysis-v1"}
        transform["sha256"] = sha(canonical(transform))
        binding = {"binding_protocol": PROTOCOL, "scope": "fixture_workspace", "image_id": wire.image_id, "case_revision": 1,
            "source_sha256": wire.sha256, "source_rgb_sha256": rgb, "wire_rgb_sha256": rgb, "wire_sha256": wire.sha256,
            "wire_byte_count": len(wire.data), "wire_media_type": wire.media_type, "wire_dimensions": {"width": 12, "height": 8},
            "modality": "UWF", "model_id": "prism-dr-5fold", "model_version": executor.pins["source_revision"], "model_pins": deepcopy(executor.pins),
            "admission_sha256": "d" * 64, "admission": {"source_origin": "SYNTHETIC", "retinal_modality": "UWF", "modality_admission": "FUNDUS_ACCEPTED", "quality_state": "GRADABLE"},
            "transform": transform, "plan_id": "fixture_plan_01", "generation": 0}
        binding["preparation_context"] = "fixture_preparation_context"
        binding["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat()
        binding["recorded_source_identity"] = {"case_source_sha256": wire.sha256, "admission_source_sha256": wire.sha256,
            "image_recorded_sha256": wire.sha256, "integrity_status": "OK", "source_origin": "SYNTHETIC", "case_revision": 1, "admission_sha256": binding["admission_sha256"]}
        for name in ["mask_sha256", "mask_png_sha256", "mask_version", "external_fov_status", "external_fov_reason_code"]:binding[name] = ticket[name]
        authority.current = {"source": wire.sha256, "revision": 1, "workspace": binding["scope"], "provider": executor.pins["config_sha256"],
            "admission": binding["admission_sha256"], "preparation": binding["preparation_context"],
            "store_handle": authority.original_store, "provider_handle": authority.original_provider}
        return binding, candidate["mask_png"]
    def run(binding, mask, callback=None):
        def validate():
            assert executor.loaded, "Local callback must never run before remote loading"
            if callback:callback()
        return client.infer_bound_prism(request, wire, mask_png=mask, binding=binding, plan_sha256=sha(canonical(binding)), before_forward=validate)
    value = SimpleNamespace(executor=executor, authority=authority, host=host, client=client, channel=channel, wire=wire, request=request,
                            state=state, prepare=prepare, run=run)
    yield value
    executor.allow_load.set();executor.allow_entry.set()
    for job in host.jobs.values():
        with job.condition:job.cancelled = True;job.condition.notify_all()
    host.join_for_test();channel.close()


def test_prepare_is_cpu_only_and_exact_wire_mask_execute_once(rig):
    rig.executor.ready_mask = True
    binding, mask = rig.prepare()
    assert rig.executor.loads == rig.executor.roi == 0
    assert rig.client.refresh_prism_preview_candidate(rig.wire)["mask_png"] == mask and rig.executor.prepares == 1
    result = rig.run(binding, mask)
    assert rig.executor.loads == rig.executor.roi == rig.authority.calls == 1
    assert not rig.authority.held and not rig.authority.quarantined
    assert result["processing_evidence"]["analysis_field"]["mask_sha256"] == binding["mask_sha256"]
    assert result["result"]["state"] == "AI_SUGGESTION" and result["result"]["lesions"] == []
    with pytest.raises(TransportError, match="NO_RETRY"):rig.run(binding, mask)
    assert rig.executor.roi == 1


@pytest.mark.parametrize("field,value", [("source", "e" * 64), ("revision", 2), ("workspace", "different"),
    ("provider", "e" * 64), ("admission", "f" * 64), ("preparation", "changed"), ("store_handle", object()), ("provider_handle", object())])
def test_source_scope_change_during_remote_load_blocks_before_roi(rig, field, value):
    binding, mask = rig.prepare()
    rig.executor.on_load = lambda: rig.authority.mutate(field, value)
    with pytest.raises(TransportError, match="STALE"):rig.run(binding, mask)
    rig.host.join_for_test()
    assert rig.executor.loads == 1 and rig.executor.roi == 0


def test_queued_remote_load_precedes_local_revalidation(rig):
    binding, mask = rig.prepare();rig.executor.allow_load.clear()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(rig.run, binding, mask)
        assert rig.executor.load_entered.wait(1) and rig.authority.calls == 0
        rig.authority.mutate("revision", 2);rig.executor.allow_load.set()
        with pytest.raises(TransportError, match="STALE"):future.result(timeout=2)
    assert rig.executor.roi == 0


def test_fence_prevents_source_change_in_network_grant_interval(rig):
    binding, mask = rig.prepare();blocked = []
    def mutation_in_transit():
        with pytest.raises(TransportError, match="MUTATION_FENCED"):rig.authority.mutate("revision", 2)
        blocked.append(True)
    rig.state["grant_hook"] = mutation_in_transit
    rig.run(binding, mask)
    assert blocked == [True] and rig.executor.roi == 1 and rig.authority.current["revision"] == 1


def test_human_edit_can_resume_after_authentic_native_entry_proof(rig):
    binding, mask = rig.prepare()
    def late_edit():
        assert rig.authority.released.wait(1)
        rig.authority.mutate("revision", 2)
    rig.executor.after_entry = late_edit
    rig.run(binding, mask)
    assert rig.authority.current["revision"] == 2  # No persistence code overwrites it.


@pytest.mark.parametrize("when", ["before_load", "during_load", "after_grant"])
def test_changed_model_config_never_reaches_roi(rig, when):
    binding, mask = rig.prepare()
    def change():rig.executor.pins["config_sha256"] = "e" * 64
    if when == "before_load":change()
    elif when == "during_load":rig.executor.on_load = change
    else:rig.executor.after_gate = change
    with pytest.raises(TransportError):rig.run(binding, mask)
    assert rig.executor.roi == 0


@pytest.mark.parametrize("change", ["source", "integrity", "mask", "transform", "wire"])
def test_forged_binding_rejected_without_model_load(rig, change):
    binding, mask = rig.prepare()
    if change == "source":binding["recorded_source_identity"]["case_source_sha256"] = "e" * 64
    elif change == "integrity":binding["recorded_source_identity"]["integrity_status"] = "SOURCE_CHANGED"
    elif change == "mask":binding["mask_sha256"] = "e" * 64
    elif change == "transform":binding["transform"]["sha256"] = "e" * 64
    else:binding["wire_sha256"] = "e" * 64
    with pytest.raises(TransportError):rig.run(binding, mask)
    assert rig.executor.loads == rig.executor.roi == 0


def test_expired_ticket_and_server_restart_never_reload(rig):
    binding, mask = rig.prepare();rig.host.epoch = "new_fixture_epoch"
    with pytest.raises(TransportError, match="RESTARTED"):rig.run(binding, mask)
    assert rig.executor.loads == 0


def test_expiry_before_admission(rig):
    binding, mask = rig.prepare();now = rig.host.clock
    rig.host.clock = lambda: now() + 301
    with pytest.raises(TransportError, match="EXPIRED"):rig.run(binding, mask)
    assert rig.executor.loads == 0


def test_concurrent_admission_rejected_before_second_load(rig):
    binding, mask = rig.prepare();rig.executor.allow_load.clear()
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(rig.run, binding, mask)
        assert rig.executor.load_entered.wait(1)
        ticket = next(iter(rig.host.tickets))
        with pytest.raises(TransportError, match="CONCURRENT"):
            rig.client._request("POST", BASE + "/execute", {"ticket_id": ticket, "binding": binding, "plan_sha256": sha(canonical(binding))})
        rig.executor.allow_load.set();first.result(timeout=2)
    assert rig.executor.loads == rig.executor.roi == 1


def test_execution_failure_and_raw_replay_do_not_run_second_roi(rig):
    binding, mask = rig.prepare();rig.executor.fail = True
    ticket = rig.client.tickets[(rig.wire.sha256, rig.wire.modality)]["ticket_id"]
    with pytest.raises(TransportError, match="FAILED_NO_RETRY"):rig.run(binding, mask)
    with pytest.raises(TransportError, match="REPLAY"):
        rig.client._request("POST", BASE + "/execute", {"ticket_id": ticket, "binding": binding, "plan_sha256": sha(canonical(binding))})
    assert rig.executor.roi == 1


def test_lost_execute_ack_does_not_retry_or_create_a_grant(rig):
    binding, mask = rig.prepare();rig.state["fault"] = "drop_execute"
    with pytest.raises(RemoteExecutionUncertain):rig.run(binding, mask)
    assert len(rig.host.jobs) == 1 and rig.authority.calls == 0
    with pytest.raises(TransportError, match="NO_RETRY"):rig.run(binding, mask)
    assert sum(path == BASE + "/execute" for _, path in rig.state["requests"]) == 1


def test_lost_grant_ack_quarantines_fence_instead_of_timeout_release(rig):
    binding, mask = rig.prepare();rig.executor.allow_entry.clear();rig.state["fault"] = "drop_grant"
    with pytest.raises(RemoteExecutionUncertain):rig.run(binding, mask)
    assert rig.authority.held and rig.authority.quarantined and not rig.authority.released.is_set()
    with pytest.raises(TransportError, match="FENCED"):rig.authority.mutate("revision", 2)
    assert sum(path == BASE + "/execute" for _, path in rig.state["requests"]) == 1


def test_missing_real_fence_rejects_before_remote_loading(rig):
    binding, mask = rig.prepare();rig.client.authority = None
    with pytest.raises(TransportError, match="FENCE_REQUIRED"):rig.run(binding, mask)
    assert rig.executor.loads == 0


def test_authentication_precedes_parsing_and_grant_requires_authority(rig):
    code, value = rig.host.handle("POST", BASE + "/execute", {}, b"not json")
    assert code == 401 and not rig.host.jobs
    binding, mask = rig.prepare()
    rig.channel.auth_headers = lambda authority=False: {"Authorization": "Bearer FIXTURE_REVIEW"}
    with pytest.raises(TransportError, match="AUTHORITY_REQUIRED"):rig.run(binding, mask)
    assert rig.executor.roi == 0


def test_skipped_native_entry_hook_fails_without_result(rig):
    binding, mask = rig.prepare();rig.executor.skip_entry = True
    with pytest.raises(TransportError, match="SKIPPED_FATAL_ENTRY"):rig.run(binding, mask)
    assert rig.executor.roi == 0 and not rig.authority.held


def test_profile_is_disabled_without_flag_override():
    assert QUALIFIED is False
    with pytest.raises(RuntimeError, match="NOT_QUALIFIED"):register_isolated_remote_profile(enabled=True)


def test_missing_preparation_authority_sends_no_image(rig):
    rig.client.authority = None
    with pytest.raises(TransportError, match="PREPARATION_AUTHORITY_REQUIRED"):
        rig.client.prepare_prism_preview_candidate(rig.wire)
    assert rig.executor.prepares == rig.executor.loads == 0
    assert not any(path.endswith('/prepare') for _, path in rig.state['requests'])


def test_cached_identity_never_sends_metadata_or_model_requests(rig):
    before = len(rig.state['requests'])
    assert rig.client.prism_preview_identity()['descriptor']['ready'] is False
    assert len(rig.state['requests']) == before and rig.executor.loads == 0


def test_expired_plan_is_rejected_even_when_cpu_ticket_is_live(rig):
    binding, mask = rig.prepare()
    binding['expires_at'] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    with pytest.raises(TransportError, match='PLAN_EXPIRED'):rig.run(binding, mask)
    assert rig.executor.loads == 0


def test_bounded_client_wait_cancels_without_early_source_validation(rig):
    binding, mask = rig.prepare();rig.executor.allow_load.clear();rig.client.wait_seconds = .03
    with pytest.raises(RemoteExecutionUncertain, match='WAIT_EXPIRED'):rig.run(binding, mask)
    assert rig.executor.roi == 0 and rig.authority.calls == 0
    assert sum(path == BASE + '/execute' for _, path in rig.state['requests']) == 1


def test_other_authenticated_principal_cannot_use_ticket(rig):
    binding, mask = rig.prepare()
    ticket = rig.client.tickets[(rig.wire.sha256, rig.wire.modality)]['ticket_id']
    code, value = rig.host.handle('POST', BASE + '/execute',
        {'authorization':'Bearer FIXTURE_OTHER','x-prism-epoch':rig.host.epoch},
        canonical({'ticket_id':ticket,'binding':binding,'plan_sha256':sha(canonical(binding))}))
    assert code == 404 and rig.executor.loads == 0
