"""Offline tracked-source hygiene audit. Never load private env, DBs, images or models.

The review context policy below is a static boundary check, not a Docker-engine
ignore-parser or container qualification. Findings expose paths/line numbers only.
"""
import argparse
import hashlib
import json
import re
import tomllib
from pathlib import Path, PurePosixPath

BINARY_SUFFIXES = {'.pt', '.pth', '.ckpt', '.onnx', '.safetensors', '.h5', '.hdf5', '.pkl', '.joblib', '.bin', '.sqlite', '.sqlite3', '.db', '.dump', '.backup', '.bak', '.pem', '.key', '.pfx', '.p12', '.dcm', '.dicom', '.tif', '.tiff', '.pyc', '.pyo'}
IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.gif', '.heic'}
PRIVATE_PARTS = {'.git', '.venv', 'node_modules', 'local-state', '.aws', '.ssh', '.codex', '.agents', '__pycache__', '.pytest_cache', '.ruff_cache', '.cache', 'dist'}
PRIVATE_NAMES = {'.netrc', '.npmrc', 'id_rsa', 'id_ed25519', 'credentials', '.pgpass', '.pg_service.conf'}
PREVIEW_ASSETS = {'frontend/public/prism-uwf-fov-preview/original.png', 'frontend/public/prism-uwf-fov-preview/field-mask.png'}
CONTEXT_FILES = {'README.md', 'pyproject.toml', 'uv.lock', 'frontend/package.json', 'frontend/package-lock.json', 'frontend/index.html', 'frontend/tsconfig.json', 'frontend/vite.config.ts', 'deployment/dual-mode/Dockerfile.review', 'deployment/dual-mode/review-requirements.lock'}
TEXT_SUFFIXES = {'.py', '.ts', '.tsx', '.json', '.toml', '.yml', '.yaml', '.md', '.qmd', '.html', '.bat', '.ps1', '.sh', '.txt', '.service', '.conf', '.ini', '.cfg', '.lock'}
TOKEN_PATTERNS = {
    'AWS_ACCESS_KEY_PATTERN': re.compile(r'\bAKIA[A-Z0-9]{16}\b'),
    'GITHUB_TOKEN_PATTERN': re.compile(r'\b(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b'),
    'OPENAI_TOKEN_PATTERN': re.compile(r'\bsk-[A-Za-z0-9_-]{30,}\b'),
    'PRIVATE_KEY_MARKER': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
}


def sensitive_path(path):
    p = PurePosixPath(path)
    return (bool(set(p.parts) & PRIVATE_PARTS)
            or p.name in PRIVATE_NAMES or p.suffix.lower() == '.env'
            or (p.name.startswith('.env') and not p.name.endswith('.env.example'))
            or p.suffix.lower() in BINARY_SUFFIXES
            or bool(re.search(r'\.(?:sqlite3?|db)-(?:wal|shm|journal)$', p.name)))


def review_context_allowed(path):
    p = PurePosixPath(path)
    if p.is_absolute() or '..' in p.parts or sensitive_path(path):
        return False
    if p.suffix.lower() in IMAGE_SUFFIXES:
        return path in PREVIEW_ASSETS
    return path in CONTEXT_FILES or path.startswith(('dr_support/', 'web/', 'frontend/src/'))


def template_findings(text):
    values, findings = {}, []
    for line in text.splitlines():
        match = re.match(r'^([A-Z][A-Z0-9_]*)=(.*)$', line)
        if match:
            key, value = match.groups()
            if key in values:
                findings.append({'key': key, 'reason': 'DUPLICATE_TEMPLATE_KEY'})
            values[key] = value.strip()
    expected = {'APP_PROFILE': 'review', 'MODEL_RUNTIME': 'remote', 'HOST': '127.0.0.1', 'WORKERS': '1', 'DR_SUPPORT_CASE_STORE': 'postgres'}
    for key, value in expected.items():
        if values.get(key) != value:
            findings.append({'key': key, 'reason': 'UNSAFE_REVIEW_TEMPLATE_DEFAULT'})
    for key, value in values.items():
        if any(word in key for word in ('TOKEN', 'PASSWORD', 'SECRET', 'DATABASE_URL')) and value:
            findings.append({'key': key, 'reason': 'CREDENTIAL_TEMPLATE_MUST_BE_EMPTY'})
    if not values.get('PORT', '').isdigit() or not 1 <= int(values['PORT']) <= 65535:
        findings.append({'key': 'PORT', 'reason': 'INVALID_PORT'})
    return findings


