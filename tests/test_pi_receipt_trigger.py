"""Native readiness, including the JUnit class prefix, gates the single operational test."""

import importlib.util
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture
def trigger(monkeypatch):
    calls = []

    class FakeRecord:
        def __init__(self, label):
            self.label = label

        def run(self, command, **kwargs):
            calls.append((command, kwargs))

    monkeypatch.setitem(sys.modules, "pi_session", types.SimpleNamespace(PiSession=FakeRecord))
    spec = importlib.util.spec_from_file_location(
        "receipt_trigger", Path(__file__).parents[1] / "scripts/pi/trigger_hub_receipt.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, calls


def test_junit_prefixed_readiness_triggers_exactly_one_connection_test(trigger):
    module, calls = trigger
    result = module.instrument_and_trigger(
        [
            sys.executable,
            "-c",
            "print('OwnHubSmokeTest:INSTRUMENTATION_STATUS: hub_receipt_wait="
            "ready_for_real_pi_connection_event'); print('OK (1 test)')",
        ]
    )
    assert result.returncode == 0 and b"OK (1 test)" in result.stdout
    assert len(calls) == 1
    assert b"--connection-test" in calls[0][1]["data"]


def test_failed_native_preflight_preserves_output_and_never_sends_pi_event(trigger):
    module, calls = trigger
    result = module.instrument_and_trigger([sys.executable, "-c", "print('FAILURES!!!')"])
    assert result.returncode == 1
    assert b"FAILURES!!!" in result.stdout and b"NOT_READY" in result.stderr
    assert calls == []
