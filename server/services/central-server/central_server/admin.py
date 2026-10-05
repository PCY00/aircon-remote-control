"""Operator-only hub provisioning; credentials go to a new private file, never stdout."""
import argparse
import json
import os
from pathlib import Path
from central_server.households import Households
from central_server.storage import ready


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['provision-hub'])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    database = Path(os.environ.get('A50_CENTRAL_DATA_DIR') or
                    Path.home()/'.local/share/aircon-central')/'central.sqlite3'
    if not ready(database):
        parser.error('Existing central database is unavailable')
    with args.output.open('x', encoding='utf-8') as output:
        args.output.chmod(0o600)
        result = Households(database).provision_hub()
        json.dump(result, output)
        output.flush()
        os.fsync(output.fileno())
    print('HUB_PROVISIONED=PASS CREDENTIAL_OUTPUT=private_file CLAIM_VALID_SECONDS=600')


if __name__ == '__main__':
    main()
