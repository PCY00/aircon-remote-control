"""Host allowlist, cross-site write rejection, body caps, upload quota and SSE cap."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.events import EventHub, EventHubFullError
from app.ir.mock import MockReceiver
from app.main import create_app
from app.settings import Settings, load_settings
from app.web_security import (
    DEVICE_REQUEST_RATE_LIMIT,
    MAX_BODY_BYTES,
    UPLOAD_OVERHEAD_BYTES,
    SlidingWindowLimiter,
    host_name,
    split_host,
    trusted_hosts,
)

PROFILE_ROOT = Path(__file__).parents[1] / "device_profiles"
PROFILE_ID = "air_conditioner/Carrier/CS-A061GS"
PNG = b"\x89PNG\r\n\x1a\n" + b"A" * 100
DEVICE = {"name": "거실 에어컨", "room": "거실", "profile_id": PROFILE_ID, "icon": "snowflake"}


def make_settings(data_dir: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "host": "100.64.0.9",
        "port": 8001,
        "log_level": "INFO",
        "data_dir": data_dir,
        "device_profiles_dir": PROFILE_ROOT,
        "ir_capture_timeout_seconds": 1,
        "max_upload_bytes": 4096,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def upload(client: TestClient, photo: bytes = PNG, **headers: str):  # noqa: ANN201
    return client.post(
        "/api/v1/device-requests",
        data={"device_type": "tv", "brand": "acme", "model": "m1"},
        files={"product_photo": ("photo.png", photo, "image/png")},
        headers=headers,
    )


def test_host_name_strips_port_brackets_and_case() -> None:
    assert host_name("Pi.Example.TS.net:8001") == "pi.example.ts.net"
    assert host_name("[::1]:8001") == "::1"
    assert host_name("100.64.0.9") == "100.64.0.9"
    assert host_name("") == ""
    assert split_host("100.64.0.9:8001") == ("100.64.0.9", 8001)
    assert split_host("[::1]:8001") == ("::1", 8001)
    assert split_host("testserver") == ("testserver", None)
    assert split_host("[::1]") == ("::1", None)
    assert split_host("testserver:abc") == ("testserver", -1)
    assert split_host("[::1]x") == ("::1", -1)


def test_trusted_hosts_include_bind_loopback_and_extras_but_not_wildcard_binds() -> None:
    assert trusted_hosts("100.64.0.9", ("Pi.example.ts.net",)) == {
        "100.64.0.9", "127.0.0.1", "localhost", "::1", "pi.example.ts.net",
    }
    assert "0.0.0.0" not in trusted_hosts("0.0.0.0")
    assert "::" not in trusted_hosts("::")


def test_allowed_hosts_env_is_parsed_and_wildcards_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIRCON_ALLOWED_HOSTS", " Pi.Example.ts.net ,, aircon.lan ")
    assert load_settings().allowed_hosts == ("pi.example.ts.net", "aircon.lan")
    monkeypatch.setenv("AIRCON_ALLOWED_HOSTS", "*.ts.net")
    with pytest.raises(ValueError, match="without wildcards"):
        load_settings()


def test_foreign_host_header_is_rejected_with_json_400(tmp_path: Path) -> None:
    # DNS rebinding: the browser connects to the Pi but sends the attacker's name.
    app = create_app(make_settings(tmp_path), MockReceiver())

    with TestClient(app) as client:
        rebinding = client.get("/api/v1/devices", headers={"host": "attacker.example"})
        rebinding_post = client.post(
            "/api/v1/devices", json=DEVICE, headers={"host": "evil.ts.net"}
        )
        own = client.get("/api/v1/devices")

    assert rebinding.status_code == 400
    assert rebinding.json() == {"detail": "Host header is not this service"}
    assert rebinding_post.status_code == 400
    assert own.status_code == 200


@pytest.mark.parametrize(
    "host",
    ["100.64.0.9:8001", "100.64.0.9", "127.0.0.1:8001", "localhost:8001", "[::1]:8001",
     "pi.example.ts.net:8001", "PI.EXAMPLE.TS.NET"],
)
def test_bind_address_loopback_and_configured_names_are_accepted(
    tmp_path: Path, host: str
) -> None:
    app = create_app(
        make_settings(tmp_path, allowed_hosts=("pi.example.ts.net",)), MockReceiver()
    )

    with TestClient(app) as client:
        response = client.get("/health", headers={"host": host})

    assert response.status_code == 200


def test_cross_site_writes_are_rejected_but_same_origin_and_headerless_clients_pass(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver())

    with TestClient(app) as client:
        foreign_origin = client.post(
            "/api/v1/devices", json=DEVICE, headers={"origin": "https://attacker.example"}
        )
        null_origin = client.post("/api/v1/devices", json=DEVICE, headers={"origin": "null"})
        fetch_metadata_only = client.post(
            "/api/v1/devices", json=DEVICE, headers={"sec-fetch-site": "cross-site"}
        )
        foreign_form_upload = upload(client, origin="https://attacker.example")
        foreign_delete = client.delete(
            "/api/v1/zigbee/join", headers={"origin": "http://attacker.example"}
        )
        # Same host, but another scheme or port is another origin (e.g. the
        # Zigbee2MQTT frontend on 127.0.0.1:8080 opened in the kiosk Chromium).
        other_scheme = client.post(
            "/api/v1/devices", json=DEVICE, headers={"origin": "https://testserver"}
        )
        other_port = client.post(
            "/api/v1/devices", json=DEVICE, headers={"origin": "http://testserver:8080"}
        )
        z2m_frontend = client.post(
            "/api/v1/devices", json=DEVICE, headers={"origin": "http://127.0.0.1:8080"}
        )
        tailnet_other_port = client.post(
            "/api/v1/devices", json=DEVICE, headers={"origin": "http://100.64.0.9:8080"}
        )
        default_port_elsewhere = client.post(
            "/api/v1/devices", json=DEVICE, headers={"origin": "http://localhost"}
        )
        same_origin = client.post(
            "/api/v1/devices", json=DEVICE,
            headers={"origin": "http://testserver", "sec-fetch-site": "same-origin"},
        )
        # This service reached through another allowed name on the service port.
        loopback_origin = client.post(
            "/api/v1/devices", json=DEVICE, headers={"origin": "http://127.0.0.1:8001"}
        )
        bind_origin = client.post(
            "/api/v1/devices", json=DEVICE, headers={"origin": "http://100.64.0.9:8001"}
        )
        # curl, tests and the central agent (urllib) send neither header.
        headerless = client.post("/api/v1/devices", json=DEVICE)
        cross_site_read = client.get(
            "/api/v1/devices", headers={"origin": "https://attacker.example"}
        )

    for response in (foreign_origin, null_origin, fetch_metadata_only, foreign_form_upload,
                     foreign_delete, other_scheme, other_port, z2m_frontend,
                     tailnet_other_port, default_port_elsewhere):
        assert response.status_code == 403, response.text
        assert response.json() == {"detail": "cross-site requests cannot change this service"}
    assert same_origin.status_code == 201
    assert loopback_origin.status_code == 201
    assert bind_origin.status_code == 201
    assert headerless.status_code == 201
    assert cross_site_read.status_code == 200
    assert len(cross_site_read.json()["items"]) == 4


def test_kiosk_origin_on_the_tailscale_address_is_its_own_origin(tmp_path: Path) -> None:
    # The kiosk loads http://<tailscale ip>:8001/?kiosk=1, so its fetches carry
    # exactly that origin; the same address on the default port is foreign.
    app = create_app(make_settings(tmp_path), MockReceiver())

    with TestClient(app, base_url="http://100.64.0.9:8001") as client:
        kiosk = client.post(
            "/api/v1/devices", json=DEVICE, headers={"origin": "http://100.64.0.9:8001"}
        )
        default_port = client.post(
            "/api/v1/devices", json=DEVICE, headers={"origin": "http://100.64.0.9"}
        )
        upload_from_kiosk = upload(client, origin="http://100.64.0.9:8001")

    assert kiosk.status_code == 201
    assert default_port.status_code == 403
    assert upload_from_kiosk.status_code == 201


def test_oversized_json_bodies_are_rejected_before_parsing(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver())
    padding = b'{"name": "' + b"x" * MAX_BODY_BYTES + b'"}'

    def chunks() -> Iterator[bytes]:
        yield padding[: len(padding) // 2]
        yield padding[len(padding) // 2:]

    with TestClient(app) as client:
        declared = client.post(
            "/api/v1/devices", content=padding, headers={"content-type": "application/json"}
        )
        chunked = client.post(
            "/api/v1/devices", content=chunks(), headers={"content-type": "application/json"}
        )
        bad_length = client.post(
            "/api/v1/devices", content=b"{}",
            headers={"content-type": "application/json", "content-length": "abc"},
        )

    assert declared.status_code == 413
    assert declared.json()["detail"] == f"request body exceeds {MAX_BODY_BYTES} bytes"
    assert chunked.status_code == 413
    assert chunked.json()["detail"] == f"request body exceeds {MAX_BODY_BYTES} bytes"
    assert bad_length.status_code == 400


def test_device_request_upload_requires_content_length_within_the_file_budget(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    app = create_app(settings, MockReceiver())
    budget = 3 * settings.max_upload_bytes + UPLOAD_OVERHEAD_BYTES

    with TestClient(app) as client:
        accepted = upload(client)
        too_large = client.post(
            "/api/v1/device-requests", content=b"x" * (budget + 1),
            headers={"content-type": "multipart/form-data; boundary=x"},
        )
        chunked = client.post(
            "/api/v1/device-requests", content=iter([b"--x--\r\n"]),
            headers={"content-type": "multipart/form-data; boundary=x"},
        )

    assert accepted.status_code == 201
    assert too_large.status_code == 413
    assert too_large.json()["detail"] == f"request body exceeds {budget} bytes"
    assert chunked.status_code == 411
    assert chunked.json() == {"detail": "device requests must declare Content-Length"}


def test_device_request_storage_quota_returns_507(tmp_path: Path) -> None:
    # Each request stores the photo plus a few hundred bytes of metadata JSON,
    # so two photos fit the quota and the third would exceed it.
    photo = PNG + b"B" * 3800
    quota = 2 * len(photo) + 900
    app = create_app(make_settings(tmp_path, device_request_quota_bytes=quota), MockReceiver())

    with TestClient(app) as client:
        first = upload(client, photo)
        second = upload(client, photo)
        third = upload(client, photo)

    assert (first.status_code, second.status_code) == (201, 201)
    assert third.status_code == 507
    assert "storage quota" in third.json()["detail"]
    stored = sum(p.stat().st_size for p in (tmp_path / "device_requests").rglob("*") if p.is_file())
    assert stored <= quota
    assert len(list((tmp_path / "device_requests").rglob("product-*.png"))) == 2


def test_device_requests_are_rate_limited_per_process(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver())

    with TestClient(app) as client:
        statuses = [upload(client).status_code for _ in range(DEVICE_REQUEST_RATE_LIMIT)]
        limited = upload(client)
        other_route = client.post("/api/v1/devices", json=DEVICE)

    assert statuses == [201] * DEVICE_REQUEST_RATE_LIMIT
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) >= 1
    assert limited.json() == {"detail": "too many device requests; try again later"}
    assert other_route.status_code == 201


def test_rejected_uploads_do_not_spend_the_rate_limit(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    app = create_app(settings, MockReceiver())
    budget = 3 * settings.max_upload_bytes + UPLOAD_OVERHEAD_BYTES
    multipart = {"content-type": "multipart/form-data; boundary=x"}

    with TestClient(app) as client:
        # Bodyless (411), oversized (413) and cross-site (403) probes never reach
        # the limiter, so they cannot lock the route for the household.
        chunked = [
            client.post("/api/v1/device-requests", content=iter([b"--x--\r\n"]),
                        headers=multipart).status_code
            for _ in range(DEVICE_REQUEST_RATE_LIMIT)
        ]
        oversized = [
            client.post("/api/v1/device-requests", content=b"x" * (budget + 1),
                        headers=multipart).status_code
            for _ in range(DEVICE_REQUEST_RATE_LIMIT)
        ]
        foreign = upload(client, origin="https://attacker.example").status_code
        accepted = [upload(client).status_code for _ in range(DEVICE_REQUEST_RATE_LIMIT)]
        limited = upload(client).status_code

    assert chunked == [411] * DEVICE_REQUEST_RATE_LIMIT
    assert oversized == [413] * DEVICE_REQUEST_RATE_LIMIT
    assert foreign == 403
    assert accepted == [201] * DEVICE_REQUEST_RATE_LIMIT
    assert limited == 429


def test_sliding_window_limiter_recovers_after_the_window() -> None:
    now = [1000.0]
    limiter = SlidingWindowLimiter(2, 60, clock=lambda: now[0])

    assert limiter.allow() and limiter.allow()
    assert not limiter.allow()
    assert limiter.retry_after_seconds() == 61
    now[0] += 30
    assert not limiter.allow()
    assert limiter.retry_after_seconds() == 31
    now[0] += 30
    assert limiter.allow()
    assert limiter.retry_after_seconds() == 0


def test_event_hub_caps_live_subscribers() -> None:
    async def scenario() -> None:
        hub = EventHub(max_subscribers=1)
        hub.start()
        async with hub.subscribe():
            assert not hub.has_capacity()
            with pytest.raises(EventHubFullError):
                async with hub.subscribe():
                    pass
        assert hub.has_capacity()
        await hub.stop()

    asyncio.run(scenario())


def test_event_stream_returns_503_when_the_subscriber_cap_is_reached(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver())
    app.state.event_hub.max_subscribers = 0

    with TestClient(app) as client:
        response = client.get("/api/v1/events")

    assert response.status_code == 503
    assert response.headers["retry-after"] == "30"
    assert response.json() == {"detail": "too many live event streams are open"}
