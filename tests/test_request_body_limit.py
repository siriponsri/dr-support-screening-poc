"""Request bodies over the limit are refused before any route reads them (AC-12)."""
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from dr_support.api.body_limit import TOO_LARGE_DETAIL, BodyLimitMiddleware


def small_app(limit=100):
    app = FastAPI()
    app.add_middleware(BodyLimitMiddleware, max_bytes=limit)
    seen = []

    @app.post('/echo')
    async def echo(request: Request):
        body = await request.body()
        seen.append(len(body))
        return {'size': len(body)}

    return TestClient(app), seen


def test_body_within_the_limit_passes():
    client, seen = small_app()
    assert client.post('/echo', content=b'x' * 100).json() == {'size': 100}
    assert seen == [100]


def test_declared_oversize_body_is_refused_before_the_route():
    client, seen = small_app()
    response = client.post('/echo', content=b'x' * 101)
    assert response.status_code == 413
    assert response.json() == {'detail': TOO_LARGE_DETAIL}
    assert seen == []


def test_streamed_body_without_length_is_refused_when_it_grows_too_large():
    client, seen = small_app()

    def chunks():
        for _ in range(5):
            yield b'x' * 40

    response = client.post('/echo', content=chunks())
    assert response.status_code == 413
    assert seen == []


def test_review_app_installs_the_limit(tmp_path, monkeypatch):
    from dr_support.api import create_app
    monkeypatch.setenv('DR_SUPPORT_STATE', str(tmp_path / 'state.sqlite'))
    monkeypatch.setenv('DR_SUPPORT_WORKSPACE_CATALOG', str(tmp_path / 'catalog.sqlite'))
    client = TestClient(create_app(include_samples=False))
    response = client.post('/v1/admissions/scan', content=b'x' * (8 * 1024 * 1024 + 1),
                           headers={'content-type': 'application/json'})
    assert response.status_code == 413
