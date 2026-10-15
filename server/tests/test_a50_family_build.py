"""Build staging must not keep private inputs or pile up old copies under the build root."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parents[1] / "scripts/android"
sys.path.insert(0, str(SCRIPTS))
import build_family_app as build  # noqa: E402

PRIVATE = ("private-build.json", "local.properties", "app/src/fixture/assets/test-fixture.json")
RELEASE = "app/build/outputs/apk/production/release/app-production-release.apk"
DEBUG = "app/build/outputs/apk/production/debug/app-production-debug.apk"
REPORT = "app/build/test-results/testProductionDebugUnitTest/TEST-unit.xml"
FIREBASE = {
    "project_info": {"project_id": "unit-project", "project_number": "123456789012"},
    "client": [
        {
            "client_info": {
                "android_client_info": {"package_name": "com.aircon.family"},
                "mobilesdk_app_id": "1:123456789012:android:unit",
            },
            "oauth_client": [{"client_type": 3, "client_id": "unit.apps.googleusercontent.com"}],
            "api_key": [{"current_key": "unit-api-key"}],
        }
    ],
}


def stage_with(root, name, age):
    stage = root / name
    for relative in PRIVATE + ("app/build/intermediates/merged/junk.bin", RELEASE, REPORT):
        path = stage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")
    stamp = time.time() - age
    os.utime(stage, (stamp, stamp))
    return stage


def test_prune_keeps_only_the_newest_two_stages(tmp_path):
    root = tmp_path / "family-android-build"
    stages = [stage_with(root, "project-" + str(i), age=i * 100) for i in range(4)]
    (root / "project-file").write_text("not a directory")
    assert build.prune_stages(root) == stages[2:]
    assert [stage.exists() for stage in stages] == [True, True, False, False]
    assert (root / "project-file").exists()


def test_scrub_removes_private_inputs_and_intermediates_but_keeps_outputs(tmp_path):
    stage = stage_with(tmp_path, "project-x", age=0)
    build.scrub_stage(stage)
    assert not any((stage / relative).exists() for relative in PRIVATE)
    assert not (stage / "app/build/intermediates").exists()
    assert (stage / RELEASE).is_file() and (stage / REPORT).is_file()


class Recorder:
    def __init__(self):
        self.lines = []

    def log(self, value):
        self.lines.append(value)


def test_build_scrubs_its_stage_and_prunes_old_ones(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tmp").mkdir()
    home = tmp_path / "home"
    root = home / ".codex/family-android-build"
    old = [stage_with(root, "project-old" + str(i), age=(i + 1) * 100) for i in range(3)]
    monkeypatch.setattr(build.Path, "home", classmethod(lambda cls: home))
    private = tmp_path / ".deploy/family-app"
    private.mkdir(parents=True)
    (private / "tools.json").write_text(
        json.dumps({"java_home": "jdk", "sdk": "C:\\unit\\sdk", "gradle": "gradle"})
    )
    (private / "signing.json").write_text(
        json.dumps({"signing_file": "unit.p12", "signing_password_file": "unit.txt"})
    )
    (private / "google-services.json").write_text(json.dumps(FIREBASE))
    source = tmp_path / "android/family-app/app/src/main"
    source.mkdir(parents=True)
    (source / "Unit.java").write_text("class Unit {}")
    recorder = Recorder()
    monkeypatch.setattr(build, "PhoneSession", lambda label: recorder)

    def gradle(command, cwd, **kwargs):
        stage = Path(cwd)
        config = json.loads((stage / "private-build.json").read_text())
        assert config["FIREBASE_API_KEY"] == "unit-api-key" and (stage / "local.properties").is_file()
        for relative in (DEBUG, RELEASE, "app/build/intermediates/dex/junk.bin", REPORT):
            path = stage / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(relative)
        return subprocess.CompletedProcess(command, 0, "BUILD SUCCESSFUL", "")

    monkeypatch.setattr(build.subprocess, "run", gradle)
    monkeypatch.setattr(sys, "argv", ["build_family_app.py"])
    build.main()
    stage = Path(json.loads((private / "last-build.json").read_text())["stage"])
    assert stage.parent == root and stage.is_dir()
    assert not any((stage / relative).exists() for relative in PRIVATE)
    assert not (stage / "app/build/intermediates").exists()
    assert (stage / RELEASE).is_file() and (stage / REPORT).is_file()
    assert [stage.exists() for stage in old] == [True, True, False]
    assert set(json.loads((tmp_path / "tmp/family-app-build/build.json").read_text())) == {
        "family-debug.apk",
        "family-release.apk",
    }
    assert "OLD_BUILD_STAGES_REMOVED=1" in recorder.lines
    assert "STAGE_PRIVATE_INPUTS_AND_INTERMEDIATES_REMOVED=TRUE" in recorder.lines


def test_failed_build_still_scrubs_private_inputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tmp").mkdir()
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    monkeypatch.setattr(build.Path, "home", classmethod(lambda cls: home))
    private = tmp_path / ".deploy/family-app"
    private.mkdir(parents=True)
    (private / "tools.json").write_text(
        json.dumps({"java_home": "jdk", "sdk": "C:\\unit\\sdk", "gradle": "gradle"})
    )
    (private / "signing.json").write_text(
        json.dumps({"signing_file": "unit.p12", "signing_password_file": "unit.txt"})
    )
    (private / "google-services.json").write_text(json.dumps(FIREBASE))
    (tmp_path / "android/family-app/app").mkdir(parents=True)
    (tmp_path / "android/family-app/app/Unit.java").write_text("class Unit {}")
    monkeypatch.setattr(build, "PhoneSession", lambda label: Recorder())
    monkeypatch.setattr(
        build.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 1, "", "FAILURE"),
    )
    monkeypatch.setattr(sys, "argv", ["build_family_app.py"])
    with pytest.raises(RuntimeError, match="build failed"):
        build.main()
    stages = list((home / ".codex/family-android-build").glob("project-*"))
    assert len(stages) == 1
    assert not any((stages[0] / relative).exists() for relative in PRIVATE)
