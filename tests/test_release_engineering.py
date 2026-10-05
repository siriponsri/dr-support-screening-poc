import json
import hashlib
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_no_code_launchers_have_expected_roles():
    assert (ROOT / "FIRST_RUN.bat").read_text(encoding="utf-8").find("release-first-run.ps1") >= 0
    assert (ROOT / "START_DR_SCREENING.bat").read_text(encoding="utf-8").find("release-start.ps1") >= 0
    assert (ROOT / "STOP_DR_SCREENING.bat").read_text(encoding="utf-8").find("release-stop.ps1") >= 0
    assert (ROOT / "CHECK_SYSTEM.bat").read_text(encoding="utf-8").find("release-check-system.ps1") >= 0
    start = (ROOT / "scripts/windows/release-start.ps1").read_text(encoding="utf-8")
    assert "npm" not in start.lower()
    assert "Test-ReleaseFrontend" in start
    assert "127.0.0.1:8000/app/" in start


def test_windows_launcher_owns_local_postgres_and_reports_manual_mode_safely():
    common = (ROOT / "scripts/windows/release-common.ps1").read_text(encoding="utf-8")
    start = (ROOT / "scripts/windows/release-start.ps1").read_text(encoding="utf-8")
    check = (ROOT / "scripts/windows/release-check-system.ps1").read_text(encoding="utf-8")
    compose = (ROOT / "deployment/docker-compose.local-postgres.yml").read_text(encoding="utf-8")
    builder = (ROOT / "scripts/release/build_release.py").read_text(encoding="utf-8")
    settings = (ROOT / "frontend/src/components/settings/ModelConnectionSettings.tsx").read_text(encoding="utf-8")

    assert "New-ReleaseLocalDatabaseConfig" in common
    assert "postgres.env" in common
    assert "DR_SUPPORT_DATABASE_URL" in common
    assert "SELECT 1" in common
    assert "Ensure-ReleasePostgres" in start
    assert "Test-ReleasePostgres" in start
    assert "managed_local" in common
    assert "compose_file" in common
    assert "PSObject.Properties.Name" in common
    assert "ReleaseCheckoutIdentity" in common
    assert "DR_SUPPORT_CHECKOUT_ID" in common
    assert "DR_SUPPORT_POSTGRES_VOLUME" in common
    assert "Legacy project-owned PostgreSQL state" in common
    assert "DR_SUPPORT_COMPOSE" not in common
    assert "ConvertFrom-Json" in check
    assert "/v1/models" in check
    assert "manual review remains available" in check
    assert "[WARN] Model API connection" in check
    assert "Workspace API readiness" in check
    assert "DR_SUPPORT_POSTGRES_PASSWORD" in compose
    assert "postgres_data:/var/lib/postgresql/data" in compose
    assert "name: ${DR_SUPPORT_POSTGRES_VOLUME}" in compose
    assert "Get-ReleaseModelCapabilityStatus" in common
    assert "CommandLine" not in start
    assert "Research use" in settings
    assert "Blocked for review" in settings
    assert "Deferred" in settings
    assert "CFP only" in settings
    assert "deployment/docker-compose.local-postgres.yml" in builder
    assert "Write-Host $password" not in common
    assert "Write-Host $env:DR_SUPPORT_DATABASE_URL" not in common


def test_release_builder_and_model_identity_are_contract_only():
    builder = (ROOT / "scripts/release/build_release.py").read_text(encoding="utf-8")
    assert "workstation_allowlist" in builder
    assert "model_api_allowlist" in builder
    assert '"scripts/model-server"' not in builder
    assert "weights_included" in builder
    identity = json.loads((ROOT / "scripts/release/model_artifacts.json").read_text(encoding="utf-8"))
    assert identity == {
        "model_id": "uspec-uwf-grading",
        "artifact": "grading_state.pt",
        "expected_bytes": 1213535294,
        "expected_sha256": "8f07eb11859f638faee368a56c7c532ca946fee320f92f030a0cf25c63b769ac",
        "status": "IDENTITY_ONLY_NOT_ACQUIRED",
        "policy": "Do not download, include, load, or infer with this artifact in the release package.",
    }


def test_model_api_helpers_remain_disabled():
    start = (ROOT / "scripts/release/model-api-start.sh").read_text(encoding="utf-8")
    health = (ROOT / "scripts/release/model-api-health.sh").read_text(encoding="utf-8")
    check = (ROOT / "scripts/release/model-api-check.sh").read_text(encoding="utf-8")
    verify = (ROOT / "scripts/release/model-api-verify.sh").read_text(encoding="utf-8")
    assert "BLOCKED" in start
    assert "NOT_RUN" in health
    assert "P3.1" in start
    assert "NOT_RUN" in check
    assert "NOT_RUN" in verify


