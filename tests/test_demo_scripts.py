"""One-click demo scripts: syntax, input checks before any action, and no secret handling in the scripts."""
import shutil
import subprocess
from pathlib import Path

import pytest

DEMO = Path(__file__).resolve().parents[1] / "scripts" / "demo"
SH = shutil.which("sh") or shutil.which("bash")
pytestmark = pytest.mark.skipif(SH is None, reason="no POSIX shell on this machine")


@pytest.mark.parametrize("name", ["remote-start-gateway.sh", "remote-stop-gateway.sh",
                                  "start-dr-train-demo.sh", "stop-dr-train-demo.sh"])
def test_scripts_parse(name):
    assert subprocess.run([SH, "-n", str(DEMO / name)], capture_output=True).returncode == 0


@pytest.mark.parametrize("args, code", [
    (["deploy-x", "regular/r04-inputs/PRISM_WORKSPACE_PINS.json", "r01"], "DEPLOYMENT_NAME_REJECTED"),
    (["regular-20261031-r04", "../../etc/passwd", "r01"], "PINS_PATH_REJECTED"),
    (["regular-20261031-r04", "regular/r04-inputs/PRISM_WORKSPACE_PINS.json", "x; rm"], "STATE_NAME_REJECTED"),
])
def test_remote_start_rejects_unexpected_arguments_before_doing_anything(args, code):
    result = subprocess.run([SH, str(DEMO / "remote-start-gateway.sh"), *args], capture_output=True, text=True)
    assert result.returncode == 2 and code in result.stdout


def test_scripts_never_read_or_print_the_model_token():
    for path in DEMO.glob("*.sh"):
        text = path.read_text(encoding="utf-8").lower()
        assert "model-api.env" not in text and "bearer" not in text and "token=" not in text


def test_example_settings_hold_no_real_workspace():
    text = (DEMO / "demo.env.example").read_text(encoding="utf-8")
    assert "DR_WORKSPACE=ws_m1_xxxxxxxxxxxxxxxxxxxx" in text
