"""Preview first Pi pairing; --apply requires explicit approval for the private hub credential."""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from pi_session import ROOT, PhoneSession, PiSession

PHONE_PROBE = """import json,sqlite3,sys,time,urllib.request
from contextlib import closing
from pathlib import Path
root=Path.home()/'services/aircon-central/current'
sys.path.insert(0,str(root))
from central_server import VERSION
db=Path.home()/'.local/share/aircon-central/central.sqlite3'
with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as c:
    assert c.execute('PRAGMA integrity_check').fetchone()==('ok',)
    hubs=c.execute('SELECT COUNT(*) FROM hubs').fetchone()[0]
with urllib.request.urlopen('http://127.0.0.1:8001/health/ready',timeout=3) as r:
    assert r.status==200
print(json.dumps({'clock':time.time(),'hubs':hubs,'version':VERSION,
 'credential_exists':(Path.home()/'.config/aircon-central/pi-central-hub.json').exists()}))
"""
PI_PROBE = """import json,subprocess,time
from pathlib import Path
assert str(Path.home())=='/home/air', 'Use only the confirmed Pi user'
linger=subprocess.run(['loginctl','show-user','air','-p','Linger'],check=True,capture_output=True)
active=subprocess.run(['systemctl','--user','is-active','aircon-controller'],capture_output=True)
assert active.stdout.strip()==b'active'
print(json.dumps({'clock':time.time(),'linger':linger.stdout.strip()==b'Linger=yes',
 'config_exists':(Path.home()/'.config/aircon-central-agent').exists()}))
"""
PROVISION = """import json,os,sys
from pathlib import Path
try:
    os.umask(0o077)
    sys.path.insert(0,str(Path.home()/'services/aircon-central/current'))
    from central_server.households import Households
    db=Path.home()/'.local/share/aircon-central/central.sqlite3'
    output=Path.home()/'.config/aircon-central/pi-central-hub.json'
    with output.open('x',encoding='utf-8') as stream:
        output.chmod(0o600)
        result=Households(db).provision_hub()
        json.dump(result,stream);stream.flush();os.fsync(stream.fileno())
    print(json.dumps(result))
except Exception:
    sys.exit(1)
"""
CONFIGURE_PI = """import base64,json,os,sys
from pathlib import Path
try:
    os.umask(0o077)
    private=Path.home()/'.config/aircon-central-agent'
    private.mkdir(mode=0o700)
    data=json.loads(base64.b64decode(PRIVATE_PAYLOAD))
    data['source_data_dir']=str(Path.home()/'aircon-controller/runtime')
    output=private/'config.json'
    with output.open('x',encoding='utf-8') as stream:
        json.dump(data,stream);stream.flush();os.fsync(stream.fileno())
    output.chmod(0o600)
    sys.path.insert(0,str(Path.home()/'services/aircon-central-agent/current'))
    from agent import load_config
    load_config(output)
    print('PI_PRIVATE_CONFIG=PASS MODE=0600 CREDENTIAL_CONTENT=NOT_LOGGED')
except Exception as error:
    print('PI_PRIVATE_CONFIG_FAILED kind='+type(error).__name__);sys.exit(1)
"""
START = """import hashlib,json,subprocess,time
from pathlib import Path
root=Path.home()/'services/aircon-central-agent'
ledger=json.loads((root/'deployment.json').read_text())
assert (root/'current').resolve()==Path(ledger['release'])
for name,sha in ledger['managed'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==sha
subprocess.run(['systemctl','--user','enable','--now','aircon-central-agent'],check=True,capture_output=True)
time.sleep(6)
subprocess.run(['systemctl','--user','is-active','aircon-central-agent'],check=True)
subprocess.run(['systemctl','--user','is-enabled','aircon-central-agent'],check=True)
subprocess.run(['systemctl','--user','is-active','aircon-controller'],check=True)
print('PI_RELAY_ENABLED_AND_ORIGINAL_CONTROLLER_ACTIVE=PASS')
"""


def private_json(record, script):
    """Sensitive stdout stays in memory; never use the transcript logger for its contents."""
    command = (
        "python3 -"
        if isinstance(record, PiSession)
        else "$HOME/services/aircon-central/.venv/bin/python -"
    )
    result = subprocess.run(
        record.command() + [command], input=script.encode(), capture_output=True, timeout=30
    )
    if result.returncode or len(result.stdout) > 8192:
        raise RuntimeError("Private SSH step failed; inspect preserved state before retry")
    return json.loads(result.stdout)


