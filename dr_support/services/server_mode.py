"""Which AI server the app uses, chosen by the administrator (phase 1 spec section 5).

``hospital_local``: the hospital model server; every admitted image may be analysed.
``team_server``: the team server (dr-train) over the SSH route; only workspaces the administrator marked as
holding public or consented images may use it (hospital rule, 31 October 2026). The launcher checks this before
it starts (``python -m dr_support.services.server_mode check``). The choice applies at the next start.
Kept in ``server-mode.json`` beside the accounts file; no secret is stored or shown.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException, Request

MODES = {"hospital_local": "Hospital model server", "team_server": "Team server (dr-train)"}
WORKSPACE_ID = re.compile(r"[A-Za-z0-9_.-]{1,80}")
FILE_NAME = "server-mode.json"


def read_mode(config_dir: Path) -> dict:
    path = Path(config_dir) / FILE_NAME
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"mode": "hospital_local", "consented_workspaces": []}
    mode = value.get("mode") if value.get("mode") in MODES else "hospital_local"
    workspaces = [item for item in value.get("consented_workspaces") or [] if isinstance(item, str) and WORKSPACE_ID.fullmatch(item)]
    return {**value, "mode": mode, "consented_workspaces": workspaces}


def team_server_refusal(config_dir: Path, workspace_id: str) -> str | None:
    """None when the team server may be used for this workspace, else a plain reason."""
    settings = read_mode(config_dir)
    if settings["mode"] != "team_server":
        return "The administrator has chosen the hospital model server. Change it on the Admin page first."
    if workspace_id not in settings["consented_workspaces"]:
        return "This workspace is not marked as public or consented images only, so it cannot use the team server."
    return None


def install_server_mode(app, require_admin, config_dir: Path):
    config_dir = Path(config_dir)

    @app.get("/v1/admin/server-mode")
    def get_mode(request: Request):
        require_admin(request)
        settings = read_mode(config_dir)
        remote = urlparse(os.environ.get("REMOTE_MODEL_URL", "")).hostname or ""
        workspace = getattr(app.state, "workspace_id", None)
        return {"mode": settings["mode"], "label": MODES[settings["mode"]], "modes": MODES,
                "consented_workspaces": settings["consented_workspaces"], "current_workspace": workspace,
                "current_model_host": remote, "applies": "at the next start",
                "updated_by": settings.get("updated_by"), "updated_utc": settings.get("updated_utc")}

    @app.put("/v1/admin/server-mode")
    def set_mode(request: Request, body: dict):
        acting = require_admin(request)
        mode = body.get("mode")
        workspaces = body.get("consented_workspaces", [])
        if mode not in MODES:
            raise HTTPException(422, "Choose the hospital model server or the team server.")
        if not isinstance(workspaces, list) or len(workspaces) > 200 or not all(
                isinstance(item, str) and WORKSPACE_ID.fullmatch(item) for item in workspaces):
            raise HTTPException(422, "Workspace IDs use letters, digits, dot, dash or underscore.")
        record = {"mode": mode, "consented_workspaces": sorted(set(workspaces)),
                  "updated_by": acting.username, "updated_utc": datetime.now(timezone.utc).isoformat()}
        config_dir.mkdir(parents=True, exist_ok=True)
        temporary = config_dir / (FILE_NAME + ".tmp")
        temporary.write_text(json.dumps(record, indent=2), encoding="utf-8")
        os.replace(temporary, config_dir / FILE_NAME)
        return get_mode(request)


def main(argv=None) -> int:
    """``check --config-dir DIR --workspace ID``: exit 0 when the team server may be used, else 3 with the reason."""
    import argparse
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("command", choices=["check"])
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args(argv)
    refusal = team_server_refusal(args.config_dir, args.workspace)
    if refusal:
        print(refusal, file=sys.stderr)
        return 3
    print("TEAM_SERVER_ALLOWED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
