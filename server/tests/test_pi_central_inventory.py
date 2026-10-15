"""Pi capability inventory (decision 0019): mapping, sanitizing, hashed ids and send timing."""

import hashlib
import json
import logging
import math
import re
import sqlite3
import types
import unicodedata
import urllib.error
import urllib.parse
from datetime import UTC, datetime

import pytest

from tests.test_central_push import setup as setup  # noqa: F401 (fixture)
from tests.test_pi_central_agent import Stop, add, agent, climate, drain, run_agent
from tests.test_pi_central_agent import sources as sources  # noqa: F401 (fixture)

NS = "00000000-0000-4000-8000-000000000000"
AIRCON = "a" * 32
REPORTED = "2026-10-16T01:00:00+00:00"
EPOCH = datetime(2026, 10, 16, 1, 0, 0, tzinfo=UTC).timestamp()
NOW = EPOCH + 100
DOOR_ID = "0x00158d0001a2b3c4"  # Zigbee2MQTT's default friendly name is the IEEE address
CLIMATE_ID = "living_climate"
KEY = re.compile(r"[a-z][a-z0-9_]{0,31}")


def aircon(ident=AIRCON, **changes):
    row = {
        "id": ident, "name": "거실 에어컨", "room": "거실",
        "profile_id": "air_conditioner/Carrier/CS-A061GS", "icon": "air-vent",
        "created_at": "2026-10-01T00:00:00+00:00",
        "zigbee_binding": {"type": "h2_ir", "model": "H2", "friendly_name": "ir_node_living"},
        "last_desired_state": {"power": True, "mode": "cool", "temperature_c": 24, "fan": "auto",
                               "confirmation": "inferred_from_ir_command"},
        "last_command": {"command_id": "cool_state", "kind": "state", "recorded_at": REPORTED},
    }
    row.update(changes)
    return row


def sensor(device_id, kind, state, metadata=None, reported=REPORTED):
    return {"device_id": device_id, "kind": kind, "state": state,
            "first_seen_at": REPORTED, "last_reported_at": reported, "last_received_at": reported,
            "source_timestamp": None, "last_changed_at": None, "metadata": metadata}


def door(**changes):
    row = sensor(DOOR_ID, "door_contact",
                 {"contact": True, "door_state": "closed", "battery_percent": 87,
                  "battery_low": False, "linkquality": 120, "voltage_mv": 3000},
                 {"display_name": "현관문", "room": "현관", "icon": "door-open",
                  "customized": True, "updated_at": REPORTED})
    row.update(changes)
    return row


def climate_sensor(**changes):
    row = sensor(CLIMATE_ID, "temperature_humidity",
                 {"temperature_c": 25.4, "humidity_percent": 51, "linkquality": 90})
    row.update(changes)
    return row


def build(devices=(), sensors=(), namespace=NS):
    return agent.build_inventory(namespace, list(devices), list(sensors), now=NOW)


def server_accepts(devices):
    """The central server's validation rules from decision 0019, section 1."""
    assert isinstance(devices, list) and len(devices) <= 50
    assert len(json.dumps({"devices": devices}).encode()) <= 32768
    assert len({device["id"] for device in devices}) == len(devices)
    no_format = lambda text: not any(unicodedata.category(c) in ("Cc", "Cf") for c in text)  # noqa: E731
    for device in devices:
        assert set(device) == {"id", "name", "room", "type", "capabilities", "state",
                               "reported_at", "controllable"}
        assert re.fullmatch(r"[0-9a-f]{32}", device["id"])
        assert isinstance(device["name"], str) and 1 <= len(device["name"].strip()) <= 80
        assert isinstance(device["room"], str) and len(device["room"]) <= 40
        assert no_format(device["name"]) and no_format(device["room"])
        assert KEY.fullmatch(device["type"])
        capabilities = device["capabilities"]
        assert len(capabilities) <= 16 and len(set(capabilities)) == len(capabilities)
        assert all(KEY.fullmatch(item) for item in capabilities)
        assert isinstance(device["state"], dict) and len(device["state"]) <= 16
        for key, value in device["state"].items():
            assert KEY.fullmatch(key)
            if isinstance(value, str):
                assert len(value) <= 40 and no_format(value)
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                assert math.isfinite(value) and abs(value) <= 1e9
            else:
                assert value is None or isinstance(value, bool)
        reported = device["reported_at"]
        assert reported is None or (isinstance(reported, float) and math.isfinite(reported)
                                    and reported <= NOW + 300)
        assert isinstance(device["controllable"], bool)
    return devices


