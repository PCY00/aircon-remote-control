"""Keep the A50 manager's declared minimum Android version consistent with the APIs it calls."""

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
MANAGER = ROOT / "android/a50-manager"
# Activity methods added in API 27 (Android 8.1); minSdk 26 devices must not call them.
API_27_METHODS = ("setTurnScreenOn", "setShowWhenLocked")
GUARD = re.compile(
    r"if\s*\(\s*(?:android\.os\.)?Build\.VERSION\.SDK_INT\s*>=\s*"
    r"(?:(?:android\.os\.)?Build\.VERSION_CODES\.O_MR1|27)\s*\)\s*\{\s*$"
)


def min_sdk() -> int:
    manifest = (MANAGER / "AndroidManifest.xml").read_text(encoding="utf-8")
    return int(re.search(r'android:minSdkVersion="(\d+)"', manifest).group(1))


def test_manifest_min_sdk_matches_dex_min_api():
    build = (ROOT / "scripts/android/build_a50_manager.py").read_text(encoding="utf-8")
    assert int(re.search(r'"--min-api",\s*"(\d+)"', build).group(1)) == min_sdk()


def test_api_27_activity_methods_are_guarded_below_api_27():
    unguarded = []
    for source in sorted((MANAGER / "src").rglob("*.java")):
        lines = source.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines):
            for method in API_27_METHODS:
                if re.search(r"\b" + method + r"\s*\(", line) and not (
                    min_sdk() >= 27 or (number and GUARD.search(lines[number - 1]))
                ):
                    unguarded.append(f"{source.name}:{number + 1}:{method}")
    assert unguarded == []


def test_api_26_keeps_turning_the_screen_on_with_the_window_flag():
    activity = (MANAGER / "src/com/aircon/a50manager/MainActivity.java").read_text(encoding="utf-8")
    assert "WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON" in activity
