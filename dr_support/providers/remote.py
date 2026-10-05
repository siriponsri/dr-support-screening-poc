"""Provider-neutral REMOTE inference adapter.

The backend exposes a single ``Bridge`` API regardless of where inference runs. When
``MODEL_RUNTIME=remote`` this module replaces the local RETFound/PRISM adapters with
HTTP proxies to a separately deployed Remote Model API. Tokens are read from the
environment only and are never persisted, logged, or surfaced in responses.

Wire format (POST /v1/predict/dr and POST /v1/predict/lesions)::

    {
        "image_id": "<id>",
        "modality": "CFP" | "UWF",
        "model_id": "retfound-aptos5" | "prism-dr-5fold",
        "image_b64": "<base64 of exact analysis payload bytes>",
        "image_sha256": "<hex>",
        "source_type": "PUBLIC" | "SYNTHETIC",
        "width":  <px>,
        "height": <px>
    }

The remote response MUST conform to the local Bridge v1 contract
(``GlobalResult`` / ``LesionResult``). The proxy validates the response with the
same Pydantic models used for local inference; no field coercion is performed.
"""
import base64
import os
import time
from typing import Any
import httpx
from dr_support.contracts import GlobalResult, LesionResult


class RemoteModelError(RuntimeError):
    """Base class for Remote Model API failures."""


class RemoteTimeoutError(RemoteModelError):
    """Remote model exceeded the configured timeout."""


class RemoteHTTPError(RemoteModelError):
    """Remote model returned a non-success HTTP status."""


class RemoteSchemaError(RemoteModelError):
    """Remote model response could not be parsed as a Bridge v1 result."""


class RemoteNotConfiguredError(RemoteModelError):
    """The review workstation has no remote model endpoint configured."""


INFERENCE_TIMEOUT_SECONDS = 30.0
METADATA_TIMEOUT_SECONDS = 5.0


def _redact_token(value: str | None) -> str:
    """Defensive helper: never echo tokens into metadata or logs."""
    return '' if not value else '***REDACTED***'