def test_air_conditioner_maps_desired_state_controllable_flag_and_command_time():
    devices = server_accepts(build([
        aircon(),
        # Registered but not bound to H2 IR: listed for family screens, never controllable.
        aircon("b" * 32, name="안방 에어컨", room="안방", zigbee_binding=None,
               last_desired_state=None, last_command=None),
        # Another air conditioner model: no reviewed control payloads yet.
        aircon("c" * 32, profile_id="air_conditioner/Other/X1",
               last_desired_state={"power": False, "confirmation": "inferred_from_ir_command"}),
        {"id": "d" * 32, "name": "TV", "room": "거실", "profile_id": "tv/Other/X"},
        aircon("not-a-pi-id"),
    ]))
    assert devices == [
        {"id": AIRCON, "name": "거실 에어컨", "room": "거실", "type": "air_conditioner",
         "capabilities": ["power", "setpoint", "mode", "fan", "actions"],
         "state": {"power": True, "mode": "cool", "setpoint_c": 24, "fan": "auto",
                   "inferred": True},
         "reported_at": EPOCH, "controllable": True},
        {"id": "b" * 32, "name": "안방 에어컨", "room": "안방", "type": "air_conditioner",
         "capabilities": ["power", "setpoint", "mode", "fan", "actions"], "state": {},
         "reported_at": None, "controllable": False},
        {"id": "c" * 32, "name": "거실 에어컨", "room": "거실", "type": "air_conditioner",
         "capabilities": ["power", "setpoint", "mode", "fan", "actions"],
         "state": {"power": False, "inferred": True}, "reported_at": EPOCH, "controllable": False},
    ]
    # The H2 friendly name stays on the Pi.
    assert "ir_node_living" not in json.dumps(devices)


def test_controllable_matches_the_heartbeat_list_exactly():
    rows = [aircon(f"{index:032x}") for index in range(25)]
    devices = build(rows)
    heartbeat = {device["id"] for device in agent.control_devices(rows)}
    assert len(heartbeat) == 20
    assert {device["id"] for device in devices if device["controllable"]} == heartbeat


def test_door_and_climate_sensors_with_and_without_metadata_and_unknown_kinds():
    devices = server_accepts(build([], [
        door(),
        climate_sensor(),
        sensor("motion_hall", "motion", {"occupancy": True}),
        sensor("plug_desk", "smart_plug", {"power_w": 3}),
        sensor(DOOR_ID + "_b", "door_contact", {"contact": False},
               {"display_name": "베란다 문", "room": "", "icon": "door-open"}, reported="invalid"),
    ]))
    assert devices == [
        {"id": agent.device_ref(NS, DOOR_ID), "name": "현관문", "room": "현관",
         "type": "door_sensor", "capabilities": ["contact", "battery"],
         "state": {"contact": "closed", "battery_percent": 87, "battery_low": False},
         "reported_at": EPOCH, "controllable": False},
        {"id": agent.device_ref(NS, CLIMATE_ID), "name": "온·습도 센서", "room": "",
         "type": "climate_sensor", "capabilities": ["temperature", "humidity"],
         "state": {"temperature_c": 25.4, "humidity_percent": 51},
         "reported_at": EPOCH, "controllable": False},
        {"id": agent.device_ref(NS, DOOR_ID + "_b"), "name": "베란다 문", "room": "",
         "type": "door_sensor", "capabilities": ["contact"], "state": {"contact": "open"},
         "reported_at": None, "controllable": False},
    ]
    # Battery only as a low flag still adds the block; the Pi app's default room is kept as is.
    low = build([], [climate_sensor(
        state={"temperature_c": 20, "battery_low": True},
        metadata={"display_name": "온·습도 센서", "room": "공간 미지정"})])
    assert low[0]["capabilities"] == ["temperature", "humidity", "battery"]
    assert low[0]["state"] == {"temperature_c": 20, "battery_low": True}
    assert low[0]["room"] == "공간 미지정"


