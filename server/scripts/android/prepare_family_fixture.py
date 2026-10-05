"""Prepare signed disposable identities and a separate loopback backend for APK integration."""

import base64
import json
import time
from pathlib import Path

import jwt
from a50_record import PhoneSession
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def main():
    record = PhoneSession("family-fixture-backend")
    record.run(
        "python -",
        data=b"""import socket
with socket.socket() as connection:
    connection.settimeout(1)
    if connection.connect_ex(('127.0.0.1',8765)) == 0:
        raise RuntimeError('Fixture port occupied; stop the recorded fixture first')
print('ISOLATED_FIXTURE_PORT_AVAILABLE=TRUE')
""",
        label="python - [fixture port preflight; refuse to replace running server or keys]",
    )
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )

    def token(name):
        now = int(time.time())
        return jwt.encode(
            dict(
                sub=name,
                email=name + "@example.test",
                email_verified=True,
                firebase={"sign_in_provider": "google.com"},
                auth_time=now,
                iat=now,
                exp=now + 3600,
                aud="test-project",
                iss="https://securetoken.google.com/test-project",
            ),
            key,
            algorithm="RS256",
            headers={"kid": "fixture"},
        )

    fixture = {
        "owner_token": token("owner"),
        "other_token": token("other"),
        "family_token": token("family"),
        "guest_token": token("guest"),
    }
    directory = Path(".deploy/family-app")
    directory.mkdir(exist_ok=True)
    (directory / "test-fixture.json").write_text(json.dumps(fixture))
    program = """
import os,sys,threading
from pathlib import Path
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from waitress import serve
sys.path.insert(0,str(Path.home()/'services/aircon-central/current'))
from central_server.auth import FirebaseIdentity
from central_server.households import Identity
from central_server.storage import initialize
from central_server.web import create_app
class Keys:
    def get(self): return {'fixture':load_pem_public_key(PUBLIC.encode())}
database=Path(__file__).parent/'fixture.sqlite3'
initialize(database)
app=create_app(database,identity_verifier=FirebaseIdentity('test-project',certificates=Keys()))
households=app.extensions['households']
user=households.user(Identity('https://securetoken.google.com/test-project','owner','owner@example.test'))
other=households.user(Identity('https://securetoken.google.com/test-project','other','other@example.test'))
if not households.homes(user): households.create_home(user,'시험용 우리 집')
if not households.homes(other): households.create_home(other,'접근하면 안 되는 다른 집')
family=households.user(Identity('https://securetoken.google.com/test-project','family','family@example.test'))
home=households.homes(user)[0]['id']
if not households.homes(family):
    invitation=households.invitation(home,user,'family@example.test','member')
    households.accept(family,invitation['invitation_token'])
@app.get('/v1/redirect')
def redirect(): return '',307,{'Location':'https://example.test/never-follow'}
threading.Timer(2400,lambda:os._exit(0)).start()
serve(app,host='127.0.0.1',port=8765,threads=2,expose_tracebacks=False)
""".replace("PUBLIC", repr(public), 1)
    encoded = base64.b64encode(program.encode()).decode()
    script = """
import base64,json,os,subprocess,tempfile,time,urllib.request
from pathlib import Path
os.umask(0o077)
root=Path(tempfile.mkdtemp(prefix='family-apk-fixture-'))
script=root/'fixture_server.py'
script.write_bytes(base64.b64decode(ENCODED))
python=Path.home()/'services/aircon-central/.venv/bin/python'
with (root/'fixture.log').open('wb') as log:
    process=subprocess.Popen([str(python),str(script)],stdout=log,stderr=log,start_new_session=True)
info=Path.home()/'.local/state/family-apk-fixture.json'
info.write_text(json.dumps({'root':str(root),'pid':process.pid}))
for attempt in range(20):
    if process.poll() is not None:
        raise RuntimeError('Isolated fixture exited; inspect private fixture log.')
    try:
        with urllib.request.urlopen('http://127.0.0.1:8765/health/ready',timeout=1) as response:
            if response.status==200:break
    except OSError:time.sleep(.5)
else:raise RuntimeError('Isolated fixture readiness failed')
print('ISOLATED_APK_BACKEND=READY BIND=loopback PORT=8765 '
      'AUTO_STOP_SECONDS=2400 PRODUCTION_DATABASE=UNTOUCHED')
""".replace("ENCODED", repr(encoded), 1)
    record.run(
        "python -",
        data=script.encode(),
        label="python - < prepare_family_fixture.py "
        "[signed fictional accounts, isolated temporary DB]",
        timeout=30,
    )


if __name__ == "__main__":
    main()
