"""Ensure preview and conflict handling preserve remote-owned files."""

import hashlib
import json
import sys
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
