from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_run_script_bounds_graceful_shutdown_for_open_sse_streams() -> None:
    # The kiosk keeps /api/v1/events open; without a limit uvicorn waits for it
    # forever and systemd SIGKILLs the service after its stop timeout.
    script = (ROOT / "scripts" / "run_pi.sh").read_text(encoding="utf-8")
    assert "--timeout-graceful-shutdown 5" in script
    unit = (ROOT / "deploy" / "systemd" / "aircon-controller.service").read_text(
        encoding="utf-8"
    )
    assert "TimeoutStopSec=20s" in unit.splitlines()


def test_service_uses_the_verified_receive_lirc_device() -> None:
    # /dev/lirc0 is the send-only gpio-ir-tx node on the Pi (ISSUE-024).
    lines = (ROOT / "deploy" / "systemd" / "aircon-controller.service").read_text(
        encoding="utf-8"
    ).splitlines()
    assert "Environment=AIRCON_IR_TRANSMITTER_DEVICE=/dev/lirc0" in lines
    assert "Environment=AIRCON_IR_RECEIVER_DEVICE=/dev/lirc1" in lines


def test_run_script_exports_bind_host_and_bounds_concurrency() -> None:
    # The Host allowlist is derived from AIRCON_HOST; the Tailscale address that
    # run_pi.sh looks up must reach the app, and open connections are capped.
    script = (ROOT / "scripts" / "run_pi.sh").read_text(encoding="utf-8")
    assert 'export AIRCON_HOST="${host_address}"' in script
    assert script.index('export AIRCON_HOST="${host_address}"') < script.index("exec ")
    assert "--limit-concurrency 64" in script
    local = (ROOT / "scripts" / "run_local.ps1").read_text(encoding="utf-8")
    assert "$env:AIRCON_HOST = $hostAddress" in local


def test_service_units_keep_the_docker_socket_out_of_reach() -> None:
    for name in ("aircon-controller.service", "aircon-kiosk.service"):
        lines = (ROOT / "deploy" / "systemd" / name).read_text(encoding="utf-8").splitlines()
        assert "InaccessiblePaths=-/run/docker.sock" in lines, name


def test_fastapi_floor_requires_strict_json_content_type() -> None:
    import tomllib

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    fastapi = next(d for d in pyproject["project"]["dependencies"] if d.startswith("fastapi"))
    assert fastapi == "fastapi>=0.141,<1.0"
