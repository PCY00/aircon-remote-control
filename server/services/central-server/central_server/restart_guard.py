"""Bound abnormal runit restarts; leave management SSH operational."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

LIMIT = 5
WINDOW = 300


def record_failure(state: Path, service: Path, *, status: int, signal: int, now: float) -> int:
    if signal in (2, 15):
        return 0  # Explicit service stop/restart does not count as a crash.
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = state / 'restart-state.json'
    try:
        history = json.loads(path.read_text(encoding='utf-8'))['failures'] if path.exists() else []
        if not isinstance(history, list) or not all(isinstance(x, (int, float)) for x in history):
            raise ValueError('Invalid restart history')
    except (ValueError, KeyError, OSError):
        # Ambiguous history fails closed rather than silently resetting the budget.
        history = [now] * LIMIT
    recent = [x for x in history if now-x < WINDOW]
    recent.append(now)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'failures': recent[-LIMIT:], 'last_exit': status,
                                     'last_signal': signal}), encoding='utf-8')
    temporary.replace(path)
    if len(recent) >= LIMIT:
        (service / 'down').touch(mode=0o600)
        # Send runsv 'down' without waiting for the current finish hook to exit.
        try:
            fd = os.open(service/'supervise/control', os.O_WRONLY | os.O_NONBLOCK)
            try:
                os.write(fd, b'd')
            finally:
                os.close(fd)
        except (OSError, AttributeError):
            pass  # down file also persists across daemon/phone restarts.
        print('CENTRAL_RESTART_BLOCKED limit=5 window_seconds=300', flush=True)
    else:
        print(f'CENTRAL_ABNORMAL_EXIT attempt={len(recent)}/5', flush=True)
    return len(recent)


def main():
    os.umask(0o077)
    state = Path.home() / '.local/state/aircon-central'
    count = record_failure(state, Path.cwd(), status=int(sys.argv[1]),
                           signal=int(sys.argv[2]), now=time.time())
    if 0 < count < LIMIT:
        time.sleep(min(count*5, 20))


if __name__ == '__main__':
    main()
