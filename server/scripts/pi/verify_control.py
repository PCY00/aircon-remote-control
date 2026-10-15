"""Read-only control readiness and unauthenticated route checks; emits no IR commands."""

import sys
from pi_session import PiSession, PhoneSession

PI = r'''
import hashlib,json,sys,subprocess
from pathlib import Path
root=Path.home()/'services/aircon-central-agent'
ledger=json.loads((root/'deployment.json').read_text())
assert (root/'current').resolve()==Path(ledger['release'])
for path,expected in ledger['managed'].items():
 assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==expected
sys.path.insert(0,str(root/'current'))
from agent import load_config,LocalController
config=load_config(Path.home()/'.config/aircon-central-agent/config.json')
controller=LocalController(config['control_origin'])
devices=controller.devices()
assert devices
print('VERIFIED_LOCAL_API_SUPPORTED_AIRCON_COUNT='+str(len(devices)))
for service in ('aircon-central-agent','aircon-controller'):
 assert subprocess.run(['systemctl','--user','is-active',service],capture_output=True).stdout.strip()==b'active'
print('PI_AGENT_AND_ORIGINAL_WEB_SERVICE=active CODE_CHECKSUMS=PASS')
print('PHYSICAL_COMMANDS_SENT=0')
'''

PHONE = r'''
import json,sqlite3,sys,time,urllib.request,urllib.error
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path.home()/'services/aircon-central/current'))
from central_server.storage import SCHEMA_VERSION
db=Path.home()/'.local/share/aircon-central/central.sqlite3'
with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as conn:
 assert conn.execute('PRAGMA user_version').fetchone()==(SCHEMA_VERSION,)
 assert conn.execute('PRAGMA integrity_check').fetchone()==('ok',)
 active=conn.execute('SELECT COUNT(*) FROM control_hubs c JOIN hubs h ON h.id=c.hub_id '
                     'JOIN homes m ON m.id=h.home_id WHERE h.active=1 AND m.active=1 AND c.last_seen>?',(time.time()-25,)).fetchone()[0]
 devices=conn.execute('SELECT COUNT(*) FROM control_devices WHERE active=1').fetchone()[0]
 assert active>0 and devices>0
 print('LIVE_CONTROL_HUBS='+str(active)+' ACTIVE_CONTROL_DEVICES='+str(devices)+' DATABASE=ok SCHEMA='+str(SCHEMA_VERSION))
 fixed=Path.home()/'.local/state/aircon-fixed-tunnel/endpoint.json'
 state=json.loads((fixed if fixed.is_file() else Path.home()/'.local/state/aircon-public-tunnel/endpoint.json').read_text())
 assert state['status']=='connected' and state['url']
 origin=state['url']
for path,method,body,token in [('/v1/homes/unknown/control','GET',None,None),
 ('/v1/homes/unknown/control/commands','POST',{},None),
 ('/v1/hub/control/next','POST',{},'hub_'+'x'*43)]:
 headers={'Content-Type':'application/json','User-Agent':'FamilySmartHome-ConnectivityCheck/0.1'}
 if token: headers['Authorization']='Bearer '+token
 request=urllib.request.Request(origin+path,method=method,headers=headers,
  data=json.dumps(body).encode() if body is not None else None)
 try:
  urllib.request.urlopen(request,timeout=10)
  raise AssertionError('Unexpected authenticated route access')
 except urllib.error.HTTPError as response:
  assert response.code==401
  print('PUBLIC_ROUTE='+path+' REJECTED_AUTH=401')
print('CONTROL_READINESS=PASS NO_PHYSICAL_COMMAND_SENT=TRUE')
'''


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    PiSession('pi-control-readiness').run('python3 -',data=PI.encode(),label='verify_control.py [read-only Pi API, owned checksums and active services]')
    # The server venv: the probe imports central_server.storage for the current SCHEMA_VERSION.
    PhoneSession('central-control-readiness').run('$HOME/services/aircon-central/.venv/bin/python -',data=PHONE.encode(),label='verify_control.py [read-only control heartbeat, schema and rejected public requests]')


if __name__=='__main__':
    main()