class RemoteModelProvider:
    """HTTP proxy adapter that conforms to the local provider protocol.

    Implements ``task``, ``model_id``, ``metadata()`` and ``infer(request, image)``
    so the existing ``dr_support.api.infer`` dispatcher can use it without
    modification. All HTTP errors are translated into ``RemoteModelError`` subclasses.
    """

    predict_path: str = '/v1/predict/dr'
    METADATA_PATH: str = '/v1/models'
    result_model: type[GlobalResult | LesionResult] = GlobalResult

    def __init__(self, model_id: str, task: str, base_url: str | None = None,
                 token: str | None = None, transport: httpx.BaseTransport | None = None,
                 timeout: float = INFERENCE_TIMEOUT_SECONDS):
        self.model_id = model_id
        self.task = task
        base = (base_url if base_url is not None else os.environ.get('REMOTE_MODEL_URL', '')).strip()
        if base and not base.startswith(('http://', 'https://')):
            raise ValueError('REMOTE_MODEL_URL must use http(s) scheme')
        self.base_url = base.rstrip('/')
        # Resolve token lazily from env so a missing token only fails on first call.
        self._env_token_name = 'REMOTE_MODEL_TOKEN'
        self._explicit_token = token
        self._transport = transport
        self._client_timeout = float(timeout)
        self.last_inference_ms: float | None = None
        self.last_metadata_ms: float | None = None
        self.last_error: str | None = None
        self.last_remote_revision: str | None = None
        self.last_remote_checkpoint_sha256: dict[str, str] | None = None

    def _token(self) -> str | None:
        if self._explicit_token:
            return self._explicit_token
        return os.environ.get(self._env_token_name) or None

    def _headers(self) -> dict[str, str]:
        headers = {'Accept': 'application/json'}
        token = self._token()
        if token:
            # Bearer scheme only; token is never logged or persisted.
            headers['Authorization'] = f'Bearer {token}'
        return headers

    def _client(self, timeout: float) -> httpx.Client:
        kwargs = {'timeout': httpx.Timeout(timeout), 'follow_redirects': False}
        if self._transport is not None:
            kwargs['transport'] = self._transport
        return httpx.Client(**kwargs)

    def _payload(self, request, image) -> dict[str, Any]:
        return {
            'image_id': request.image_id,
            'modality': request.modality,
            'model_id': request.model_id,
            'image_b64': base64.b64encode(image.data).decode('ascii'),
            'image_sha256': image.sha256,
            'source_type': image.source_type,
            'width': image.size[0],
            'height': image.size[1],
        }

    def _send(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = self.base_url + path
        headers = self._headers()
        start = time.perf_counter()
        try:
            with self._client(kwargs.pop('timeout', self._client_timeout)) as client:
                response = client.request(method, url, headers=headers, **kwargs)
        except httpx.TimeoutException as exc:
            self.last_error = f'timeout after {self._client_timeout:.0f}s'
            raise RemoteTimeoutError(f'Remote model timeout: {exc}') from None
        except httpx.HTTPError as exc:
            self.last_error = f'transport error: {type(exc).__name__}'
            raise RemoteModelError(f'Remote model transport error: {exc}') from None
        except Exception as exc:  # pragma: no cover - defensive guard
            # Any non-httpx exception (DNS resolution failures, SSL errors that
            # escape httpx, etc.) must be translated to ``RemoteModelError`` so
            # the metadata() caller never crashes the local /v1/models handler.
            self.last_error = f'unexpected: {type(exc).__name__}'
            raise RemoteModelError(f'Remote model unexpected error: {exc}') from None
        elapsed_ms = (time.perf_counter() - start) * 1000
        if path == self.METADATA_PATH or path.endswith('/health'):
            self.last_metadata_ms = elapsed_ms
        return response

    def infer(self, request, image):
        if not self.base_url:
            self.last_error = 'remote endpoint not configured'
            raise RemoteNotConfiguredError('Remote model endpoint is not configured')
        start = time.perf_counter()
        payload = self._payload(request, image)
        try:
            response = self._send('POST', self.predict_path, json=payload,
                                  timeout=self._client_timeout)
        except RemoteModelError:
            raise
        except Exception as exc:  # pragma: no cover - defensive guard
            self.last_error = f'unexpected: {type(exc).__name__}'
            raise RemoteModelError(f'Remote model unexpected failure: {exc}') from None

        self.last_inference_ms = (time.perf_counter() - start) * 1000

        if response.status_code != 200:
            self.last_error = f'HTTP {response.status_code}'
            raise RemoteHTTPError(f'Remote model HTTP {response.status_code}; response rejected')
        try:
            body = response.json()
        except ValueError as exc:
            self.last_error = 'invalid JSON'
            raise RemoteSchemaError(f'Remote model returned non-JSON response: {exc}') from None
        try:
            result = self.result_model.model_validate(body)
        except Exception as exc:
            self.last_error = 'schema mismatch'
            raise RemoteSchemaError(f'Remote model returned malformed response: {exc}') from None
        if result.provenance.image_sha256 != payload['image_sha256']:
            self.last_error = 'image hash mismatch'
            raise RemoteSchemaError('Remote model returned a result for different image bytes')
        # Record provenance surfaced by the remote for the metadata endpoint.
        prov = getattr(result, 'provenance', None)
        if prov is not None:
            self.last_remote_revision = getattr(prov, 'source_revision', None) or None
            self.last_remote_checkpoint_sha256 = dict(getattr(prov, 'checkpoint_sha256', {}) or {}) or None
        self.last_error = None
        return result

    def _runtime_warnings(self) -> list[str]:
        warnings = ([
            'REMOTE_RUNTIME: model served by REMOTE_MODEL_URL'
        ] if self.base_url else [
            'REMOTE_RUNTIME: remote model endpoint is not configured'
        ])
        if self.last_inference_ms is not None:
            warnings.append(f'Last inference latency: {self.last_inference_ms:.0f}ms')
        if self.last_metadata_ms is not None:
            warnings.append(f'Last metadata fetch: {self.last_metadata_ms:.0f}ms')
        if self.last_error:
            warnings.append(f'Last error: {self.last_error}')
        return warnings

    def metadata(self) -> dict[str, Any]:
        """Return Models & Audit metadata, including remote revision/hash/latency.

        The local review ``/v1/models`` endpoint must never crash because of a
        remote metadata failure. Every failure mode below produces an explicit
        degraded descriptor with HTTP 200 so the UI can still render the
        Worklist and Models & Audit page.
        """
        if not self.base_url:
            return self._degraded_metadata(
                'REMOTE_NOT_CONFIGURED',
                'REMOTE_MODEL_URL is not configured; AI analysis is not available.',
            )
        try:
            return self._collect_metadata()
        except Exception as exc:  # pragma: no cover - defensive guard
            # Any exception that escapes the structured degradation paths
            # (e.g. unexpected response shape, missing dict key, programming
            # bug) must still surface as a degraded descriptor. Crashing here
            # would propagate to the local /v1/models handler and turn into a
            # HTTP 500 — exactly the symptom that blocked the Worklist UI.
            self.last_error = f'unexpected: {type(exc).__name__}'
            return self._degraded_metadata('REMOTE_INVALID_SCHEMA',
                                           f'Unexpected remote metadata error: {exc}')

    def readiness_probe(self):
        """Verify current remote health and capability discovery before inference."""

        from dr_support.services.model_gateway import probe_model_connection

        return probe_model_connection(
            self.base_url,
            self._token(),
            transport=self._transport,
        )

    def _collect_metadata(self) -> dict[str, Any]:
        """Inner metadata collection; every branch returns a degraded dict."""
        try:
            response = self._send('GET', self.METADATA_PATH, timeout=METADATA_TIMEOUT_SECONDS)
        except (RemoteTimeoutError, RemoteModelError) as exc:
            return self._degraded_metadata('REMOTE_UNREACHABLE', str(exc))

        if response.status_code == 401 or response.status_code == 403:
            self.last_error = f'HTTP {response.status_code}'
            return self._degraded_metadata('REMOTE_AUTH_FAILED', 'Remote rejected the supplied token')
        if response.status_code != 200:
            self.last_error = f'HTTP {response.status_code}'
            return self._degraded_metadata(f'REMOTE_HTTP_{response.status_code}',
                                          f'GET {self.METADATA_PATH} returned HTTP {response.status_code}')

        try:
            body = response.json()
        except ValueError:
            return self._degraded_metadata('REMOTE_INVALID_JSON',
                                          f'GET {self.METADATA_PATH} returned non-JSON body')
        if not isinstance(body, list):
            return self._degraded_metadata('REMOTE_INVALID_SCHEMA',
                                          f'GET {self.METADATA_PATH} must be a JSON array')

        match = next((m for m in body if isinstance(m, dict) and m.get('model_id') == self.model_id), None)
        if match is None:
            return self._degraded_metadata('REMOTE_MODEL_NOT_LISTED',
                                            f'{self.model_id} not present in remote {self.METADATA_PATH} response')

        # Prefer the freshest provenance values from the most recent inference, but fall back
        # to whatever the /v1/models list advertises.
        revision = self.last_remote_revision or match.get('revision') or match.get('model_version')
        checkpoint = (self.last_remote_checkpoint_sha256
                      if self.last_remote_checkpoint_sha256 is not None
                      else match.get('checkpoint_sha256'))
        advertised_task = match.get('task')
        advertised_modalities = match.get('modalities')
        if not isinstance(advertised_task, str) or not advertised_task.strip():
            return self._degraded_metadata(
                'REMOTE_INVALID_CAPABILITY',
                f'{self.model_id} did not advertise a task',
            )
        if advertised_task != self.task:
            return self._degraded_metadata(
                'REMOTE_INVALID_CAPABILITY',
                f'{self.model_id} advertised task {advertised_task!r}, expected {self.task!r}',
            )
        if (
            not isinstance(advertised_modalities, list)
            or not advertised_modalities
            or any(not isinstance(modality, str) or not modality.strip() for modality in advertised_modalities)
        ):
            return self._degraded_metadata(
                'REMOTE_INVALID_CAPABILITY',
                f'{self.model_id} did not advertise supported modalities',
            )
        remote_status = match.get('status')
        status = remote_status.strip() if isinstance(remote_status, str) and remote_status.strip() else 'REMOTE_DEGRADED'
        remote_warnings = list(match.get('warnings') or [])
        preprocessing = match.get('preprocessing') or match.get('preprocessing_version')
        metadata = {
            'model_id': self.model_id,
            'task': advertised_task,
            'runtime': 'remote',
            'remote_url': self.base_url,
            'revision': revision,
            'checkpoint_sha256': checkpoint or {},
            'remote_status': remote_status,
            'status': status,
            'modalities': advertised_modalities,
            'warnings': remote_warnings + self._runtime_warnings(),
            'preprocessing': preprocessing,
            'preprocessing_version': preprocessing,
            'capability_id': match.get('capability_id'),
            'domain_status': match.get('domain_status'),
            'release_status': match.get('release_status'),
            'explanation_types': match.get('explanation_types') or [],
        }
        if 'ready' in match:
            metadata['ready'] = match['ready']
        return metadata

    def _degraded_metadata(self, status: str, detail: str | None = None) -> dict[str, Any]:
        warnings = [f'Remote runtime degraded: {status}']
        if detail:
            warnings.append(detail)
        warnings.extend(self._runtime_warnings())
        if self.base_url:
            warnings.append('REMOTE_MODEL_TOKEN must be set in the backend environment when required by the remote')
        return {
            'model_id': self.model_id,
            'task': self.task,
            'runtime': 'remote',
            'remote_url': self.base_url,
            'status': status,
            'modalities': [],
            'warnings': warnings,
        }


class RemoteGlobalProvider(RemoteModelProvider):
    task = 'global'
    model_id = 'retfound-aptos5'
    predict_path = '/v1/predict/dr'
    result_model = GlobalResult

    def __init__(self, base_url: str | None = None, token: str | None = None,
                 transport: httpx.BaseTransport | None = None, timeout: float = INFERENCE_TIMEOUT_SECONDS):
        super().__init__(model_id=self.model_id, task=self.task, base_url=base_url,
                         token=token, transport=transport, timeout=timeout)


class RemoteLesionProvider(RemoteModelProvider):
    task = 'lesion-roi'
    model_id = 'prism-dr-5fold'
    predict_path = '/v1/predict/lesions'
    result_model = LesionResult

    def __init__(self, base_url: str | None = None, token: str | None = None,
                 transport: httpx.BaseTransport | None = None, timeout: float = INFERENCE_TIMEOUT_SECONDS):
        super().__init__(model_id=self.model_id, task=self.task, base_url=base_url,
                         token=token, transport=transport, timeout=timeout)


def provider_from_descriptor(
    descriptor: dict[str, Any],
    *,
    base_url: str,
    token: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> RemoteModelProvider:
    """Build a provider from an advertised capability without hard-coding it.

    Legacy IDs retain their specialized classes.  New descriptors use the
    generic Bridge-compatible provider and inherit the task-specific route and
    response contract from capability discovery.
    """

    model_id = str(descriptor.get('model_id') or '').strip()
    task = str(descriptor.get('task') or '').strip()
    if model_id == RemoteGlobalProvider.model_id:
        if task != RemoteGlobalProvider.task:
            raise ValueError(f'Advertised task does not match {model_id!r}')
        return RemoteGlobalProvider(base_url=base_url, token=token, transport=transport)
    if model_id == RemoteLesionProvider.model_id:
        if task != RemoteLesionProvider.task:
            raise ValueError(f'Advertised task does not match {model_id!r}')
        return RemoteLesionProvider(base_url=base_url, token=token, transport=transport)
    if task not in {'global', 'lesion-roi'}:
        raise ValueError(f'Unsupported remote capability task for {model_id!r}')
    provider = RemoteModelProvider(
        model_id=model_id,
        task=task,
        base_url=base_url,
        token=token,
        transport=transport,
    )
    provider.predict_path = '/v1/predict/lesions' if task == 'lesion-roi' else '/v1/predict/dr'
    provider.result_model = LesionResult if task == 'lesion-roi' else GlobalResult
    return provider
