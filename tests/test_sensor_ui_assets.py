from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_sensor_times_are_rendered_in_korea_time() -> None:
    script = (ROOT / "app" / "static" / "sensors.js").read_text(encoding="utf-8")

    assert "const DISPLAY_TIME_ZONE = 'Asia/Seoul';" in script
    assert script.count("timeZone: DISPLAY_TIME_ZONE") == 3


def test_door_detail_distinguishes_baseline_from_real_transition() -> None:
    script = (ROOT / "app" / "static" / "sensors.js").read_text(encoding="utf-8")
    html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")

    assert "실제 상태 변경 기록 없음 · 최초 상태 확인" in script
    assert "['최초 상태 확인', formatDateTime(sensor.first_seen_at)]" in script
    assert "최근 20개 · 한국 시간" in html


def test_display_controls_are_product_settings_not_design_toolbar() -> None:
    html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")

    assert "따뜻한 A · 장면 먼저" not in html
    assert 'class="studio-toolbar"' not in html
    assert 'data-view="auto"' in html
    assert 'data-view="mobile"' in html
    assert 'data-view="desktop"' in html
    assert "smart-home.view-mode.v1" in html
    assert "width: min(100%, 1920px)" in html
    assert "min-height: min(100dvh, 1080px)" in html
    assert 'src="/static/sensors.js?v=20260912-1"' in html
    assert 'src="/static/automations.js?v=20260908-1"' in html


def test_sensor_refresh_patches_existing_nodes_and_limits_history_requests() -> None:
    script = (ROOT / "app" / "static" / "sensors.js").read_text(encoding="utf-8")

    assert "function updateSensorCard(button, sensor)" in script
    assert "overview.querySelector(`.sensor-card[data-sensor-id=" in script
    assert "if (iconsChanged) refreshIcons();" in script
    assert "const previousById = new Map" in script
    assert "previous?.last_changed_at !== sensor.last_changed_at" in script
    assert "function syncFacts(list, entries)" in script


def test_sensor_metadata_and_pairing_use_server_apis() -> None:
    script = (ROOT / "app" / "static" / "sensors.js").read_text(encoding="utf-8")
    html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")

    assert "smart-home.sensor-metadata" not in script
    assert "/metadata`" in script
    assert "method: 'PATCH'" in script
    assert "'/api/v1/zigbee/join'" in script
    assert "'/api/v1/zigbee/devices'" in script
    assert 'data-zigbee-join-duration' in html
    assert 'data-close-zigbee-join' in html
    assert "120초" in html
