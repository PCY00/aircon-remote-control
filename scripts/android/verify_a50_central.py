"""Verify the foundation; recovery and reboot tests require explicit flags."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from a50_adb import A50ADB
from a50_record import PhoneSession

PROBE = '''import concurrent.futures, hashlib, json, os, platform, socket, sqlite3
import time, urllib.request
from pathlib import Path
root=Path.home()/"services/aircon-central"
db=Path.home()/".local/share/aircon-central/central.sqlite3"
state=Path.home()/".local/state/aircon-central"
service=Path(os.environ["PREFIX"])/"var/service/aircon-central"
with sqlite3.connect(db.resolve().as_uri()+"?mode=ro",uri=True) as conn:
 identity=conn.execute("SELECT * FROM runtime_metadata").fetchall()
 assert conn.execute("PRAGMA integrity_check").fetchone()==("ok",)
print("DATABASE_INTEGRITY=ok")
ssh_boot=Path.home()/".termux/boot/10-start-ssh"
baseline=state/"verification-baseline.json"
if SAVE_BASELINE:
 baseline.write_text(json.dumps({"identity":identity,"ssh_boot_sha256":hashlib.sha256(ssh_boot.read_bytes()).hexdigest()}))
 print("PRIVATE_PERSISTENCE_BASELINE_SAVED=TRUE")
elif CHECK_BASELINE:
 expected=json.loads(baseline.read_text())
 assert identity==[tuple(x) for x in expected["identity"]]
 assert hashlib.sha256(ssh_boot.read_bytes()).hexdigest()==expected["ssh_boot_sha256"]
 print("DATABASE_IDENTITY_PERSISTED=TRUE\\nSSH_BOOT_SCRIPT_UNCHANGED=TRUE")
ledger=json.loads((root/"deployment.json").read_text())
assert (root/"current").resolve()==Path(ledger["release"])
for filename,expected in ledger["managed"].items():
 assert hashlib.sha256(Path(filename).read_bytes()).hexdigest()==expected
print("MANAGED_SOURCE_AND_HOOK_CHECKSUMS=PASS")
def request(path):
 with urllib.request.urlopen("http://127.0.0.1:8001"+path,timeout=3) as response:
  return response.status,json.loads(response.read())
print("LIVE="+json.dumps(request("/health/live")))
print("READY="+json.dumps(request("/health/ready")))
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 replies=list(pool.map(lambda _:request("/health/ready"),range(8)))
 assert all(status==200 and body["status"]=="ready" for status,body in replies)
print("CONCURRENT_READINESS_8_REQUESTS_4_CLIENTS=PASS")
with socket.socket() as sock:
 sock.settimeout(2)
 assert sock.connect_ex((PHONE_ADDRESS,8001))!=0
print("LAN_INTERFACE_8001_NOT_LISTENING=PASS")
pid=int((service/"supervise/pid").read_text())
command=Path("/proc")/str(pid)/"cmdline"
assert b"central_server" in command.read_bytes().split(b"\\0")
status=(Path("/proc")/str(pid)/"status").read_text()
rss=next(x.split(":",1)[1].strip() for x in status.splitlines() if x.startswith("VmRSS:"))
print("SERVER_RSS="+rss)
print("PYTHON_VERSION="+platform.python_version())
for name in ("sshd","ssh-agent"):
 assert (service.parent/name/"down").exists()
print("EXISTING_SSH_SERVICE_DOWN_MARKERS_PRESERVED=TRUE")
if EXERCISE:
 os.kill(pid,9)
 print("CONTROLLED_WORKER_SIGKILL=ONE_REQUEST")
 deadline=time.monotonic()+40
 while time.monotonic()<deadline:
  time.sleep(1)
  try:
   new=int((service/"supervise/pid").read_text())
   if new!=pid and request("/health/ready")[0]==200:break
  except (OSError,ValueError):pass
 else:raise RuntimeError("Bounded worker restart failed")
 assert not (service/"down").exists()
 history=json.loads((state/"restart-state.json").read_text())
 assert len(history["failures"])==1
 print("WORKER_PID_CHANGED=TRUE\\nSINGLE_CRASH_BUDGET_RECORDED=TRUE\\nWORKER_AUTOMATIC_RECOVERY=PASS")
print("CENTRAL_RUNTIME_PROBE=PASS")
'''


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exercise-recovery', action='store_true')
    parser.add_argument('--reboot', action='store_true')
    args = parser.parse_args()
    session = PhoneSession('central-runtime-verification')

    def probe(*, save=False, check=False, exercise=False):
        variables = (f'SAVE_BASELINE={save!r}\nCHECK_BASELINE={check!r}\nEXERCISE={exercise!r}\n'
                     f'PHONE_ADDRESS={session.config["host"]!r}\n')
        session.run('python -', data=(variables+PROBE).encode(), timeout=90,
                    label='python - < verified runtime probe '
                    '[database integrity, checksum, health, loopback, persistence, worker]')

    probe(save=args.exercise_recovery or args.reboot, exercise=args.exercise_recovery)
    if args.exercise_recovery:
        probe(check=True)
    if not args.reboot:
        return
    adb = A50ADB(Path('.deploy/a50/adb.json'))
    endpoint = adb.connect(timeout=40)
    session.log('$ adb [verified paired A50] reboot [one request]')
    start = time.monotonic()
    try:
        response = adb.run('-s', endpoint, 'reboot', timeout=10)
        session.log('REBOOT_REQUEST_EXIT='+str(response.returncode))
    except subprocess.TimeoutExpired:
        session.log('REBOOT_RESPONSE_TIMEOUT=10s; request not repeated')
    time.sleep(5)
    endpoint = adb.connect(timeout=300, rediscover=True)
    session.log('HANDS_FREE_REBOOT_ADB_SECONDS='+str(round(time.monotonic()-start,1)))
    probe(check=True)
    response = adb.run('-s', endpoint, 'shell', 'input keyevent 3; input keyevent 223', timeout=15)
    session.log('$ adb [verified A50] shell [home then screen off]\nEXIT_CODE='
                +str(response.returncode))
    if response.returncode:
        raise RuntimeError('Screen-off request failed')
    for index in range(1,9):
        time.sleep(15)
        if not adb.verify(endpoint):
            raise RuntimeError('Screen-off ADB connection lost')
        session.run('curl --fail --silent --max-time 5 http://127.0.0.1:8001/health/ready',
                    label='curl [phone loopback]/health/ready [screen off '+str(index)+'/8]')
    probe(check=True)
    response = adb.run('-s', endpoint, 'shell', 'am broadcast -a com.aircon.a50manager.STATUS '
                       '-n com.aircon.a50manager/.StatusReceiver', timeout=15)
    output = (response.stdout+response.stderr).decode('utf-8',errors='replace')
    session.log('$ adb [verified A50] shell [manager status]\n'+output)
    if response.returncode or 'interactive=false' not in output:
        raise RuntimeError('Final screen-off status failed')
    session.log('CENTRAL_HANDS_FREE_REBOOT_AND_SCREEN_OFF_TWO_MINUTES=PASS')


if __name__ == '__main__':
    main()