def test_aircons_come_first_then_sensors_in_api_order():
    devices = build([aircon()], [door(), climate_sensor()])
    assert [device["type"] for device in devices] == ["air_conditioner", "door_sensor",
                                                      "climate_sensor"]


def test_names_rooms_and_state_strings_are_sanitized_like_the_server():
    devices = server_accepts(build([
        aircon(name="‮거실​ 에어컨\x00", room="  거실\x7f  "),
        aircon("b" * 32, name="x" * 100, room="y" * 50,
               last_desired_state={"power": "yes", "mode": "cool\x07", "temperature_c": True,
                                   "fan": "z" * 50}),
        aircon("c" * 32, name="\x01​﻿", room=None,
               last_desired_state={"mode": "", "temperature_c": float("nan"), "fan": 3}),
        aircon("e" * 32, name="\ud800거실", last_desired_state={"temperature_c": 10**400},
               last_command={"recorded_at": "2026-10-16T01:00:00"}),  # no offset
        aircon("f" * 32, name="ir_node_living", room="0x00158d0001a2b3c4",  # Zigbee names
               last_command={"recorded_at": "2030-01-01T00:00:00+00:00"}),  # future
    ], [
        door(metadata={"display_name": DOOR_ID, "room": DOOR_ID}),
        climate_sensor(metadata={"display_name": "센서 " + DOOR_ID, "room": CLIMATE_ID.upper()},
                       state={"temperature_c": 300, "humidity_percent": 150,
                              "battery_percent": -1, "battery_low": "no"}),
    ]))
    assert [(device["name"], device["room"]) for device in devices] == [
        ("거실 에어컨", "거실"), ("x" * 80, "y" * 40), ("에어컨", ""), ("거실", "거실"),
        ("에어컨", ""), ("문 열림 센서", ""), ("온·습도 센서", ""),
    ]
    assert devices[1]["state"] == {"mode": "cool", "fan": "z" * 40, "inferred": True}
    assert [device["state"] for device in devices[2:4]] == [{}, {}]
    assert [device["reported_at"] for device in devices[3:5]] == [None, None]
    assert devices[6]["state"] == {} and devices[6]["capabilities"] == ["temperature", "humidity"]
    assert DOOR_ID not in json.dumps(devices) and "ir_node_living" not in json.dumps(devices)


def test_list_is_capped_at_fifty_and_thirty_two_kib():
    rows = [aircon(f"{index:032x}") for index in range(3)]
    sensors = [sensor(f"door_{index:02d}", "door_contact", {"contact": True})
               for index in range(60)]
    devices = server_accepts(build(rows, sensors))
    assert len(devices) == 50
    assert [device["id"] for device in devices[:3]] == [row["id"] for row in rows]
    assert devices[-1]["id"] == agent.device_ref(NS, "door_46")
    # Worst case: every label at its limit in escaped Hangul. Trailing devices give way.
    long = [sensor(f"door_{index:02d}", "door_contact", {"contact": True},
                   {"display_name": "가" * 80, "room": "나" * 40}) for index in range(50)]
    trimmed = server_accepts(build([], long))
    assert 20 < len(trimmed) < 50
    assert [device["id"] for device in trimmed] == [
        agent.device_ref(NS, f"door_{index:02d}") for index in range(len(trimmed))]


