"""Check URL selection, bounded recovery, and remote-change preservation."""

import importlib.util
import json
import logging
import subprocess
import sys
import types
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


def test_fixed_credential_stays_out_of_process_arguments(tmp_path):
    credential = tmp_path / "tunnel.token"
    credential.write_text("private-credential" * 8)
    credential.chmod(0o600)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"hostname": "house.example.com", "token_file": str(credential)}))
    config.chmod(0o600)
    # Windows chmod cannot express Unix owner-only mode; remote execution uses POSIX.
    if sys.platform == "win32":
        pytest.skip("POSIX owner-only credential check")
    command, url = tunnel.fixed_command(config)
    assert url == "https://house.example.com"
    assert "--token-file" in command and str(credential) == command[-1]
    assert credential.read_text() not in " ".join(command)
    credential.chmod(0o644)
    with pytest.raises(ValueError, match="owner-only"):
        tunnel.fixed_command(config)


@pytest.mark.parametrize("hostname", ["https://example.com", "example.com/path", "x.example.com?key=x", "-bad.example.com", "example.com:443"])
def test_fixed_rejects_hostname_with_extra_url_parts(tmp_path, hostname):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"hostname": hostname, "token_file": str(tmp_path / "token")}))
    with pytest.raises(ValueError, match="configuration"):
        tunnel.fixed_command(config)


def stop_during(monkeypatch, tmp_path, phase):
    """Run the supervisor with SIGTERM delivered inside the final probe or inside the spawn."""
    handlers, events = {}, []
    shim = types.SimpleNamespace(SIGTERM=15, SIGINT=2, SIGALRM=14,
                                 signal=handlers.__setitem__, alarm=lambda s: events.append(("alarm", s)))
    monkeypatch.setattr(tunnel, "signal", shim)
    monkeypatch.setattr(tunnel, "STATE", tmp_path / "state")

    class Ready:
        status = 200
        def __enter__(self):
            if phase == "probe":
                handlers[15](15, None)
            return self
        def __exit__(self, *args):
            pass

    class Child:
        returncode = None
        def __init__(self, *args, **kwargs):
            events.append("spawn")
            if phase == "spawn":
                handlers[15](15, None)
            self.stdout = self.lines()
        def lines(self):
            events.append("read")
            if self.returncode is None:
                yield "Visit https://four-random-test-words.trycloudflare.com\n"
                yield "Registered tunnel connection\n"
        def poll(self):
            return self.returncode
        def terminate(self):
            events.append("terminate")
            self.returncode = -15
        def wait(self, timeout=None):
            return self.returncode
        kill = terminate

    monkeypatch.setattr(tunnel.urllib.request, "urlopen", lambda *a, **k: Ready())
    monkeypatch.setattr(tunnel, "subprocess", types.SimpleNamespace(
        Popen=Child, PIPE=-1, STDOUT=-2, TimeoutExpired=subprocess.TimeoutExpired))
    logger = logging.getLogger("tunnel")
    try:
        code = tunnel.run()
    finally:
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)
    return code, events, json.loads((tmp_path / "state/endpoint.json").read_text())


def test_stop_during_final_probe_never_starts_tunnel(monkeypatch, tmp_path):
    code, events, endpoint = stop_during(monkeypatch, tmp_path, "probe")
    assert code == 0 and "spawn" not in events
    assert endpoint["status"] == "stopped" and endpoint["url"] is None


def test_stop_during_spawn_terminates_before_reading(monkeypatch, tmp_path, capsys):
    code, events, endpoint = stop_during(monkeypatch, tmp_path, "spawn")
    assert code == 0 and events.index("terminate") < events.index("read")
    assert endpoint["status"] == "stopped" and endpoint["url"] is None
    assert "TUNNEL_CONNECTED" not in capsys.readouterr().out


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


def test_fixed_preview_preserves_quick_service_and_writes_no_credential(remote, tmp_path):
    install, home, prefix = remote
    quick = home / "services/aircon-public-tunnel"
    quick.mkdir(parents=True)
    (quick / "owner.txt").write_text("keep running")
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    install({"release_id": "fixed-test", "mode": "fixed", "hostname": "house.example.com", "files": {}}, False)
    after = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert before == after
    assert not (home / ".config/aircon-fixed-tunnel").exists()


def test_fixed_untracked_credentials_are_not_overwritten(remote):
    install, home, _ = remote
    private = home / ".config/aircon-fixed-tunnel"
    private.mkdir(parents=True)
    (private / "tunnel.token").write_text("owner credential")
    with pytest.raises(RuntimeError, match="Untracked private"):
        install({"mode": "fixed", "files": {}}, True)
    assert (private / "tunnel.token").read_text() == "owner credential"


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
