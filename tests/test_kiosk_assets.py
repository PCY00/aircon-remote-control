from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_kiosk_launcher_waits_for_display_and_dashboard() -> None:
    launcher = (PROJECT_ROOT / "scripts" / "run_kiosk.sh").read_text(encoding="utf-8")

    assert "has_connected_display" in launcher
    assert "/usr/bin/tailscale ip -4" in launcher
    assert 'health_url="http://${tailscale_ipv4}:${service_port}/health"' in launcher
    assert '"${health_url}"' in launcher
    assert "/usr/bin/cage -d -s" in launcher
    assert "--kiosk" in launcher
    assert "--ozone-platform=wayland" in launcher
    assert 'cache_dir="${project_root}/runtime/kiosk/cache"' in launcher
    assert 'export XDG_CACHE_HOME="${XDG_CACHE_HOME:-${cache_dir}}"' in launcher


def test_kiosk_url_hides_cursor_without_affecting_regular_web_clients() -> None:
    launcher = (PROJECT_ROOT / "scripts" / "run_kiosk.sh").read_text(encoding="utf-8")
    html = (PROJECT_ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")

    assert 'dashboard_url="http://${tailscale_ipv4}:${service_port}/?kiosk=1"' in launcher
    assert 'health_url="http://${tailscale_ipv4}:${service_port}/health"' in launcher
    assert "get('kiosk') === '1'" in html
    assert 'html[data-kiosk="true"] * { cursor: none !important; }' in html


def test_kiosk_unit_is_recoverable_and_does_not_expose_a_public_url() -> None:
    unit = (PROJECT_ROOT / "deploy" / "systemd" / "aircon-kiosk.service").read_text(
        encoding="utf-8"
    )

    assert "User=air" in unit
    assert "Conflicts=getty@tty1.service" in unit
    assert "After=" in unit and "getty@tty1.service" in unit
    assert "Restart=on-failure" in unit
    assert "ExecStart=/home/air/aircon-controller/scripts/run_kiosk.sh" in unit
    assert "ReadWritePaths=/home/air/aircon-controller/runtime/kiosk" in unit
    assert "Environment=XDG_RUNTIME_DIR=/run/user/1000" in unit
    assert "Environment=XDG_CACHE_HOME=/home/air/aircon-controller/runtime/kiosk/cache" in unit
    assert "ReadWritePaths=/run/user/1000" in unit
    assert "192.168." not in unit
    assert "100." not in unit


def test_kiosk_setup_keeps_package_set_minimal() -> None:
    setup = (PROJECT_ROOT / "scripts" / "setup_kiosk.sh").read_text(encoding="utf-8")

    assert "--no-install-recommends" in setup
    assert "cage" in setup
    assert "chromium" in setup
    assert "fonts-noto-cjk" in setup
    assert "systemctl enable aircon-kiosk.service" in setup
    assert "systemctl restart aircon-kiosk.service" in setup
    assert '"${project_root}/runtime/kiosk/cache"' in setup
    assert 'chmod 0755 "${project_root}/scripts/setup_kiosk.sh"' in setup
    assert 'install -o "${kiosk_user}"' not in setup