def test_sensor_ids_are_stable_hashes_that_never_contain_the_raw_id():
    first, again = build([], [door(), climate_sensor()]), build([], [door(), climate_sensor()])
    assert first == again
    for device, raw in zip(first, (DOOR_ID, CLIMATE_ID), strict=True):
        assert device["id"] == hashlib.sha256((NS + ":device:" + raw).encode()).hexdigest()[:32]
        assert re.fullmatch(r"[0-9a-f]{32}", device["id"])
    encoded = json.dumps(first)
    assert DOOR_ID not in encoded and CLIMATE_ID not in encoded and "0x" not in encoded
    other = build([], [door()], namespace="11111111-1111-4111-8111-111111111111")
    assert other[0]["id"] != first[0]["id"]  # each Pi agent has its own namespace


def test_malformed_pi_lists_fail_instead_of_sending_a_partial_inventory():
    for devices, sensors in (({}, []), ([], None)):
        with pytest.raises(ValueError):
            agent.build_inventory(NS, devices, sensors, now=NOW)


def test_door_and_climate_events_carry_the_inventory_device_id(sources):
    directory, store, clock = sources
    climate(directory, 1000, 20)
    store.collect(directory)
    add(directory)
    clock[0] = 1001
    climate(directory, 1001, 21)
    counts = store.collect(directory)
    assert (counts["queued"], counts["climate_queued"]) == (1, 1)
    namespace = store.namespace()
    inventory = agent.build_inventory(namespace, [], [
        sensor("private-mac", "door_contact", {"contact": True}),
        sensor("private-sensor-mac", "temperature_humidity", {"temperature_c": 21}),
    ], now=NOW)
    items = {item["kind"]: item for item in drain(store)}
    door_event, climate_event = items["sensor.door_changed"], items["sensor.climate_report"]
    door_payload, climate_payload = (json.loads(door_event["payload"]),
                                     json.loads(climate_event["payload"]))
    assert door_payload["device_id"] == inventory[0]["id"]
    assert climate_payload["device_id"] == inventory[1]["id"]
    assert set(door_payload) == {"state", "previous_state", "device_id", "source", "occurred_at",
                                 "notification_expires_at"}
    assert set(climate_payload) == {"temperature_c", "humidity_percent", "source", "sensor_ref",
                                    "device_id", "occurred_at", "notification_expires_at"}
    for event in (door_event, climate_event):
        assert "private" not in event["payload"]
    # Event ids are unchanged by the new field, so a restart never re-sends under a new id.
    sensor_ref = hashlib.sha256((namespace + ":climate:private-sensor-mac").encode()).hexdigest()
    assert door_event["event_id"] == hashlib.sha256((namespace + ":door:1").encode()).hexdigest()
    assert climate_event["event_id"] == hashlib.sha256(
        (sensor_ref + ":" + str(1001.0)).encode()).hexdigest()


class FakeChannel:
    def __init__(self, command=None):
        self.sender = types.SimpleNamespace(blocked=False)
        self.calls, self.inventory_errors, self.command = [], [], command

    def request(self, path, body, method="POST"):
        self.calls.append((path, method, body))
        if path == "/v1/hub/inventory" and self.inventory_errors:
            error = self.inventory_errors.pop(0)
            if error is not None:
                raise error
        if path == "/v1/hub/control/next":
            command, self.command = self.command, None
            return {"command": command}
        return {}

    def sent(self):
        return [body for path, _, body in self.calls if path == "/v1/hub/inventory"]


def http_error(code, headers=None):
    return urllib.error.HTTPError("https://example.test", code, "fixture", headers or {}, None)


@pytest.fixture
def timing(monkeypatch):
    monkeypatch.setattr(agent, "LOGGED", {})
    controller = agent.LocalController("http://127.0.0.1:8001")
    lists = {"/api/v1/devices": [aircon()], "/api/v1/sensors": [door(), climate_sensor()]}
    reads = []

    def request(path, value=None, timeout=15):
        reads.append(path)
        return {"items": lists[path]}

    controller.request = request
    clock = [1000.0]
    sync = agent.InventorySync(NS, monotonic=lambda: clock[0], clock=lambda: NOW)
    return sync, FakeChannel(), controller, lists, reads, clock


