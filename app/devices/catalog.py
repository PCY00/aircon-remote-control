"""Source-controlled device profile catalog."""

from __future__ import annotations

import json
from pathlib import Path


class ProfileNotFoundError(LookupError):
    """Raised when a requested device profile does not exist."""


class InvalidProfileError(ValueError):
    """Raised when a checked-in profile is malformed."""


class DeviceProfileCatalog:
    """Load model profiles without coupling the API to a specific appliance."""

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    @staticmethod
    def _read_object(path: Path) -> dict[str, object]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ProfileNotFoundError(path) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise InvalidProfileError(f"cannot read profile file: {path}") from exc
        if not isinstance(payload, dict):
            raise InvalidProfileError(f"profile file must contain an object: {path}")
        return payload

    def _profile_path(self, profile_id: str) -> Path:
        pieces = profile_id.split("/")
        if len(pieces) != 3 or any(not piece or piece in {".", ".."} for piece in pieces):
            raise ProfileNotFoundError(profile_id)
        candidate = self._root.joinpath(*pieces, "profile.json")
        try:
            candidate.resolve().relative_to(self._root.resolve())
        except ValueError as exc:
            raise ProfileNotFoundError(profile_id) from exc
        return candidate

    def get(self, profile_id: str) -> dict[str, object]:
        path = self._profile_path(profile_id)
        profile = self._read_object(path)
        if profile.get("id") != profile_id:
            raise InvalidProfileError(f"profile id does not match directory: {path}")
        required = ("device_type", "brand", "model", "display_name", "transport")
        if any(not profile.get(field) for field in required):
            raise InvalidProfileError(f"profile is missing required fields: {path}")
        return profile

    def get_commands(self, profile_id: str) -> dict[str, object]:
        profile_path = self._profile_path(profile_id)
        profile = self.get(profile_id)
        files = profile.get("files")
        if not isinstance(files, dict) or not isinstance(files.get("commands"), str):
            raise InvalidProfileError(f"profile does not declare a commands file: {profile_path}")
        commands_path = profile_path.parent / str(files["commands"])
        try:
            commands_path.resolve().relative_to(profile_path.parent.resolve())
        except ValueError as exc:
            raise InvalidProfileError("commands file escapes its profile directory") from exc
        return self._read_object(commands_path)

    def list(self) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        if not self._root.exists():
            return items
        for path in sorted(self._root.glob("*/*/*/profile.json")):
            profile_id = "/".join(path.relative_to(self._root).parts[:-1])
            profile = self.get(profile_id)
            items.append(
                {
                    "id": profile["id"],
                    "device_type": profile["device_type"],
                    "brand": profile["brand"],
                    "model": profile["model"],
                    "display_name": profile["display_name"],
                    "transport": profile["transport"],
                    "status": profile.get("status", "unknown"),
                    "capabilities": profile.get("capabilities", {}),
                }
            )
        return items

    def detail(self, profile_id: str) -> dict[str, object]:
        profile = dict(self.get(profile_id))
        command_data = self.get_commands(profile_id)
        commands = command_data.get("commands", {})
        profile["command_ids"] = sorted(commands) if isinstance(commands, dict) else []
        profile["encoders"] = sorted(command_data.get("encoders", {}))
        return profile

