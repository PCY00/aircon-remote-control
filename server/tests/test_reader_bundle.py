"""Reader and Tistory bundles must not ship stale photos or private values."""

import importlib
import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin

ROOT = Path(__file__).parents[1]


@pytest.fixture
def bundle(monkeypatch, tmp_path):
    """The real bundle modules, pointed at an empty temporary server folder."""
    monkeypatch.syspath_prepend(str(ROOT / "scripts/reader"))
    reader = importlib.import_module("make_reader_bundle")
    tistory = importlib.import_module("build_tistory_bundle")
    monkeypatch.setattr(reader, "ROOT", tmp_path)
    monkeypatch.setattr(tistory, "ROOT", tmp_path)
    monkeypatch.setattr(tistory, "DOCS", tmp_path / "docs/blog/mobile-app")
    monkeypatch.setattr(reader, "ACCOUNT_NAMES", {"tester-account"})
    return reader, tistory


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_reader_bundle_version_and_control_tests():
    spec = importlib.util.spec_from_file_location(
        "reader_central_version", ROOT / "services/central-server/central_server/__init__.py"
    )
    central = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(central)
    sys.path.insert(0, str(ROOT / "scripts/reader"))
    reader = importlib.import_module("make_reader_bundle")
    expected_name = "smart-home-reader-v" + central.VERSION + ".zip"
    assert reader.VERSION == central.VERSION
    assert expected_name == reader.BUNDLE_NAME
    assert (ROOT / "tests/test_aircon_control.py").resolve() in reader.sources()


def test_bundle_audit_rejects_png_text_and_jpeg_app13(bundle, tmp_path):
    reader, _ = bundle
    png = tmp_path / "docs/assets/terminal/comment.png"
    png.parent.mkdir(parents=True)
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Comment", "private")
    Image.new("RGB", (4, 4), "white").save(png, format="PNG", pnginfo=metadata)
    jpeg = tmp_path / "docs/assets/hardware/iptc.jpg"
    jpeg.parent.mkdir(parents=True)
    Image.new("RGB", (4, 4), "white").save(jpeg, format="JPEG")
    data = jpeg.read_bytes()
    payload = b"Photoshop 3.0\x008BIM\x04\x04city=private"
    app13 = b"\xff\xed" + (len(payload) + 2).to_bytes(2, "big") + payload
    jpeg.write_bytes(data[:2] + app13 + data[2:])

    for path in [png, jpeg]:
        with pytest.raises(ValueError, match="Private image metadata remains"):
            reader.audit([path])


def test_bundle_audit_rejects_png_c2pa_chunk(bundle, tmp_path):
    reader, _ = bundle
    png = tmp_path / "docs/assets/hardware/edited.png"
    png.parent.mkdir(parents=True)
    Image.new("RGB", (4, 4), "white").save(png, format="PNG")
    data = png.read_bytes()
    end = data.rindex(b"IEND") - 4
    chunk = b"\x00\x00\x00\x04caBX" + b"c2pa" + b"\x00\x00\x00\x00"
    png.write_bytes(data[:end] + chunk + data[end:])
    with pytest.raises(ValueError, match="Private image metadata remains"):
        reader.audit([png])


@pytest.mark.parametrize(
    "text, issue",
    [
        ("adb connect 192.168.0.23:5555\n", "Private network address"),
        ("tailscale ip 100.101.102.103\n", "Private network address"),
        ("Wi-Fi MAC 3c:71:bf:12:34:56\n", "Hardware address"),
        ("C:\\Users\\reader-name\\AppData\\Local\\Android\\Sdk\n", "Windows user folder path"),
        ("c:\\users\\reader-name\\appdata\n", "Windows user folder path"),
        ("$ ls /c/Users/reader-name/AppData\n", "Windows user folder path"),
        ("cd /mnt/c/Users/reader-name\n", "Windows user folder path"),
        ("ieee_address 00:12:4b:00:29:ab:cd:ef\n", "Hardware address"),
        ("tailscale ip -6 fd7a:115c:a1e0:ab12:4843:cd96:6258:b240\n", "Private network address"),
        ("Signed in as reader.name@gmail.com\n", "Email address"),
        ("https://calm-river-blue-sky.trycloudflare.com\n", "Live tunnel URL"),
        ("quick tunnel four-random-words.trycloudflare.com\n", "Live tunnel URL"),
        # The prefix is split so a repository-wide search finds only the captures.
        ("tmp_path = WindowsPath('[REDACTED_LOCAL_PATH]/AppData/Local/Temp/pytest-of" "-reader-name/pytest-3/x0')\n",
         "Pytest temp folder"),
        ("ping aircon-pi.tail1a2b3c.ts.net\n", "Tailscale host name"),
        ("curl https://a50.example-tailnet.tailscale.net:8443/health\n", "Tailscale host name"),
        ("current_key: AIza" + "a" * 35 + "\n", "Credential-like token"),
        ("client_secret=GOCSPX-" + "b" * 28 + "\n", "Credential-like token"),
        ("tailscale up --auth-key tskey-auth-" + "c" * 30 + "\n", "Credential-like token"),
        ("Authorization: Bearer hub_" + "d" * 40 + "\n", "Credential-like token"),
        ("invite_" + "e" * 40 + "\n", "Credential-like token"),
        ("claim_" + "f" * 40 + "\n", "Credential-like token"),
        ("cloudflared tunnel run --token eyJhIjoi" + "g" * 60 + "\n", "Credential-like token"),
        ("id_token=eyJhbGciOiJSUzI1NiJ9." + "h" * 24 + "." + "i" * 16 + "\n", "Credential-like token"),
        ("Logged in as Tester-Account on this PC\n", "PC account name"),
    ],
)
def test_bundle_audit_rejects_private_values_in_terminal_capture(bundle, tmp_path, text, issue):
    reader, _ = bundle
    capture = write(tmp_path / "docs/assets/terminal/150-x.txt", text)
    with pytest.raises(ValueError, match=issue):
        reader.audit([capture])


