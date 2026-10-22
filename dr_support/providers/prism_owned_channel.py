"""Unregistered fixed-session transport; reuse existing injected backend token."""
import json
import re
import time

import httpx

from dr_support.services.prism_owned_runtime import MAX_BODY, OwnedWorkerChannel
from dr_support.services.prism_remote_transport import BASE, TransportError
from dr_support.providers.prism_remote_bound import FixedSessionRemoteProvider, RemoteBoundTransportCandidate


class DeadlineHttpExchange:
    """One attempt, fixed private loopback, bounded bytes, absolute checks.

    A blocking read shares the remaining absolute RPC budget; scheduler/OS
    behavior still needs host qualification. No credential discovery or logging.
    The separate parent watchdog bounds worker load/forward even if RPC stalls.
    """
    def __init__(self, *, token, transport, clock=time.monotonic, port=7862):
        if (not isinstance(token, str) or not 32 <= len(token) <= 1024 or not token.isascii()
                or any(ord(c) < 33 or ord(c) > 126 for c in token)):
            raise ValueError('EXISTING_PRIVATE_BACKEND_TOKEN_REQUIRED')
        if type(transport) not in (httpx.HTTPTransport, httpx.MockTransport):
            raise ValueError('EXPLICIT_NO_RETRY_HTTP_TRANSPORT_REQUIRED')
        if type(transport) is httpx.HTTPTransport and getattr(transport._pool, '_retries', None) != 0:
            raise ValueError('HTTP_RETRIES_MUST_BE_ZERO')
        # Production caller must use HTTPTransport(retries=0). No default socket
        # transport is silently constructed by importing/instantiating this port.
        if port not in {7862, 17860}:
            raise ValueError('FIXED_PRIVATE_LOOPBACK_PORT_REQUIRED')
        self.port = port
        self.client = httpx.Client(base_url='http://127.0.0.1:'+str(port), transport=transport,
            headers={'Authorization': 'Bearer '+token}, follow_redirects=False, trust_env=False)
        self.clock = clock

    def __call__(self, method, path, value=None, *, epoch=None, authority=False, deadline):
        operation = ('READINESS' if path == BASE+'/readiness' else
                     'CAPABILITIES' if path == BASE+'/capabilities' else
                     'PREPARE' if path == BASE+'/prepare' else
                     'EXECUTE' if path == BASE+'/execute' else
                     'GRANT' if path.endswith('/grant') else
                     'CANCEL' if path.endswith('/cancel') else 'STATUS')
        try:
            return self._typed_request(method, path, value, epoch=epoch, authority=authority, deadline=deadline)
        except TransportError as error:
            error.control_operation = operation
            raise

    def _typed_request(self, method, path, value=None, *, epoch=None, authority=False, deadline):
        try:
            return self._request_once(method, path, value, epoch=epoch,
                                      authority=authority, deadline=deadline)
        except httpx.ReadTimeout:
            raise TransportError('CONTROL_RPC_READ_TIMEOUT', 504) from None
        except httpx.ConnectTimeout:
            raise TransportError('CONTROL_RPC_CONNECT_TIMEOUT', 504) from None
        except httpx.TimeoutException:
            raise TransportError('CONTROL_RPC_OTHER_TIMEOUT', 504) from None
        except httpx.ProtocolError:
            raise TransportError('CONTROL_RPC_PROTOCOL_ERROR', 502) from None
        except httpx.NetworkError:
            raise TransportError('CONTROL_RPC_NETWORK_ERROR', 502) from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise TransportError('CONTROL_RPC_INVALID_JSON', 502) from None

    def _request_once(self, method, path, value=None, *, epoch=None, authority=False, deadline):
        if method not in {'GET', 'POST'} or not re.fullmatch(re.escape(BASE)+
            r'/(capabilities|readiness|prepare|execute|jobs/[A-Za-z0-9_-]{8,80}(/(grant|cancel))?)', path):
            raise TransportError('FIXED_PRIVATE_ROUTE_REQUIRED', 422)
        remaining = deadline-self.clock()
        if remaining <= 0:
            raise TransportError('ABSOLUTE_RPC_DEADLINE', 408)
        headers = {'X-Prism-Epoch': epoch} if epoch else {}
        with self.client.stream(method, path, json=value, headers=headers,
            timeout=httpx.Timeout(min(remaining, 1), read=remaining)) as response:
            data = bytearray()
            for chunk in response.iter_bytes():
                if self.clock() >= deadline:
                    raise TransportError('ABSOLUTE_RPC_DEADLINE', 408)
                data.extend(chunk)
                if len(data) > MAX_BODY:
                    raise TransportError('RESPONSE_LIMIT', 502)
            if self.clock() >= deadline:
                raise TransportError('ABSOLUTE_RPC_DEADLINE', 408)
            result = json.loads(data)
            if not isinstance(result, dict):
                raise TransportError('CONTROL_RPC_BODY_TYPE', 502)
            if response.status_code not in {200, 202}:
                error = TransportError(result.get('error', 'OWNED_RPC_REJECTED'), response.status_code)
                kind = result.get('error_class')
                error.remote_error_class = kind if type(kind) is str and kind in {'RuntimeError','ValueError','TypeError','KeyError','OSError','PermissionError','FileNotFoundError','JSONDecodeError','TimeoutExpired','OTHER'} else None
                error.http_status = response.status_code
                raise error
            return result

    def close(self):
        self.client.close()


class OwnedFixedSessionRemoteProvider(FixedSessionRemoteProvider):
    """Explicit injection subtype accepted by da164ac; registration stays OFF.

    The original MockTransport-only class is untouched. Only the owned-channel
    subtype can take this reviewed future path; no env/HTTP switch activates it.
    """
    def __init__(self, channel, **kwargs):
        if not isinstance(channel, (OwnedWorkerChannel, PrivateGatewayChannel)):
            raise TransportError('OWNED_WORKER_CHANNEL_REQUIRED', 503)
        RemoteBoundTransportCandidate.__init__(self, channel, **kwargs)


class PrivateGatewayChannel:
    """Windows app -> existing loopback17860 SSH -> QA owned gateway.

    Linux child ownership stays on QA, never faked by a Windows PID. Before any
    image preparation, require the authenticated loaded worker epoch/pins.
    """
    def __init__(self, exchange, *, expected_epoch, expected_pins):
        if not isinstance(exchange, DeadlineHttpExchange) or exchange.port != 17860:
            raise TransportError('PRIVATE_QA_GATEWAY_CHANNEL_REQUIRED', 503)
        self.exchange, self.epoch, self.pins = exchange, expected_epoch, expected_pins
        self.ready = self.quarantined = False

    def establish(self):
        if self.ready or self.quarantined:
            raise TransportError('GATEWAY_ESTABLISH_ONCE_NO_RETRY')
        try:
            status = self.exchange('GET', BASE+'/readiness', deadline=self.exchange.clock()+5)
            from dr_support.services.loaded_attestation import require_loaded_identity
            require_loaded_identity(status, expected_pins=self.pins, expected_epoch=self.epoch)
            self.ready = True
        except BaseException:
            self.quarantined = True
            raise

    def request(self, method, path, value=None, *, epoch=None, authority=False):
        if not self.ready or self.quarantined or epoch is not None and epoch != self.epoch:
            raise TransportError('PRIVATE_GATEWAY_NOT_READY_OR_QUARANTINED', 503)
        try:
            return self.exchange(method, path, value, epoch=epoch, authority=authority,
                                 deadline=self.exchange.clock()+5)
        except BaseException:
            self.quarantined = True
            raise