def test_sender_sends_changes_at_most_every_fifteen_seconds_and_refreshes_every_five_minutes(
        timing):
    sync, channel, controller, lists, reads, clock = timing

    def at(moment):
        clock[0] = moment
        return sync.sync(channel, controller)

    assert at(1000) == "sent"
    assert channel.sent() == [{"devices": build([aircon()], [door(), climate_sensor()])}]
    assert at(1005) == "waiting" and len(reads) == 2  # not even a local read inside 15 s
    assert at(1015) == "unchanged" and len(channel.sent()) == 1
    lists["/api/v1/devices"] = [aircon(last_desired_state={"power": False})]
    assert at(1020) == "waiting"
    assert at(1030) == "sent"  # the change goes out at the next 15 s slot
    assert channel.sent()[-1]["devices"][0]["state"] == {"power": False, "inferred": True}
    assert at(1045) == "unchanged" and at(1320) == "unchanged" and at(1329.9) == "waiting"
    assert at(1330) == "sent" and len(channel.sent()) == 3  # unchanged, 300 s after the last send
    assert channel.sent()[-1] == channel.sent()[-2]
    lists["/api/v1/sensors"] = [door(state={"contact": False, "door_state": "open"})]
    assert at(1344.9) == "waiting" and at(1345) == "sent"
    assert len(reads) == 2 * 7  # the Pi app is read only at the 7 checks, never while waiting


def test_older_central_server_without_the_route_is_skipped_for_an_hour_and_logged_once(
        timing, caplog):
    sync, channel, controller, _, reads, clock = timing
    caplog.set_level(logging.INFO)
    channel.inventory_errors = [http_error(404), http_error(404), None]
    assert sync.sync(channel, controller) == "missing_route"
    clock[0] = 1000 + 3599.9
    assert sync.sync(channel, controller) == "waiting" and len(reads) == 2
    clock[0] = 1000 + 3600
    assert sync.sync(channel, controller) == "missing_route"
    clock[0] = 1000 + 7200
    assert sync.sync(channel, controller) == "sent"
    messages = [record.getMessage() for record in caplog.records]
    assert messages.count("INVENTORY_ROUTE_MISSING wait=3600") == 1


@pytest.mark.parametrize("headers,wait", [({"Retry-After": "120"}, 120), ({"Retry-After": "1"}, 15),
                                          ({}, 30), ({"Retry-After": "999999"}, 300)])
def test_rate_limited_inventory_waits_retry_after_but_never_less_than_fifteen_seconds(
        timing, headers, wait):
    sync, channel, controller, _, _, clock = timing
    channel.inventory_errors = [http_error(429, headers)]
    assert sync.sync(channel, controller) == "rate_limited"
    clock[0] = 1000 + wait - 0.1
    assert sync.sync(channel, controller) == "waiting"
    clock[0] = 1000 + wait
    assert sync.sync(channel, controller) == "sent"


@pytest.mark.parametrize("error,outcome,wait", [
    (http_error(500), "retry", 60), (http_error(503), "retry", 60),
    (urllib.error.URLError("reset"), "retry", 60), (TimeoutError("timed out"), "retry", 60),
    (ValueError("Control response too large"), "retry", 60),
    (http_error(400), "rejected", 300), (http_error(413), "rejected", 300),
])
def test_failed_inventory_is_retried_later_without_hammering(timing, error, outcome, wait, caplog):
    sync, channel, controller, _, _, clock = timing
    caplog.set_level(logging.WARNING)
    channel.inventory_errors = [error]
    assert sync.sync(channel, controller) == outcome
    clock[0] = 1000 + wait - 0.1
    assert sync.sync(channel, controller) == "waiting"
    clock[0] = 1000 + wait
    assert sync.sync(channel, controller) == "sent"
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "INVENTORY_DEFERRED" in logged and "거실" not in logged and "example.test" not in logged


def test_local_pi_app_failure_sends_nothing_and_is_read_again_later(timing):
    sync, channel, controller, lists, _, clock = timing
    del lists["/api/v1/sensors"]  # e.g. the Pi app is restarting: a KeyError from the fixture
    assert sync.sync(channel, controller) == "local_unavailable" and channel.sent() == []
    lists["/api/v1/sensors"] = [door()]
    clock[0] = 1015
    assert sync.sync(channel, controller) == "sent"


