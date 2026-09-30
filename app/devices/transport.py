"""Transport boundary between semantic device commands and physical hardware."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections import deque
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Protocol
from uuid import uuid4


class TransportError(RuntimeError):
    """Base class for failures while handing a command to device hardware."""


class InvalidTransmissionError(TransportError):
    """Raised when a checked-in command cannot be rendered safely."""


class TransportUnavailableError(TransportError):
    """Raised when the configured sender command or device is unavailable."""


class TransportExecutionError(TransportError):
    """Raised when the hardware sender returns an error or times out."""


class DeviceTransport(Protocol):
    """Contract implemented by Mock, local IR, and future Zigbee transports."""

    def status(self) -> dict[str, object]: ...

    def send(
        self,
        *,
        device_id: str,
        profile_id: str,
        command: dict[str, object],
    ) -> dict[str, object]: ...

    def list(self) -> list[dict[str, object]]: ...


def _positive_integer(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InvalidTransmissionError(f"{field} must be a positive integer")
    return value


def _parse_frames(value: object) -> list[list[int]]:
    if not isinstance(value, list) or not value:
        raise InvalidTransmissionError("frames_hex must be a non-empty list")

    frames: list[list[int]] = []
    for frame_index, raw_frame in enumerate(value):
        if not isinstance(raw_frame, list) or not raw_frame:
            raise InvalidTransmissionError(f"frames_hex[{frame_index}] must contain bytes")
        if len(raw_frame) > 64:
            raise InvalidTransmissionError("an IR frame cannot exceed 64 bytes")
        frame: list[int] = []
        for byte_index, raw_byte in enumerate(raw_frame):
            if not isinstance(raw_byte, str) or len(raw_byte) != 2:
                raise InvalidTransmissionError(
                    f"frames_hex[{frame_index}][{byte_index}] must be two hex digits"
                )
            try:
                byte = int(raw_byte, 16)
            except ValueError as exc:
                raise InvalidTransmissionError(
                    f"frames_hex[{frame_index}][{byte_index}] is not hexadecimal"
                ) from exc
            frame.append(byte)
        frames.append(frame)
    return frames


def render_ir_ctl_payload(command: dict[str, object]) -> tuple[str, int, int]:
    """Render a validated model command into the raw ``ir-ctl --send`` format."""

    carrier_hz = _positive_integer(command.get("carrier_hz"), field="carrier_hz")
    if not 20_000 <= carrier_hz <= 500_000:
        raise InvalidTransmissionError("carrier_hz must be between 20000 and 500000")

    bit_order = command.get("bit_order")
    if bit_order not in {"msb_first", "msb_first_observed"}:
        raise InvalidTransmissionError("only MSB-first IR frames are currently supported")

    timing = command.get("timing_us")
    if not isinstance(timing, dict):
        raise InvalidTransmissionError("timing_us must be an object")
    leader_pulse = _positive_integer(timing.get("leader_pulse"), field="leader_pulse")
    leader_space = _positive_integer(timing.get("leader_space"), field="leader_space")
    bit_pulse = _positive_integer(timing.get("bit_pulse"), field="bit_pulse")
    zero_space = _positive_integer(timing.get("zero_space"), field="zero_space")
    one_space = _positive_integer(timing.get("one_space"), field="one_space")
    inter_frame_space = _positive_integer(
        timing.get("inter_frame_space"), field="inter_frame_space"
    )
    frames = _parse_frames(command.get("frames_hex"))

    lines = [f"carrier {carrier_hz}"]
    duration_us = 0
    for frame_index, frame in enumerate(frames):
        lines.extend((f"pulse {leader_pulse}", f"space {leader_space}"))
        duration_us += leader_pulse + leader_space
        for byte in frame:
            for shift in range(7, -1, -1):
                bit_space = one_space if byte & (1 << shift) else zero_space
                lines.extend((f"pulse {bit_pulse}", f"space {bit_space}"))
                duration_us += bit_pulse + bit_space
        lines.append(f"pulse {bit_pulse}")
        duration_us += bit_pulse
        if frame_index < len(frames) - 1:
            lines.append(f"space {inter_frame_space}")
            duration_us += inter_frame_space

    if duration_us > 2_000_000:
        raise InvalidTransmissionError("IR command duration cannot exceed 2 seconds")
    return "\n".join(lines) + "\n", duration_us, len(frames)


class _TransmissionHistory:
    def __init__(self) -> None:
        self._history_lock = Lock()
        self._transmissions: deque[dict[str, object]] = deque(maxlen=100)

    def _record(self, transmission: dict[str, object]) -> None:
        with self._history_lock:
            self._transmissions.append(deepcopy(transmission))

    def list(self) -> list[dict[str, object]]:
        with self._history_lock:
            return deepcopy(list(self._transmissions))


class MockIrTransport(_TransmissionHistory):
    """Record transmissions without touching GPIO or an appliance."""

    def __init__(self) -> None:
        super().__init__()

    def status(self) -> dict[str, object]:
        return {
            "transport": "mock-ir",
            "available": True,
            "hardware_output": False,
            "details": "commands are recorded but no IR is emitted",
        }

    def send(
        self,
        *,
        device_id: str,
        profile_id: str,
        command: dict[str, object],
    ) -> dict[str, object]:
        transmission: dict[str, object] = {
            "id": uuid4().hex,
            "status": "mock_recorded",
            "device_id": device_id,
            "profile_id": profile_id,
            "command": deepcopy(command),
            "sent_at": datetime.now(UTC).isoformat(),
            "hardware_output": False,
        }
        self._record(transmission)
        return deepcopy(transmission)


Runner = Callable[..., subprocess.CompletedProcess[str]]


class IrCtlTransport(_TransmissionHistory):
    """Send rendered pulse/space commands through a send-capable LIRC device."""

    def __init__(
        self,
        command: str,
        device: Path,
        timeout_seconds: float,
        runner: Runner | None = None,
    ) -> None:
        super().__init__()
        self._command = command
        self._device = device
        self._timeout_seconds = timeout_seconds
        self._runner = runner or subprocess.run
        self._send_lock = Lock()

    def _resolved_command(self) -> str | None:
        command_path = Path(self._command)
        if command_path.is_absolute() or command_path.parent != Path("."):
            return str(command_path) if command_path.is_file() else None
        return shutil.which(self._command)

    def status(self) -> dict[str, object]:
        command = self._resolved_command()
        if command is None:
            return {
                "transport": "ir-ctl",
                "available": False,
                "hardware_output": False,
                "command": None,
                "device": str(self._device),
                "details": f"command not found: {self._command}",
            }
        if not self._device.exists():
            return {
                "transport": "ir-ctl",
                "available": False,
                "hardware_output": False,
                "command": command,
                "device": str(self._device),
                "details": f"device not found: {self._device}",
            }

        try:
            result = self._runner(
                [command, f"--device={self._device}", "--features"],
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {
                "transport": "ir-ctl",
                "available": False,
                "hardware_output": False,
                "command": command,
                "device": str(self._device),
                "details": str(exc),
            }

        feature_output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        can_send = result.returncode == 0 and "Device can send" in feature_output
        details = (
            "send-capable LIRC device ready; physical emission is not appliance confirmation"
            if can_send
            else feature_output.strip() or f"ir-ctl --features exited {result.returncode}"
        )
        return {
            "transport": "ir-ctl",
            "available": can_send,
            "hardware_output": can_send,
            "command": command,
            "device": str(self._device),
            "details": details,
        }

    def send(
        self,
        *,
        device_id: str,
        profile_id: str,
        command: dict[str, object],
    ) -> dict[str, object]:
        payload, duration_us, frame_count = render_ir_ctl_payload(command)
        with self._send_lock:
            status = self.status()
            if not status["available"]:
                raise TransportUnavailableError(str(status["details"]))

            with tempfile.TemporaryDirectory(prefix="aircon-ir-") as temp_dir:
                send_file = Path(temp_dir) / "command.ir"
                send_file.write_text(payload, encoding="ascii", newline="\n")
                try:
                    result = self._runner(
                        [
                            str(status["command"]),
                            f"--device={self._device}",
                            f"--send={send_file}",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=self._timeout_seconds,
                        check=False,
                    )
                except subprocess.TimeoutExpired as exc:
                    raise TransportExecutionError(
                        f"ir-ctl send timed out after {self._timeout_seconds:g} seconds"
                    ) from exc
                except (OSError, subprocess.SubprocessError) as exc:
                    raise TransportExecutionError(str(exc)) from exc

            if result.returncode != 0:
                message = result.stderr.strip() or result.stdout.strip() or "ir-ctl send failed"
                raise TransportExecutionError(message)

        transmission: dict[str, object] = {
            "id": uuid4().hex,
            "status": "sent",
            "device_id": device_id,
            "profile_id": profile_id,
            "command_id": command.get("command_id"),
            "carrier_hz": command.get("carrier_hz"),
            "frame_count": frame_count,
            "duration_us": duration_us,
            "sent_at": datetime.now(UTC).isoformat(),
            "hardware_output": True,
            "appliance_state_confirmed": False,
        }
        self._record(transmission)
        return deepcopy(transmission)
