"""Run the fixed hostname separately, keeping the Quick Tunnel available for rollback."""

import os
import sys
import time
from pathlib import Path

from tunnel import record_failure, run

STATE = Path.home() / ".local/state/aircon-fixed-tunnel"
SERVICE = Path(os.environ["PREFIX"]) / "var/service/aircon-fixed-tunnel"
CONFIG = Path.home() / ".config/aircon-fixed-tunnel/config.json"

if __name__ == "__main__":
    os.umask(0o077)
    if len(sys.argv) > 1 and sys.argv[1] == "finish":
        count = record_failure(
            STATE, SERVICE, status=int(sys.argv[2]), sig=int(sys.argv[3]), now=time.time()
        )
        if 0 < count < 5:
            time.sleep(min(5 * count, 20))
    else:
        raise SystemExit(run(state=STATE, config_path=CONFIG))
