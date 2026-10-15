"""Deploy a separate Quick or fixed HTTPS route; preview is the default."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from pathlib import Path

from a50_record import PhoneSession

REMOTE = r"""
import base64,hashlib,json,os,subprocess,time
from pathlib import Path
os.umask(0o077)
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def install(payload, apply):
    home, prefix = Path.home(), Path(os.environ['PREFIX'])
    fixed = payload.get('mode','quick-test') == 'fixed'
    name = 'aircon-fixed-tunnel' if fixed else 'aircon-public-tunnel'
    root = home/'services'/name
    service = prefix/'var/service'/name
    state = home/'.local/state'/name
    config_root = home/'.config'/name
    ledger = root/'deployment.json'
    previous = json.loads(ledger.read_text()) if ledger.exists() else None
    if previous:
        for path,expected in previous['managed'].items():
            if not Path(path).is_file() or digest(Path(path)) != expected:
                raise RuntimeError('Remote managed tunnel source changed; preserve and inspect.')
        if (root/'current').resolve() != Path(previous['release']):
            raise RuntimeError('Remote tunnel link changed; preserve and inspect.')
        for path,expected in previous.get('private',{}).items():
            if not Path(path).is_file() or digest(Path(path)) != expected:
                raise RuntimeError('Remote private tunnel configuration changed; preserve and inspect.')
    elif root.exists() or service.exists() or state.exists():
        raise RuntimeError('Untracked tunnel directory exists; preserve and inspect.')
    if fixed and not previous and config_root.exists():
        raise RuntimeError('Untracked private tunnel configuration; preserve and inspect.')
    vendor = prefix/'var/service/cloudflared'
    if not (vendor/'down').is_file():
        raise RuntimeError('Vendor cloudflared service unexpectedly enabled.')
    print('PLAN='+('separate_fixed_tunnel' if fixed else 'separate_quick_test_tunnel')+' ORIGIN=loopback:8001 ROUTER_CHANGES=none')
    print('SOURCE_FILES='+str(len(payload['files'])))
    print('ORIGINAL_CENTRAL_SOURCE_DATABASE_AND_SSH_HOOK=preserved')
    if not apply:
        print('PREVIEW_ONLY=NO_DEVICE_MUTATION')
        return
    private = {}
    if fixed:
        with __import__('urllib.request',fromlist=['urlopen']).urlopen('http://127.0.0.1:8001/health/ready',timeout=5) as reply:
            assert reply.status==200
        config_root.mkdir(parents=True,exist_ok=True,mode=0o700)
        credential = config_root/'tunnel.token'
        config = config_root/'config.json'
        contents = {credential:payload['token'].encode('ascii'),
                    config:json.dumps({'hostname':payload['hostname'],'token_file':str(credential)}).encode()}
        # A redeployment cannot silently rotate or overwrite an existing credential.
        for path,content in contents.items():
            if path.exists() and path.read_bytes()!=content:
                raise RuntimeError('Existing private tunnel configuration differs; preserve and inspect.')
        for path,content in contents.items():
            if not path.exists():
                with path.open('xb') as output: output.write(content)
                path.chmod(0o600)
            private[str(path)] = digest(path)
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    release = root/'releases'/payload['release_id']
    release.mkdir(parents=True,exist_ok=True,mode=0o700)
    managed = {}
    for name,encoded in payload['files'].items():
        if name not in {'tunnel.py','fixed.py','run','finish','log-run'}:
            raise RuntimeError('Unexpected source name')
        target,content = release/name,base64.b64decode(encoded)
        if target.exists() and digest(target) != hashlib.sha256(content).hexdigest():
            raise RuntimeError('Immutable release changed; preserve and inspect.')
        if not target.exists(): target.write_bytes(content)
        managed[str(target)] = digest(target)
    environment = dict(os.environ,SVDIR=str(prefix/'var/service'))
    if previous:
        subprocess.run(['sv','-w','20','down',str(service)],check=True,env=environment)
    service.mkdir(parents=True,exist_ok=True,mode=0o700)
    (service/'down').touch(mode=0o600)
    hooks = {'run':service/'run','finish':service/'finish','log-run':service/'log/run'}
    for name,target in hooks.items():
        target.parent.mkdir(parents=True,exist_ok=True)
        staging=target.with_name(target.name+'.tunnel-new')
        if staging.exists(): raise RuntimeError('Untracked temporary hook; preserve.')
        staging.write_bytes((release/name).read_bytes())
        staging.chmod(0o700)
        staging.replace(target)
        managed[str(target)] = digest(target)
    logs=state/'service-log'
    logs.mkdir(parents=True,exist_ok=True,mode=0o700)
    (logs/'config').write_text('s1048576\nn3\n',encoding='ascii')
    managed[str(logs/'config')] = digest(logs/'config')
    staging=root/'current.new'
    if staging.exists() or staging.is_symlink():
        raise RuntimeError('Untracked staging link; preserve.')
    staging.symlink_to(release,target_is_directory=True)
    staging.replace(root/'current')
    ledger.write_text(json.dumps({'release':str(release),'managed':managed,'private':private},indent=2),encoding='utf-8')
    # runsvdir discovers newly created service directories asynchronously.
    deadline = time.monotonic()+15
    while not (service/'supervise/ok').exists():
        if time.monotonic() >= deadline:
            raise RuntimeError('runit has not discovered the new service; inspect before retrying.')
        time.sleep(0.25)
    # The existing central boot hook already starts this runit service directory.
    subprocess.run(['sv-enable',service.name],check=True,env=environment)
    time.sleep(2)
    subprocess.run(['sv','status',str(service)],check=True,env=environment)
    for path,expected in managed.items():
        if digest(Path(path)) != expected: raise RuntimeError('Post-deployment checksum mismatch')
    print('TUNNEL_SOURCE_AND_HOOK_SHA256_MATCH=PASS')
    print('FIXED_HOSTNAME='+str(fixed).upper()+' OTHER_TUNNEL_SERVICE=preserved')
