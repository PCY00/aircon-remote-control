"""Run an explicit SSH script and preserve its sanitized real output for the blog."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from a50_adb import A50ADB


class PhoneSession:
    def __init__(self, label: str):
        self.config = json.loads(Path('.deploy/a50/connection.json').read_text(encoding='utf-8'))
        self.redactor = A50ADB(Path('.deploy/a50/adb.json'))
        directory = Path('docs/assets/terminal')
        number = max(int(p.name.split('-')[0]) for p in directory.glob('*.txt')) + 1
        self.record = directory / f'{number:02d}-a50-{label}.txt'
        self.record.write_text('# Actual phone SSH operations; private details removed\n\n',
                               encoding='utf-8')

    def log(self, value: str):
        safe = self.redactor.redact(value)
        for private in (str(Path.cwd()), str(Path.home()), self.config['identity_file'],
                        self.config['known_hosts_file']):
            safe = safe.replace(private, '[REDACTED_LOCAL_PATH]')
        with self.record.open('a', encoding='utf-8') as stream:
            stream.write(safe + '\n')
        print(safe, flush=True)

    def command(self) -> list[str]:
        c = self.config
        return ['ssh', '-i', c['identity_file'], '-p', str(c['port']),
                '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
                '-o', 'StrictHostKeyChecking=yes',
                '-o', 'UserKnownHostsFile=' + c['known_hosts_file'],
                '-o', 'ConnectTimeout=10', c['user'] + '@' + c['host']]

    def run(self, command: str, *, label: str | None = None, data: bytes | None = None,
            timeout: int = 120) -> bytes:
        self.log('$ SSH [verified host key] ' + (label or command))
        result = subprocess.run(self.command() + [command], input=data,
                                capture_output=True, timeout=timeout)
        self.log((result.stdout + result.stderr).decode('utf-8', errors='replace')
                 + '\nEXIT_CODE=' + str(result.returncode))
        if result.returncode:
            raise RuntimeError('Remote operation failed; later steps were not run.')
        return result.stdout


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', required=True)
    parser.add_argument('--script', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z0-9-]+', args.label):
        parser.error('Invalid capture label')
    session = PhoneSession(args.label)
    script = args.script.read_bytes()
    session.log('# Executed script:\n' + script.decode('utf-8'))
    session.run('sh -s', label='sh -s < '+args.script.as_posix(), data=script, timeout=args.timeout)


if __name__ == '__main__':
    main()
