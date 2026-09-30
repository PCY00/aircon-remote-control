"""Resolve semantic appliance requests into model-specific IR commands."""

from __future__ import annotations

from app.devices.catalog import DeviceProfileCatalog, InvalidProfileError


class UnsupportedCommandError(ValueError):
    """Raised when a semantic request cannot be represented by a profile."""


class DeviceCommandResolver:
    """Translate UI-facing state into a checked-in model profile command."""

    def __init__(self, catalog: DeviceProfileCatalog) -> None:
        self._catalog = catalog

    @staticmethod
    def _command_from_catalog(
        command_id: str, command_data: dict[str, object]
    ) -> dict[str, object]:
        commands = command_data.get("commands")
        if not isinstance(commands, dict) or command_id not in commands:
            raise UnsupportedCommandError(f"unsupported command: {command_id}")
        command = commands[command_id]
        if not isinstance(command, dict):
            raise InvalidProfileError(f"command must be an object: {command_id}")
        result = dict(command)
        result["command_id"] = command_id
        return result

    @staticmethod
    def _cool_state(
        request: dict[str, object], command_data: dict[str, object]
    ) -> dict[str, object]:
        encoders = command_data.get("encoders")
        if not isinstance(encoders, dict):
            raise InvalidProfileError("profile has no command encoders")
        encoder = encoders.get("cool_state")
        if not isinstance(encoder, dict) or encoder.get("kind") != "carrier_gray_code_48":
            raise UnsupportedCommandError("profile cannot encode a cooling state")

        temperature = request.get("temperature_c")
        if isinstance(temperature, bool) or not isinstance(temperature, int):
            raise UnsupportedCommandError("temperature_c is required for cooling")
        minimum = int(encoder.get("temperature_min_c", 17))
        maximum = int(encoder.get("temperature_max_c", 30))
        if not minimum <= temperature <= maximum:
            raise UnsupportedCommandError(
                f"temperature_c must be between {minimum} and {maximum}"
            )

        fan = request.get("fan")
        fan_bytes = encoder.get("fan_bytes")
        if not isinstance(fan, str) or not isinstance(fan_bytes, dict) or fan not in fan_bytes:
            raise UnsupportedCommandError("fan must be one of: auto, low, medium, high")
        selected_fan = fan_bytes[fan]
        prefix = encoder.get("prefix")
        if (
            not isinstance(prefix, list)
            or len(prefix) != 2
            or not isinstance(selected_fan, list)
            or len(selected_fan) != 2
        ):
            raise InvalidProfileError("cool-state encoder bytes are malformed")

        offset = temperature - minimum
        gray = offset ^ (offset >> 1)
        temperature_byte = (gray << 4) & 0xF0
        complement = temperature_byte ^ 0xFF
        frame = [*prefix, *selected_fan, f"{temperature_byte:02x}", f"{complement:02x}"]
        repeat_count = int(encoder.get("repeat_count", 2))
        return {
            "command_id": f"cool_{temperature}_{fan}",
            "kind": "state",
            "frames_hex": [frame for _ in range(repeat_count)],
            "source": "generated_from_measured_gray_code_rule",
            "verification": "encoding_rule_verified_17_to_20_only",
            "warning": "hardware transmission remains unverified until Step 4",
            "effective_state": {
                "power": True,
                "mode": "cool",
                "temperature_c": temperature,
                "fan": fan,
            },
        }

    def resolve(self, profile_id: str, request: dict[str, object]) -> dict[str, object]:
        command_data = self._catalog.get_commands(profile_id)
        action = request.get("action")
        if action == "execute":
            command_id = request.get("command_id")
            if not isinstance(command_id, str) or not command_id:
                raise UnsupportedCommandError("command_id is required for execute")
            command = self._command_from_catalog(command_id, command_data)
        elif action == "set_state":
            power = request.get("power")
            if power is False:
                command = self._command_from_catalog("power_off", command_data)
            elif power is True:
                mode = request.get("mode")
                if mode == "cool":
                    command = self._cool_state(request, command_data)
                elif mode in {"auto", "dry", "fan_only"}:
                    command = self._command_from_catalog(f"mode_{mode}", command_data)
                else:
                    raise UnsupportedCommandError(
                        "mode must be one of: cool, auto, dry, fan_only"
                    )
            else:
                raise UnsupportedCommandError("power is required for set_state")
        else:
            raise UnsupportedCommandError("action must be set_state or execute")

        command["carrier_hz"] = command_data.get("carrier_hz")
        command["carrier_verification"] = command_data.get("carrier_verification")
        command["bit_order"] = command_data.get("bit_order")
        command["timing_us"] = command_data.get("timing_us")
        return command
