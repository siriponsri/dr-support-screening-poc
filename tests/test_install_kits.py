"""No-code install kits: hospital server installer and offline bundle, Cloudflare Tunnel demo helper.

Static checks (scripts parse, no secret or placeholder leaks, private file modes, no password echo) and one
runtime proof: the demo review app behind a Cloudflare Tunnel accepts sign-in from the public hostname.
"""
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOSPITAL = REPO / "deployment" / "hospital-server"
CLOUDFLARE = REPO / "deployment" / "cloudflare-access"
INSTALL = HOSPITAL / "install.sh"
BUNDLE = HOSPITAL / "bin" / "make-offline-bundle.sh"
TUNNEL_PS1 = CLOUDFLARE / "tunnel.ps1"
BASH = shutil.which("bash")
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")
KIT_FILES = sorted(p for p in list(HOSPITAL.rglob("*")) + list(CLOUDFLARE.rglob("*")) if p.is_file())
TEST_PASSWORD = "synthetic-test-pass-7"


def _bash_path(path):
    """Path as bash sees it (Git Bash on Windows wants /c/...)."""
    text = str(path)
    if os.name == "nt" and re.match(r"^[A-Za-z]:\\", text):
        text = "/" + text[0].lower() + text[2:].replace("\\", "/")
    return text


# ----------------------------------------------------------------------------------------------- scripts parse

