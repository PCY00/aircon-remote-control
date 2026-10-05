"""Build a local reader ZIP from selected source files, linked docs and public images."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
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
}
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


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
    ]:
        files.add((ROOT / name).resolve())
    for pattern in [
        "test_a50_*.py",
        "test_central_*.py",
        "test_pi_agent_deploy.py",
        "test_pi_central_agent.py",
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


def audit(files):
    sensitive = private_values()
    metadata_count = 0
    image_count = 0
    for path in files:
        data = path.read_bytes()
        if path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            with Image.open(path) as picture:
                image_count += 1
                metadata_count += bool(
                    picture.getexif()
                    or picture.info.get("exif")
                    or picture.info.get("xmp")
                    or picture.info.get("XML:com.adobe.xmp")
                )
            continue
        text = data.decode("utf-8")
        if any(value in text for value in sensitive):
            raise ValueError(
                "Private configured value found in " + path.relative_to(ROOT).as_posix()
            )
        if re.search(
            r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s+[A-Za-z0-9+/=]{30}", text
        ):
            raise ValueError("Private key content found in " + path.relative_to(ROOT).as_posix())
        if path.is_relative_to(ROOT / "docs/blog/mobile-app"):
            if re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text):
                raise ValueError("Email address in reader prose: " + path.name)
            if re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", text):
                raise ValueError("Live tunnel URL in reader prose: " + path.name)
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
        "서버와 앱 소스 0.4.0, 본인 설정을 만드는 도구, 글과 공개용 화면을 포함합니다. "
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
    parser.add_argument(
        "--output", type=Path, default=ROOT / "tmp/mobile-app-reader/smart-home-reader-v0.4.0.zip"
    )
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