def test_bundle_audit_allows_fixtures_and_network_literals(bundle, tmp_path, capsys):
    reader, _ = bundle
    files = [
        write(tmp_path / "tests/test_fixture.py", "ORIGIN = 'http://192.168.1.2:8001'\n"),
        write(
            tmp_path / "services/pi-central-agent/agent.py",
            "TAILNET = '100.64.0.0/10'\nOWNER = 'owner@example.test'\n",
        ),
        write(
            tmp_path / "docs/assets/terminal/151-x.txt",
            "C:\\Users\\<name>\\adb.exe /c/Users/<name>/x fd7a:115c:a1e0::/48\n"
            "SHA-256 " + ":".join(["AB"] * 32) + " GET https://example.com/c/users/list\n",
        ),
        write(
            tmp_path / "docs/assets/terminal/153-x.txt",
            "pytest-of" "-[REDACTED_USER]/pytest-21/x pytest-of" "-<name> pytest-of" "-%USERNAME%\n"
            "INSTRUMENTATION_STATUS: hub_claim=one_time_claim_consumed_by_this_run_only\n"
            "def test_hub_expiry_without_renewal_rejects_claims(): eyJhbGciOiJIUzI1NiJ9\n"
            "quick tunnels end in api.trycloudflare.com; tester-accounting is not a login\n",
        ),
        write(
            tmp_path / "tests/test_tunnel.py",
            "URL = 'https://four-random-test-words.trycloudflare.com'\n"
            "HOST = 'pi.tail0000.ts.net'\n"
            "BARE = 'abc.trycloudflare.com'\n"
            "TMP = '/Temp/pytest-of" "-someone/pytest-1'\n",
        ),
    ]
    reader.audit(files)
    assert "BUNDLE_PRIVATE_VALUES_FOUND=0" in capsys.readouterr().out


def test_bundle_audit_rejects_service_account_json(bundle, tmp_path):
    reader, _ = bundle
    key = "-----BEGIN PRIVATE KEY-----\n" + "A" * 64 + "\n-----END PRIVATE KEY-----\n"
    account = write(
        tmp_path / "examples/mobile-app/project-firebase-adminsdk-x.json",
        json.dumps({"type": "service_account", "private_key": key}),
    )
    with pytest.raises(ValueError, match="Service account key"):
        reader.audit([account])
    # The same key pasted as escaped JSON text into another file is still caught.
    escaped = write(tmp_path / "docs/assets/terminal/152-x.txt", json.dumps({"k": key}))
    with pytest.raises(ValueError, match="Private key content"):
        reader.audit([escaped])


