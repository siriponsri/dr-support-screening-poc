"""Bounded request bodies for the review API (GOAL AC-12 / OP-05).

The review API takes no file uploads; its largest bodies are annotation sets.
Bodies over the limit are refused with 413 before a route reads them, whether
the size is declared in Content-Length or only discovered while streaming.
"""

from __future__ import annotations

import json

MAX_REQUEST_BODY_BYTES = 8 * 1024 * 1024
TOO_LARGE_DETAIL = 'The request is too large. Nothing was saved.'


class _BodyTooLarge(Exception):
    pass


class BodyLimitMiddleware:
    def __init__(self, app, max_bytes: int = MAX_REQUEST_BODY_BYTES):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        declared = dict(scope.get('headers') or []).get(b'content-length')
        if declared is not None:
            try:
                too_large = int(declared) > self.max_bytes
            except ValueError:
                too_large = True
            if too_large:
                await _reject(send)
                return

        received = 0
        started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message['type'] == 'http.request':
                received += len(message.get('body', b''))
                if received > self.max_bytes:
                    raise _BodyTooLarge()
            return message

        async def tracked_send(message):
            nonlocal started
            if message['type'] == 'http.response.start':
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _BodyTooLarge:
            if not started:
                await _reject(send)


async def _reject(send) -> None:
    body = json.dumps({'detail': TOO_LARGE_DETAIL}).encode()
    await send({'type': 'http.response.start', 'status': 413,
                'headers': [(b'content-type', b'application/json'), (b'content-length', str(len(body)).encode())]})
    await send({'type': 'http.response.body', 'body': body})
