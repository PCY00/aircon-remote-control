"""Check cleanup guards and preservation of the actual original enabled state."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts/android"))
import a50_app_cleanup as cleanup


def dump(flags="HAS_CODE", shared=""):
    return (
        "\r\nPackages:\r\n  Package [com.google.android.youtube] (abc):\r\n"
        f"    pkgFlags=[ {flags} ]\r\n{shared}"
        "    User 0: ceDataInode=123 installed=true hidden=false enabled=1\r\n"
        "Hidden system packages:\r\n  Package [com.google.android.youtube] (old):\r\n"
        "    pkgFlags=[ SYSTEM HAS_CODE ]\r\n"
        "    User 0: ceDataInode=0 installed=true hidden=false enabled=0\r\n"
    )


def test_active_updated_package_is_used_instead_of_hidden_original():
    assert cleanup.active_package_state(dump(), "com.google.android.youtube") == {
        "installed": True, "enabled": 1, "data_inode": "123"
    }


@pytest.mark.parametrize("flags,shared", [
    ("PERSISTENT HAS_CODE", ""),
    ("HAS_CODE", "    sharedUser=SharedUserSetting{system}\r\n"),
])
def test_system_identity_or_persistent_process_is_rejected(flags, shared):
    with pytest.raises(RuntimeError, match="Persistent/shared"):
        cleanup.active_package_state(dump(flags, shared), "com.google.android.youtube")


def test_modified_allowlist_cannot_disable_a_core_app():
    state = {"installed": True, "enabled": 0}
    apps = {package: dict(state) for package in cleanup.APPS}
    apps["com.termux"] = dict(state)
    with pytest.raises(RuntimeError, match="allowlist"):
        cleanup.validate_baseline({"schema": 1, "apps": apps})
    with pytest.raises(RuntimeError, match="Unreviewed"):
        cleanup.restore_command("com.android.settings", state)


def test_restore_preserves_default_vs_explicitly_enabled_state():
    package = "com.google.android.youtube"
    assert cleanup.restore_command(package, {"enabled": 0}) == (
        "pm default-state --user 0 " + package
    )
    assert cleanup.restore_command(package, {"enabled": 1}) == "pm enable --user 0 " + package
    with pytest.raises(RuntimeError):
        cleanup.restore_command(package, {"enabled": 3})


def test_self_named_shared_identity_requires_actual_singleton_membership():
    text = dump(shared="    sharedUser=SharedUserSetting{abc com.google.android.youtube/10001}\r\n")
    with pytest.raises(RuntimeError):
        cleanup.active_package_state(text, "com.google.android.youtube")
    assert cleanup.active_package_state(
        text, "com.google.android.youtube", verified_singleton_uid=True
    )["enabled"] == 1
    other = dump(shared="    sharedUser=SharedUserSetting{abc android.uid.system/1000}\r\n")
    with pytest.raises(RuntimeError):
        cleanup.active_package_state(
            other, "com.google.android.youtube", verified_singleton_uid=True
        )
