"""Offline packaging guards; no app factory, DB, container, image or model access."""
import io
import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib import request

import pytest
from scripts.audit.check_repo_hygiene import lock_findings, review_context_allowed, sensitive_path, template_findings, TOKEN_PATTERNS

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('path', ['.env', '.env.production', 'deployment/private.env', '.aws/credentials', 'dr_support/.env.qa', 'frontend/src/credentials', 'frontend/src/patient.png', 'frontend/src/retina.dcm', 'dr_support/checkpoint.safetensors', 'dr_support/nested/cache.sqlite-wal', 'frontend/node_modules/cache.js', 'frontend/dist/index.html', 'local-state/patient.csv', 'data/patient.jpg', 'docs/manuals/index.md', 'deployment/model-api/Dockerfile.prism', '../private.txt'])
def test_private_and_unrelated_paths_cannot_enter_review_context(path):
    assert not review_context_allowed(path)


@pytest.mark.parametrize('path', ['dr_support/workflow.py', 'dr_support/providers/retfound_lock.json', 'frontend/src/main.tsx', 'frontend/package-lock.json', 'web/app.js', 'uv.lock', 'deployment/dual-mode/review-requirements.lock', 'frontend/public/prism-uwf-fov-preview/field-mask.png'])
def test_required_review_source_and_explicit_synthetic_asset_remain_available(path):
    assert review_context_allowed(path)


def test_private_template_values_are_rejected_without_repeating_values():
    secret = 'synthetic-secret-do-not-echo'
    text = (ROOT/'.env.example').read_text() + '\nREMOTE_MODEL_TOKEN='+secret+'\n'
    findings = template_findings(text)
    assert any(f['reason'] == 'CREDENTIAL_TEMPLATE_MUST_BE_EMPTY' for f in findings)
    assert secret not in json.dumps(findings)
    assert any(f['reason'] == 'DUPLICATE_TEMPLATE_KEY' for f in findings)


@pytest.mark.parametrize('key,value', [('WORKERS','4'),('MODEL_RUNTIME','local'),('PORT','70000'),('HOST','0.0.0.0')])
def test_invalid_review_defaults_fail_closed(key, value):
    text = re.sub(rf'^{key}=.*$', key+'='+value, (ROOT/'.env.example').read_text(), flags=re.M)
    assert any(f['key'] == key for f in template_findings(text))


def copy_lock_fixture(tmp_path):
    for name in ['pyproject.toml','uv.lock','package.json','package-lock.json','frontend/package.json','frontend/package-lock.json','deployment/dual-mode/review-requirements.lock']:
        target = tmp_path/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, target)
    return tmp_path


def test_existing_core_export_matches_project_and_package_locks():
    assert lock_findings(ROOT) == []


def test_missing_transitive_requirement_is_detected(tmp_path):
    root = copy_lock_fixture(tmp_path)
    path = root/'deployment/dual-mode/review-requirements.lock'
    blocks = re.split(r'\n(?=[A-Za-z0-9])', path.read_text())
    path.write_text('\n'.join(block for block in blocks if not block.startswith('h11==')))
    assert any(f.get('package') == 'h11' and f['reason'] == 'MISSING_REVIEW_DEPENDENCY' for f in lock_findings(root))


def test_changed_wheel_hash_is_detected(tmp_path):
    root = copy_lock_fixture(tmp_path)
    path = root/'deployment/dual-mode/review-requirements.lock'
    path.write_text(re.sub(r'--hash=sha256:[a-f0-9]{64}', '--hash=sha256:'+'0'*64, path.read_text(), count=1))
    assert any(f['reason'] == 'REVIEW_REQUIREMENT_HASH_DRIFT' for f in lock_findings(root))


def test_lock_manifest_drift_is_detected(tmp_path):
    root = copy_lock_fixture(tmp_path)
    path = root/'frontend/package.json'
    content = json.loads(path.read_text())
    content['dependencies']['react'] = '0.0.0'
    path.write_text(json.dumps(content))
    assert any(f['reason'] == 'NPM_MANIFEST_LOCK_DRIFT' for f in lock_findings(root))


