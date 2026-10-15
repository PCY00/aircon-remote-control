"""Broker credential handling and least-privilege ACL in the Zigbee deployment files."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]
MQTT_HELPER_SCRIPTS = [
    "check_zigbee_stack.sh",
    "zigbee_join_control.sh",
    "rename_zigbee_devices.sh",
    "zigbee_device_summary.sh",
    "zigbee_sensor_live_monitor.sh",
    "zigbee_sensor_state_summary.sh",
]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_mqtt_password_never_appears_on_a_command_line() -> None:
    for name in [*MQTT_HELPER_SCRIPTS, "setup_zigbee_stack.sh", "setup_app_mqtt.sh"]:
        script = read(f"scripts/{name}")
        assert '-P "$mqtt_password"' not in script, name
        assert "mosquitto_passwd -b" not in script, name
        # -e NAME (no =value) propagates the variable from the docker CLI environment.
        assert "-e MQTT_PW=" not in script, name
    for name in MQTT_HELPER_SCRIPTS:
        script = read(f"scripts/{name}")
        assert (
            'MQTT_PW="$mqtt_password" docker exec -e MQTT_PW "$mosquitto_container" sh -c'
        ) in script
        assert 'XDG_CONFIG_HOME="$dir" "$0" -h 127.0.0.1 -p 1883 -u zigbee2mqtt "$@"' in script
        assert "umask 077" in script


def test_broker_passwords_are_hashed_from_mode_600_files() -> None:
    setup = read("scripts/setup_zigbee_stack.sh")
    assert "mosquitto_passwd -U /work/passwords" in setup
    assert "printf '%s:%s\\n' zigbee2mqtt \"$mqtt_password\" >\"$mosquitto_dir/passwords\"" in setup
    assert 'acl.conf" ]]' in setup

    app_setup = read("scripts/setup_app_mqtt.sh")
    assert 'app_mqtt_user="aircon-controller"' in app_setup
    assert 'mosquitto_passwd -U "/work/${staging_name}"' in app_setup
    assert 'docker kill --signal=HUP "${mosquitto_container}"' in app_setup
    # The broker bind-mounts this single file; a rename hides the new user until a restart.
    assert 'cat -- "${passwords_file}.tmp" >"${passwords_file}"' in app_setup
    assert 'mv -f -- "${passwords_file}.tmp"' not in app_setup
    assert "secret.yaml" not in app_setup
    assert 'APP_MQTT_PASSWORD="${app_password}"' in app_setup
    assert '"AIRCON_MQTT_USERNAME": os.environ["APP_MQTT_USERNAME"]' in app_setup


def test_app_broker_identity_is_limited_by_the_acl() -> None:
    acl = read("deploy/zigbee/mosquitto/acl.conf")
    users = [line.split()[1] for line in acl.splitlines() if line.startswith("user ")]
    assert users == ["zigbee2mqtt", "aircon-controller"]
    app_section = acl.split("user aircon-controller", 1)[1]
    app_rules = [line for line in app_section.splitlines() if line.startswith("topic ")]
    assert app_rules == [
        "topic read zigbee2mqtt/#",
        "topic write zigbee2mqtt/+/set",
        "topic write zigbee2mqtt/bridge/request/permit_join",
    ]
    z2m_section = acl.split("user zigbee2mqtt", 1)[1].split("user aircon-controller", 1)[0]
    assert "topic readwrite zigbee2mqtt/#" in z2m_section

    assert "acl_file /mosquitto/config/acl.conf" in read("deploy/zigbee/mosquitto/mosquitto.conf")
    compose = read("deploy/zigbee/compose.yaml")
    assert "- ./mosquitto/acl.conf:/mosquitto/config/acl.conf:ro" in compose
    assert "- ./mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro" in compose


def test_stack_check_verifies_the_acl_mount_and_app_user() -> None:
    check = read("scripts/check_zigbee_stack.sh")
    assert 'test -s /mosquitto/config/acl.conf' in check
    assert "MQTT_ACL_FILE_MOUNTED=" in check
    assert "APP_MQTT_USER_PRESENT=" in check
    assert 'bridge_state="$(mqtt_sub -t zigbee2mqtt/bridge/state -C 1 -W 10)"' in check


def test_permit_join_script_targets_the_coordinator_only() -> None:
    script = read("scripts/zigbee_join_control.sh")
    assert '"device\\":\\"coordinator\\"' in script
