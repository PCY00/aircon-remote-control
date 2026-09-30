"""Exercise firmware staging and device selection without an SDK or hardware."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHELL = shutil.which("pwsh") or shutil.which("powershell")
pytestmark = pytest.mark.skipif(os.name != "nt" or not SHELL, reason="Windows helper")


@pytest.fixture
def environment(tmp_path: Path) -> dict:
    project = tmp_path / "프로젝트"
    (project / "scripts").mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/esp32_h2_firmware.ps1", project / "scripts")
    firmware = project / "firmware/esp32-h2-ir-node"
    (firmware / "main/nested").mkdir(parents=True)
    for name in ("CMakeLists.txt", "sdkconfig.defaults", "main/main.c", "main/nested/profile.h"):
        (firmware / name).write_text("test source\n", encoding="utf-8")
    idf = tmp_path / "idf"
    (idf / "tools").mkdir(parents=True)
    (idf / "tools/idf.py").touch()
    (idf / "export.ps1").write_text(
        """function global:idf.py {
    Add-Content -LiteralPath $env:TEST_IDF_CALLS -Value ($args -join ' ')
    if ($args[0] -eq 'set-target') {
        Set-Content -LiteralPath sdkconfig -Value 'CONFIG_IDF_TARGET="esp32h2"'
    }
    $global:LASTEXITCODE = [int]$env:TEST_IDF_EXIT
}
Set-Content -LiteralPath $env:TEST_EXPORTED_TOOLS -Value $env:IDF_TOOLS_PATH
""",
        encoding="utf-8",
    )
    return {"project": project, "idf": idf, "root": tmp_path / "builds", "tmp": tmp_path}


def invoke(environment: dict, *arguments: str) -> subprocess.CompletedProcess:
    temp = environment["tmp"]
    process_env = os.environ | {
        "TEST_IDF_CALLS": str(temp / "calls.txt"),
        "TEST_EXPORTED_TOOLS": str(temp / "tools.txt"),
        "TEST_IDF_EXIT": str(environment.get("exit", 0)),
        "IDF_TOOLS_PATH": str(temp / "existing-tools"),
    }
    return subprocess.run(
        [
            SHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(environment["project"] / "scripts/esp32_h2_firmware.ps1"),
            *arguments,
            "-IdfPath", str(environment["idf"]),
            "-BuildRoot", str(environment["root"]),
        ],
        env=process_env, capture_output=True, timeout=30, check=False,
    )


def test_flash_requires_explicit_port_before_sdk_or_device_access(environment: dict) -> None:
    result = invoke(environment, "flash")
    assert result.returncode != 0
    assert b"Specify the connected board" in result.stderr
    assert not (environment["tmp"] / "calls.txt").exists()
    assert not environment["root"].exists()


def test_recursive_staging_preserves_tools_path_and_initializes_target_once(
    environment: dict,
) -> None:
    assert invoke(environment, "build").returncode == 0
    stages = list(environment["root"].iterdir())
    assert len(stages) == 1
    assert stages[0].name.isascii()
    assert (stages[0] / "main/nested/profile.h").read_text() == "test source\n"
    assert (environment["tmp"] / "tools.txt").read_text().strip() == str(
        environment["tmp"] / "existing-tools"
    )
    assert invoke(environment, "flash", "-Port", "COM12").returncode == 0
    assert (environment["tmp"] / "calls.txt").read_text().splitlines() == [
        "set-target esp32h2", "build", "-p COM12 flash",
    ]


def test_another_checkout_gets_independent_build_directory(environment: dict) -> None:
    assert invoke(environment, "build").returncode == 0
    other = environment["tmp"] / "another-checkout"
    shutil.copytree(environment["project"], other)
    assert invoke(environment | {"project": other}, "build").returncode == 0
    assert len(list(environment["root"].iterdir())) == 2


def test_wrong_existing_target_is_not_flashed(environment: dict) -> None:
    assert invoke(environment, "build").returncode == 0
    stage = next(environment["root"].iterdir())
    (stage / "sdkconfig").write_text('CONFIG_IDF_TARGET="esp32c3"\n')
    result = invoke(environment, "flash", "-Port", "COM12")
    assert result.returncode != 0
    assert b"not for esp32h2" in result.stderr
    assert (environment["tmp"] / "calls.txt").read_text().splitlines() == [
        "set-target esp32h2", "build",
    ]


def test_failed_idf_action_is_not_reported_as_success(environment: dict) -> None:
    result = invoke(environment | {"exit": 7}, "build")
    assert result.returncode != 0
    assert b"idf.py failed with exit code 7" in result.stderr