@pytest.mark.parametrize('payload,expected', [({'status':'PASS'},0),({'status':'PASS_WITH_WARNINGS'},0),({'status':'FAIL'},1),({},1)])
def test_container_liveness_checks_body_and_never_connects_to_network(payload, expected, monkeypatch):
    dockerfile = (ROOT/'deployment/dual-mode/Dockerfile.review').read_text()
    body = re.search(r'CMD python -c "([^"\n]+)"', dockerfile)[1]
    calls = []
    def fake_urlopen(url, timeout):
        calls.append((url, timeout))
        return io.StringIO(json.dumps(payload))
    monkeypatch.setattr(request, 'urlopen', fake_urlopen)
    with pytest.raises(SystemExit) as result:
        exec(compile(body, '<container-liveness-fixture>', 'exec'), {'__name__':'__main__'})
    assert result.value.code == expected
    assert calls == [('http://127.0.0.1:8000/health',3)]


def test_review_build_uses_frozen_inputs_and_does_not_install_model_extras():
    text = (ROOT/'deployment/dual-mode/Dockerfile.review').read_text()
    assert 'npm ci --ignore-scripts' in text
    assert '--require-hashes --only-binary=:all: --no-deps' in text
    assert 'pip install --no-cache-dir --no-deps -e .' not in text
    assert 'USER 10001:10001' in text
    assert 'DR_SUPPORT_CASE_STORE=postgres' in text
    assert 'portable-source-unpinned' not in text
    assert '^[a-f0-9]{40}$' in text


def test_context_file_has_default_deny_and_last_explicit_preview_exceptions():
    lines = [line for line in (ROOT/'deployment/dual-mode/Dockerfile.review.dockerignore').read_text().splitlines() if line and not line.startswith('#')]
    assert lines[0] == '**'
    assert '**/node_modules' in lines and '**/.env.*' in lines and '**/*.png' in lines
    assert lines[-2:] == ['!frontend/public/prism-uwf-fov-preview/original.png','!frontend/public/prism-uwf-fov-preview/field-mask.png']


def test_hardcoded_secret_pattern_detection_is_value_free():
    synthetic = 'ghp_'+'x'*36
    assert TOKEN_PATTERNS['GITHUB_TOKEN_PATTERN'].search(synthetic)
    assert sensitive_path('config/private.env')
    assert not sensitive_path('.env.example')


def test_real_git_ignore_rules_keep_public_source_and_exclude_private_artifacts(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True, capture_output=True)
    shutil.copyfile(ROOT/'.gitignore', tmp_path/'.gitignore')
    empty = tmp_path/'empty-excludes'
    empty.write_text('')
    ignored = ['.env.production', 'config/private.env', 'weights/model.onnx', 'local-state/patients.json', 'cache/reviews.sqlite-wal', 'keys/host.pem', 'state/qa.db-shm', 'backups/clinical.sql', 'logs/runtime.log', '.pgpass']
    public = ['.env.example', 'frontend/src/main.tsx', 'README.md', 'deployment/dual-mode/review-requirements.lock']
    result = subprocess.run(['git', '-c', f'core.excludesFile={empty}', '-C', str(tmp_path), 'check-ignore', '--no-index', '-z', '--stdin'], input=('\0'.join(ignored+public)+'\0').encode(), capture_output=True, check=False)
    assert result.returncode == 0
    assert set(result.stdout.decode().rstrip('\0').split('\0')) == set(ignored)


def test_dedicated_context_excludes_backup_and_bytecode_variants():
    lines = set((ROOT/'deployment/dual-mode/Dockerfile.review.dockerignore').read_text().splitlines())
    assert {'**/*.backup', '**/*.bak', '**/*.pyc', '**/*.pyo'} <= lines