"""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--mode", choices=("quick-test", "fixed"), default="quick-test")
    parser.add_argument("--hostname", help="The purchased hostname, required for fixed mode")
    parser.add_argument("--token-file", type=Path, help="Private local tunnel token, never argv text")
    args = parser.parse_args()
    fixed = args.mode == "fixed"
    if fixed and (not args.hostname or not re.fullmatch(
        r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}",args.hostname
    )):
        parser.error("Fixed mode requires a plain lower-case hostname")
    if fixed and args.apply and (not args.token_file or not args.token_file.is_file()):
        parser.error("Fixed apply requires --token-file pointing to a private credential")
    root = Path("services/central-tunnel")
    files = {
        name: (root / name).read_bytes().replace(b"\r\n", b"\n")
        for name in (("tunnel.py", "fixed.py", "run", "finish", "log-run") if fixed else ("tunnel.py", "run", "finish", "log-run"))
    }
    if fixed:
        for name in ("run", "finish", "log-run"):
            files[name] = files[name].replace(b"aircon-public-tunnel", b"aircon-fixed-tunnel")
            if name != "log-run":
                files[name] = files[name].replace(b"/tunnel.py", b"/fixed.py")
    digest = hashlib.sha256()
    for name, data in sorted(files.items()):
        digest.update(name.encode() + b"\0" + data + b"\0")
    payload = {
        "release_id": ("fixed-" if fixed else "quick-") + digest.hexdigest()[:16],
        "mode": args.mode,
        "files": {name: base64.b64encode(data).decode() for name, data in files.items()},
    }
    if fixed:
        payload["hostname"] = args.hostname
        if args.apply:
            token = args.token_file.read_text(encoding="ascii").strip()
            if not re.fullmatch(r"[A-Za-z0-9_+/=-]{40,8192}", token):
                parser.error("Private token file does not contain a valid token format")
            payload["token"] = token
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    script = (
        REMOTE
        + "\ninstall(json.loads(base64.b64decode("
        + repr(encoded)
        + ")), "
        + repr(args.apply)
        + ")\n"
    )
    session = PhoneSession("tunnel-" + args.mode + "-deploy-" + ("apply" if args.apply else "preview"))
    session.log("LOCAL_TUNNEL_RELEASE=" + payload["release_id"])
    session.run(
        "python -",
        label="python - < deploy_a50_tunnel.py [checked manifest; "
        + ("apply" if args.apply else "preview")
        + "]",
        data=script.encode(),
        timeout=60,
    )


if __name__ == "__main__":
    main()
