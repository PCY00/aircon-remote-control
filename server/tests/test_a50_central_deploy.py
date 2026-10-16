"""Ensure preview and conflict handling preserve remote-owned files."""

import base64
import hashlib
import json
import os
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]/'scripts/android'))
import apply_a50_central as installer
import deploy_a50_central as deployer

SERVER = Path(__file__).parents[1]/'services/central-server'
# A PNG signature contains CR LF; a text-style normalization would corrupt every icon.
PNG = bytes.fromhex('89504e470d0a1a0a0000000d49484452')


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


def fresh_install(device, monkeypatch, *, discovered_after, extra=None):
    """Run a first install with runsvdir already running and a delayed service rescan."""
    _, device_prefix = device
    service = device_prefix/'var/service/aircon-central'
    hooks = ('termux/run', 'termux/finish', 'termux/log-run', 'termux/20-start-central')
    files = {name: base64.b64encode(b'#!/bin/sh\n').decode() for name in hooks}
    files['requirements.txt'] = base64.b64encode(b'').decode()
    files.update({name: base64.b64encode(data).decode() for name, data in (extra or {}).items()})
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


def test_release_includes_nested_web_app_files_and_keeps_binary_bytes(tmp_path):
    root = tmp_path/'central-server'
    content = {
        'requirements.txt': b'flask==3.1.3\r\n',
        '.env.example': b'A50_CENTRAL_DATA_DIR=\r\n',
        'central_server/__init__.py': b"VERSION = '0.8.0'\r\n",
        'central_server/webapp/index.html': b'<!doctype html>\r\n<title>home</title>\r\n',
        'central_server/webapp/sw.js': b'self.skipWaiting();\r\n',
        'central_server/webapp/app.webmanifest': b'{}\r\n',
        'central_server/webapp/vendor/firebase-app.js': b'export{};\r\n',
        'central_server/webapp/vendor/README.md': b'# sha256\r\n',
        'central_server/webapp/icons/icon-192.png': PNG + b'\r\n\x00\r\n',
        'central_server/webapp/favicon.ico': b'\x00\x00\x01\x00\r\n',
        'termux/run': b'#!/bin/sh\r\nexec python\r\n',
    }
    ignored = ['central_server/webapp/.DS_Store', 'central_server/webapp/.cache/x.js',
               'central_server/webapp/__pycache__/x.pyc', 'central_server/notes.md',
               'central_server/webapp/vendor/.git/HEAD']
    for name in [*content, *ignored]:
        (root/name).parent.mkdir(parents=True, exist_ok=True)
        (root/name).write_bytes(content.get(name, b'ignored\r\n'))
    sources = deployer.release_sources(root)
    assert set(sources) == set(content)
    for name, data in content.items():
        binary = name.endswith(('.png', '.ico'))
        assert sources[name] == (data if binary else data.replace(b'\r\n', b'\n')), name
    assert sources['central_server/webapp/icons/icon-192.png'].startswith(PNG)


def test_real_release_carries_the_web_app_module_and_every_web_file_unchanged():
    sources = deployer.release_sources(SERVER)
    assert 'central_server/web_app.py' in sources and 'central_server/__main__.py' in sources
    webapp = SERVER/'central_server/webapp'
    expected = {path.relative_to(SERVER).as_posix() for path in deployer.web_app_files(webapp)}
    assert expected <= set(sources)
    assert not [name for name in sources if '/.' in '/'+name.removeprefix('.env.example')
                or '__pycache__' in name]
    for name in expected:
        if not name.endswith(tuple(deployer.TEXT_SUFFIXES)):
            assert sources[name] == (SERVER/name).read_bytes(), name


def test_fresh_install_writes_nested_binary_files_byte_for_byte(device, monkeypatch):
    nested = {'central_server/webapp/icons/icon-192.png': PNG + b'\r\n\x00',
              'central_server/webapp/vendor/firebase-app.js': b'export{};\n'}
    _, install = fresh_install(device, monkeypatch, discovered_after=1, extra=nested)
    install()
    device_home, _ = device
    root = device_home/'services/aircon-central'
    release = root/'releases/reviewed'
    managed = json.loads((root/'deployment.json').read_text())['managed']
    for name, data in nested.items():
        assert (release/name).read_bytes() == data
        assert managed[str(release/name)] == hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize('name', ['../escape.js', 'central_server/../../escape.js',
                                  '..\\escape.js', 'webapp\\..\\..\\escape.js'])
def test_install_refuses_paths_leaving_the_release(device, monkeypatch, name):
    device_home, _ = device
    monkeypatch.setattr(installer.os, 'umask', lambda mask: 0)
    files = {name: base64.b64encode(b'x').decode()}
    with pytest.raises(RuntimeError, match='Invalid source path'):
        installer.install({'release_id': 'reviewed', 'files': files}, apply=True)
    assert not list(device_home.parent.rglob('escape.js'))


@pytest.mark.parametrize('name', ['/escape.js', 'C:/escape.js', 'C:escape.js', '//server/share/escape.js'])
def test_install_refuses_rooted_paths_before_writing(device, monkeypatch, name):
    # Writes are intercepted: on Windows a rooted name keeps the drive of the release folder, so
    # a missed check would otherwise write outside the test folder.
    if name != '/escape.js' and os.name != 'nt':
        pytest.skip('drive and UNC names are ordinary relative names on the POSIX phone')
    monkeypatch.setattr(installer.os, 'umask', lambda mask: 0)
    written = []
    monkeypatch.setattr(installer.Path, 'write_bytes', lambda self, data: written.append(self))

    def no_process(*args, **kwargs):
        raise AssertionError('A rooted name must stop the install before any process runs')

    monkeypatch.setattr(installer.subprocess, 'run', no_process)
    files = {name: base64.b64encode(b'x').decode()}
    with pytest.raises(RuntimeError, match='Invalid source path'):
        installer.install({'release_id': 'reviewed', 'files': files}, apply=True)
    assert written == []
