import hashlib

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from dr_support.api import create_app
from dr_support.images import admitted_demo_images


def _write_image(path, color):
    image = Image.new('RGB', (32, 24), color)
    image.save(path, format='JPEG')


def test_demo_admission_is_hashed_and_deduplicated(tmp_path):
    first = tmp_path / 'IMG_01.jpg'
    second = tmp_path / 'IMG_02.jpg'
    third = tmp_path / 'IMG_03.jpg'
    _write_image(first, 'red')
    second.write_bytes(first.read_bytes())
    _write_image(third, 'blue')
    before = first.read_bytes()

    registry = admitted_demo_images(tmp_path)

    assert list(registry) == [hashlib.sha256(before).hexdigest(), hashlib.sha256(third.read_bytes()).hexdigest()]
    assert registry[list(registry)[0]].filename == 'IMG_01.jpg'
    assert first.read_bytes() == before


def test_demo_admission_rejects_invalid_supported_file(tmp_path):
    (tmp_path / 'IMG_01.jpg').write_bytes(b'not an image')
    with pytest.raises(RuntimeError, match='valid image'):
        admitted_demo_images(tmp_path)


def test_demo_folder_cases_are_stable_across_app_restarts(tmp_path, monkeypatch):
    for name, color in [('IMG_01.jpg', 'red'), ('IMG_02.jpg', 'green'), ('IMG_03.jpg', 'blue')]:
        _write_image(tmp_path / name, color)
    monkeypatch.setenv('DR_DEMO_FOLDER', str(tmp_path))
    first_client = TestClient(create_app(tmp_path / 'state.sqlite'))
    first_cases = first_client.get('/v1/cases').json()
    second_client = TestClient(create_app(tmp_path / 'state.sqlite'))
    second_cases = second_client.get('/v1/cases').json()

    assert [case['display_name'] for case in first_cases] == ['IMG_01', 'IMG_02', 'IMG_03']
    assert [case['image_id'] for case in first_cases] == [case['image_id'] for case in second_cases]
    assert len(second_cases) == 3


def test_models_remains_json_when_remote_is_offline(monkeypatch):
    monkeypatch.delenv('DR_DEMO_FOLDER', raising=False)
    monkeypatch.setenv('REMOTE_MODEL_URL', 'http://127.0.0.1:9')
    monkeypatch.setenv('MODEL_RUNTIME', 'remote')
    client = TestClient(create_app())
    response = client.get('/v1/models')
    assert response.status_code == 200
    assert isinstance(response.json(), list)