def native(home, test, *extra, apply=False):
    command = [
        sys.executable,
        str(ROOT / "scripts/android/run_a50_family_smoke.py"),
        "--home-name",
        home,
        "--hub-test",
        test,
        *extra,
    ]
    if apply:
        command.append("--apply")
    subprocess.run(command, check=True, timeout=210)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home-name", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    endpoint = json.loads(Path(".deploy/a50/tunnel-endpoint.json").read_text())["endpoint"]["url"]
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed.port not in (None, 443)
    ):
        raise RuntimeError("Approved private HTTPS origin required")
    phone = PhoneSession("pi-home-pairing-" + ("apply" if args.apply else "preview"))
    p = private_json(phone, PHONE_PROBE)
    phone.log("A50_PRIVATE_READONLY_PREFLIGHT=PASS SERVER_VERSION=" + p["version"])
    pi = PiSession("pi-home-pairing-preflight")
    q = private_json(pi, PI_PROBE)
    pi.log("PI_ORIGINAL_CONTROLLER_ACTIVE=PASS LINGER=" + str(q["linger"]))
    if abs(p["clock"] - q["clock"]) > 20 or not q["linger"]:
        raise RuntimeError("Clock/boot prerequisite needs inspection; no credential created")
    if p["version"] != "0.3.1" or p["hubs"] or p["credential_exists"] or q["config_exists"]:
        raise RuntimeError("Existing pairing or unexpected version; preserve and inspect")
    native(args.home_name, "verifyOwnerBeforeProvisioning", apply=args.apply)
    subprocess.run([sys.executable, str(ROOT / "scripts/pi/deploy_central_agent.py")], check=True)
    if not args.apply:
        phone.log("PAIRING_PREVIEW_ONLY=NO_NEW_CREDENTIAL_NO_HOME_BINDING_NO_SERVICE_START")
        phone.log(
            "APPLY_PLAN=dedicated_Pi_key; normal_Google_owner_one_time_claim; "
            "skip_existing_history; real_connection_notification_once; enable_new_relay"
        )
        return
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/pi/deploy_central_agent.py"), "--apply"],
        check=True,
        timeout=120,
    )
    credential = private_json(phone, PROVISION)
    if (
        set(credential) != {"hub_id", "hub_token", "claim_code", "claim_expires_at"}
        or credential["claim_expires_at"] <= time.time() + 120
    ):
        raise RuntimeError("Private provisioning result invalid; preserve and inspect")
    phone.log("HUB_PROVISIONED=PASS SERVER_PRIVATE_COPY=0600 CLAIM_LIFETIME_SECONDS=600")
    encoded = base64.b64encode(
        json.dumps(
            {"endpoint": endpoint.rstrip("/"), "hub_token": credential["hub_token"]}
        ).encode()
    ).decode()
    pi.run(
        "python3 -",
        data=("PRIVATE_PAYLOAD=" + repr(encoded) + "\n" + CONFIGURE_PI).encode(),
        label="install dedicated hub config via private stdin; no credential in logs",
    )
    # Only the short-lived claim is staged locally; the long-lived hub key never goes to disk here.
    claim_file = Path(".deploy/a50/pairing/approved-hub-claim.json")
    claim_file.parent.mkdir(parents=True, exist_ok=True)
    with claim_file.open("x", encoding="utf-8") as stream:
        json.dump({key: credential[key] for key in ("hub_id", "claim_code")}, stream)
    try:
        native(args.home_name, "claimApprovedHub", "--claim-file", str(claim_file), apply=True)
    finally:
        claim_file.unlink()
    phone.log("EXACT_HUB_CLAIMED_BY_REAL_GOOGLE_HOME_OWNER=PASS NO_TOKEN_EXPORT=TRUE")
    pi.run(
        "/usr/bin/python3 $HOME/services/aircon-central-agent/current/agent.py --once",
        label="initialize new read-only source cursors; skip historical rows",
    )
    native(args.home_name, "observeActualHubFCM", "--trigger-pi-connection", apply=True)
    pi.run(
        "python3 -",
        data=START.encode(),
        timeout=30,
        label="verify source checksums; systemctl --user enable --now aircon-central-agent",
    )
    phone.log("REAL_PI_HOME_PAIRING_CONNECTION_EVENT_AND_FCM_RECEIPT=PASS")


if __name__ == "__main__":
    main()
