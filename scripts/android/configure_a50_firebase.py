"""Store the verified project ID privately; refuse unexpected configuration changes."""
import argparse
import json
import sys
from a50_record import PhoneSession


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-id',required=True)
    args = parser.parse_args()
    from pathlib import Path
    sys.path.insert(0,str(Path('services/central-server').resolve()))
    from central_server.auth import FirebaseIdentity
    FirebaseIdentity(args.project_id)
    script = '''
import json,os,subprocess
from pathlib import Path
os.umask(0o077)
desired = CONFIG
path = Path.home()/'.config/aircon-central/config.json'
if path.exists():
    if json.loads(path.read_text()) != desired:
        raise RuntimeError('Unexpected existing configuration; preserve and inspect.')
else:
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with path.open('x') as output:
        json.dump(desired,output)
        output.flush(); os.fsync(output.fileno())
    path.chmod(0o600)
service = Path(os.environ['PREFIX'])/'var/service/aircon-central'
subprocess.run(['sv','-w','15','restart',str(service)],check=True)
print('FIREBASE_PROJECT_CONFIGURATION=private_file CONFIG_PERMISSIONS=0600')
'''.replace('CONFIG',repr({'firebase_project_id':args.project_id}),1)
    PhoneSession('firebase-private-config').run('python -',data=script.encode(),
        label='python - < configure_a50_firebase.py [verified project ID; value redacted]',timeout=45)


if __name__ == '__main__': main()
