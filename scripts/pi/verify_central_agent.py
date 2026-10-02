"""Read-only verification of an already paired Pi relay and its A50 household binding."""

from __future__ import annotations

import sys

from pi_session import PhoneSession, PiSession

PI_PROBE = """import hashlib,json,sqlite3,stat,subprocess,sys
from contextlib import closing
from pathlib import Path
root=Path.home()/'services/aircon-central-agent'
ledger=json.loads((root/'deployment.json').read_text())
assert (root/'current').resolve()==Path(ledger['release'])
for name,sha in ledger['managed'].items():
 assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==sha
sys.path.insert(0,str(root/'current'))
from agent import load_config
config=Path.home()/'.config/aircon-central-agent/config.json'
private=load_config(config)
assert stat.S_IMODE(config.stat().st_mode)==0o600
print('MANAGED_SOURCE_AND_PRIVATE_CONFIGURATION=PASS CONFIG_MODE=0600')
state=Path.home()/'.local/state/aircon-central-agent/outbox.sqlite3'
with closing(sqlite3.connect(state.as_uri()+'?mode=ro',uri=True)) as c:
 assert c.execute('PRAGMA integrity_check').fetchone()==('ok',)
 cursors=c.execute('SELECT source,last_id FROM cursors ORDER BY source').fetchall()
 print('SOURCE_CURSORS='+json.dumps(cursors))
 count=c.execute('SELECT COUNT(*) FROM climate_cursors').fetchone()[0]
 print('CLIMATE_TRACKED_SENSOR_COUNT='+str(count))
 states=c.execute('SELECT kind,state,COUNT(*) FROM outbox GROUP BY kind,state').fetchall()
 print('OUTBOX_STATES='+json.dumps(states))
sources=[('sensors/sensors.sqlite3','door_events'),
         ('automations/automations.sqlite3','automation_events')]
for relative,table in sources:
 source=Path(private['source_data_dir'])/relative
 with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as c:
  assert c.execute('PRAGMA integrity_check').fetchone()==('ok',)
  count=c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
  print('READONLY_SOURCE_COUNT='+table+':'+str(count))
show=subprocess.run(['systemctl','--user','show','aircon-central-agent',
 '--property=ActiveState,SubState,UnitFileState,NRestarts,MainPID'],
 check=True,capture_output=True).stdout.decode()
print(show.strip())
assert 'ActiveState=active' in show and 'UnitFileState=enabled' in show
pid=next(line.split('=',1)[1] for line in show.splitlines() if line.startswith('MainPID='))
status=(Path('/proc')/pid/'status').read_text()
rss=next(line.split(':',1)[1].strip() for line in status.splitlines() if line.startswith('VmRSS:'))
print('AGENT_RSS='+rss)
subprocess.run(['systemctl','--user','is-active','aircon-controller'],check=True)
print('PAIRED_PI_RUNTIME_VERIFICATION=PASS')
"""

PHONE_PROBE = """import json,sqlite3,stat,urllib.request
from contextlib import closing
from pathlib import Path
private=Path.home()/'.config/aircon-central/pi-central-hub.json'
assert stat.S_IMODE(private.stat().st_mode)==0o600
saved=json.loads(private.read_text())
db=Path.home()/'.local/share/aircon-central/central.sqlite3'
with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as c:
 assert c.execute('PRAGMA integrity_check').fetchone()==('ok',)
 hub=c.execute('SELECT home_id,active,claim_digest FROM hubs WHERE id=?',
               (saved['hub_id'],)).fetchone()
 assert hub and hub[0] and hub[1]==1 and hub[2] is None
 print('PROVISIONED_HUB_ACTIVE_AND_ONE_TIME_CLAIM_CONSUMED=PASS')
 counts={table:c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
         for table in ('users','homes','hubs','events','installations')}
 print('CENTRAL_COUNTS='+json.dumps(counts))
 kinds=c.execute('SELECT kind,COUNT(*) FROM events WHERE home_id=? GROUP BY kind',
                 (hub[0],)).fetchall()
 print('BOUND_HOME_EVENT_KINDS='+json.dumps(kinds))
 states=c.execute('SELECT state,COUNT(*) FROM push_jobs GROUP BY state').fetchall()
 print('PUSH_STATES='+json.dumps(states))
 choices=c.execute('SELECT door,climate,warning,climate_interval_minutes '
                   'FROM notification_preferences').fetchall()
 print('PHONE_NOTIFICATION_CHOICES_ONLY='+json.dumps(choices))
with urllib.request.urlopen('http://127.0.0.1:8001/health/ready',timeout=3) as response:
 assert response.status==200
print('PAIRED_A50_DATABASE_AND_READINESS=PASS PRIVATE_PROVISIONING_MODE=0600')
"""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    PiSession("pi-paired-runtime-readonly").run(
        "python3 -",
        data=PI_PROBE.encode(),
        label="verify_central_agent.py [read-only Pi source, private modes, cursors and services]",
    )
    PhoneSession("pi-paired-central-readonly").run(
        "$HOME/services/aircon-central/.venv/bin/python -",
        data=PHONE_PROBE.encode(),
        label="verify_central_agent.py [read-only A50 private hub binding, events and readiness]",
    )


if __name__ == "__main__":
    main()
