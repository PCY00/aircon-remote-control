import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render_sw_component_diagram.py"


def load():
    spec = importlib.util.spec_from_file_location("render_sw_component_diagram", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_component_sources_exist_and_svg_is_self_contained():
    module = load()
    if not all(path.is_file() for path in module.FONT_FILES.values()):
        pytest.skip("Malgun Gothic is needed for the label-width check")
    svg = module.render()
    assert svg.startswith("<svg") and "<script" not in svg and "href=" not in svg
    assert "<image" not in svg and "@import" not in svg
    for title in ("Controls (control.py)", "LocalController", "DeviceService", "ZCL airconIr 0xFF00"):
        assert title in svg


def test_committed_svg_matches_generator():
    module = load()
    if not all(path.is_file() for path in module.FONT_FILES.values()):
        pytest.skip("Malgun Gothic is needed for the label-width check")
    assert module.OUTPUT.read_text(encoding="utf-8") == module.render()
