"""Read private tunnel state and test its public TLS route without exposing auth data."""

from __future__ import annotations

import json
import argparse
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from a50_record import PhoneSession

PROBE = r"""
import hashlib,json,os,sqlite3,subprocess
from pathlib import Path
home,prefix=Path.home(),Path(os.environ['PREFIX'])
root=home/'services/aircon-public-tunnel'
ledger=json.loads((root/'deployment.json').read_text())
assert (root/'current').resolve()==Path(ledger['release'])
for path,expected in ledger['managed'].items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==expected
for path,expected in ledger.get('private',{}).items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==expected
    assert Path(path).stat().st_mode & 0o077 == 0
assert (prefix/'var/service/cloudflared/down').is_file()
assert not (prefix/'var/service/aircon-public-tunnel/down').exists()
log_config=home/'.local/state/aircon-public-tunnel/service-log/config'
assert log_config.read_text()=='s1048576\nn3\n'
result=subprocess.run(['sv','status',str(prefix/'var/service/aircon-public-tunnel')],capture_output=True,text=True)
assert result.returncode==0 and result.stdout.startswith('run:')
state=json.loads((home/'.local/state/aircon-public-tunnel/endpoint.json').read_text())
os.kill(state['supervisor_pid'],0)
central=home/'services/aircon-central'
central_ledger=json.loads((central/'deployment.json').read_text())
for path,expected in central_ledger['managed'].items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==expected
baseline=json.loads((home/'.local/state/aircon-central/verification-baseline.json').read_text())
boot_digest=hashlib.sha256((home/'.termux/boot/10-start-ssh').read_bytes()).hexdigest()
assert boot_digest==baseline['ssh_boot_sha256']
database=home/'.local/share/aircon-central/central.sqlite3'
with sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True) as conn:
    assert conn.execute('PRAGMA integrity_check').fetchone()==('ok',)
    identity=conn.execute('SELECT * FROM runtime_metadata').fetchall()
    assert identity==[tuple(x) for x in baseline['identity']]
    counts={name:conn.execute('SELECT COUNT(*) FROM '+name).fetchone()[0]
            for name in ('users','homes','hubs')}
print(json.dumps({'endpoint':state,'checksums':'PASS','vendor_disabled':True,
                  'service':result.stdout.strip(),'central_counts':counts}))
"""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixed", action="store_true")
    parser.add_argument("--hostname", help="Expected fixed hostname")
    args = parser.parse_args()
    if args.fixed and not args.hostname:
        parser.error("--fixed requires --hostname")
    session = PhoneSession("tunnel-" + ("fixed" if args.fixed else "quick") + "-public-verification")
    session.log(
        "$ SSH [verified host key] python - < verify_a50_tunnel.py [private state; metadata only]"
    )
    probe = PROBE.replace("aircon-public-tunnel", "aircon-fixed-tunnel") if args.fixed else PROBE
    result = subprocess.run(
        session.command() + ["python -"], input=probe.encode(), capture_output=True, timeout=20
    )
    if result.returncode:
        session.log(result.stderr.decode("utf-8", errors="replace"))
        raise RuntimeError("Remote tunnel verification failed; URL not delivered.")
    value = json.loads(result.stdout)
    state = value["endpoint"]
    valid_url = state.get("url") == "https://" + args.hostname if args.fixed else bool(re.fullmatch(
        r"https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com", state.get("url") or ""
    ))
    if state.get("status") != "connected" or not valid_url or state.get("mode") != ("fixed" if args.fixed else "quick-test"):
        raise RuntimeError("Tunnel is not connected; inspect private bounded logs.")
    session.log("TUNNEL_MANAGED_CHECKSUMS=PASS VENDOR_SERVICE_DISABLED=TRUE")
    session.log("CENTRAL_MANAGED_CHECKSUMS_DATABASE_IDENTITY_AND_SSH_BOOT_PRESERVED=PASS")
    session.log("PRODUCTION_COUNTS="+json.dumps(value['central_counts'],sort_keys=True))
    session.log(value["service"])
    session.log("PRIVATE_ENDPOINT_STATUS=connected FIXED_HOSTNAME=" + str(args.fixed).upper())
    url = state["url"]
    private = Path(".deploy/a50/tunnel-endpoint.json")
    private.parent.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(NoRedirect())

    def response(path, token=None):
        headers = {"User-Agent": "FamilySmartHome-ConnectivityCheck/0.1"}
        if token:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(url + path, headers=headers)
        try:
            with opener.open(request, timeout=12) as reply:
                return reply.status, reply.read(4096), reply.headers
        except urllib.error.HTTPError as reply:
            return reply.code, reply.read(4096), reply.headers

    for attempt in range(4):
        try:
            status, data, headers = response("/health/ready")
            if status == 200:
                break
        except (OSError, urllib.error.URLError):
            status = 0
        session.log("PUBLIC_EDGE_READINESS_RETRY=" + str(attempt + 1) + " STATUS=" + str(status))
        time.sleep(2)
    else:
        raise RuntimeError("Public HTTPS readiness did not pass.")
    assert json.loads(data) == {"database": "ok", "status": "ready"}
    assert "no-store" in headers.get("Cache-Control", "")
    session.log("PUBLIC_HTTPS_SYSTEM_CERTIFICATE_VALIDATION=PASS HEALTH_READY=200 DATABASE=ok")
    for path, token in [("/v1/me", None), ("/v1/homes", None), ("/v1/me", "forged-token")]:
        status, data, headers = response(path, token)
        assert status == 401, (path, status)
        assert json.loads(data).get("error") == "invalid_credentials"
        assert "no-store" in headers.get("Cache-Control", "")
        session.log(
            path + " AUTH=" + ("forged" if token else "missing") + " STATUS=401 NO_STORE=PASS"
        )
    session.log("EXTERNAL_ROUTE=PASS REAL_APP_FLOW_REQUIRES_SEPARATE_UI_VERIFICATION")
    # Do not deliver a new endpoint to Pi configuration tools before TLS and auth pass.
    if private.is_file() and args.fixed:
        backup = private.with_name("tunnel-endpoint.before-fixed.json")
        if not backup.exists():
            backup.write_bytes(private.read_bytes())
    staging = private.with_suffix(".new")
    staging.write_text(json.dumps(value, indent=2), encoding="utf-8")
    staging.replace(private)
    session.log("VERIFIED_ENDPOINT_SAVED_PRIVATELY=TRUE FIXED_HOSTNAME=" + str(args.fixed).upper())
    print("PRIVATE_DELIVERY_FILE=" + str(private))


if __name__ == "__main__":
    main()
