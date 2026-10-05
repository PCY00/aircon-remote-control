"""Preview or install the SSH boot file, refusing to replace an unknown existing file."""

import argparse
import base64
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "android"))
from a50_record import PhoneSession  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    source = Path("scripts/android/start-a50-ssh.sh").read_bytes().replace(b"\r\n", b"\n")
    script = """import base64,hashlib,os,subprocess
from pathlib import Path
content=base64.b64decode(CONTENT)
path=Path.home()/'.termux/boot/10-start-ssh'
if path.exists() and path.read_bytes()!=content:
    raise RuntimeError('Existing boot file differs; keep it and investigate')
print('BOOT_SOURCE_SHA256='+hashlib.sha256(content).hexdigest())
if APPLY and not path.exists():
    os.umask(0o077)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as output: output.write(content)
    path.chmod(0o700)
if APPLY:
    subprocess.run(['sh','-n',str(path)],check=True)
print('BOOT_FILE_READY='+str(APPLY)+' SSH_RESTARTED=False')
"""
    prefix = (
        "CONTENT=" + repr(base64.b64encode(source).decode()) + "\nAPPLY=" + repr(args.apply) + "\n"
    )
    record = PhoneSession("reader-ssh-boot-" + ("apply" if args.apply else "preview"))
    record.log("LOCAL_BOOT_SOURCE_SHA256=" + hashlib.sha256(source).hexdigest())
    record.run(
        "python -",
        data=(prefix + script).encode(),
        timeout=25,
        label="install reader SSH boot script; preserve existing files; "
        + ("apply" if args.apply else "preview"),
    )


if __name__ == "__main__":
    main()
