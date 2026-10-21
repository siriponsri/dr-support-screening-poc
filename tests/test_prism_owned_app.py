"""Actual fixed app -> owned channel/executor, wholly synthetic and MockTransport."""
import httpx
import pytest

import test_prism_fixed_app as fixed
from test_prism_owned_runtime import executor
from dr_support.providers.prism_owned_channel import DeadlineHttpExchange, OwnedFixedSessionRemoteProvider, PrivateGatewayChannel
from dr_support.services.prism_remote_transport import BASE


@pytest.mark.parametrize('prepared_mask', [False, True])
def test_actual_app_owned_channel_preserves_frozen_input_and_saver(tmp_path, monkeypatch, prepared_mask):
    exchanges = []
    def injected_provider(channel, **options):
        caps = channel.request('GET', BASE+'/capabilities')
        def endpoint(request):
            assert request.headers['authorization'] == 'Bearer '+'x'*64
            if request.url.path == BASE+'/readiness':
                return httpx.Response(200, json={'state':'LOADED', 'epoch':caps['epoch'], 'pins':caps['pins']})
            # Translate only test credentials between two existing mock fixtures.
            request.headers['authorization'] = 'Bearer FIXTURE_SERVICE'
            return channel.client._transport.handle_request(request)
        exchange = DeadlineHttpExchange(token='x'*64, transport=httpx.MockTransport(endpoint), port=17860)
        exchanges.append(exchange)
        private = PrivateGatewayChannel(exchange, expected_epoch=caps['epoch'], expected_pins=caps['pins'])
        private.establish()
        return OwnedFixedSessionRemoteProvider(private, **options)
    monkeypatch.setattr(fixed, 'FixedSessionRemoteProvider', injected_provider)
    fixture = fixed.app_rig.__wrapped__(tmp_path, monkeypatch)
    rig = next(fixture)
    try:
        raw_provider, loaded = executor(rig)
        loaded.load_until(loaded.clock()+1, lambda:False)
        rig.host.executor = loaded
        rig.executor.ready_mask = prepared_mask
        plan = fixed.prepare(rig)
        assert (plan['mask']['sha256'] is not None) is prepared_mask
        assert rig.client.get(plan['input_preview']['url']).status_code == 200
        assert rig.client.post('/v1/cases/fixture_image/review', json={}).status_code == 423
        result = fixed.submit(rig, plan)
        assert result.status_code == 200, result.text
        assert result.json()['status'] == 'APPLIED'
        assert raw_provider.loads == loaded.load_attempts == 1
        assert len(raw_provider.calls) == 1 and rig.executor.prepares == rig.executor.roi == 1
        wire, mask, binding = raw_provider.calls[0]
        assert (mask is not None) is prepared_mask
        assert binding['wire_sha256'] == plan['wire_sha256']
        assert binding['mask_sha256'] == plan['mask']['sha256']
        assert rig.storage.case['inference_history'][-1]['preview_binding']['plan_sha256'] == plan['plan_sha256']
        assert rig.storage.case['lesion']['state'] == 'AI_SUGGESTION'
        assert fixed.submit(rig, plan).status_code == 409
    finally:
        fixture.close()
        for exchange in exchanges: exchange.close()
