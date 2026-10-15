"""Build a local reader ZIP from selected source files, linked docs and public images."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from sanitize_blog_images import find_private_metadata  # noqa: E402

VERSION = re.search(
    r"VERSION = ['\"]([^'\"]+)['\"]",
    (ROOT / "services/central-server/central_server/__init__.py").read_text(encoding="utf-8"),
)[1]
BUNDLE_NAME = f"smart-home-reader-v{VERSION}.zip"
BAD_PARTS = {
    ".git",
    ".deploy",
    ".venv",
    "tmp",
    "runtime",
    "runtime_preview",
    "logs",
    "__pycache__",
    ".gradle",
    "build",
    "secrets",
    "node_modules",
}
BAD_NAMES = {"google-services.json", "private-build.json", "test-fixture.json", "local.properties"}
EXTENSIONS = {
    ".py",
    ".java",
    ".xml",
    ".gradle",
    ".properties",
    ".md",
    ".txt",
    ".json",
    ".sh",
    ".service",
    ".ps1",
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
}
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
TUNNEL = re.compile(r"(?:https?://)?([a-z0-9-]+)\.trycloudflare\.com")
PRIVATE_KEY = re.compile(
    # JSON service-account files escape the PEM line breaks as a literal \n.
    r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----(?:\s|\\[rn])+[A-Za-z0-9+/=]{30}"
)
PRIVATE_IPV4 = re.compile(
    r"(?<![\d.])(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}"
    r"|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}"
    r"|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])(?:\.\d{1,3}){2})(?!\.?\d)(/\d{1,2})?"
)
# Tailscale gives every device an IPv6 address in fd7a:115c:a1e0::/48.
# [:] keeps this pattern from matching its own source when the bundle audits itself.
TAILSCALE_IPV6 = re.compile(r"(?i)(?<![0-9a-f:])fd7a[:]115c[:]a1e0[:][0-9a-f:]*(/\d{1,3})?")
# MAC-48 (6 octets) or EUI-64 such as a Zigbee IEEE address (8 octets or 0x + 16 hex).
HARDWARE_ADDRESS = re.compile(
    r"(?<![0-9A-Fa-f:-])[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}"
    r"(?:(?:[:-][0-9A-Fa-f]{2}){2})?(?![0-9A-Fa-f:-])"
    r"|\b0x[0-9A-Fa-f]{16}\b"
)
# C:\Users\<name>, c:/users/<name>, Git Bash /c/Users/<name>, WSL /mnt/c/Users/<name>.
WINDOWS_USER_PATH = re.compile(
    r"(?i)(?:\b[a-z]:[\\/]{1,2}|(?<![\w.:/])/(?:mnt/)?[a-z]/)users[\\/]{1,2}(?![<\[%$])"
)
# pytest names its temp folder after the account that ran the tests. A placeholder
# such as <name>, [REDACTED_USER] or %USERNAME% after the prefix is fine; the split
# literal keeps this pattern from matching its own source.
PYTEST_TEMP_FOLDER = re.compile(r"pytest-of" r"-(?![<\[%$])[^\\/\s'\"]+")
# Tailscale MagicDNS names reveal the tailnet and the device behind it.
TAILNET_HOST = re.compile(r"(?i)\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:ts|tailscale)\.net\b")
# Prefixes of Google API keys and OAuth client secrets, Tailscale auth keys,
# household hub tokens, invitation and claim codes, and JWT-like tokens
# (cloudflared tunnel tokens look like a JWT as well).
CREDENTIAL_TOKEN = re.compile(
    r"AIza[0-9A-Za-z_-]{30,}"
    r"|GOCSPX-[0-9A-Za-z_-]{10,}"
    r"|tskey-[0-9A-Za-z-]{6,}"
    r"|(?<![0-9A-Za-z_])(?:hub|invite|claim)_[0-9A-Za-z_-]{32,}"
    r"|(?<![0-9A-Za-z_])eyJ[0-9A-Za-z_.-]{37,}"
)
RESERVED_EMAIL_DOMAINS = (".test", ".example", ".invalid", ".localhost", "example.com")


def account_names():
    """Login name of the PC running the audit; short names would match everywhere."""
    try:
        name = getpass.getuser()
    except Exception:  # no login name available on this system
        return set()
    return {name} if len(name) >= 4 else set()


ACCOUNT_NAMES = account_names()


def allowed(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    return (
        not set(relative.parts) & BAD_PARTS
        and path.name not in BAD_NAMES
        and (
            path.suffix.lower() in EXTENSIONS
            or path.name
            in {"run", "finish", "log-run", "20-start-central", ".env.example", ".gitignore"}
        )
    )


def linked_files(path: Path):
    for match in LINK.finditer(path.read_text(encoding="utf-8")):
        ref = match[1].strip().strip("<>").split(' "', 1)[0]
        if urlsplit(ref).scheme or ref.startswith("#"):
            continue
        target = (path.parent / unquote(ref.split("#", 1)[0])).resolve()
        if target.is_dir():  # A folder link reads as that folder's README in the bundle.
            target = target / "README.md"
        if not target.is_relative_to(ROOT) or not target.is_file() or not allowed(target):
            raise ValueError("Missing or excluded link in " + path.relative_to(ROOT).as_posix())
        yield target


def sources():
    files = set()
    for directory in [
        "scripts/android",
        "scripts/pi",
        "scripts/reader",
        "services/central-server",
        "services/central-tunnel",
        "services/pi-central-agent",
        "android/a50-manager",
        "android/family-app",
        "examples/mobile-app",
        "docs/blog/mobile-app",
        "tests/android",
    ]:
        files.update(
            path.resolve()
            for path in (ROOT / directory).rglob("*")
            if path.is_file() and allowed(path)
        )
    for name in [
        "scripts/render_terminal_capture.py",
        "scripts/sanitize_blog_images.py",
        "tests/__init__.py",
        ".gitignore",
        "pytest.ini",
    ]:
        files.add((ROOT / name).resolve())
    for pattern in [
        "test_a50_*.py",
        "test_aircon_control.py",
        "test_central_*.py",
        "test_pi_agent_deploy.py",
        "test_pi_central_agent.py",
        "test_pi_receipt_trigger.py",
        "test_reader_setup.py",
    ]:
        files.update(p.resolve() for p in (ROOT / "tests").glob(pattern))
    pending = [path for path in files if path.suffix == ".md"]
    visited = set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        for target in linked_files(path):
            files.add(target)
            if target.suffix == ".md":
                pending.append(target)
    # Terminal screenshots always include their searchable original, and vice versa.
    for path in list(files):
        if path.parent == ROOT / "docs/assets/terminal" and path.suffix in {".png", ".txt"}:
            other = path.with_suffix(".txt" if path.suffix == ".png" else ".png")
            if not other.is_file():
                raise ValueError("Terminal image/text pair missing: " + path.name)
            files.add(other)
    return sorted(files)


def private_values():
    values = set()
    fields = {
        "device_serial",
        "manager_rpc_token",
        "private_key",
        "hub_token",
        "firebase_project_id",
        "project_id",
        "project_number",
        "mobilesdk_app_id",
        "client_id",
        "current_key",
        "client_email",
        "host",
        "cached_endpoint",
        "identity_file",
        "known_hosts_file",
        # Local tool and signing paths contain the PC user name.
        "adb_path",
        "java_home",
        "sdk",
        "gradle",
        "signing_file",
        "signing_password_file",
        "executable",
        "folder",
        "stage",
        # Private Notion pages and household test tokens.
        "notification_page_url",
        "notification_page_id",
        "diary_page_id",
        "month_page_id",
        "topic_page_id",
        "day_block_id",
        "schedule_block_id",
        "owner_token",
        "family_token",
        "guest_token",
        "other_token",
    }

    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if isinstance(item, str) and key in fields and len(item) >= 7:
                    values.add(item)
                if key == "url" and isinstance(item, str) and ".trycloudflare.com" in item:
                    values.add(item)
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    for path in (ROOT / ".deploy").rglob("*.json"):
        try:
            visit(json.loads(path.read_text(encoding="utf-8-sig")))
        except (ValueError, UnicodeError):
            continue
    return values


def text_privacy_issue(text, *, prose=False, fixture=False):
    """Name the first kind of private value in a bundled text, or return None.

    Test fixtures may use made-up LAN and hardware addresses on purpose, so
    those two checks only apply to code, documents and terminal captures.
    Made-up pytest temp folders and Tailscale host names in fixtures are fine
    as well; credential-like tokens and the login name itself are rejected
    everywhere.
    """
    if PRIVATE_KEY.search(text):
        return "Private key content"
    for match in TUNNEL.finditer(text):
        # api.trycloudflare.com and test fixtures in code are not live tunnels,
        # and a bare host name without a scheme inside a fixture is made up too.
        if prose:
            return "Live tunnel URL"
        if match[1] == "api" or "test" in match[1].split("-"):
            continue
        if match[0].startswith("http") or not fixture:
            return "Live tunnel URL"
    for match in EMAIL.finditer(text):
        # Reader prose never shows an address; code may use reserved test domains
        # and Google's public token signer.
        domain = match[1].lower()
        if prose or not (
            domain.endswith(RESERVED_EMAIL_DOMAINS) or domain == "system.gserviceaccount.com"
        ):
            return "Email address"
    for match in [] if fixture else PRIVATE_IPV4.finditer(text):
        # A network literal such as 100.64.0.0/10 is not a device address.
        if not (match[1] and match[0].split("/")[0].endswith(".0")):
            return "Private network address"
    for match in [] if fixture else TAILSCALE_IPV6.finditer(text):
        # The fd7a:115c:a1e0::/48 network literal itself is not a device address.
        if not (match[1] and match[0].split("/")[0].endswith("::")):
            return "Private network address"
    for match in [] if fixture else HARDWARE_ADDRESS.finditer(text):
        # 02:00:00:... is the locally administered prefix used for fixtures.
        if not match[0].replace("-", ":").lower().startswith("02:00:00:"):
            return "Hardware address"
    if WINDOWS_USER_PATH.search(text):
        return "Windows user folder path"
    if not fixture and PYTEST_TEMP_FOLDER.search(text):
        return "Pytest temp folder with account name"
    if not fixture and TAILNET_HOST.search(text):
        return "Tailscale host name"
    if CREDENTIAL_TOKEN.search(text):
        return "Credential-like token"
    for name in ACCOUNT_NAMES:
        if re.search(r"(?i)(?<![0-9A-Za-z_])" + re.escape(name) + r"(?![0-9A-Za-z_])", text):
            return "PC account name"
    return None


def service_account_json(value):
    if isinstance(value, dict):
        if value.get("type") == "service_account" or "private_key" in value:
            return True
        value = list(value.values())
    return isinstance(value, list) and any(service_account_json(item) for item in value)


def audit(files):
    sensitive = private_values()
    metadata_count = 0
    image_count = 0
    for path in files:
        data = path.read_bytes()
        if path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            with Image.open(path):
                image_count += 1
            metadata_count += bool(find_private_metadata(path))
            continue
        text = data.decode("utf-8")
        relative = path.relative_to(ROOT)
        label = relative.as_posix()
        if any(value in text for value in sensitive):
            raise ValueError("Private configured value found in " + label)
        if path.suffix.lower() == ".json":
            try:
                document = json.loads(text)
            except ValueError:
                document = None
            if service_account_json(document):
                raise ValueError("Service account key found in " + label)
        issue = text_privacy_issue(
            text,
            prose=path.is_relative_to(ROOT / "docs/blog/mobile-app"),
            fixture=relative.parts[0] == "tests"
            or not {"test", "androidTest", "fixture"}.isdisjoint(relative.parts),
        )
        if issue:
            raise ValueError(issue + " found in " + label)
    if metadata_count:
        raise ValueError("Private image metadata remains")
    print("BUNDLE_PRIVATE_VALUES_FOUND=0 PRIVATE_METADATA_COUNT=0 IMAGE_COUNT=" + str(image_count))


def check_tutorial():
    directory = ROOT / "docs/blog/mobile-app"
    chapters = [
        directory / name
        for name in [
            "01-galaxy-a50-preparation.md",
            "02-a50-central-server.md",
            "03-household-permissions.md",
            "04-family-android-app.md",
            "05-external-https-connection.md",
            "06-family-fcm-notifications.md",
            "07-raspberry-pi-event-relay.md",
            "08-notification-choices-and-home-management.md",
            "09-ui-redesign-and-scroll.md",
        ]
    ]
    command_count = 0
    for i, path in enumerate(chapters):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("# [편하게 살자] 스마트홈 알림 - ") or "앞에서 준비할 것" not in text:
            raise ValueError("Chapter opening missing: " + path.name)
        if i < 8 and "여기까지 확인할 것" not in text:
            raise ValueError("Chapter completion missing: " + path.name)
        if re.search(r"(?m)^#{1,6}\s+(?:\d+편|\d+[. ]|1편부터)", text):
            raise ValueError("Numbered heading remains: " + path.name)
        if re.search(r"(?<!!)\[[^\]]*\]\((?!https?://)[^)]+\)", text):
            raise ValueError("Local document link remains: " + path.name)
        if re.search(r"(?m)^## [^\n]+\n(?!\n---\n)", text):
            raise ValueError("Heading divider missing: " + path.name)
        body = re.sub(r"```.*?```", "", text, flags=re.S)
        if re.search(r"검증|점검|보완", body):
            raise ValueError("Requested plain-language edit missing: " + path.name)
        for match in re.finditer(r"\.venv/Scripts/python\.exe\s+(scripts/[^\s`]+\.py)", text):
            if not (ROOT / match[1]).is_file():
                raise ValueError("Command script missing: " + match[1])
            command_count += 1
    print("CHAPTER_FLOW=9/9 COMMAND_REFERENCES_PRESENT=" + str(command_count))


def build(output):
    check_tutorial()
    files = sources()
    audit(files)
    manifest = {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files
    }
    readme = (
        "# 스마트홈 블로그 따라 하기 자료\n\n"
        "[전체 목차](docs/blog/mobile-app/README.md)와 "
        "[시작 안내](docs/blog/mobile-app/00-reader-start.md)부터 읽으세요.\n\n"
        f"서버와 앱 소스 {VERSION}, 본인 설정을 만드는 도구, 글과 공개용 화면을 포함합니다. "
        "실제 계정 설정과 개인 키 및 APK는 포함하지 않습니다. "
        "본인 Firebase 프로젝트와 서명으로 앱을 만드세요. "
        "Pi 기록 연결 글은 기존 Pi 센서 프로그램의 기록이 있는 환경에서 사용합니다.\n"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            item = zipfile.ZipInfo(
                path.relative_to(ROOT).as_posix(), date_time=(2026, 10, 4, 0, 0, 0)
            )
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, path.read_bytes())
        for name, content in [
            ("README.md", readme),
            ("MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"),
        ]:
            item = zipfile.ZipInfo(name, date_time=(2026, 10, 4, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, content.encode("utf-8"))
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(
        digest + "  " + output.name + "\n", encoding="utf-8"
    )
    print("READER_BUNDLE_FILES=" + str(len(manifest) + 2) + " BYTES=" + str(output.stat().st_size))
    print("READER_BUNDLE_SHA256=" + digest + " PUBLISHED=False")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "tmp/mobile-app-reader" / BUNDLE_NAME)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.check_only:
        check_tutorial()
        files = sources()
        audit(files)
        print("BUNDLE_SOURCE_FILES=" + str(len(files)))
    else:
        build(args.output.resolve())


if __name__ == "__main__":
    main()
