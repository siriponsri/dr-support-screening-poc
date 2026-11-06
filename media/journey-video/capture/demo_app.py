"""Start a throwaway demo Workbench for the journey video (demo data only).

Used by capture_journey.py; can also be run alone to look around:

  python media/journey-video/capture/demo_app.py --port 8031 --samples <folder with the 10 public HRF samples>

Everything lives in a new temporary folder: SQLite state, the Workspace input
folder (only the ten pinned public HRF samples, checked byte for byte against
docs/reference/SAMPLE_SOURCE_MANIFEST.json), and a sign-in users file with two
throwaway local accounts whose random passwords exist only in memory and in
that temporary folder. No hospital root, model server, database server or
token is configured: the app runs APP_PROFILE=review MODEL_RUNTIME=remote with no
model URL, like scripts/docs/capture_manual_screenshots.py, so no model runs and
sign-in is enforced on every API route. (The full demo profile grafts routes
without the sign-in middleware, so a signed report has no signer there.)
"""
from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
SAMPLE_MANIFEST = ROOT / "docs" / "reference" / "SAMPLE_SOURCE_MANIFEST.json"
CLEAR = ("DR_SUPPORT_", "MODEL_", "REMOTE_MODEL", "PRISM_", "RETFOUND_", "USPEC_", "CVAT_", "PG", "APP_PROFILE",
         "GEMINI", "GOOGLE")
ADMIN = "demo.admin"
DOCTOR = "demo.doctor"


def approved_samples(samples: Path) -> dict[str, bytes]:
    pinned = {row["filename"]: row["sha256"] for row in json.loads(SAMPLE_MANIFEST.read_text(encoding="utf-8"))
              if row.get("source_type") == "PUBLIC"}
    entries = {path.name: path for path in samples.iterdir() if path.suffix.lower() in {".jpg", ".jpeg", ".png"}}
    if len(pinned) != 10 or set(entries) != set(pinned):
        raise SystemExit("PUBLIC_SAMPLES_REQUIRED: the folder must hold exactly the ten pinned public samples")
    approved = {}
    for name, path in entries.items():
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != pinned[name]:
            raise SystemExit("CHANGED_SAMPLE")
        approved[name] = data
    return approved


class Client:
    def __init__(self, base: str):
        self.base = base
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method: str, path: str, body=None):
        request = urllib.request.Request(self.base + path, method=method, headers={"Content-Type": "application/json"},
                                         data=json.dumps(body).encode() if body is not None else None)
        with self.opener.open(request, timeout=60) as response:
            return json.loads(response.read() or b"null")


def set_user(auth_file: Path, username: str, password: str, role: str) -> None:
    subprocess.run([sys.executable, "-m", "dr_support.services.pilot_auth", "set-user", "--file", str(auth_file),
                    "--username", username, "--role", role], input=password + "\n", text=True, check=True,
                   cwd=ROOT, stdout=subprocess.DEVNULL)


class DemoApp:
    """Context manager: temp state, users, server process and an opened Workspace."""

    def __init__(self, port: int, samples: Path):
        self.port = port
        self.base = f"http://127.0.0.1:{port}"
        self.samples = approved_samples(samples)
        self.passwords = {ADMIN: secrets.token_urlsafe(12) + "a1", DOCTOR: secrets.token_urlsafe(12) + "a1"}

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="dr-journey-", ignore_cleanup_errors=True)
        state = self.state = Path(self._tmp.name)
        auth_file = state / "users.json"
        set_user(auth_file, ADMIN, self.passwords[ADMIN], "admin")
        set_user(auth_file, DOCTOR, self.passwords[DOCTOR], "physician")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", self.port))
        env = {key: value for key, value in os.environ.items() if not key.upper().startswith(CLEAR)}
        env.update(APP_PROFILE="review", MODEL_RUNTIME="remote", DR_SUPPORT_CASE_STORE="sqlite",
                   DR_SUPPORT_STATE=str(state / "review.sqlite"), DR_SUPPORT_WORKSPACE_CATALOG=str(state / "workspaces.sqlite"),
                   DR_SUPPORT_AUTH_FILE=str(auth_file), PYTHONPATH=str(ROOT))
        if not (ROOT / "frontend" / "dist" / "index.html").is_file():
            raise SystemExit("BUILT_FRONTEND_REQUIRED: run npm run build in frontend/")
        code = ("import uvicorn; from dr_support.app import create_app; "
                f"uvicorn.run(create_app(), host='127.0.0.1', port={self.port}, log_level='warning')")
        self.process = subprocess.Popen([sys.executable, "-c", code], cwd=ROOT, env=env)
        for _ in range(120):
            try:
                urllib.request.urlopen(self.base + "/health", timeout=2)
                break
            except OSError:
                time.sleep(1)
        else:
            self.process.terminate()
            raise SystemExit("DEMO_APP_NOT_READY")
        self._open_workspace()
        return self

    def _open_workspace(self) -> None:
        (self.state / "input").mkdir()
        (self.state / "output").mkdir()
        for name, data in sorted(self.samples.items()):
            (self.state / "input" / name).write_bytes(data)
        admin = Client(self.base)
        admin.call("POST", "/v1/auth/login", {"username": ADMIN, "password": self.passwords[ADMIN]})
        created = admin.call("POST", "/v1/workspaces", {
            "name": "Demo clinic (public samples)", "input_folder": str(self.state / "input"),
            "output_folder": str(self.state / "output"), "database_path": str(self.state / "workspace.sqlite")})
        self.workspace_id = created.get("id") or created["workspace"]["id"]
        admin.call("POST", f"/v1/workspaces/{self.workspace_id}/open", {})

    def __exit__(self, *exc):
        self.process.terminate()
        try:
            self.process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.process.kill()
        self._tmp.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8031)
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--credentials-out", type=Path, help="write the throwaway accounts here (outside the repo)")
    args = parser.parse_args()
    with DemoApp(args.port, args.samples) as app:
        if args.credentials_out:
            args.credentials_out.write_text(json.dumps(app.passwords), encoding="utf-8")
        print(f"Demo app ready at {app.base}/app/ (Ctrl+C to stop)", flush=True)
        try:
            app.process.wait()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
