"""Put the Firebase *web* app settings into the A50 private config; default is a read-only preview.

The values come from the Firebase console's web app snippet (apiKey, appId, messagingSenderId,
projectId). They are public in every browser that opens the web app, but this project still keeps
them out of the repository and out of transcripts: the snippet is pasted into a local window (or
read from a private file), sent over the verified SSH session on stdin, and only field names and
pass/fail lines are printed.

Usage (from server/):
  ..\\.venv\\Scripts\\python.exe scripts/android/set_a50_web_config.py            # preview
  ..\\.venv\\Scripts\\python.exe scripts/android/set_a50_web_config.py --apply    # write + restart
  add --from-file PATH to read the snippet from a private file instead of the paste window
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from pathlib import Path

from a50_record import PhoneSession

PATTERNS = {
    'api_key': ('apiKey', r'AIza[0-9A-Za-z_-]{35}'),
    'app_id': ('appId', r'1:[0-9]{6,20}:web:[0-9a-f]{6,40}'),
    'messaging_sender_id': ('messagingSenderId', r'[0-9]{6,20}'),
    'project_id': ('projectId', r'[a-z][a-z0-9-]{4,28}[a-z0-9]'),
}
HOST = re.compile(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}')


def parse(snippet: str) -> dict:
    """Read the console snippet (JavaScript object or JSON); every field must match its format."""
    values = {}
    for key, (name, pattern) in PATTERNS.items():
        found = re.findall(r'["\']?' + name + r'["\']?\s*:\s*["\']([^"\']+)["\']', snippet)
        if len(set(found)) != 1 or not re.fullmatch(pattern, found[0]):
            raise ValueError(f'{name} is missing, repeated or not in the expected format')
        values[key] = found[0]
    return values


def paste_window() -> str:
    import tkinter as tk
    from tkinter import messagebox
    result = {'text': ''}
    root = tk.Tk()
    root.title('Firebase 웹 앱 설정 붙여넣기')
    tk.Label(root, text='Firebase 콘솔의 웹 앱 설정(firebaseConfig)을 그대로 붙여넣으세요.').pack(padx=12, pady=(12, 4))
    box = tk.Text(root, width=72, height=12)
    box.pack(padx=12, pady=4)
    box.focus_set()

    def done():
        result['text'] = box.get('1.0', 'end')
        try:
            parse(result['text'])
        except ValueError as error:
            messagebox.showerror('형식 확인', str(error))
            return
        root.destroy()

    tk.Button(root, text='확인', command=done).pack(pady=(4, 12))
    root.attributes('-topmost', True)
    root.mainloop()
    return result['text']


REMOTE = r'''import base64,json,os,stat,subprocess,sys,time,urllib.request
from pathlib import Path
data=json.loads(base64.b64decode(PAYLOAD))
home=Path.home(); path=home/'.config/aircon-central/config.json'
config=json.loads(path.read_text()) if path.exists() else {}
assert isinstance(config,dict), 'private config is not an object'
print('CONFIG_FIELDS_BEFORE='+json.dumps(sorted(config)))
same=config.get('firebase_project_id')==data['project_id']
print('PROJECT_ID_MATCHES_SERVER='+str(same).upper())
if not same: sys.exit('Web app belongs to a different Firebase project; nothing changed.')
web={k:data[k] for k in ('api_key','app_id','messaging_sender_id','auth_domain')}
print('WEB_APP_ALREADY_SAME='+str(config.get('web_app')==web).upper())
if not APPLY:
    print('PREVIEW_ONLY=NO_DEVICE_MUTATION'); sys.exit(0)
backup=path.with_name('config.json.before-web-'+str(time.time_ns()))
fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w',encoding='utf-8') as stream: json.dump(config,stream)
updated=dict(config,web_app=web)
temporary=path.with_name('.config.json.web-new')
fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w',encoding='utf-8') as stream:
    json.dump(updated,stream); stream.flush(); os.fsync(stream.fileno())
os.replace(temporary,path)
print('CONFIG_FIELDS_AFTER='+json.dumps(sorted(json.loads(path.read_text())))+' MODE='+oct(stat.S_IMODE(path.stat().st_mode)))
prefix=Path(os.environ['PREFIX']); env=dict(os.environ,SVDIR=str(prefix/'var/service'))
subprocess.run(['sv','-w','30','restart',str(prefix/'var/service/aircon-central')],check=True,env=env)
deadline=time.monotonic()+40
while True:
    try:
        with urllib.request.urlopen('http://127.0.0.1:8001/app/config.json',timeout=2) as r:
            reply=json.loads(r.read()); break
    except Exception:
        if time.monotonic()>deadline: sys.exit('Web config did not come up; previous config kept at the backup path.')
        time.sleep(1)
firebase=reply.get('firebase',{})
print('APP_CONFIG_FIELDS='+json.dumps(sorted(firebase)))
print('APP_CONFIG_MATCHES='+str(firebase.get('apiKey')==web['api_key'] and firebase.get('appId')==web['app_id']
      and firebase.get('authDomain')==web['auth_domain'] and firebase.get('projectId')==data['project_id']).upper())
print('A50_WEB_CONFIG=PASS')
'''


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--from-file', type=Path)
    parser.add_argument('--auth-domain', default='roomrelay.top')
    args = parser.parse_args()
    if not HOST.fullmatch(args.auth_domain):
        parser.error('auth domain must be a bare hostname')
    snippet = args.from_file.read_text(encoding='utf-8') if args.from_file else paste_window()
    values = parse(snippet)
    values['auth_domain'] = args.auth_domain
    payload = base64.b64encode(json.dumps(values).encode()).decode()
    script = REMOTE.replace('PAYLOAD', repr(payload), 1).replace('APPLY', repr(args.apply), 1)
    PhoneSession('web-config-' + ('apply' if args.apply else 'preview')).run(
        '$HOME/services/aircon-central/.venv/bin/python -', data=script.encode(),
        label='python - [Firebase web app settings on stdin; values never printed]', timeout=120)


if __name__ == '__main__':
    main()