def test_rejected_hub_credential_blocks_the_hub_and_stops_inventory(timing):
    sync, _, controller, _, _, clock = timing
    sender = agent.Sender({"endpoint": "https://house.example.test", "hub_token": "hub_test"})

    class Revoked:
        calls = 0

        def open(self, request, **kwargs):
            self.calls += 1
            raise urllib.error.HTTPError(request.full_url, 401, "revoked", {}, None)

    sender.opener = Revoked()
    channel = agent.ControlChannel({"endpoint": "https://house.example.test"}, sender)
    with pytest.raises(urllib.error.HTTPError):
        sync.sync(channel, controller)
    assert sender.blocked
    clock[0] = 5000
    assert sync.sync(channel, controller) == "waiting" and sender.opener.calls == 1


def test_inventory_put_names_the_client_and_accepts_an_empty_reply(timing):
    sync, _, controller, _, _, _ = timing
    sender = agent.Sender({"endpoint": "https://house.example.test", "hub_token": "hub_test"})
    requests = []

    class NoContent:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, limit):
            return b""

    class Edge:
        def open(self, request, **kwargs):
            requests.append(request)
            return NoContent()

    sender.opener = Edge()
    channel = agent.ControlChannel({"endpoint": "https://house.example.test"}, sender)
    assert sync.sync(channel, controller) == "sent"
    request, = requests
    assert request.full_url == "https://house.example.test/v1/hub/inventory"
    assert request.get_method() == "PUT"
    assert request.get_header("User-agent") == "FamilySmartHome-Pi/0.7.0"
    assert request.get_header("Authorization") == "Bearer hub_test"
    body = json.loads(request.data)
    assert set(body) == {"devices"} and server_accepts(body["devices"]) == body["devices"]
    assert DOOR_ID not in request.data.decode() and "ir_node_living" not in request.data.decode()


class Controller:
    def __init__(self, inventory_error=None):
        self.inventory_error, self.executed = inventory_error, []

    def devices(self):
        return [{"id": AIRCON, "name": "거실 에어컨"}]

    def inventory(self, namespace, *, clock):
        if self.inventory_error:
            raise self.inventory_error
        return build([aircon()])

    def execute(self, command):
        self.executed.append(command["action"])
        return "sent"


@pytest.mark.parametrize("local_error,central_error", [
    (OSError("Pi app restarting"), None), (None, http_error(500)), (None, http_error(404)),
    (None, urllib.error.URLError("reset")), (None, http_error(429, {"Retry-After": "60"})),
])
def test_inventory_failure_never_stops_the_heartbeat_or_the_command(tmp_path, monkeypatch,
                                                                     local_error, central_error):
    monkeypatch.setattr(agent, "LOGGED", {})
    store = agent.Store(tmp_path / "outbox.sqlite3")
    command = {"id": "12345678-1234-4234-8234-123456789abc", "device_id": AIRCON,
               "attempt_token": "f" * 64, "action": "power_off", "remaining_seconds": 20}
    channel, controller = FakeChannel(command), Controller(local_error)
    channel.inventory_errors = [central_error]
    agent.poll_control(store, channel, controller, agent.InventorySync(store.namespace()))
    assert controller.executed == ["power_off"]
    assert [path for path, _, _ in channel.calls] == (
        ["/v1/hub/control/status"]
        + ([] if local_error else ["/v1/hub/inventory"])
        + ["/v1/hub/control/next", "/v1/hub/control/" + command["id"] + "/result",
           "/v1/hub/control/status"])
    assert store.pending_result() is None


def test_rejected_credential_on_inventory_still_stops_like_other_channel_requests(tmp_path):
    store = agent.Store(tmp_path / "outbox.sqlite3")
    channel = FakeChannel()
    channel.inventory_errors = [http_error(403)]
    with pytest.raises(urllib.error.HTTPError):
        agent.poll_control(store, channel, Controller(), agent.InventorySync(store.namespace()))
    assert "/v1/hub/control/next" not in [path for path, _, _ in channel.calls]