@pytest.mark.skipif(BASH is None, reason="no bash on this machine")
@pytest.mark.parametrize("script", [INSTALL, BUNDLE], ids=lambda p: p.name)
def test_new_shell_scripts_parse(script):
    result = subprocess.run([BASH, "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck is not installed")
@pytest.mark.parametrize("script", [INSTALL, BUNDLE], ids=lambda p: p.name)
def test_new_shell_scripts_pass_shellcheck(script):
    result = subprocess.run(["shellcheck", "-S", "warning", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="no PowerShell on this machine")
def test_tunnel_powershell_helper_parses():
    command = (
        "$e = $null; [void][System.Management.Automation.Language.Parser]::ParseFile("
        f"'{TUNNEL_PS1}', [ref]$null, [ref]$e); if ($e.Count) {{ $e | ForEach-Object {{ $_.Message }}; exit 1 }}"
    )
    result = subprocess.run([POWERSHELL, "-NoProfile", "-Command", command], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_windows_files_are_ascii_and_batch_files_call_the_helper():
    # Windows PowerShell 5.1 reads BOM-less files as ANSI; keep every Windows file plain ASCII.
    for name in ("tunnel.ps1", "start-tunnel.bat", "stop-tunnel.bat"):
        assert (CLOUDFLARE / name).read_bytes().isascii(), name
    assert "tunnel.ps1" in (CLOUDFLARE / "start-tunnel.bat").read_text() and "-Action Start" in (
        CLOUDFLARE / "start-tunnel.bat").read_text()
    assert "-Action Stop" in (CLOUDFLARE / "stop-tunnel.bat").read_text()


# ------------------------------------------------------------------------------------- no secrets in the repo

SECRET_PATTERNS = [
    re.compile(r"eyJ[A-Za-z0-9_-]{20,}"),                       # Cloudflare tunnel token / JWT
    re.compile(r"(?<![0-9a-f])[0-9a-f]{40,}(?![0-9a-f])"),      # long hex value (token, password, SHA)
    re.compile(r"\b(?:10|100|172|192\.168)\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),  # private or tailnet address
    re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"),
]


@pytest.mark.parametrize("path", KIT_FILES, ids=lambda p: str(p.relative_to(REPO)).replace("\\", "/"))
def test_kit_files_hold_no_secret_looking_values_or_real_hosts(path):
    text = path.read_text(encoding="utf-8")
    for pattern in SECRET_PATTERNS:
        assert not pattern.search(text), f"{pattern.pattern} in {path.name}"
    placeholders = re.sub(r"<[A-Za-z][A-Za-z0-9_ -]*>", "placeholder.example", text)   # <your-domain> etc.
    for host in re.findall(r"https?://([A-Za-z0-9.-]+)", placeholders):
        assert (host in {"127.0.0.1", "localhost", "download.docker.com", "nvidia.github.io", "one.dash.cloudflare.com",
                         "dash.cloudflare.com", "developers.cloudflare.com", "docs.docker.com", "docs.nvidia.com"}
                or host.endswith((".example.test", ".example")) or host.startswith("<")), f"{host} in {path.name}"


# ------------------------------------------------------------------------------------------ hospital installer

def _install_text():
    return INSTALL.read_text(encoding="utf-8")


def test_installer_never_prints_a_secret_and_never_traces():
    text = _install_text()
    assert not re.search(r"^\s*set\s+-[a-z]*x", text, re.M) and "xtrace" not in text
    for number, line in enumerate(text.splitlines(), 1):
        code = line.split("#", 1)[0]
        if re.search(r"\b(echo|printf|say|warn|fail|ask)\b", code):
            assert not re.search(r"\$\{?(DR_SUPPORT_POSTGRES_PASSWORD|REMOTE_MODEL_TOKEN|password|token)\b", code,
                                 re.I), f"line {number} may print a secret: {line.strip()}"
    # Secrets are generated on the machine and only ever written into the env file block.
    assert "/dev/urandom" in text
    for line in text.splitlines():
        if "$(new_secret)" in line:
            assert line.strip().startswith("printf '") and "=%s\\n'" in line


def test_installer_writes_the_env_file_privately_and_keeps_an_existing_one():
    text = _install_text()
    assert "umask 077" in text and 'chmod 600 "$ENV_FILE"' in text
    assert "/etc/dr-screening/hospital.env" in text
    assert re.search(r'if \[ -f "\$ENV_FILE" \]', text)          # re-run keeps settings
    assert "pilot-users.json" in text                             # re-run keeps accounts
    assert '"$PKG/bin/start.sh"' in text and '"$PKG/bin/create-admin.sh"' in text
    assert "setup_models --model" in text and "--verify" in text  # reuse the pinned asset verification


def test_installer_only_installs_docker_or_toolkit_after_the_operator_types_yes():
    text = _install_text()
    for marker in ("download.docker.com/linux/ubuntu", "nvidia.github.io/libnvidia-container"):
        start = text.index(marker)
        function_start = text.rfind("\n", 0, text.rfind("()", 0, start))
        assert 'confirm_yes' in text[function_start:start], marker
    assert re.search(r'confirm_yes\(\)[\s\S]{0,400}\[ "\$answer" = "yes" \]', text)


@pytest.mark.skipif(BASH is None, reason="no bash on this machine")
def test_installer_env_file_has_every_template_key_no_placeholder_and_fresh_secrets(tmp_path):
    env_file = tmp_path / "hospital.env"
    script = f"""
set -eu
. '{_bash_path(INSTALL)}'
ENV_FILE='{_bash_path(env_file)}'
SITE_ADDRESS=dr-screening.example.test DATA_DIR=/srv/dr-screening/data IMAGES_DIR=/srv/dr-screening/images
MODELS_DIR=/srv/dr-screening/models SOURCE_COMMIT=0123456789abcdef0123456789abcdef01234567 IMAGE_TAG=git-0123456789ab
write_env_file
"""
    result = subprocess.run([BASH, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "" and result.stderr == ""            # nothing printed, least of all a secret
    text = env_file.read_text(encoding="utf-8")
    assert "REPLACE" not in text
    written = dict(line.split("=", 1) for line in text.splitlines() if line and not line.startswith("#"))
    template = dict(line.split("=", 1) for line in (HOSPITAL / "hospital.env.example").read_text().splitlines()
                    if line and not line.startswith("#"))
    assert set(template) <= set(written)
    assert re.fullmatch(r"[0-9a-f]{48}", written["DR_SUPPORT_POSTGRES_PASSWORD"])
    assert re.fullmatch(r"[0-9a-f]{48}", written["REMOTE_MODEL_TOKEN"])
    assert written["DR_SUPPORT_POSTGRES_PASSWORD"] != written["REMOTE_MODEL_TOKEN"]
    assert written["MODEL_API_BASE_IMAGE"] == template["MODEL_API_BASE_IMAGE"]
    assert written["DUAL_MODE_GPU_PROFILE"] == "hospital-3090"
    assert written["DR_SITE_ADDRESS"] == "dr-screening.example.test"
    if os.name != "nt":                                           # NTFS has no POSIX modes
        assert env_file.stat().st_mode & 0o777 == 0o600


# ------------------------------------------------------------------------------------------- offline bundle

def test_offline_bundle_saves_every_hospital_image_with_checksums_and_no_weights():
    text = BUNDLE.read_text(encoding="utf-8")
    for image in ("dr-screening/review", "dr-screening/model-gateway", "dr-screening/uspec-api",
                  "dr-screening/prism-api", "dr-screening/retfound-api", "postgres:16-alpine", "caddy:2.8-alpine"):
        assert image in text, image
    assert "docker save" in text and "gzip" in text and "SHA256SUMS" in text and "git archive" in text
    assert "linux/amd64" in text
    assert not re.search(r"\b(cp|rsync)\b[^\n]*(models|weights|\.pth)", text)   # weights stay out
    assert "not included" in text.lower()
    # The installer verifies what the bundle writes.
    assert "SHA256SUMS" in _install_text() and "BUNDLE_INFO" in _install_text()


def test_it_checklist_and_readme_lead_with_the_installer():
    readme = (HOSPITAL / "README.md").read_text(encoding="utf-8")
    checklist = (HOSPITAL / "IT_CHECKLIST.md").read_text(encoding="utf-8")
    assert "install.sh" in readme.split("\n## ", 2)[1] if "\n## " in readme else "install.sh" in readme
    for needed in ("443", "RTX 3090", "make-offline-bundle.sh", "install.sh", "backup.sh", "stop.sh"):
        assert needed in checklist, needed


# --------------------------------------------------------------------------------------- Cloudflare helper

def test_tunnel_helper_keeps_the_token_private_and_never_downloads():
    text = TUNNEL_PS1.read_text(encoding="utf-8")
    assert "cloudflare-tunnel.token" in text and "/inheritance:r" in text and "AsSecureString" in text
    assert "TUNNEL_TOKEN" in text                       # passed by environment, not on the command line
    assert not re.search(r"--token\b", text)
    for line in text.splitlines():
        if re.search(r"Write-(Host|Output)|\bSay\b", line):
            assert not re.search(r"\$\w*(token|plain|pasted|secret|bstr)|TUNNEL_TOKEN", line, re.I), line
    assert not re.search(r"Invoke-WebRequest|Invoke-RestMethod|Start-BitsTransfer|DownloadFile|curl", text, re.I)
    assert re.search(r"winget install --id Cloudflare\.cloudflared", text)
    assert "YES" in text and "demo-rule" in text


def test_tunnel_helper_refuses_a_non_public_demo_image_mode():
    text = TUNNEL_PS1.read_text(encoding="utf-8")
    assert "public-samples" in text and "public-folder" in text and "DR_IMAGES" in text
    assert "http://127.0.0.1:" in text


def test_cloudflare_readme_uses_placeholders_and_the_ipv4_loopback_target():
    text = (CLOUDFLARE / "README.md").read_text(encoding="utf-8")
    assert "<your-domain>" in text and "One-time PIN" in text and "Self-hosted" in text
    assert "http://127.0.0.1:8010" in text and "HTTP Host Header" in text


# ------------------------------------------------- proof: sign-in through the tunnel reaches the demo app

def _free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _raw_request(port, method, path, headers, body=b""):
    """Plain HTTP/1.1 over a socket to 127.0.0.1, like cloudflared does for a local http:// service."""
    lines = [f"{method} {path} HTTP/1.1"] + [f"{k}: {v}" for k, v in headers.items()]
    lines += [f"Content-Length: {len(body)}", "Connection: close", "", ""]
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as conn:
        conn.settimeout(10)
        conn.connect(("127.0.0.1", port))
        conn.sendall("\r\n".join(lines).encode("latin1") + body)
        data = b""
        while chunk := conn.recv(65536):
            data += chunk
    head, _, payload = data.partition(b"\r\n\r\n")
    status = int(head.split(b" ", 2)[1])
    return status, head.decode("latin1"), payload


@pytest.fixture
def demo_app_server(tmp_path, monkeypatch):
    """The review app served exactly like scripts/qa/m1_server_app.py does: uvicorn.run(app, host=127.0.0.1)."""
    import uvicorn
    from dr_support.api._factory import create_app
    from dr_support.services.pilot_auth import UserStore

    users = tmp_path / "pilot-users.json"
    UserStore(users).set_user("doctor1", TEST_PASSWORD, role="user", must_change=False, enforce_policy=False)
    monkeypatch.setenv("DR_SUPPORT_AUTH_FILE", str(users))
    monkeypatch.delenv("FORWARDED_ALLOW_IPS", raising=False)      # the demo launcher does not set it
    app = create_app(tmp_path / "state.sqlite", include_samples=False, include_demo_fixtures=False)
    port = _free_port()
    # Same arguments as the demo launcher; proxy_headers and forwarded_allow_ips stay at uvicorn's defaults.
    config = uvicorn.Config(app, host="127.0.0.1", port=port, workers=1, access_log=False, log_level="warning")
    assert config.proxy_headers is True and "127.0.0.1" in config.forwarded_allow_ips
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started:
        assert thread.is_alive() and time.monotonic() < deadline, "uvicorn did not start"
        time.sleep(0.05)
    yield port
    server.should_exit = True
    thread.join(timeout=10)


LOGIN = b'{"username": "doctor1", "password": "' + TEST_PASSWORD.encode() + b'"}'
TUNNEL_HEADERS = {
    # What cloudflared sends to http://127.0.0.1:8010 for https://dr-demo.example.test with the HTTP Host Header
    # setting left empty: the public Host, the visitor's scheme, the browser's Origin.
    "Host": "dr-demo.example.test",
    "X-Forwarded-Proto": "https",
    "X-Forwarded-For": "203.0.113.7",
    "Origin": "https://dr-demo.example.test",
    "Content-Type": "application/json",
}


@pytest.mark.skipif(sys.platform == "emscripten", reason="needs real sockets")
def test_sign_in_through_the_tunnel_is_accepted_by_the_demo_app(demo_app_server):
    status, head, payload = _raw_request(demo_app_server, "POST", "/v1/auth/login", TUNNEL_HEADERS, LOGIN)
    assert status == 200, payload
    assert b'"username":"doctor1"' in payload
    cookie = re.search(r"(?im)^set-cookie: (dr_session=[^;]+)", head).group(1)
    # A later write with the session cookie is accepted too (sign-out is a POST).
    status, _, payload = _raw_request(demo_app_server, "POST", "/v1/auth/logout",
                                      {**TUNNEL_HEADERS, "Cookie": cookie})
    assert status == 200, payload


def test_without_the_forwarded_scheme_or_with_a_rewritten_host_the_write_is_refused(demo_app_server):
    no_scheme = {k: v for k, v in TUNNEL_HEADERS.items() if k != "X-Forwarded-Proto"}
    status, _, payload = _raw_request(demo_app_server, "POST", "/v1/auth/login", no_scheme, LOGIN)
    assert status == 403 and b"Cross-origin" in payload
    # Pointing the tunnel at the Docker web app's Caddy front (site address localhost) needs the Host rewritten
    # to localhost; the app then sees https://localhost and refuses the dr-demo Origin.
    rewritten = {**TUNNEL_HEADERS, "Host": "localhost"}
    status, _, payload = _raw_request(demo_app_server, "POST", "/v1/auth/login", rewritten, LOGIN)
    assert status == 403 and b"Cross-origin" in payload
