"""Operations helpers: dashboard smoke check, PCB blog validator and Pi deploy manifest."""

import importlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.verify_live_dashboard import ui_asset_revisions

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell.exe") or shutil.which("powershell")
needs_powershell = pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is required")


def run_powershell(script: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *arguments],
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_dashboard_smoke_check_accepts_the_current_ui_revision() -> None:
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    revisions = ui_asset_revisions(html)
    assert set(revisions) == {"sensors", "automations"}
    assert all(revisions.values())


def test_dashboard_smoke_check_follows_revision_bumps() -> None:
    html = (
        '<script src="/static/sensors.js?v=20991231-7"></script>'
        '<script src="/static/automations.js?v=20991231-2"></script>'
    )
    assert ui_asset_revisions(html) == {"sensors": "20991231-7", "automations": "20991231-2"}
    with pytest.raises(AssertionError):
        ui_asset_revisions('<script src="/static/sensors.js?v=20991231-7"></script>')


@needs_powershell
def test_pcb_blog_validator_runs_on_windows_powershell(tmp_path: Path) -> None:
    result = run_powershell(ROOT / "scripts/validate_pcb_blog.ps1")
    assert "GetRelativePath" not in result.stderr
    assert "MARKDOWN_FILES_CHECKED=" in result.stdout

    # In an empty copy every document is missing and reported by its repository path.
    copy = tmp_path / "scripts/validate_pcb_blog.ps1"
    copy.parent.mkdir()
    shutil.copy2(ROOT / "scripts/validate_pcb_blog.ps1", copy)
    result = run_powershell(copy)
    assert result.returncode == 1, result.stderr
    assert "MISSING_DOCUMENT=docs/blog/pcb-ir-node/README.md" in result.stdout
    assert "MISSING_DOCUMENT=docs/journal/2026-09-22-pcb-blog-series.md" in result.stdout


