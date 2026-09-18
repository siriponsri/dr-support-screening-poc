import hashlib
import subprocess
from pathlib import Path


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_source(path, revision):
    path = Path(path)
    result = subprocess.run(['git', '-C', str(path), 'rev-parse', 'HEAD'], capture_output=True, text=True)
    dirty = subprocess.run(['git', '-C', str(path), 'diff', '--quiet', 'HEAD'], capture_output=True)
    if result.returncode or result.stdout.strip() != revision or dirty.returncode:
        raise RuntimeError('Source revision mismatch or modified source')
    return path


def verify_weight(path, expected):
    if not expected or len(expected) != 64 or sha256(path) != expected:
        raise RuntimeError('Checkpoint SHA256 mismatch or hash not configured')
    return Path(path)
