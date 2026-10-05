"""Remote installer called only with the locally constructed file manifest."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install(payload: dict, *, apply: bool) -> None:
    os.umask(0o077)
    home, prefix = Path.home(), Path(os.environ['PREFIX'])
    root = home/'services/aircon-central'
    service = prefix/'var/service/aircon-central'
    ledger = root/'deployment.json'
    previous = json.loads(ledger.read_text()) if ledger.exists() else None
    if previous:
        for filename, expected in previous['managed'].items():
            if not Path(filename).is_file() or digest(Path(filename)) != expected:
                raise RuntimeError('Remote managed file changed; preserve and inspect: '+filename)
        if (root/'current').resolve() != Path(previous['release']):
            raise RuntimeError('Remote current release changed; preserve and inspect.')
    elif root.exists() or service.exists():
        raise RuntimeError('Untracked remote service directory exists; preserve and inspect.')
    hooks = {'termux/run': service/'run', 'termux/finish': service/'finish',
             'termux/log-run': service/'log/run',
             'termux/20-start-central': home/'.termux/boot/20-start-central'}
    if not previous and any(p.exists() for p in hooks.values()):
        raise RuntimeError('Untracked hook exists; preserve and inspect.')
    for name in ('sshd', 'ssh-agent'):
        existing = prefix/'var/service'/name
        if existing.exists() and not (existing/'down').exists():
            raise RuntimeError(
                'Existing SSH service unexpectedly enabled; inspect before starting.'
            )
    print('EXISTING_SSH_SERVICES_DISABLED=PASS', flush=True)
    print('PLAN_VERSION='+payload['release_id'], flush=True)
    print('PLAN_FILES='+str(len(payload['files'])), flush=True)
    print('BIND=loopback PORT=8001 DATABASE=outside_release LOG_LIMIT=1MiB_x4', flush=True)
    if not apply:
        print('PREVIEW_ONLY=NO_DEVICE_MUTATION', flush=True)
        return
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    release = root/'releases'/payload['release_id']
    release.mkdir(parents=True, exist_ok=True, mode=0o700)
    managed = {}
    for name, encoded in payload['files'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise RuntimeError('Invalid source path')
        target = release/relative
        content = base64.b64decode(encoded)
        expected = hashlib.sha256(content).hexdigest()
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if digest(target) != expected:
                raise RuntimeError('Immutable release differs; preserve and inspect.')
        else:
            target.write_bytes(content)
        managed[str(target)] = expected
    venv = root/'.venv'
    if not venv.exists():
        subprocess.run([sys.executable, '-m', 'venv', '--system-site-packages', str(venv)], check=True)
    else:
        subprocess.run([sys.executable, '-m', 'venv', '--system-site-packages', str(venv)], check=True)
    subprocess.run([str(venv/'bin/python'), '-m', 'pip', 'install',
                    '--disable-pip-version-check', '--require-virtualenv',
                    '-r', str(release/'requirements.txt')], check=True)
    subprocess.run([str(venv/'bin/python'), '-m', 'pip', 'check'], check=True)
    environment = dict(os.environ, SVDIR=str(prefix/'var/service'))
    if previous:
        subprocess.run(['sv', '-w', '15', 'down', str(service)], check=True, env=environment)
        database = home/'.local/share/aircon-central/central.sqlite3'
        if not database.is_file():
            raise RuntimeError('Existing database missing; preserve and inspect.')
        backups = home/'.local/share/aircon-central/backups'
        backups.mkdir(exist_ok=True, mode=0o700)
        backup = backups/(payload['release_id']+'-'+str(time.time_ns())+'.sqlite3')
        from contextlib import closing
        with closing(sqlite3.connect(database)) as source, closing(sqlite3.connect(backup)) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                raise RuntimeError('Database backup verification failed.')
        backup.chmod(0o600)
        print('CONSISTENT_DATABASE_BACKUP=PASS', flush=True)
    service.mkdir(parents=True, exist_ok=True)
    (service/'down').touch(mode=0o600)
    for name, target in hooks.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name+'.central-new')
        if temporary.exists():
            raise RuntimeError('Untracked temporary hook exists; preserve and inspect.')
        temporary.write_bytes((release/name).read_bytes())
        temporary.chmod(0o700)
        temporary.replace(target)
        managed[str(target)] = digest(target)
    state = home/'.local/state/aircon-central'
    logs = state/'service-log'
    logs.mkdir(parents=True, exist_ok=True, mode=0o700)
    config = logs/'config'
    config.write_text('s1048576\nn3\n', encoding='ascii')
    managed[str(config)] = digest(config)
    link = root/'current.new'
    if link.exists() or link.is_symlink():
        raise RuntimeError('Untracked staging symlink exists; preserve and inspect.')
    link.symlink_to(release, target_is_directory=True)
    link.replace(root/'current')
    result = {'schema': 1, 'release': str(release), 'managed': managed}
    temporary = ledger.with_suffix('.new')
    temporary.write_text(json.dumps(result, indent=2), encoding='utf-8')
    temporary.replace(ledger)
    if not previous:
        subprocess.run(['sh', str(hooks['termux/20-start-central'])], check=True, env=environment)
    time.sleep(2)
    subprocess.run(['sv-enable', 'aircon-central'], check=True, env=environment)
    deadline = time.monotonic()+40
    while time.monotonic() < deadline:
        try:
            url = 'http://127.0.0.1:8001/health/ready'
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    print('READINESS='+response.read().decode().strip(), flush=True)
                    break
        except (OSError, ValueError):
            time.sleep(1)
    else:
        raise RuntimeError('Service readiness failed; inspect bounded logs.')
    for filename, expected in managed.items():
        if digest(Path(filename)) != expected:
            raise RuntimeError('Post-deployment checksum mismatch.')
    subprocess.run(['sv', 'status', str(service)], check=True, env=environment)
    print('CODE_AND_HOOK_SHA256_MATCH=TRUE\nCENTRAL_DEPLOYMENT=PASS', flush=True)
