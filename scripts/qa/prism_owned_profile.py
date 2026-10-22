"""Explicit assembly only; live CLI/profile registration remains hard-disabled.

No env or HTTP flag activates these constructors. Existing gateway host/port,
private token and Linux ownership adapters must be explicitly injected after
review/authorization. Import does not read credentials, spawn, bind or load.
"""
from dr_support.services.prism_owned_runtime import (
    LoadedPrismExecutor, OwnedRuntimeSession, OwnedWorkerChannel,
    child_application, owned_gateway_application, register_fixed_owned_runtime,
)
from dr_support.providers.prism_owned_channel import OwnedFixedSessionRemoteProvider, PrivateGatewayChannel


def injected_worker(provider, *, token, expected_pins, epoch, issue_id, **executor_options):
    executor = LoadedPrismExecutor(provider, expected_pins=expected_pins, **executor_options)
    app, host = child_application(executor, token=token, epoch=epoch, issue_id=issue_id)
    return app, host, executor


def injected_server_gateway(controller, *, token, exchange, listener_owned):
    session = OwnedRuntimeSession(controller)
    channel = OwnedWorkerChannel(controller, exchange=exchange, listener_owned=listener_owned)
    app = owned_gateway_application(channel, token=token)
    return session, channel, app


def injected_windows_provider(exchange, *, expected_pins, expected_epoch, on_phase=None, **provider_options):
    observe = on_phase if callable(on_phase) else lambda phase: None
    channel = PrivateGatewayChannel(exchange, expected_pins=expected_pins, expected_epoch=expected_epoch)
    observe("GATEWAY_LOADED_ASSERTION")
    channel.establish()  # Authenticated load/pin proof BEFORE any synthetic input.
    provider = OwnedFixedSessionRemoteProvider(channel, **provider_options)
    observe("CAPABILITIES_NEGOTIATION")
    provider.negotiate()
    if provider.capabilities['epoch'] != expected_epoch or provider.capabilities['pins'] != expected_pins:
        channel.quarantined = True
        raise RuntimeError('OWNED_GATEWAY_CAPABILITY_IDENTITY_CHANGED')
    return provider


def worker_factory():
    # Proposed uvicorn --factory target, deliberately refuses live startup now.
    register_fixed_owned_runtime()


if __name__ == '__main__':
    register_fixed_owned_runtime()
