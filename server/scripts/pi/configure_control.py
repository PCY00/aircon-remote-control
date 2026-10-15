"""Preview by default; enable control through the existing paired Pi and private API only."""

import argparse
import base64
import json
import subprocess
import sys
from pathlib import Path

from pi_session import PiSession

PROBE = r'''
import hashlib,ipaddress,json,os,subprocess,sys,time,urllib.request
from pathlib import Path
home=Path.home()
path=home/'.config/aircon-central-agent/config.json'
raw=path.read_bytes()
config=json.loads(raw)
assert set(config) in ({'endpoint','hub_token','source_data_dir'}, {'endpoint','hub_token','source_data_dir','control_origin'})
fingerprint=hashlib.sha256(raw).hexdigest()
if expected is not None:
 assert fingerprint==expected, 'Private configuration changed; preserve and inspect'
pid=subprocess.run(['systemctl','--user','show','aircon-controller','--property=MainPID','--value'],check=True,capture_output=True,text=True).stdout.strip()
args=(Path('/proc')/pid/'cmdline').read_bytes().decode().split('\0')
host=args[args.index('--host')+1];port=args[args.index('--port')+1]
assert port=='8001'
if host=='0.0.0.0': host='127.0.0.1'
address=ipaddress.ip_address(host)
if not address.is_loopback:
 own=subprocess.run(['tailscale','ip','-4'],check=True,capture_output=True,text=True).stdout.strip()
 assert host==own and address in ipaddress.ip_network('100.64.0.0/10')
origin='http://'+host+':8001'
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open(origin+'/api/v1/devices',timeout=5) as response:
 rows=json.load(response)['items']
count=sum(d.get('profile_id')=='air_conditioner/Carrier/CS-A061GS' and isinstance(d.get('zigbee_binding'),dict) and d['zigbee_binding'].get('type')=='h2_ir' for d in rows)
assert count>0, 'No supported, linked air conditioner'
with opener.open(urllib.request.Request(target+'/health/ready',headers={'User-Agent':'FamilySmartHome-ConnectivityCheck/0.1'}),timeout=5) as response:
 assert response.status==200 and json.load(response)['database']=='ok'
# An older deployed agent rejects control_origin and would also stop the notification relay.
sys.path.insert(0,str(home/'services/aircon-central-agent/current'))
try:
 from agent import control_origin as check_origin,load_config
 check_origin(origin);supported=True
except (ImportError,ValueError):
 supported=False
if apply:
 assert expected is not None
 assert supported, 'Deployed agent lacks control support; deploy the agent first'
 backup=path.with_name('config.before-control-'+str(time.time_ns())+'.json')
 with backup.open('xb') as output: output.write(raw)
 backup.chmod(0o600)
 config.update(endpoint=target,control_origin=origin)
 temporary=path.with_suffix('.control-new')
 with temporary.open('x',encoding='utf-8') as output: json.dump(config,output)
 temporary.chmod(0o600)
 try: load_config(temporary)
 except Exception: temporary.unlink();raise
 temporary.replace(path)
 try:
  subprocess.run(['systemctl','--user','restart','aircon-central-agent'],check=True)
  # Watch several loops: an agent that exits shows as activating/failed while systemd waits 20 s.
  for _ in range(6):
   time.sleep(4)
   assert subprocess.run(['systemctl','--user','is-active','aircon-central-agent'],capture_output=True,text=True).stdout.strip()=='active'
 except Exception:
  restore=path.with_suffix('.control-restore')
  restore.unlink(missing_ok=True)
  with restore.open('xb') as output: output.write(raw)
  restore.chmod(0o600);restore.replace(path)
  subprocess.run(['systemctl','--user','restart','aircon-central-agent'],check=True)
  raise AssertionError('Agent did not stay active; previous configuration restored')
print(json.dumps({'fingerprint':fingerprint,'supported_device_count':count,'control_enabled':apply,'agent_control_supported':supported,'private_api_origin_verified':True,'central_health_ready':True}))
'''


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    from urllib.parse import urlsplit
    target=json.loads(Path('.deploy/a50/tunnel-endpoint.json').read_text())['endpoint']['url']
    parsed=urlsplit(target)
    if parsed.scheme!='https' or not parsed.hostname or parsed.path not in ('','/') or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.port not in (None,443):
        raise RuntimeError('Verified current HTTPS origin required')
    cache=Path('.deploy/pi-central-agent/control-config-preview.json')
    expected=json.loads(cache.read_text())['fingerprint'] if args.apply else None
    record=PiSession('pi-control-config-'+('apply' if args.apply else 'preview'))
    script='target='+repr(target)+'\nexpected='+repr(expected)+'\napply='+repr(args.apply)+'\n'+PROBE
    result=subprocess.run(record.command()+['python3 -'],input=script.encode(),capture_output=True,timeout=90)
    if result.returncode:
        record.log('CONTROL_CONFIGURATION=FAILED PRIVATE_DETAILS_NOT_LOGGED=TRUE')
        raise RuntimeError('Pi configuration preflight failed; private state preserved')
    data=json.loads(result.stdout)
    if not args.apply:
        cache.write_text(json.dumps({'fingerprint':data.pop('fingerprint')}))
    else:
        data.pop('fingerprint')
    record.log('$ configure_control.py '+('--apply' if args.apply else '[preview; no remote mutation]'))
    record.log(json.dumps(data,sort_keys=True))
    record.log('EXISTING_HUB_TOKEN_PRESERVED=TRUE NO_NEW_PORT_OR_FIREWALL_CHANGE=TRUE')


if __name__=='__main__':
    main()
