"""Public captures must not carry the PC account, network identifiers, hosts or pairing codes."""

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parents[1] / "scripts/android"
sys.path.insert(0, str(SCRIPTS))
import a50_adb  # noqa: E402
import a50_record  # noqa: E402

TOKEN = "UNIT_TEST_TOKEN_00000000000000000000000000"


def phone_files(root, home_user="unitowner"):
    private = root / ".deploy/a50"
    private.mkdir(parents=True)
    binary = root / "adb.exe"
    binary.touch()
    (private / "adb.json").write_text(
        json.dumps(
            {
                "adb_path": str(binary),
                "device_serial": "EXPECTED",
                "model": "SM-A505N",
                "mdns_prefix": "adb-EXPECTED-",
                "manager_rpc_token": TOKEN,
            }
        )
    )
    (private / "connection.json").write_text(
        json.dumps(
            {
                "identity_file": str(root / ("key-" + home_user)),
                "known_hosts_file": str(root / ("known-" + home_user)),
                "port": 8022,
                "user": "u0_a1",
                "host": "192.0.2.1",
            }
        )
    )
    return private


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("USERNAME", "unitowner")
    monkeypatch.setenv("USER", "unitowner")
    monkeypatch.setattr(a50_adb.getpass, "getuser", lambda: "unitowner")
    return a50_adb.A50ADB(phone_files(tmp_path) / "adb.json")


@pytest.mark.parametrize(
    ("sample", "expected"),
    [
        (
            # Drive letter joined at runtime so the bundle audit does not read a real user path.
            "C:" + r"\Users\unitowner\AppData\Local\Temp\pytest-of-unitowner\pytest-3\x",
            "C:" + r"\Users\[REDACTED_USER]\AppData\Local\Temp\pytest-of-[REDACTED_USER]\pytest-3\x",
        ),
        (
            "unitowner@phone: Permission denied; /tmp/pytest-of-other/pytest-1",
            "[REDACTED_USER]@phone: Permission denied; /tmp/pytest-of-[REDACTED_USER]/pytest-1",
        ),
        (
            "fe80::1%wlan0 2001:db8:85a3::8a2e:370:7334 [fd7a:115c:a1e0::1]:8022 ::1",
            "[REDACTED_ADDRESS] [REDACTED_ADDRESS] [[REDACTED_ADDRESS]]:8022 [REDACTED_ADDRESS]",
        ),
        (
            "2001:0db8:0000:0000:0000:ff00:0042:8329 2001:db8::/32",
            "[REDACTED_ADDRESS] [REDACTED_ADDRESS]",
        ),
        ("BSSID: aa:bb:cc:dd:ee:ff AP 02-00-00-00-AA-01", "BSSID: [REDACTED_MAC] AP [REDACTED_MAC]"),
        (
            "ssh: connect to host raspberrypi.tail1234.ts.net port 22",
            "ssh: connect to host [REDACTED_TAILNET_HOST] port 22",
        ),
        (
            "https://quiet-test-words.trycloudflare.com/health",
            "https://[REDACTED_TUNNEL_HOST]/health",
        ),
        (
            "Enter pairing code: 123456 | Wi-Fi pairing code 654321",
            "Enter pairing code: [REDACTED_CODE] | Wi-Fi pairing code [REDACTED_CODE]",
        ),
        (
            "EXPECTED " + TOKEN + " u0_a123 uid=10123 192.0.2.1:43210",
            "[REDACTED_DEVICE_ID] [REDACTED_CAPABILITY] [REDACTED_APP_USER] uid=[REDACTED] "
            "[REDACTED_ADDRESS]",
        ),
    ],
)
def test_private_values_are_replaced(client, sample, expected):
    assert client.redact(sample) == expected


@pytest.mark.parametrize(
    "sample",
    [
        "10-15 12:34:56.789 I/tag: std::string Foo::bar()",
        "SHA256:AB:CD:EF:01:23:45:67:89:AB:CD:EF:01:23:45:67:89:AB:CD:EF:01:23:45:67:89:AB:CD:EF:01:23:45:67:89",
        "EXIT_CODE=0 BYTES=123456 timeout 123456 ms code 1234567 cert aa:bb:cc:dd:ee:ff:00",
        "the unitowners key unitowner_x unitowner1",
    ],
)
def test_timestamps_fingerprints_counts_and_other_words_are_kept(client, sample):
    assert client.redact(sample) == sample


def test_session_log_hides_home_path_account_and_pi_style_ssh_errors(tmp_path, monkeypatch):
    home = tmp_path / "home-unitowner"
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setenv("USERNAME", "unitowner")
    monkeypatch.setenv("USER", "unitowner")
    monkeypatch.setattr(a50_adb.getpass, "getuser", lambda: "unitowner")
    monkeypatch.setattr(a50_record.Path, "home", classmethod(lambda cls: home))
    phone_files(work)
    session = a50_record.PhoneSession("unit")
    session.log(
        "Warning: Identity file " + str(home / ".ssh" / "pi-reader") + " not accessible.\n"
        # Joined at runtime so the bundle audit does not read the made-up host as an email.
        "piuser" + "@" + "raspberrypi.tail1234.ts.net: Permission denied (publickey).\n"
        "ssh: connect to host fd7a:115c:a1e0::1234 port 22: Connection timed out"
    )
    record = session.record.read_text(encoding="utf-8")
    assert "[REDACTED_LOCAL_PATH]" + str(Path("/.ssh/pi-reader")).replace("/", "\\") in record
    assert str(tmp_path) not in record and "unitowner" not in record
    assert "[REDACTED_TAILNET_HOST]" in record and "tail1234" not in record
    assert "[REDACTED_ADDRESS] port 22" in record and "fd7a" not in record
