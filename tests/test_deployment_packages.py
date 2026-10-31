"""Docker packages (web app, hospital server): scripts parse, templates hold no real secrets, images stay read-only."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "deployment"
SCRIPTS = sorted((ROOT / "webapp" / "bin").glob("*.sh")) + sorted((ROOT / "hospital-server" / "bin").glob("*.sh"))
SH = shutil.which("sh") or shutil.which("bash")


@pytest.mark.skipif(SH is None, reason="no POSIX shell on this machine")
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda path: f"{path.parent.parent.name}/{path.name}")
def test_package_scripts_parse(script):
    assert subprocess.run([SH, "-n", str(script)], capture_output=True).returncode == 0


@pytest.mark.parametrize("template", ["webapp/webapp.env.example", "hospital-server/hospital.env.example"])
def test_env_templates_hold_placeholders_not_secrets(template):
    values = dict(line.split("=", 1) for line in (ROOT / template).read_text(encoding="utf-8").splitlines()
                  if line and not line.startswith("#"))
    for key in ("DR_SUPPORT_POSTGRES_PASSWORD", "DR_SCREENING_SOURCE_COMMIT"):
        assert values[key].startswith("REPLACE")
    token = values.get("REMOTE_MODEL_TOKEN", "")
    assert token.startswith("REPLACE")


@pytest.mark.parametrize("compose", ["webapp/compose.yml", "hospital-server/compose.override.yml"])
def test_image_folders_are_mounted_read_only_and_sign_in_is_on(compose):
    text = (ROOT / compose).read_text(encoding="utf-8")
    assert re.search(r":/data/input:ro\b", text)
    assert "DR_SUPPORT_AUTH_FILE: /data/config/pilot-users.json" in text


def test_web_app_port_is_loopback_only_behind_https():
    text = (ROOT / "webapp" / "compose.yml").read_text(encoding="utf-8")
    assert '"127.0.0.1:${REVIEW_PORT:-8000}:8000"' in text and "--internal-certs" in text
