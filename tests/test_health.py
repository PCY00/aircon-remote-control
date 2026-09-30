from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_serves_smart_home_ui() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'id="room-first-design-studio"' in response.text
    assert "/api/v1/device-profiles" in response.text
    assert "/api/v1/devices" in response.text
    assert "data-device-profile" in response.text
    assert "data-device-icon-picker" in response.text
    assert "/static/vendor/lucide.min.js" in response.text
    assert "/static/sensors.css" in response.text
    assert "/static/sensors.js" in response.text
    assert "data-sensor-section" in response.text
    assert "data-sensor-detail" in response.text
    assert "07:00~19:00 자동 갱신 안 함" in response.text
    assert "Mock IR 연결 · 실제 송신 없음" in response.text


def test_vendored_lucide_bundle_is_served() -> None:
    response = client.get("/static/vendor/lucide.min.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert len(response.content) > 400_000


def test_sensor_dashboard_assets_are_served() -> None:
    stylesheet = client.get("/static/sensors.css")
    script = client.get("/static/sensors.js")

    assert stylesheet.status_code == 200
    assert "text/css" in stylesheet.headers["content-type"]
    assert ".sensor-overview-grid" in stylesheet.text
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]
    assert "/api/v1/sensors/status" in script.text
    assert "/api/v1/sensors" in script.text
    assert "smart-home.sensor-refresh-policy.v1" in script.text
    assert "/api/v1/zigbee/join" in script.text
    assert "sensor-join-panel" in stylesheet.text


def test_system_reports_port_and_ui_state() -> None:
    response = client.get("/api/v1/system")

    assert response.status_code == 200
    assert response.json() == {
        "service": "aircon-controller",
        "status": "ir-receiver-ready",
        "port": 8001,
        "ui": "room-first-smart-home",
    }


def test_health_is_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "aircon-controller"}
