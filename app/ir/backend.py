"""IR receiver hardware abstraction and the Raspberry Pi ``ir-ctl`` adapter."""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol


class ReceiverError(RuntimeError):
    """Base class for receiver failures exposed by the service layer."""


class ReceiverUnavailableError(ReceiverError):
    """Raised when the command or LIRC device is unavailable."""


class ReceiverTimeoutError(ReceiverError):
    """Raised when no complete IR packet arrives before the timeout."""


class ReceiverExecutionError(ReceiverError):
    """Raised when ``ir-ctl`` exits unsuccessfully."""


@dataclass(frozen=True)
class ReceiverStatus:
    backend: str
    available: bool
    command: str | None
    device: str
    details: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ReceiverBackend(Protocol):
    """Boundary that lets a future receiver replace LIRC without changing the API."""

    def status(self) -> ReceiverStatus: ...

    async def capture_once(self, timeout_seconds: float) -> str: ...


class IrCtlReceiver:
    """Capture a single raw packet using Linux media-utils ``ir-ctl``."""

    def __init__(self, command: str, device: Path) -> None:
        self._command = command
        self._device = device

    def _resolved_command(self) -> str | None:
        command_path = Path(self._command)
        if command_path.is_absolute() or command_path.parent != Path("."):
            return str(command_path) if command_path.is_file() else None
        return shutil.which(self._command)

    def status(self) -> ReceiverStatus:
        command = self._resolved_command()
        device_exists = self._device.exists()
        available = command is not None and device_exists
        missing: list[str] = []
        if command is None:
            missing.append(f"command not found: {self._command}")
        if not device_exists:
            missing.append(f"device not found: {self._device}")
        return ReceiverStatus(
            backend="ir-ctl",
            available=available,
            command=command,
            device=str(self._device),
            details="ready" if available else "; ".join(missing),
        )

    async def capture_once(self, timeout_seconds: float) -> str:
        status = self.status()
        if not status.available or status.command is None:
            raise ReceiverUnavailableError(status.details)

        process = await asyncio.create_subprocess_exec(
            status.command,
            "--one-shot",
            "--receive",
            f"--device={self._device}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout_seconds)
        except TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise ReceiverTimeoutError(
                f"no complete IR packet received within {timeout_seconds:g} seconds"
            ) from exc
        except asyncio.CancelledError:
            process.kill()
            await process.communicate()
            raise

        if process.returncode != 0:
            message = stderr.decode(errors="replace").strip() or "ir-ctl failed"
            raise ReceiverExecutionError(message)
        raw = stdout.decode(errors="strict").strip()
        if not raw:
            raise ReceiverExecutionError("ir-ctl returned an empty capture")
        return raw
