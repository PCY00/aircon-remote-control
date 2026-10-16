"""Download the pinned Firebase web SDK modules into the family web app's vendor folder.

The /app/ pages only allow scripts from the same origin, so the three ES modules the web app
uses are stored next to it. The only change made to the downloaded files is turning the
absolute import of firebase-app.js in an import statement into a relative one. String constants
that merely contain the URL (the library name used for version logging) are left as they are.

    python -I server/scripts/web/fetch_firebase_sdk.py            # download, rewrite, write README
    python -I server/scripts/web/fetch_firebase_sdk.py --verify   # offline: re-hash the vendored files
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import urllib.request
from pathlib import Path

VERSION = "12.19.0"
BASE = f"https://www.gstatic.com/firebasejs/{VERSION}/"
FILES = ("firebase-app.js", "firebase-auth.js", "firebase-messaging.js")
APP_IMPORT = BASE + "firebase-app.js"
MAX_BYTES = 4 * 1024 * 1024
# SHA-256 of the originals as served on the first download (2026-10-16). A later download with
# different bytes stops instead of silently replacing reviewed files.
PINNED = {
    "firebase-app.js": "39a50952b5def557337b2290069c7d7371f3515ad46c44a43b9c520f734d8d14",
    "firebase-auth.js": "59f60ce3adcb4c85a5260e963fd14134eec088de5b18ddfb9e95771c72f65264",
    "firebase-messaging.js": "7572acc95d2f0182ef70bb16b2920b022340bde54cea5962704c745488e98b23",
}
VENDOR = Path(__file__).resolve().parents[2] / "services/central-server/central_server/webapp/vendor"
# Import specifiers only: `from"<url>"`, `from "<url>"`, `import("<url>")`, `import"<url>"`.
SPECIFIER = r"""((?:\bfrom|\bimport)\s*\(?\s*["']){url}(["'])"""
REMOTE_IMPORT = re.compile(r"""(?:\bfrom|\bimport)\s*\(?\s*["'`](?:https?:)?//""")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def swap(text: str, old: str, new: str) -> tuple[str, int]:
    return re.subn(SPECIFIER.format(url=re.escape(old)), lambda m: m.group(1) + new + m.group(2), text)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # the pinned URL must answer directly
        return None


def download(name: str) -> bytes:
    opener = urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(BASE + name, headers={"User-Agent": "family-webapp-vendor/1"})
    with opener.open(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"{name}: HTTP {response.status}")
        kind = response.headers.get("Content-Type", "")
        if "javascript" not in kind:
            raise RuntimeError(f"{name}: unexpected content type {kind!r}")
        data = response.read(MAX_BYTES + 1)
    if not data or len(data) > MAX_BYTES:
        raise RuntimeError(f"{name}: unexpected size {len(data)}")
    return data


def rewrite(name: str, data: bytes) -> bytes:
    text, count = swap(data.decode("utf-8"), APP_IMPORT, "./firebase-app.js")
    if name != "firebase-app.js" and count != 1:
        raise RuntimeError(f"{name}: expected one import of {APP_IMPORT}, found {count}")
    remaining = REMOTE_IMPORT.findall(text)
    if remaining:
        raise RuntimeError(f"{name}: {len(remaining)} remote import(s) remain after rewriting")
    return text.encode("utf-8")


def original(data: bytes) -> bytes:
    """Undo the rewrite, so the vendored file can be checked against the pinned download."""
    return swap(data.decode("utf-8"), "./firebase-app.js", APP_IMPORT)[0].encode("utf-8")


def readme(rows) -> str:
    lines = [
        "# Firebase 웹 SDK (고정 버전)",
        "",
        f"가족 웹앱이 쓰는 Firebase JS SDK {VERSION} ES 모듈 세 개다. Firebase SDK 세 파일을 같은 출처에서 제공하기 위해",
        "실행 중에 외부 CDN에서 받지 않고 이 폴더의 파일을 쓴다.",
        "",
        "- 받은 곳: " + ", ".join(f"`{BASE}{name}`" for name in FILES),
        f"- 바꾼 것: import 문의 `{APP_IMPORT}`를 `./firebase-app.js`로 바꾼 것뿐이다"
        " (`firebase-auth.js`, `firebase-messaging.js`에 하나씩). `firebase-app.js`는 받은 그대로다.",
        "- 다시 받기: 저장소 루트에서 `python -I server/scripts/web/fetch_firebase_sdk.py`",
        "- 해시 확인(네트워크 없음): `python -I server/scripts/web/fetch_firebase_sdk.py --verify`",
        "",
        "| 파일 | 원본 크기(바이트) | 받은 원본 SHA-256 | 이 폴더 파일 SHA-256 |",
        "|---|---:|---|---|",
    ]
    for name, digest, size, written in rows:
        lines.append(f"| `{name}` | {size} | `{digest}` | `{written}` |")
    lines.append("")
    return "\n".join(lines)


def verify() -> int:
    text = (VENDOR / "README.md").read_text(encoding="utf-8")
    failed = 0
    for name in FILES:
        data = (VENDOR / name).read_bytes()
        digest, source = sha256(data), sha256(original(data))
        listed = re.search(
            rf"\| `{re.escape(name)}` \| \d+ \| `([0-9a-f]{{64}})` \| `([0-9a-f]{{64}})` \|", text)
        remote = REMOTE_IMPORT.findall(data.decode("utf-8"))
        ok = (bool(listed) and listed.group(1) == PINNED[name] == source
              and listed.group(2) == digest and not remote)
        failed += not ok
        print(f"{'OK  ' if ok else 'FAIL'} {name} vendored={digest} original={source} "
              f"remote_imports={len(remote)}")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verify", action="store_true", help="only re-hash the vendored files")
    parser.add_argument("--readme", action="store_true",
                        help="offline: rewrite README.md from the vendored files")
    args = parser.parse_args()
    if args.verify:
        return verify()
    VENDOR.mkdir(parents=True, exist_ok=True)
    rows = []
    for name in FILES:
        if args.readme:
            written = (VENDOR / name).read_bytes()
            source = original(written)
        else:
            source = download(name)
            written = rewrite(name, source)
        digest = sha256(source)
        if PINNED[name] != digest:
            raise RuntimeError(f"{name}: SHA-256 {digest} differs from the pinned {PINNED[name]}")
        if not args.readme:
            (VENDOR / name).write_bytes(written)
        rows.append((name, digest, len(source), sha256(written)))
        print(f"{name}: original {digest} ({len(source)} bytes) -> vendored {sha256(written)}")
    (VENDOR / "README.md").write_text(readme(rows), encoding="utf-8", newline="\n")
    return verify()


if __name__ == "__main__":
    sys.exit(main())
