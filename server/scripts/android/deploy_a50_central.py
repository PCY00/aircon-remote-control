"""Explicit one-way A50 foundation deployment; default is a read-only preview."""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import sys
from pathlib import Path

from a50_record import PhoneSession


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = Path('services/central-server')
    files = [root/'requirements.txt', root/'.env.example',
             *sorted((root/'central_server').glob('*.py')),
             *sorted((root/'termux').glob('*'))]
    sources = {p.relative_to(root).as_posix(): p.read_bytes().replace(b'\r\n', b'\n')
               for p in files if p.is_file()}
    checksum = hashlib.sha256()
    for name, data in sorted(sources.items()):
        checksum.update(name.encode()+b'\0'+data+b'\0')
    tree = ast.parse(sources['central_server/__init__.py'].decode())
    version = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == 'VERSION' for target in node.targets))
    payload = {'release_id': 'v'+version+'-'+checksum.hexdigest()[:16],
               'files': {name: base64.b64encode(data).decode() for name, data in sources.items()}}
    script = Path('scripts/android/apply_a50_central.py').read_text(encoding='utf-8')
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    script += ('\ninstall(json.loads(base64.b64decode('+repr(encoded)+')),'
               ' apply='+repr(args.apply)+')\n')
    session = PhoneSession('central-deploy-'+('apply' if args.apply else 'preview'))
    session.log('LOCAL_RELEASE='+payload['release_id'])
    for name, content in sources.items():
        session.log('SOURCE_SHA256='+hashlib.sha256(content).hexdigest()+' '+name)
    session.run('python -', label='python - < locally versioned apply_a50_central.py '
                '[checked source manifest; '+('apply' if args.apply else 'preview')+']',
                data=script.encode(), timeout=600)


if __name__ == '__main__':
    main()