def test_agent_loop_hands_one_inventory_timer_with_the_store_namespace_to_control(
        sources, tmp_path, monkeypatch):
    directory, _, _ = sources
    polls = []
    with pytest.raises(Stop):
        run_agent(monkeypatch, tmp_path, directory, True, lambda *a: polls.append(a))
    timers = {id(poll[3]) for poll in polls}
    assert len(polls) == 8 and len(timers) == 1
    assert isinstance(polls[0][3], agent.InventorySync)
    assert polls[0][3].namespace == agent.Store(tmp_path / "s/outbox.sqlite3").namespace()


class Reply:
    def __init__(self, status, data):
        self.status, self.data = status, data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, limit):
        return self.data[:limit]


class FlaskEdge:
    """The agent's exact request bytes and headers, answered by the real central route."""

    def __init__(self, client):
        self.client, self.statuses = client, []

    def open(self, request, timeout):
        response = self.client.open(urllib.parse.urlsplit(request.full_url).path,
                                    method=request.get_method(), data=request.data,
                                    headers=dict(request.header_items()))
        self.statuses.append(response.status_code)
        if response.status_code >= 400:
            raise urllib.error.HTTPError(request.full_url, response.status_code, "fixture",
                                         dict(response.headers), None)
        return Reply(response.status_code, response.get_data())


def test_real_central_route_stores_odd_and_largest_inventories_whole(setup, monkeypatch):
    from central_server.web import create_app

    monkeypatch.setattr(agent, "LOGGED", {})
    db, *_, hub = setup
    app = create_app(db)
    app.extensions["inventory"].clock = lambda: NOW
    sender = agent.Sender({"endpoint": "https://house.example.test", "hub_token": hub["hub_token"]})
    sender.opener = FlaskEdge(app.test_client())
    channel = agent.ControlChannel({"endpoint": "https://house.example.test"}, sender)
    controller = agent.LocalController("http://127.0.0.1:8001")
    odd = {
        "/api/v1/devices": [aircon(name="‮거실​ 에어컨\x00",
                                   last_desired_state={"mode": "\ud800cool", "fan": "z" * 50}),
                            aircon("b" * 32, name="\x01", room=None, last_command=None)],
        "/api/v1/sensors": [door(metadata={"display_name": DOOR_ID, "room": "현관⁦"}),
                            climate_sensor(state={"temperature_c": float("inf"),
                                                  "battery_percent": 55}),
                            sensor("motion_hall", "motion", {"occupancy": True})],
    }
    largest = {"/api/v1/devices": [], "/api/v1/sensors": [
        sensor(f"door_{index:02d}", "door_contact", {"contact": True},
               {"display_name": "가" * 80, "room": "나" * 40}) for index in range(50)]}
    lists = [odd]
    controller.request = lambda path, value=None, timeout=15: {"items": lists[0][path]}
    clock = [1000.0]
    sync = agent.InventorySync(NS, monotonic=lambda: clock[0], clock=lambda: NOW)
    for case in (odd, largest):
        lists[0] = case
        expected = build(case["/api/v1/devices"], case["/api/v1/sensors"])
        assert sync.sync(channel, controller) == "sent", sender.opener.statuses
        with sqlite3.connect(db) as conn:
            stored = conn.execute("SELECT device_id,name,room,state FROM hub_devices "
                                  "WHERE hub_id=? ORDER BY position", (hub["hub_id"],)).fetchall()
        assert [(row[0], row[1], row[2], json.loads(row[3])) for row in stored] == [
            (device["id"], device["name"], device["room"], device["state"]) for device in expected]
        clock[0] += agent.INVENTORY_MIN_INTERVAL
    assert sender.opener.statuses == [200, 200] and not sender.blocked
    assert len(stored) > 30  # the largest case still fits the route's own 32 KiB cap
