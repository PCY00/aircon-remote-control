"""Read-only production verification, with no real users, invites, or hub provisioning."""
from a50_record import PhoneSession

PROBE = '''
import hashlib,json,sqlite3,sys,urllib.request,urllib.error
from pathlib import Path
home = Path.home()
root = home/'services/aircon-central'
sys.path.insert(0,str(root/'current'))
from central_server.auth import Certificates
from central_server import VERSION
db = home/'.local/share/aircon-central/central.sqlite3'
baseline = json.loads((home/'.local/state/aircon-central/verification-baseline.json').read_text())
with sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True) as conn:
    assert conn.execute('PRAGMA user_version').fetchone()[0] == 2
    assert conn.execute('PRAGMA integrity_check').fetchone() == ('ok',)
    assert conn.execute('SELECT * FROM runtime_metadata').fetchall() == [tuple(x) for x in baseline['identity']]
    assert conn.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0
    assert conn.execute('SELECT COUNT(*) FROM hubs').fetchone()[0] == 0
print('SCHEMA_VERSION=2 DATABASE_INTEGRITY=ok ORIGINAL_RUNTIME_ID_PRESERVED=TRUE')
print('PRODUCTION_FIXTURE_USERS_AND_HUBS=0')
assert hashlib.sha256((home/'.termux/boot/10-start-ssh').read_bytes()).hexdigest() == baseline['ssh_boot_sha256']
print('EXISTING_SSH_BOOT_UNCHANGED=TRUE')
backups = list((db.parent/'backups').glob('*.sqlite3'))
assert backups
with sqlite3.connect(backups[-1].resolve().as_uri()+'?mode=ro',uri=True) as backup:
    assert backup.execute('PRAGMA user_version').fetchone()[0] == 1
    assert backup.execute('SELECT * FROM runtime_metadata').fetchall() == [tuple(x) for x in baseline['identity']]
print('PRE_MIGRATION_BACKUP_SCHEMA_1_AND_IDENTITY=PASS')
ledger = json.loads((root/'deployment.json').read_text())
assert (root/'current').resolve() == Path(ledger['release'])
for filename,expected in ledger['managed'].items():
    assert hashlib.sha256(Path(filename).read_bytes()).hexdigest() == expected
print('LOCAL_MANIFEST_AND_DEVICE_SOURCE_CHECKSUMS=PASS')
keys = Certificates().get()
assert keys
print('GOOGLE_HTTPS_PUBLIC_CERTIFICATE_FETCH_AND_PARSE=PASS')
def response(path,authorization=None):
    request = urllib.request.Request('http://127.0.0.1:8001'+path,
              headers={'Authorization':authorization} if authorization else {})
    try:
        with urllib.request.urlopen(request,timeout=10) as reply: return reply.status,reply.read()
    except urllib.error.HTTPError as reply: return reply.code,reply.read()
for path in ('/health/live','/health/ready'):
    status,body = response(path)
    assert status == 200
    print(path+' '+body.decode().strip())
assert response('/v1/me')[0] == 401
assert response('/v1/me','Bearer forged-token')[0] == 401
assert response('/v1/me?user_id=owner')[0] == 401
print('PRODUCTION_MISSING_AND_FORGED_CREDENTIALS=401 QUERY_ID_BYPASS=DENIED')
print('PRODUCTION_API_REAL_FIREBASE_TOKEN=NOT_YET_TESTED FCM=NOT_IMPLEMENTED')
print('A50_HOUSEHOLD_PRODUCTION_VERIFICATION=PASS')
'''

if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    PhoneSession('household-production-verification').run('$HOME/services/aircon-central/.venv/bin/python -',data=PROBE.encode(),
        label='$HOME/services/aircon-central/.venv/bin/python - < verify_a50_households.py [read-only private comparisons]',timeout=60)
