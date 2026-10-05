"""Preview/install an explicitly authorized, server-only FCM credential via private SSH stdin."""

import argparse
import base64
import json
import sys
from pathlib import Path

from a50_record import PhoneSession
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key

REMOTE = """
import base64,json,os,sys,subprocess,urllib.request,time
from pathlib import Path
try:
    os.umask(0o077)
    private=Path.home()/'.config/aircon-central'
    config_path=private/'config.json'
    config=json.loads(config_path.read_text())
    info=json.loads(base64.b64decode(PAYLOAD))
    assert info['project_id']==config['firebase_project_id']
    assert info['client_email']=='a50-fcm-sender@'+info['project_id']+'.iam.gserviceaccount.com'
    credential=private/'fcm-service-account.json'
    desired=(json.dumps(info,sort_keys=True)+'\\n').encode()
    if credential.exists():
        assert credential.read_bytes()==desired, 'Existing credential differs; preserve and inspect'
    if config.get('fcm_service_account_file'):
        assert config['fcm_service_account_file']==str(credential)
    print('CREDENTIAL_PROJECT_AND_DEDICATED_ACCOUNT=PASS CONTENT=PRIVATE',flush=True)
    if not APPLY:
        print('PREVIEW_ONLY=NO_DEVICE_MUTATION',flush=True);sys.exit(0)
    if not credential.exists():
        with credential.open('xb') as stream:stream.write(desired)
    credential.chmod(0o600)
    sys.path.insert(0,str(Path.home()/'services/aircon-central/current'))
    from central_server.fcm import FCMSender
    FCMSender(config['firebase_project_id'],credential)
    print('GOOGLE_CREDENTIAL_PARSE_AND_PRIVATE_FILE_MODE=PASS',flush=True)
    backup=private/'config.before-fcm.json'
    if not backup.exists():
        with backup.open('xb') as stream:stream.write(config_path.read_bytes())
    config['fcm_service_account_file']=str(credential)
    temporary=private/'config.fcm-new.json'
    assert not temporary.exists()
    with temporary.open('x') as stream:json.dump(config,stream)
    temporary.chmod(0o600);temporary.replace(config_path)
    env=dict(os.environ,SVDIR=os.environ['PREFIX']+'/var/service')
    service=os.environ['PREFIX']+'/var/service/aircon-central'
    subprocess.run(['sv','-w','15','restart',service],check=True,env=env,capture_output=True)
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        try:
            with urllib.request.urlopen('http://127.0.0.1:8001/health/ready',timeout=2) as response:
                assert response.status==200;break
        except OSError:time.sleep(1)
    else:raise RuntimeError('readiness failed')
    print('SERVER_RESTART_READINESS=PASS FCM_CREDENTIAL_INSTALLED=TRUE '
          'ACTUAL_DELIVERY=SEPARATE_TEST',flush=True)
except SystemExit:raise
except Exception as error:
    print('FCM_CONFIGURATION_FAILED kind='+type(error).__name__,flush=True);sys.exit(1)
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    info = json.loads(args.source.read_text(encoding="utf-8"))
    project = json.loads(Path(".deploy/family-app/google-services.json").read_text())[
        "project_info"
    ]["project_id"]
    assert info.get("type") == "service_account" and info.get("project_id") == project
    assert info.get("client_email") == "a50-fcm-sender@" + project + ".iam.gserviceaccount.com"
    assert info.get("token_uri") == "https://oauth2.googleapis.com/token"
    key = load_pem_private_key(info["private_key"].encode(), None)
    assert isinstance(key, RSAPrivateKey) and key.key_size >= 2048
    encoded = base64.b64encode(json.dumps(info).encode()).decode()
    script = "PAYLOAD=" + repr(encoded) + "\nAPPLY=" + repr(args.apply) + "\n" + REMOTE
    record = PhoneSession("fcm-credential-" + ("apply" if args.apply else "preview"))
    record.run(
        "$HOME/services/aircon-central/.venv/bin/python -",
        data=script.encode(),
        label="configure_a50_fcm.py [authorized server-only credential; private stdin; "
        + ("apply" if args.apply else "preview")
        + "]",
        timeout=60,
    )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
