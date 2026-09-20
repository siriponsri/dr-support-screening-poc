from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_start_cmd_is_the_single_owner_launcher():
    launcher = (ROOT / 'START.cmd').read_text(encoding='utf-8')

    assert 'set "APP_PROFILE=review"' in launcher
    assert 'set "MODEL_RUNTIME=remote"' in launcher
    assert 'Open http://127.0.0.1:8000/app/' in launcher
    assert 'DR_DEMO_FOLDER' not in launcher
    assert 'IMG_01.jpg' not in launcher
    assert 'IMG_02.jpg' not in launcher
    assert 'IMG_03.jpg' not in launcher
    assert not (ROOT / 'START_DEMO.cmd').exists()
