"""The published component model must match what the architecture poster draws."""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def renderer(monkeypatch):
    """Load the renderer with stand-in text metrics; links and components do not use them."""
    pdfmetrics = types.ModuleType("reportlab.pdfbase.pdfmetrics")
    pdfmetrics.stringWidth = lambda text, font, size: 0.4 * size * len(text)
    pdfmetrics.registerFont = lambda font: None
    modules = {
        "reportlab": types.ModuleType("reportlab"),
        "reportlab.lib": types.ModuleType("reportlab.lib"),
        "reportlab.lib.units": types.SimpleNamespace(mm=72 / 25.4),
        "reportlab.pdfbase": types.SimpleNamespace(pdfmetrics=pdfmetrics),
        "reportlab.pdfbase.pdfmetrics": pdfmetrics,
        "reportlab.pdfbase.ttfonts": types.SimpleNamespace(TTFont=object),
        "reportlab.pdfgen": types.SimpleNamespace(canvas=None),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location(
        "architecture_renderer_under_test", ROOT / "scripts/render_software_architecture.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_two_way_arrows_are_two_way_links(renderer):
    for diagram in [renderer.poster(), renderer.overview()]:
        assert all("reverse" in link for link in diagram.links)
        drawn = {
            tuple(map(tuple, item["points"]))
            for item in diagram.items
            if item["type"] == "arrow" and item["reverse"]
        }
        published = {tuple(map(tuple, link["points"])) for link in diagram.links if link["reverse"]}
        assert drawn and drawn == published


def test_components_labelled_external_are_drawn_external(renderer):
    for diagram in [renderer.poster(), renderer.overview()]:
        for component in diagram.components:
            text = component["title"] + " ".join(component["description"])
            if "외부" in text:
                assert component["external"], component["id"]
    poster = {component["id"]: component for component in renderer.poster().components}
    assert poster["fcm-provider"]["external"] is True


def test_committed_component_model_matches_renderer(renderer):
    committed = json.loads((ROOT / "docs/architecture/component-model.json").read_text("utf-8"))
    poster = renderer.poster()
    assert committed["components"] == json.loads(json.dumps(poster.components))
    assert committed["connections"] == json.loads(json.dumps(poster.links))
