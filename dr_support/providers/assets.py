import hashlib
import subprocess
from pathlib import Path


def sha256(path):
    from dr_support.services.identity_budget import check_identity_budget
    remaining = check_identity_budget()
    with Path(path).open('rb') as stream:
        if remaining is None:
            return hashlib.file_digest(stream, 'sha256').hexdigest()
        value = hashlib.sha256()
        while True:
            check_identity_budget()
            chunk = stream.read(1024 * 1024)
            check_identity_budget()
            if not chunk:
                return value.hexdigest()
            value.update(chunk)


def verify_source(path, revision):
    path = Path(path)
    from dr_support.services.identity_budget import check_identity_budget
    result = subprocess.run(['git', '-C', str(path), 'rev-parse', 'HEAD'], capture_output=True, text=True, timeout=check_identity_budget())
    dirty = subprocess.run(['git', '-C', str(path), 'diff', '--quiet', 'HEAD'], capture_output=True, timeout=check_identity_budget())
    check_identity_budget()
    if result.returncode or result.stdout.strip() != revision or dirty.returncode:
        raise RuntimeError('Source revision mismatch or modified source')
    return path


def verify_weight(path, expected):
    if not expected or len(expected) != 64 or sha256(path) != expected:
        raise RuntimeError('Checkpoint SHA256 mismatch or hash not configured')
    return Path(path)
