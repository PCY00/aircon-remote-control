"""Ensure preview and conflict handling preserve remote-owned files."""

import base64
import hashlib
import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]/'scripts/android'))
import apply_a50_central as installer


@pytest.fixture
def device(tmp_path, monkeypatch):
    device_home, device_prefix = tmp_path/'phone-home', tmp_path/'phone-prefix'
    device_home.mkdir()
    device_prefix.mkdir()
    monkeypatch.setattr(installer.Path, 'home', lambda: device_home)
    monkeypatch.setenv('PREFIX', str(device_prefix))
    return device_home, device_prefix


def test_fresh_preview_creates_no_files(device, tmp_path):
    before = set(tmp_path.rglob('*'))
    installer.install({'release_id': 'reviewed', 'files': {}}, apply=False)
    assert set(tmp_path.rglob('*')) == before


def test_untracked_remote_directory_is_preserved(device):
    device_home, _ = device
    root = device_home/'services/aircon-central'
    root.mkdir(parents=True)
    original = root/'owner-note.txt'
    original.write_text('preserve')
    with pytest.raises(RuntimeError, match='Untracked'):
        installer.install({'release_id': 'reviewed', 'files': {}}, apply=True)
    assert original.read_text() == 'preserve'
    assert not (root/'.venv').exists()


def test_modified_managed_source_stops_before_install(device, monkeypatch):
    device_home, _ = device
    root = device_home/'services/aircon-central'
    root.mkdir(parents=True)
    source = root/'owned.py'
    source.write_text('remote owner change')
    ledger = {'managed': {str(source): hashlib.sha256(b'original').hexdigest()}}
    (root/'deployment.json').write_text(json.dumps(ledger))

    def no_process(*args, **kwargs):
        raise AssertionError('Dependency or service mutation must not run')

    monkeypatch.setattr(installer.subprocess, 'run', no_process)
    with pytest.raises(RuntimeError, match='Remote managed file changed'):
        installer.install({'release_id': 'reviewed', 'files': {}}, apply=True)
    assert source.read_text() == 'remote owner change'


def test_untracked_boot_hook_is_not_overwritten(device):
    device_home, _ = device
    hook = device_home/'.termux/boot/20-start-central'
    hook.parent.mkdir(parents=True)
    hook.write_text('owner hook')
    with pytest.raises(RuntimeError, match='Untracked hook'):
        installer.install({'release_id': 'reviewed', 'files': {}}, apply=True)
    assert hook.read_text() == 'owner hook'


def fresh_install(device, monkeypatch, *, discovered_after):
    """Run a first install with runsvdir already running and a delayed service rescan."""
    _, device_prefix = device
    service = device_prefix/'var/service/aircon-central'
    hooks = ('termux/run', 'termux/finish', 'termux/log-run', 'termux/20-start-central')
    files = {name: base64.b64encode(b'#!/bin/sh\n').decode() for name in hooks}
    files['requirements.txt'] = base64.b64encode(b'').decode()
    clock, sleeps, calls = [0.0], [0], []

    def sleep(seconds):
        clock[0] += seconds
        sleeps[0] += 1
        if discovered_after is not None and sleeps[0] >= discovered_after:
            (service/'supervise').mkdir(exist_ok=True)
            (service/'supervise/ok').touch()

    def run(command, **kwargs):
        calls.append((list(command), (service/'supervise/ok').exists()))
        return installer.subprocess.CompletedProcess(command, 0)

    class Ready:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'ready'

    fake_time = types.SimpleNamespace(
        monotonic=lambda: clock[0], sleep=sleep, time_ns=lambda: 0
    )
    monkeypatch.setattr(installer, 'time', fake_time)
    monkeypatch.setattr(installer.os, 'umask', lambda mask: 0)
    monkeypatch.setattr(installer.subprocess, 'run', run)
    monkeypatch.setattr(installer.urllib.request, 'urlopen', lambda *a, **k: Ready())
    monkeypatch.setattr(
        installer.Path, 'symlink_to',
        lambda self, target, target_is_directory=False: self.write_text(str(target)),
    )
    return calls, lambda: installer.install(
        {'release_id': 'reviewed', 'files': files}, apply=True
    )


def test_fresh_install_waits_for_runit_supervise_before_enable(device, monkeypatch):
    calls, install = fresh_install(device, monkeypatch, discovered_after=12)
    install()
    enable = [ready for command, ready in calls if command[0] == 'sv-enable']
    assert enable == [True]


def test_fresh_install_stops_when_runit_never_discovers_service(device, monkeypatch):
    calls, install = fresh_install(device, monkeypatch, discovered_after=None)
    with pytest.raises(RuntimeError, match='runit has not discovered'):
        install()
    assert not [command for command, _ in calls if command[0] == 'sv-enable']