@pytest.fixture
def tistory_build(bundle, tmp_path, monkeypatch):
    """Run build_tistory_bundle.main() with a fake Markdown renderer and reader build."""
    reader, tistory = bundle
    assets = tmp_path / "docs/assets/hardware"
    assets.mkdir(parents=True)
    for name in ["unredacted-server-address.png", "safe.png"]:
        Image.new("RGB", (4, 4), "white").save(assets / name, format="PNG")
    chapter_images = {}
    failures = []

    def fake_render(command, **kwargs):
        if failures:
            raise subprocess.CalledProcessError(1, command)
        stage = Path(command[command.index("-OutputDirectory") + 1])
        stage.mkdir(parents=True, exist_ok=True)
        for number, chapter in enumerate(tistory.CHAPTERS, 1):
            images = "".join(
                '<p><img src="../../assets/hardware/' + name + '" alt="사진"></p>\n'
                for name in chapter_images.get(chapter, [])
            )
            heading = f"<h1>글 {number}</h1>\n<h2>준비</h2>\n<hr>\n"
            (stage / (chapter + ".html")).write_text(
                heading + "<p>본문 문단이다.</p>\n" + images, encoding="utf-8"
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(tistory.subprocess, "run", fake_render)
    monkeypatch.setattr(tistory, "build_reader", lambda output: output.write_bytes(b"reader"))
    monkeypatch.setattr(tistory, "audit", lambda files: None)
    output = tmp_path / "tmp/mobile-app-tistory"

    def build(first_chapter_images, *, fail=False):
        chapter_images[tistory.CHAPTERS[0]] = first_chapter_images
        failures[:] = [True] if fail else []
        monkeypatch.setattr(
            sys, "argv", ["build", "--output-dir", str(output), "--pwsh", "fixture-pwsh"]
        )
        tistory.main()

    return reader, tistory, output, build


def zip_names(output):
    with zipfile.ZipFile(output.with_suffix(".zip")) as archive:
        return sorted(archive.namelist())


def test_tistory_rebuild_drops_removed_photos(tistory_build, capsys):
    reader, tistory, output, build = tistory_build
    build(["unredacted-server-address.png", "safe.png"])
    build(["safe.png"])

    photos = [name for name in zip_names(output) if name.startswith("사진/")]
    assert photos == ["사진/01-01-safe.png"]
    assert sorted(path.name for path in (output / "사진").iterdir()) == ["01-01-safe.png"]
    with zipfile.ZipFile(output.with_suffix(".zip")) as archive:
        instructions = archive.read("읽는법.txt").decode("utf-8")
    assert reader.BUNDLE_NAME in instructions and "v0.4.0" not in instructions
    assert "PHOTO_UPLOAD_SLOTS=1" in capsys.readouterr().out
    record = json.loads((output / tistory.BUILD_MARKER).read_text(encoding="utf-8"))
    assert "사진/01-01-safe.png" in record["files"]
    assert "사진/01-02-safe.png" not in record["files"]
    assert not list(output.parent.glob(".mobile-app-tistory-build-*"))


def test_tistory_build_refuses_folder_it_did_not_create(tistory_build):
    _, _, output, build = tistory_build
    personal = output / "사진/family.jpg"
    personal.parent.mkdir(parents=True)
    personal.write_bytes(b"personal photo")

    with pytest.raises(ValueError, match="without a build record"):
        build(["safe.png"])
    assert personal.read_bytes() == b"personal photo"
    assert sorted(path.name for path in output.rglob("*")) == ["family.jpg", "사진"]
    assert not output.with_suffix(".zip").exists()


def test_tistory_rebuild_keeps_files_it_did_not_write(tistory_build):
    _, tistory, output, build = tistory_build
    build(["unredacted-server-address.png", "safe.png"])
    notes = output / "사진/author-notes.txt"
    notes.write_text("keep me", encoding="utf-8")

    build(["safe.png"])
    assert notes.read_text(encoding="utf-8") == "keep me"
    assert "사진/author-notes.txt" not in zip_names(output)
    assert not (output / "사진/01-01-unredacted-server-address.png").exists()

    # A failed build leaves the last good outputs and the user's file in place.
    before = sorted(path.relative_to(output) for path in output.rglob("*"))
    with pytest.raises(subprocess.CalledProcessError):
        build(["unredacted-server-address.png"], fail=True)
    assert sorted(path.relative_to(output) for path in output.rglob("*")) == before
    assert not list(output.parent.glob(".mobile-app-tistory-build-*"))


def test_bundle_audit_still_rejects_a_live_tunnel_url_inside_a_fixture(bundle, tmp_path):
    reader, _ = bundle
    fixture = write(
        tmp_path / "tests/test_live.py", "URL = 'https://made-up-words-only.trycloudflare.com'\n"
    )
    with pytest.raises(ValueError, match="Live tunnel URL"):
        reader.audit([fixture])


def test_account_name_check_uses_the_login_name_but_skips_short_names(bundle, monkeypatch):
    reader, _ = bundle
    monkeypatch.setattr(reader.getpass, "getuser", lambda: "pi")
    assert reader.account_names() == set()
    monkeypatch.setattr(reader.getpass, "getuser", lambda: "tester-account")
    assert reader.account_names() == {"tester-account"}
    assert reader.text_privacy_issue("signed in as tester-account\n") == "PC account name"
    assert reader.text_privacy_issue("tester-accounting\n") is None
