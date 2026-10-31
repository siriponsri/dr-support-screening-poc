"""Small config files that only the app's own account may read (accounts, server mode, referral connector)."""
from __future__ import annotations

import os
from pathlib import Path


def write_private(path: Path, text: str) -> None:
    """Write atomically, created as 0600 on Linux so no other local account can read it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(text)
    os.replace(temporary, path)
