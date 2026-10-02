"""Send one real Pi connection event only after the own native test reports readiness."""

from __future__ import annotations

import queue
import subprocess
import threading
import time

from pi_session import PiSession


def instrument_and_trigger(command):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines = queue.Queue()

    def read():
        for line in iter(process.stdout.readline, b""):
            lines.put(line)
        lines.put(None)

    threading.Thread(target=read, daemon=True).start()
    output = bytearray()
    triggered = False
    deadline = time.monotonic() + 125
    try:
        while time.monotonic() < deadline:
            line = lines.get(timeout=max(0.1, deadline - time.monotonic()))
            if line is None:
                break
            output.extend(line)
            if line.strip().endswith(
                b"INSTRUMENTATION_STATUS: hub_receipt_wait=ready_for_real_pi_connection_event"
            ):
                if triggered:
                    raise RuntimeError("Unexpected duplicate native readiness")
                record = PiSession("pi-real-connection-test")
                script = """import subprocess
from pathlib import Path
active=subprocess.run(['systemctl','--user','is-active','aircon-central-agent'],
                      capture_output=True)
assert active.stdout.strip()!=b'active', 'Start service only after initial receipt test'
agent=Path.home()/'services/aircon-central-agent/current/agent.py'
subprocess.run(['/usr/bin/python3',str(agent),'--once','--connection-test'],check=True)
"""
                record.run(
                    "python3 -",
                    data=script.encode(),
                    timeout=25,
                    label="queue and send one real hub.connection_test [no sensor fabrication]",
                )
                triggered = True
        result = process.wait(timeout=max(0.1, deadline - time.monotonic()))
        return subprocess.CompletedProcess(
            command,
            result if triggered else 1,
            bytes(output),
            b"" if triggered else b"PI_TRIGGER_SKIPPED_NATIVE_NOT_READY\n",
        )
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        process.stdout.close()
