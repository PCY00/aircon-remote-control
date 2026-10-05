"""Check URL selection, bounded recovery, and remote-change preservation."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location(
    "a50_tunnel", ROOT / "services/central-tunnel/tunnel.py"
)
tunnel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tunnel)
sys.path.insert(0, str(ROOT / "scripts/android"))
from deploy_a50_tunnel import REMOTE  # noqa: E402


def test_endpoint_is_https_quick_hostname():
    assert (
        tunnel.quick_url("Visit https://four-random-test-words.trycloudflare.com |")
        == "https://four-random-test-words.trycloudflare.com"
    )
    assert tunnel.quick_url("https://api.trycloudflare.com") is None
    assert tunnel.quick_url("https://example.com") is None
    assert tunnel.quick_url("http://four-random-test-words.trycloudflare.com") is None


def test_stop_does_not_count_and_repeated_failures_disable(tmp_path):
    state, service = tmp_path / "state", tmp_path / "service"
    service.mkdir()
    assert tunnel.record_failure(state, service, status=0, sig=0, now=1) == 0
    assert tunnel.record_failure(state, service, status=1, sig=15, now=1) == 0
    assert not state.exists()
    for count in range(1, 6):
        assert tunnel.record_failure(state, service, status=1, sig=0, now=count) == count
    assert (service / "down").is_file()


def test_expired_failures_and_corrupt_history(tmp_path):
    state, service = tmp_path / "state", tmp_path / "service"
    state.mkdir()
    service.mkdir()
    (state / "restart-state.json").write_text(json.dumps({"failures": [1, 2, 3, 4]}))
    assert tunnel.record_failure(state, service, status=1, sig=0, now=400) == 1
    (state / "restart-state.json").write_text("corrupt")
    assert tunnel.record_failure(state, service, status=1, sig=0, now=401) == 5
    assert (service / "down").exists()


def test_restart_removes_stale_url(tmp_path):
    tunnel.save_endpoint(tmp_path, status="connected", url="https://test.trycloudflare.com", pid=1)
    tunnel.save_endpoint(tmp_path, status="starting", url=None, pid=2)
    value = json.loads((tmp_path / "endpoint.json").read_text())
    assert value["url"] is None and value["status"] == "starting"


@pytest.fixture
def remote(tmp_path, monkeypatch):
    home, prefix = tmp_path / "home", tmp_path / "prefix"
    home.mkdir()
    (prefix / "var/service/cloudflared").mkdir(parents=True)
    (prefix / "var/service/cloudflared/down").touch()
    namespace = {}
    exec(REMOTE, namespace)
    monkeypatch.setattr(namespace["Path"], "home", lambda: home)
    monkeypatch.setenv("PREFIX", str(prefix))
    return namespace["install"], home, prefix


def test_preview_has_no_mutations(remote, tmp_path):
    install, _, _ = remote
    before = set(tmp_path.rglob("*"))
    install({"release_id": "test", "files": {}}, False)
    assert set(tmp_path.rglob("*")) == before


def test_untracked_remote_source_is_preserved(remote):
    install, home, _ = remote
    root = home / "services/aircon-public-tunnel"
    root.mkdir(parents=True)
    note = root / "note.txt"
    note.write_text("preserve")
    with pytest.raises(RuntimeError, match="Untracked"):
        install({"release_id": "test", "files": {}}, True)
    assert note.read_text() == "preserve"


def test_modified_remote_source_stops_before_mutation(remote):
    install, home, _ = remote
    root = home / "services/aircon-public-tunnel"
    root.mkdir(parents=True)
    source = root / "tunnel.py"
    source.write_text("owner modification")
    (root / "deployment.json").write_text(json.dumps({"managed": {str(source): "expected"}}))
    with pytest.raises(RuntimeError, match="changed"):
        install({"release_id": "test", "files": {}}, True)
    assert source.read_text() == "owner modification"
