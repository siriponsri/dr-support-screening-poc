"""Auth envelope for a future private gateway; no proxy/listener/credential creation.

Wrap the WHOLE ASGI app, including health/discovery/docs and unknown paths. Supply
an existing private token, never a hardcoded default. No downstream handler or
request body is accessed before authentication. Deployment is not wired here.
"""
from secrets import compare_digest


class PrivateGatewayAuth:
    def __init__(self, app, token: str):
        if (not isinstance(token, str) or not 32 <= len(token) <= 1024
                or not token.isascii() or any(ord(character) < 33 or ord(character) > 126 for character in token)):
            raise ValueError("PRIVATE_TOKEN_CONFIGURATION_REQUIRED")
        self._app = app
        self._expected = b"Bearer " + token.encode("ascii")

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self._app(scope, receive, send)
            return
        if scope["type"] != "http":
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            return
        authorization = [value for key, value in scope.get("headers", []) if key.lower() == b"authorization"]
        if len(authorization) != 1 or len(authorization[0]) > 2048 or not compare_digest(authorization[0], self._expected):
            body = b'{"detail":"Unauthorized"}'
            await send({"type": "http.response.start", "status": 401, "headers": [
                (b"content-type", b"application/json"), (b"www-authenticate", b"Bearer"),
                (b"cache-control", b"no-store")]})
            await send({"type": "http.response.body", "body": body})
            return
        await self._app(scope, receive, send)
