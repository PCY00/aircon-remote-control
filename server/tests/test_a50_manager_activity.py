"""Opening the exported manager Activity must not run recovery; only the explicit paths do."""

import re
from pathlib import Path

MANAGER = Path(__file__).parents[1] / "android/a50-manager"
SOURCES = MANAGER / "src/com/aircon/a50manager"


def method_body(source: str, signature: str) -> str:
    start = source.index(signature)
    depth = 0
    for index in range(source.index("{", start), len(source)):
        depth += {"{": 1, "}": -1}.get(source[index], 0)
        if depth == 0:
            return source[start : index + 1]
    raise AssertionError("Unbalanced method body")


def test_activity_lifecycle_does_not_restore_wireless_debugging():
    source = (SOURCES / "MainActivity.java").read_text(encoding="utf-8")
    assert "restore(" not in method_body(source, "public void onResume(")
    # onCreate may only wire the explicit buttons; drop their listener bodies before checking.
    outside_listeners = re.sub(
        r"new View\.OnClickListener\(\) \{.*?\n\s*\}\);",
        "",
        method_body(source, "public void onCreate("),
        flags=re.DOTALL,
    )
    assert "restore(" not in outside_listeners
    assert source.count("Maintenance.restore(") == 1
    enable_button = method_body(source, "public void onClick(View view)")
    assert "Maintenance.setEnabled(MainActivity.this, true)" in enable_button
    assert "Maintenance.restore(MainActivity.this)" in enable_button


def test_explicit_recovery_paths_are_kept():
    for name, call in [
        ("BootReceiver", "Maintenance.restore(context)"),
        ("RecoveryJob", "Maintenance.restore(this)"),
        ("RecoveryReceiver", "Maintenance.restore(context)"),
    ]:
        assert call in (SOURCES / (name + ".java")).read_text(encoding="utf-8")


def test_manifest_version_moved_past_the_installed_0_4_0():
    manifest = (MANAGER / "AndroidManifest.xml").read_text(encoding="utf-8")
    assert int(re.search(r'android:versionCode="(\d+)"', manifest).group(1)) >= 5
    assert re.search(r'android:versionName="0\.4\.[1-9]"', manifest)