def make_deploy_tree(root: Path) -> Path:
    files = {
        "app/main.py": "app",
        "app/.env": "SECRET=1",
        "app/logs/run.log": "log",
        "app/runtime/state.json": "{}",
        "app/server.pem": "key",
        "app/tmp/scratch.txt": "tmp",
        "app/node_modules/x.js": "js",
        "app/secrets/token.txt": "token",
        "deploy/zigbee/.env": "MQTT_PASSWORD=1",
        "deploy/zigbee/.env.local": "MQTT_PASSWORD=1",
        "deploy/zigbee/.env.example": "MQTT_PASSWORD=",
        "deploy/zigbee/compose.yaml": "services: {}",
        "device_profiles/profile.json": "{}",
        "tests/test_app.py": "def test(): pass",
        "tests/.pytest_cache/v/cache": "cache",
        "tests/signing.p12": "key",
        "scripts/run_pi.sh": "#!/bin/sh",
        "scripts/setup_app_mqtt.sh": "#!/bin/sh",
        ".env.example": "NAME=",
        "pyproject.toml": "[project]",
        "README.md": "readme",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    shutil.copy2(ROOT / "scripts/deploy.ps1", root / "scripts/deploy.ps1")
    identity = root / "identity-fixture"
    identity.write_text("not a key", encoding="utf-8")
    return identity


@needs_powershell
def test_deploy_preview_excludes_secrets_logs_and_runtime_files(tmp_path: Path) -> None:
    identity = make_deploy_tree(tmp_path)
    result = run_powershell(tmp_path / "scripts/deploy.ps1", "-IdentityFile", str(identity))
    assert result.returncode == 0, result.stderr
    assert "MODE=PREVIEW" in result.stdout and "NO_REMOTE_CHANGES=preview-only" in result.stdout
    deployed = set(re.findall(r"^FILE=(\S+)", result.stdout, flags=re.MULTILINE))
    assert deployed == {
        ".env.example",
        "README.md",
        "app/main.py",
        "deploy/zigbee/.env.example",
        "deploy/zigbee/compose.yaml",
        "device_profiles/profile.json",
        "pyproject.toml",
        "scripts/run_pi.sh",
        "scripts/setup_app_mqtt.sh",
        "tests/test_app.py",
    }

    result = run_powershell(
        tmp_path / "scripts/deploy.ps1",
        "-IdentityFile",
        str(identity),
        "-Include",
        "deploy/zigbee/.env",
    )
    assert result.returncode != 0
    assert "secret, log, cache or runtime file" in result.stdout + result.stderr
    assert "FILE=" not in result.stdout


def test_deploy_sets_run_script_mode_only_when_it_is_deployed() -> None:
    script = (ROOT / "scripts/deploy.ps1").read_text(encoding="utf-8")
    guard = script.index('if ($files.RelativePath -contains "scripts/run_pi.sh") {')
    chmod = script.index("chmod 755 -- '$RemotePath/scripts/run_pi.sh'")
    # The chmod call sits inside the guard block, which closes at column 0.
    assert guard < chmod and "\n}" not in script[guard:chmod]
    assert script.count("chmod 755") == 1


# A PC user folder (the Users folder on the Windows drive, also as seen from Git
# Bash or WSL) or a personal tool cache must never be spelled out in a tracked script.
PC_USER_PATH = re.compile(
    r"(?i)(?:\b[a-z]:[\\/]{1,2}|(?<![\w.:/])/(?:mnt/)?[a-z]/)users[\\/]{1,2}(?![<\[%$])"
    r"|codex-runtimes"
)
TEXT_SUFFIXES = {".py", ".cjs", ".mjs", ".js", ".ps1", ".sh", ".txt", ".md", ".json"}


def tracked_files(directory: str) -> list[Path]:
    try:
        listing = subprocess.run(
            ["git", "ls-files", "-z", "--", directory], cwd=ROOT, capture_output=True, check=True
        ).stdout.decode("utf-8")
    except (OSError, subprocess.CalledProcessError):
        folder = ROOT / directory
        return [p for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    return [ROOT / name for name in listing.split("\0") if name]


def test_scripts_do_not_embed_pc_user_paths() -> None:
    offenders = []
    for path in tracked_files("scripts"):
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            if PC_USER_PATH.search(line):
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{number}")
    assert offenders == []


@pytest.fixture
def hardware_paths(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts/hardware"))
    for name in (
        "IR_H2_KICAD_ROOT",
        "KICAD_INSTALL_DIR",
        "KICAD_CLI",
        "IR_H2_VENDOR_FOOTPRINTS",
        "IR_H2_ROUTE_TOOLS",
    ):
        monkeypatch.delenv(name, raising=False)
    return importlib.import_module("hw_paths")


def test_hardware_paths_use_environment_then_defaults_then_a_clear_error(
    hardware_paths, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    with pytest.raises(SystemExit, match="set IR_H2_KICAD_ROOT"):
        hardware_paths.kicad_root()
    project = tmp_path / "home/OneDrive/Desktop/설계-하드웨어/kicad/IR_ESP32H2"
    project.mkdir(parents=True)
    assert hardware_paths.kicad_root() == project
    # The autorouter is optional, so its default folder does not have to exist.
    assert hardware_paths.route_tools() == project.parent / "KeyRing/tmp/route_tools"
    with pytest.raises(SystemExit, match="set IR_H2_VENDOR_FOOTPRINTS"):
        hardware_paths.vendor_footprints()

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("IR_H2_KICAD_ROOT", str(elsewhere))
    assert hardware_paths.kicad_root() == elsewhere
    monkeypatch.setenv("IR_H2_KICAD_ROOT", str(tmp_path / "missing"))
    with pytest.raises(SystemExit, match="IR_H2_KICAD_ROOT=.* is not the IR_ESP32H2"):
        hardware_paths.kicad_root()

    cli = tmp_path / "kicad-cli.exe"
    cli.write_bytes(b"")
    monkeypatch.setenv("KICAD_CLI", str(cli))
    monkeypatch.setenv("KICAD_INSTALL_DIR", str(tmp_path / "no-kicad"))
    assert hardware_paths.kicad_cli() == cli  # the install folder is not consulted


@pytest.mark.parametrize("ignore_file", [".gitignore", "server/.gitignore"])
def test_gitignore_keeps_logs_keys_packages_and_databases_out(ignore_file: str) -> None:
    lines = (ROOT / ignore_file).read_text(encoding="utf-8").splitlines()
    for pattern in ("*.log", "*.sqlite3", "*.db", "*.jks", "*.keystore", "*.apk", "*.aab"):
        assert pattern in lines, pattern
    assert "!.env.example" in lines
