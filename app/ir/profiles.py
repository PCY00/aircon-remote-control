"""Pluggable remote-control profiles built on the protocol-neutral parser."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.ir.parser import IrParseError, analyze_capture


class RemoteProfile(Protocol):
    """A model-specific interpretation layer for captured packets."""

    profile_id: str
    display_name: str

    def analyze(self, raw: str) -> dict[str, object]: ...


@dataclass(frozen=True)
class GenericRemoteProfile:
    profile_id: str = "generic"
    display_name: str = "Generic raw IR remote"

    def analyze(self, raw: str) -> dict[str, object]:
        return analyze_capture(raw)


@dataclass(frozen=True)
class Carrier1621415597Profile:
    """Known framing facts for the Carrier remote marked 16214-15597."""

    profile_id: str = "carrier-16214-15597"
    display_name: str = "Carrier 16214-15597 air-conditioner remote"

    def analyze(self, raw: str) -> dict[str, object]:
        analysis = analyze_capture(raw)
        frames = analysis["frames"]
        assert isinstance(frames, list)
        bit_counts = [frame["bit_count"] for frame in frames]
        if any(bit_count != 48 for bit_count in bit_counts):
            raise IrParseError(
                "Carrier 16214-15597 packets must contain 48 bits (6 bytes) per frame"
            )
        analysis["profile"] = {
            "id": self.profile_id,
            "display_name": self.display_name,
            "expected_bits_per_frame": 48,
            "validation": "matched",
        }
        return analysis


class ProfileRegistry:
    """Resolve profiles without coupling API and capture service to remote models."""

    def __init__(self, profiles: list[RemoteProfile] | None = None) -> None:
        supplied = profiles or [GenericRemoteProfile(), Carrier1621415597Profile()]
        self._profiles = {profile.profile_id: profile for profile in supplied}

    def get(self, profile_id: str) -> RemoteProfile:
        try:
            return self._profiles[profile_id]
        except KeyError as exc:
            available = ", ".join(sorted(self._profiles))
            raise KeyError(f"unknown profile '{profile_id}'; available: {available}") from exc

    def list(self) -> list[dict[str, str]]:
        return [
            {"id": profile.profile_id, "display_name": profile.display_name}
            for profile in sorted(self._profiles.values(), key=lambda item: item.profile_id)
        ]