def test_builder_rejects_missing_prebuilt_frontend(tmp_path, monkeypatch):
    import scripts.release.build_release as builder

    monkeypatch.setattr(builder, "ROOT", tmp_path)
    try:
        builder.package("workstation", "test", tmp_path / "out", "abc")
    except SystemExit as exc:
        assert "frontend/dist" in str(exc)
    else:
        raise AssertionError("missing prebuilt frontend must block workstation packaging")


def _temporary_git_repo(path: Path):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Release Test"], cwd=path, check=True)


def test_release_zip_ignores_untracked_files_and_rejects_hostile_artifacts(tmp_path, monkeypatch):
    import scripts.release.build_release as builder

    root = tmp_path / "repo"
    root.mkdir()
    (root / "dr_support").mkdir()
    (root / "dr_support" / "app.py").write_text("print('tracked')\n", encoding="utf-8")
    (root / "scripts" / "release").mkdir(parents=True)
    (root / "scripts" / "release" / "model_artifacts.json").write_text("{}\n", encoding="utf-8")
    (root / "dr_support" / "notes.txt").write_text("untracked but harmless\n", encoding="utf-8")
    _temporary_git_repo(root)
    subprocess.run(["git", "add", "dr_support/app.py", "scripts/release/model_artifacts.json"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
    (root / "dr_support" / ".env.production").write_text("SECRET=do-not-package\n", encoding="utf-8")
    (root / "dr_support" / "service.env.local").write_text("SECRET=do-not-package\n", encoding="utf-8")
    (root / "dr_support" / "credentials.json").write_text("{}\n", encoding="utf-8")
    (root / "dr_support" / "weights.pt").write_bytes(b"weights")
    (root / "dr_support" / "weights.bin").write_bytes(b"weights")
    (root / "dr_support" / "runtime.db").write_bytes(b"database")
    (root / "dr_support" / "debug.log").write_text("log\n", encoding="utf-8")

    monkeypatch.setattr(builder, "ROOT", root)
    monkeypatch.setattr(builder, "model_api_allowlist", lambda: ["dr_support", "scripts/release/model_artifacts.json"])
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1735689600")
    source_commit = builder.git("rev-parse", "HEAD")

    with pytest.raises(SystemExit, match="forbidden release artifact"):
        builder.package("model-api", "test", root / "out", source_commit)

    for hostile in (
        ".env.production", "service.env.local", "credentials.json", "weights.pt", "weights.bin",
        "runtime.db", "debug.log",
    ):
        (root / "dr_support" / hostile).unlink()
    archive = builder.package("model-api", "test", root / "out", source_commit)
    with zipfile.ZipFile(archive) as package_zip:
        names = set(package_zip.namelist())
        assert "dr_support/app.py" in names
        assert "dr_support/notes.txt" not in names
        assert not any(name.endswith((".pt", ".db", ".log")) for name in names)
    first_bytes = archive.read_bytes()
    archive.unlink()
    second = builder.package("model-api", "test", root / "out", source_commit)
    assert second.read_bytes() == first_bytes


def test_release_builder_rejects_path_escape_and_symlink(tmp_path, monkeypatch):
    import scripts.release.build_release as builder

    root = tmp_path / "repo"
    root.mkdir()
    (root / "dr_support").mkdir()
    (root / "dr_support" / "app.py").write_text("print('tracked')\n", encoding="utf-8")
    _temporary_git_repo(root)
    subprocess.run(["git", "add", "dr_support/app.py"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
    monkeypatch.setattr(builder, "ROOT", root)
    monkeypatch.setattr(builder, "model_api_allowlist", lambda: ["dr_support"])
    source_commit = builder.git("rev-parse", "HEAD")

    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    link = root / "dr_support" / "linked.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pass
    else:
        with pytest.raises(SystemExit, match="unsafe symlink"):
            builder.package("model-api", "test", root / "out", source_commit)
        link.unlink()

    monkeypatch.setattr(builder, "model_api_allowlist", lambda: ["../outside.txt"])
    with pytest.raises(SystemExit, match="escapes repository root"):
        builder.package("model-api", "test", root / "out", source_commit)


def test_frontend_build_identity_detects_stale_source(tmp_path, monkeypatch):
    import scripts.release.build_release as builder

    root = tmp_path / "repo"
    frontend = root / "frontend"
    (frontend / "src").mkdir(parents=True)
    for name, content in {
        "index.html": "<div id='root'></div>\n",
        "package.json": "{}\n",
        "package-lock.json": "{}\n",
        "tsconfig.json": "{}\n",
        "vite.config.ts": "export default {}\n",
    }.items():
        (frontend / name).write_text(content, encoding="utf-8")
    (frontend / "src" / "main.ts").write_text("export {}\n", encoding="utf-8")
    (frontend / "dist").mkdir()
    monkeypatch.setattr(builder, "ROOT", root)
    output = b"index\n"
    (frontend / "dist" / "index.html").write_bytes(output)
    digest = builder.frontend_source_digest()
    entry = {"path": "index.html", "sha256": hashlib.sha256(output).hexdigest()}
    identity = {
        "schema_version": "frontend-build-identity.v1",
        "source_commit": "abc123",
        "source_digest": digest,
        "output_files": [entry],
        "output_set_sha256": builder._frontend_output_set_digest([entry]),
    }
    (frontend / "dist" / "build-identity.json").write_text(json.dumps(identity), encoding="utf-8")

    assert builder.verify_frontend_build("abc123")["source_digest"] == digest
    (frontend / "src" / "main.ts").write_text("export const stale = true;\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="stale"):
        builder.verify_frontend_build("abc123")


def test_release_capability_check_rejects_malformed_discovery_and_accepts_array(tmp_path):
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("PowerShell 7 is unavailable")
    common = (ROOT / "scripts/windows/release-common.ps1").as_posix()
    command = f"""
. '{common}'
$valid = Get-ReleaseModelCapabilityStatus '[{{\"model_id\":\"uwf-model\",\"task\":\"global\",\"status\":\"LOADED\",\"modalities\":[\"UWF\"]}}]'
$badShape = Get-ReleaseModelCapabilityStatus '{{\"model_id\":\"uwf-model\",\"task\":\"global\",\"status\":\"LOADED\",\"modalities\":\"UWF\"}}'
$badModalities = Get-ReleaseModelCapabilityStatus '[{{\"model_id\":\"uwf-model\",\"task\":\"global\",\"status\":\"LOADED\",\"modalities\":\"UWF\"}}]'
if (-not $valid.Valid -or -not $valid.Ready -or $badShape.Valid -or $badModalities.Valid) {{ exit 1 }}
"""
    result = subprocess.run([pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


def test_local_postgres_compose_config_is_valid_without_starting_services(tmp_path):
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("Docker CLI is unavailable")
    env_file = tmp_path / "postgres.env"
    env_file.write_text(
        "DR_SUPPORT_POSTGRES_DB=dr_support\n"
        "DR_SUPPORT_POSTGRES_USER=dr_support\n"
        "DR_SUPPORT_POSTGRES_PASSWORD=placeholder\n"
        "DR_SUPPORT_POSTGRES_BIND=127.0.0.1\n"
        "DR_SUPPORT_POSTGRES_PORT=54329\n"
        "DR_SUPPORT_POSTGRES_VOLUME=dr_support_test_volume\n",
        encoding="ascii",
    )
    result = subprocess.run(
        [docker, "compose", "--project-name", "dr-support-test", "--file", str(ROOT / "deployment/docker-compose.local-postgres.yml"), "--env-file", str(env_file), "config", "--quiet"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_frontend_build_identity_rejects_output_set_and_byte_drift(tmp_path, monkeypatch):
    import hashlib
    import scripts.release.build_release as builder

    root = tmp_path / "repo"
    frontend = root / "frontend"
    (frontend / "src").mkdir(parents=True)
    for name, content in {
        "index.html": "<div id='root'></div>\n",
        "package.json": "{}\n",
        "package-lock.json": "{}\n",
        "tsconfig.json": "{}\n",
        "vite.config.ts": "export default {}\n",
    }.items():
        (frontend / name).write_text(content, encoding="utf-8")
    (frontend / "src" / "main.ts").write_text("export {}\n", encoding="utf-8")
    dist = frontend / "dist"
    (dist / "assets").mkdir(parents=True)
    outputs = {"index.html": b"index\n", "assets/app.js": b"app\n"}
    for relative, content in outputs.items():
        path = dist / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    entries = [
        {"path": relative, "sha256": hashlib.sha256(content).hexdigest()}
        for relative, content in sorted(outputs.items())
    ]
    monkeypatch.setattr(builder, "ROOT", root)
    identity = {
        "schema_version": "frontend-build-identity.v1",
        "source_commit": "abc123",
        "source_digest": builder.frontend_source_digest(),
        "output_files": entries,
        "output_set_sha256": builder._frontend_output_set_digest(entries),
    }
    (dist / "build-identity.json").write_text(json.dumps(identity), encoding="utf-8")
    assert builder.verify_frontend_build("abc123")["output_set_sha256"] == identity["output_set_sha256"]
    (dist / "extra.txt").write_text("unexpected\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="output set"):
        builder.verify_frontend_build("abc123")
    (dist / "extra.txt").unlink()
    (dist / "assets/app.js").write_bytes(b"modified\n")
    with pytest.raises(SystemExit, match="output bytes"):
        builder.verify_frontend_build("abc123")
    (dist / "assets/app.js").write_bytes(outputs["assets/app.js"])
    (dist / "index.html").unlink()
    with pytest.raises(SystemExit, match="output set"):
        builder.verify_frontend_build("abc123")


def test_gitignore_excludes_release_runtime():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "local-state/release/" in text
    assert "*.pt" in text
    assert ".env" in text
