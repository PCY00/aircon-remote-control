from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from app.devices.catalog import DeviceProfileCatalog
from app.devices.commands import DeviceCommandResolver
from app.devices.service import DeviceService
from app.devices.store import RegisteredDeviceStore
from app.devices.transport import MockIrTransport, TransportExecutionError


def make_service(tmp_path: Path) -> tuple[DeviceService, RegisteredDeviceStore, MockIrTransport]:
    catalog = DeviceProfileCatalog(Path(__file__).parents[1] / "device_profiles")
    store = RegisteredDeviceStore(tmp_path)
    transport = MockIrTransport()
    return (
        DeviceService(
            catalog=catalog,
            store=store,
            resolver=DeviceCommandResolver(catalog),
            transport=transport,
        ),
        store,
        transport,
    )


def test_concurrent_commands_preserve_send_save_and_notification_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, store, transport = make_service(tmp_path)
    device = service.register(
        name="test", room="test", profile_id="air_conditioner/Carrier/CS-A061GS"
    )
    first_saving, release_first, second_started, second_sent = (
        Event(), Event(), Event(), Event()
    )
    original_record = store.record_command
    original_send = transport.send
    notifications: list[str] = []
    service.add_listener(
        lambda result: notifications.append(result["resolved_command"]["command_id"])
    )

    def delayed_record(device_id: str, **kwargs: object) -> dict[str, object]:
        if kwargs["command_id"] == "cool_24_high":
            first_saving.set()
            assert release_first.wait(5)
        return original_record(device_id, **kwargs)

    def observed_send(**kwargs: object) -> dict[str, object]:
        result = original_send(**kwargs)
        if kwargs["command"]["command_id"] == "power_off":
            second_sent.set()
        return result

    def turn_off() -> dict[str, object]:
        second_started.set()
        return service.execute(device["id"], {"action": "set_state", "power": False})

    monkeypatch.setattr(store, "record_command", delayed_record)
    monkeypatch.setattr(transport, "send", observed_send)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            service.execute,
            device["id"],
            {
                "action": "set_state", "power": True, "mode": "cool",
                "temperature_c": 24, "fan": "high",
            },
        )
        try:
            assert first_saving.wait(5)
            second = pool.submit(turn_off)
            assert second_started.wait(5)
            assert not second_sent.wait(0.1)
        finally:
            release_first.set()
        first.result(timeout=5)
        second.result(timeout=5)

    expected = ["cool_24_high", "power_off"]
    assert [item["command"]["command_id"] for item in transport.list()] == expected
    assert notifications == expected
    assert store.get(device["id"])["last_desired_state"]["power"] is False
    assert store.get(device["id"])["last_command"]["command_id"] == "power_off"


def test_failed_send_preserves_state_and_releases_command_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, store, transport = make_service(tmp_path)
    device = service.register(
        name="test", room="test", profile_id="air_conditioner/Carrier/CS-A061GS"
    )
    original_send = transport.send

    def fail_send(**_kwargs: object) -> dict[str, object]:
        raise TransportExecutionError("test failure")

    monkeypatch.setattr(transport, "send", fail_send)
    with pytest.raises(TransportExecutionError):
        service.execute(device["id"], {"action": "set_state", "power": False})
    assert store.get(device["id"])["last_command"] is None

    monkeypatch.setattr(transport, "send", original_send)
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(
            service.execute, device["id"], {"action": "set_state", "power": False}
        ).result(timeout=5)
    assert result["device"]["last_command"]["command_id"] == "power_off"
