"""Selection/opt-in regressions: synthetic values only, no credentials/network."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.qa import m1_server_app as launcher


@pytest.fixture
def no_actions(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Diagnostic/refused serve attempted a side effect')

    for name in ('runtime_values', 'authority_database', 'private_values', 'roots', 'host_token',
                 'ssh', 'owned_tunnel', 'compose', 'create_workspace', 'port_free', 'session_environment'):
        monkeypatch.setattr(launcher, name, forbidden)
    monkeypatch.setattr(launcher.subprocess, 'run', forbidden)
    monkeypatch.setattr(launcher.subprocess, 'Popen', forbidden)
    monkeypatch.setattr(launcher.socket, 'socket', forbidden)
    for name in ('read_bytes', 'read_text', 'open', 'mkdir', 'write_bytes', 'write_text'):
        monkeypatch.setattr(Path, name, forbidden)


@pytest.mark.parametrize('opt_in', [False, True])
def test_diagnostic_redacts_ignored_config_and_has_no_side_effects(monkeypatch, capsys, no_actions, opt_in):
    secret = 'SYNTHETIC_SECRET_MUST_NEVER_APPEAR'
    monkeypatch.setenv('REMOTE_MODEL_TOKEN', secret)
    monkeypatch.setenv('REMOTE_MODEL_URL', 'https://private-user:' + secret + '@ignored.invalid/path?q=' + secret)
    monkeypatch.setenv('DR_SUPPORT_DATABASE_URL', 'postgresql://user:' + secret + '@ignored.invalid/private')
    before = dict(os.environ)
    args = ['diagnose', '--model-port', '48123']
    if opt_in:
        args.append('--allow-remote-token-read')
    assert launcher.main(args) == 0
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert not output.err and secret not in output.out
    assert 'ignored.invalid' not in output.out and 'postgresql' not in output.out
    assert not any('sha' in key or 'hash' in key for key in report)
    assert report['python_executable'] == launcher.sys.executable
    assert report['cwd'] == str(Path.cwd())
    assert report['deployment_profile'] == 'QA_SERVER'
    assert report['app_profile'] == 'review' and report['model_runtime'] == 'remote'
    assert report['endpoint'] == {'scheme': 'http', 'host': '127.0.0.1', 'port': 48123}
    assert report['tunnel_target'] == {'host': launcher.HOST, 'loopback_host': '127.0.0.1', 'port': 7860}
    assert report['token'] == {
        'source_name': 'dr-train-existing-model-api-file', 'source_path': launcher.HOST_TOKEN_PATH,
        'source_selected': True, 'source_presence': 'NOT_CHECKED', 'value_loaded': False,
        'authentication': 'NOT_CHECKED', 'transfer_opt_in': opt_in,
    }
    assert report['database_configuration'] == 'NOT_READ'
    assert report['repository_dotenv_selected'] is False
    assert report['inherited_remote_model_settings_selected'] is False
    assert dict(os.environ) == before


@pytest.mark.parametrize('args', [['serve'], ['serve', '--model-port', '48123']])
def test_serve_refuses_default_before_any_action(args, capsys, no_actions):
    assert launcher.main(args) == 2
    output = capsys.readouterr()
    assert not output.out
    assert json.loads(output.err) == {
        'status': 'REFUSED', 'code': 'REMOTE_TOKEN_READ_REQUIRES_EXPLICIT_OPT_IN',
    }


@pytest.mark.parametrize('allowed', [False, None, 1, 'true'])
def test_direct_token_reader_requires_boolean_opt_in_before_ssh(monkeypatch, allowed):
    monkeypatch.setattr(launcher, 'ssh', lambda *args, **kwargs: pytest.fail('Unapproved SSH'))
    with pytest.raises(launcher.SessionError, match='REMOTE_TOKEN_READ_REQUIRES_EXPLICIT_OPT_IN'):
        launcher.host_token(allow_remote_token_read=allowed)


def test_token_reader_default_refuses_before_ssh(monkeypatch):
    monkeypatch.setattr(launcher, 'ssh', lambda *args, **kwargs: pytest.fail('Unapproved SSH'))
    with pytest.raises(launcher.SessionError, match='REMOTE_TOKEN_READ_REQUIRES_EXPLICIT_OPT_IN'):
        launcher.host_token()


def test_explicit_opt_in_reaches_only_the_selected_reader_with_fake_ssh(monkeypatch, capsys):
    calls = []
    synthetic = b'SYNTHETIC_FOR_UNIT_TEST_ONLY_1234567890'

    def fake_ssh(command):
        calls.append(command)
        return synthetic

    monkeypatch.setattr(launcher, 'ssh', fake_ssh)
    assert launcher.host_token(allow_remote_token_read=True) == synthetic.decode()
    assert len(calls) == 1 and launcher.HOST_TOKEN_PATH in calls[0]
    assert launcher.HOST_TOKEN_READER_PATH in calls[0]
    output = capsys.readouterr()
    assert not output.out and not output.err


def test_actual_environment_uses_the_same_selection_and_restores_inherited_values(monkeypatch):
    monkeypatch.setattr(launcher, 'runtime_values', lambda: {})
    monkeypatch.setattr(launcher, 'roots', lambda: {'UWF': 'synthetic-uwf', 'CFP': 'synthetic-cfp'})
    monkeypatch.setenv('REMOTE_MODEL_URL', 'https://ignored.invalid')
    monkeypatch.setenv('REMOTE_MODEL_TOKEN', 'SYNTHETIC_OLD_TOKEN')
    before = dict(os.environ)
    with launcher.session_environment(model_port=48123, token='SYNTHETIC_SELECTED_TOKEN'):
        for key, value in launcher.model_configuration(48123).items():
            assert os.environ[key] == value
        assert os.environ['REMOTE_MODEL_TOKEN'] == 'SYNTHETIC_SELECTED_TOKEN'
        assert os.environ['MODEL_RUNTIME'] == 'remote'
    assert dict(os.environ) == before


@pytest.mark.parametrize('port', [True, 1024, 65536, '47860'])
def test_invalid_selected_port_is_refused_without_echo_or_action(port, capsys):
    with pytest.raises(launcher.SessionError, match='VALID_LOCAL_MODEL_PORT_REQUIRED'):
        launcher.diagnose(SimpleNamespace(model_port=port))
    assert not capsys.readouterr().out


def test_prepare_never_loads_a_token_or_model_connection(monkeypatch):
    import uvicorn
    import dr_support.api._factory as factory

    calls = []
    monkeypatch.setattr(launcher, 'port_free', lambda port: True)
    monkeypatch.setattr(launcher, 'host_token', lambda **_: pytest.fail('No token in manual prepare'))
    monkeypatch.setattr(launcher, 'owned_tunnel', lambda *_: pytest.fail('No tunnel in manual prepare'))

    @contextmanager
    def fake_environment(**kwargs):
        assert kwargs == {'workspace_id': 'ws_m1_synthetic'}
        calls.append('environment')
        yield
    monkeypatch.setattr(launcher, 'session_environment', fake_environment)
    monkeypatch.setattr(factory, 'create_app', lambda **kwargs: calls.append(kwargs) or SimpleNamespace(
        state=SimpleNamespace(model_connection=None)))
    monkeypatch.setattr(uvicorn, 'run', lambda *args, **kwargs: calls.append('fake-app'))
    assert launcher.main(['prepare', '--workspace-id', 'ws_m1_synthetic', '--app-port', '48124']) == 0
    assert calls[0] == 'environment' and calls[1]['workspace_id'] == 'ws_m1_synthetic' and calls[2] == 'fake-app'
    assert launcher.main(['prepare', '--workspace-id', 'other']) == 2


def test_opted_in_serve_passes_selection_without_real_network_or_app(monkeypatch, tmp_path):
    import uvicorn

    calls = []
    pins = tmp_path / 'synthetic-pins.json'
    pins.write_text('{}', encoding='utf-8')
    monkeypatch.setattr(launcher, 'port_free', lambda port: True)

    def fake_token(**kwargs):
        assert kwargs == {'allow_remote_token_read': True}
        calls.append('token')
        return 'SYNTHETIC_TOKEN'

    @contextmanager
    def fake_tunnel(port):
        assert port == 48123
        calls.append('tunnel')
        yield

    @contextmanager
    def fake_environment(**kwargs):
        assert kwargs == {'workspace_id': 'synthetic-workspace', 'model_port': 48123,
                          'token': 'SYNTHETIC_TOKEN'}
        calls.append('environment')
        yield

    authority = SimpleNamespace(close=lambda: calls.append('authority.close'))
    channel = SimpleNamespace(close=lambda: calls.append('channel.close'))
    monkeypatch.setattr(launcher, 'host_token', fake_token)
    monkeypatch.setattr(launcher, 'owned_tunnel', fake_tunnel)
    monkeypatch.setattr(launcher, 'session_environment', fake_environment)
    monkeypatch.setattr(launcher, 'compose', lambda *args: (object(), authority, channel))
    monkeypatch.setattr(uvicorn, 'run', lambda *args, **kwargs: calls.append('fake-app'))
    assert launcher.main(['serve', '--allow-remote-token-read', '--workspace-id', 'synthetic-workspace',
                          '--prism-pins', str(pins), '--model-port', '48123']) == 0
    assert calls == ['token', 'tunnel', 'environment', 'fake-app', 'authority.close', 'channel.close']