def lock_findings(root):
    project = tomllib.loads((root/'pyproject.toml').read_text())['project']
    lock = tomllib.loads((root/'uv.lock').read_text())
    packages = {(p['name'], p.get('version')): p for p in lock['package']}
    own = next(p for p in lock['package'] if p['name'] == project['name'])
    metadata = {p['name']: p.get('specifier') for p in own['metadata']['requires-dist']}
    findings = []
    for dependency in project['dependencies']:
        match = re.fullmatch(r'([A-Za-z0-9_-]+)(?:\[[^]]+\])?==(.+)', dependency)
        if not match or metadata.get(match[1].lower()) != '=='+match[2]:
            findings.append({'reason': 'PYTHON_DIRECT_LOCK_DRIFT'})
    requirements = (root/'deployment/dual-mode/review-requirements.lock').read_text()
    blocks = re.split(r'\n(?=[A-Za-z0-9])', requirements.strip())
    exported = set()
    for block in blocks:
        match = re.match(r'([A-Za-z0-9_-]+)==([^\s;\\]+)', block)
        if not match:
            findings.append({'reason': 'UNPINNED_REVIEW_REQUIREMENT'})
            continue
        name, version = match.groups()
        exported.add(name)
        package = packages.get((name, version))
        hashes = re.findall(r'--hash=sha256:([a-f0-9]{64})', block)
        available = {artifact['hash'].removeprefix('sha256:') for artifact in ((package or {}).get('wheels', []) + ([(package or {})['sdist']] if (package or {}).get('sdist') else []))}
        if not package or not hashes or not set(hashes) <= available:
            findings.append({'reason': 'REVIEW_REQUIREMENT_HASH_DRIFT', 'package': name})
    if exported & {'torch', 'torchvision', 'timm', 'ultralytics', 'sahi', 'gdown', 'opencv-python'}:
        findings.append({'reason': 'MODEL_DEPENDENCY_IN_REVIEW_IMAGE'})
    pending = list(own['dependencies'])
    visited = set()
    while pending:
        dependency = pending.pop()
        extras = dependency.get('extra', [])
        extras = [extras] if isinstance(extras, str) else extras
        key = (dependency['name'], tuple(extras))
        if key in visited:
            continue
        visited.add(key)
        if dependency['name'] not in exported:
            findings.append({'reason': 'MISSING_REVIEW_DEPENDENCY', 'package': dependency['name']})
        for (name, _version), package in packages.items():
            if name != dependency['name']:
                continue
            pending.extend(package.get('dependencies', []))
            for extra in extras:
                pending.extend(package.get('optional-dependencies', {}).get(extra, []))
    for relative in ['frontend', '.']:
        folder = root/relative
        manifest = json.loads((folder/'package.json').read_text())
        npm_lock = json.loads((folder/'package-lock.json').read_text())
        for section in ['dependencies', 'devDependencies']:
            if manifest.get(section, {}) != npm_lock['packages'][''].get(section, {}):
                findings.append({'reason': 'NPM_MANIFEST_LOCK_DRIFT', 'path': relative})
        for name, package in npm_lock['packages'].items():
            if package.get('resolved', '').startswith('https://') and not package.get('integrity'):
                findings.append({'reason': 'NPM_MISSING_INTEGRITY', 'path': relative, 'package': name})
    return findings


def scan(root, paths):
    findings, context, images, ci = [], [], [], []
    for relative in sorted(set(paths)):
        p = PurePosixPath(relative)
        if p.is_absolute() or '..' in p.parts:
            findings.append({'path': relative, 'reason': 'INVALID_TRACKED_PATH'})
            continue
        if sensitive_path(relative):
            findings.append({'path': relative, 'reason': 'SENSITIVE_TRACKED_PATH'})
            continue  # Never open a private env, binary, database, credential or model.
        if p.suffix.lower() in IMAGE_SUFFIXES:
            images.append(relative)  # Filename inventory only; no image bytes read.
        if relative.startswith(('.github/workflows/', '.gitlab-ci', 'azure-pipelines')) or p.name == 'Jenkinsfile':
            ci.append(relative)
        if review_context_allowed(relative):
            context.append(relative)
        if p.suffix.lower() in TEXT_SUFFIXES or p.name.endswith('.env.example') or p.name.startswith('Dockerfile'):
            target = root/relative
            if not target.resolve().is_relative_to(root.resolve()):
                findings.append({'path': relative, 'reason': 'SOURCE_PATH_ESCAPES_ROOT'})
                continue
            for number, line in enumerate(target.read_text(encoding='utf-8-sig').splitlines(), 1):
                for name, pattern in TOKEN_PATTERNS.items():
                    if pattern.search(line):
                        findings.append({'path': relative, 'line': number, 'reason': name})
    findings += template_findings((root/'.env.example').read_text())
    findings += lock_findings(root)
    return {'status': 'PASS' if not findings else 'FAIL', 'tracked_path_count': len(set(paths)), 'findings': findings,
            'tracked_image_paths': images, 'image_contents_inspected': False, 'image_review_limit': 'Filename/source-label inventory only; publication rights and absence of identifiers in existing screenshots/retinal examples are not certified', 'review_context_policy_path_count': len(context),
            'review_context_policy_paths': context, 'ci_files': ci,
            'ci_limit': 'No remote/inherited workflow, app or deployment setting was inspected',
            'scope': 'Offline tracked text/path and public template checks only; no private env, DB, image, model, network or Docker engine',
            'uv_lock_sha256': hashlib.sha256((root/'uv.lock').read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tracked-paths-file', type=Path, required=True)
    parser.add_argument('--json-out', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    raw = args.tracked_paths_file.read_text(encoding='utf-8-sig')
    paths = raw.split('\0') if '\0' in raw else raw.splitlines()
    report = scan(root, [p for p in paths if p])
    if args.json_out:
        args.json_out.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ['status', 'tracked_path_count', 'review_context_policy_path_count', 'findings', 'ci_files', 'scope']}, indent=2))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
