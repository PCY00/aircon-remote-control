"""Stop only our recorded disposable APK fixture process; preserve production data."""

from a50_record import PhoneSession

SCRIPT = """
import json,os,signal
from pathlib import Path
info=Path.home()/'.local/state/family-apk-fixture.json'
if not info.exists():print('FIXTURE_ALREADY_STOPPED=TRUE')
else:
    values=json.loads(info.read_text()); pid=int(values['pid']); root=Path(values['root'])
    if not root.name.startswith('family-apk-fixture-'):
        raise RuntimeError('Unrecognized fixture path')
    command=Path('/proc')/str(pid)/'cmdline'
    if command.exists():
        expected=str(root/'fixture_server.py').encode()
        if expected not in command.read_bytes().split(b'\\0'):
            raise RuntimeError('PID does not belong to recorded fixture; preserved')
        os.kill(pid,signal.SIGTERM)
        print('RECORDED_ISOLATED_FIXTURE_PROCESS_STOPPED=TRUE')
    else:print('FIXTURE_ALREADY_STOPPED=TRUE')
print('PRODUCTION_SERVICE_AND_DATABASE=UNCHANGED')
"""
if __name__ == "__main__":
    PhoneSession("family-fixture-stop").run(
        "python -",
        data=SCRIPT.encode(),
        label="python - < stop_family_fixture.py [recorded fixture PID and exact command verified]",
    )
