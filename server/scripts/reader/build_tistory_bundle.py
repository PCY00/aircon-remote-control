"""Export blog body HTML with inline styles, upload-ready photos and an author preview."""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from make_reader_bundle import BUNDLE_NAME, audit, build as build_reader

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/blog/mobile-app"
PUBLIC_CODE_URL = "https://github.com/PCY00/aircon-remote-control/tree/main/server"
# Lists the files a build wrote, so a rebuild only replaces its own outputs.
BUILD_MARKER = ".tistory-build.json"
CHAPTERS = [
    "01-galaxy-a50-preparation", "02-a50-central-server", "03-household-permissions",
    "04-family-android-app", "05-external-https-connection", "06-family-fcm-notifications",
    "07-raspberry-pi-event-relay", "08-notification-choices-and-home-management",
    "09-ui-redesign-and-scroll",
]
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
STYLES = {
    "p": "margin:18px 0 22px;text-indent:1em;line-height:1.9;word-break:keep-all;overflow-wrap:anywhere;",
    "h3": "margin:38px 0 10px;font-size:23px;line-height:1.5;font-weight:700;word-break:keep-all;",
    "hr": "margin:0 0 24px;border:0;border-top:1px solid #d8d8d8;width:100%;",
    "table": "width:100%;border-collapse:collapse;margin:22px 0 28px;font-size:15px;table-layout:auto;",
    "th": "background-color:#6ed3d8;border:1px solid #b7d9db;padding:10px 12px;text-align:center;font-weight:400;overflow-wrap:anywhere;",
    "td": "border:1px solid #ddd;padding:10px 12px;text-align:center;vertical-align:middle;overflow-wrap:anywhere;",
    "pre": "margin:22px 0 28px;padding:16px;background-color:#f5f5f5;border:1px solid #e1e1e1;overflow-x:auto;white-space:pre;line-height:1.7;text-indent:0;tab-size:4;",
    "code": "font-family:Consolas,monospace;font-size:0.9em;",
    "ul": "padding-left:24px;margin:18px 0 24px;line-height:1.9;",
    "ol": "padding-left:26px;margin:18px 0 24px;line-height:1.9;",
    "li": "margin:8px 0;line-height:1.9;",
    "blockquote": "margin:20px 0;padding:12px 18px;border-left:3px solid #6ed3d8;",
    "figure": "margin:24px 0;",
    "figcaption": "font-size:14px;line-height:1.7;text-align:center;color:#666;margin-top:8px;",
    "img": "display:block;max-width:100%;height:auto;margin:0 auto;",
    "a": "color:#247f85;text-decoration:underline;overflow-wrap:anywhere;",
}


@dataclass
class Element:
    tag: str
    attrs: dict[str, str | None] = field(default_factory=dict)
    children: list = field(default_factory=list)


class DOM(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Element("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Element(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, text):
        self.stack[-1].children.append(text)


def text_of(node):
    return node if isinstance(node, str) else "".join(text_of(c) for c in node.children)


def serialize(node):
    if isinstance(node, str):
        return html.escape(node, quote=False)
    if node.tag == "root":
        return "\n".join(serialize(c) for c in node.children)
    if node.tag == "comment":
        return "<!-- " + text_of(node).replace("--", "—") + " -->"
    attributes = "".join(
        " " + k + ("" if v is None else '="' + html.escape(v, quote=True) + '"')
        for k, v in node.attrs.items()
    )
    start = "<" + node.tag + attributes + ">"
    if node.tag in VOID:
        return start
    return start + "".join(serialize(c) for c in node.children) + "</" + node.tag + ">"


def walk(node):
    if not isinstance(node, str):
        yield node
        for child in node.children:
            yield from walk(child)


def photo_positions(root):
    """Read the actual preceding block, including tables and consecutive photos."""
    section = "글 첫머리"
    previous = None
    previous_photo = None
    positions = []
    for node in root.children:
        if not isinstance(node, Element):
            continue
        if node.tag in {"h2", "h3"}:
            section = text_of(node).strip()
            previous = None
            previous_photo = None
            continue
        images = [n for n in walk(node) if n.tag == "img"]
        if images:
            if previous_photo is not None:
                position = {"section": section, "after_kind": "photo", "after_text": "", "previous_photo": previous_photo}
            elif previous is not None:
                kind = {"table": "table", "ol": "list", "ul": "list", "pre": "code"}.get(previous.tag, "paragraph")
                anchor = previous
                if kind == "table":
                    anchor = [n for n in walk(previous) if n.tag == "tr"][-1]
                    phrase = " | ".join(text_of(c).strip() for c in anchor.children if isinstance(c, Element) and c.tag in {"td", "th"})
                elif kind == "list":
                    phrase = text_of([n for n in walk(previous) if n.tag == "li"][-1])
                else:
                    phrase = text_of(anchor)
                position = {"section": section, "after_kind": kind, "after_text": re.sub(r"\s+", " ", phrase).strip(), "previous_photo": None}
            else:
                raise ValueError("Photo must follow a meaningful block in its section")
            if len(images) != 1:
                raise ValueError("Each photo must have its own block")
            positions.append(position)
            previous_photo = len(positions) - 1
        elif node.tag not in {"hr"} and text_of(node).strip():
            previous = node
            previous_photo = None
    return positions


def placement_text(photo):
    if photo["after_kind"] == "photo":
        return "바로 앞 사진 " + photo["previous_photo"] + " 아래에 이어서 넣는다."
    label = {"paragraph": "문단", "table": "표", "list": "목록", "code": "코드"}[photo["after_kind"]]
    suffix = " (마지막 줄)" if photo["after_kind"] in {"table", "list"} else ""
    return "다음 " + label + " 아래에 넣는다" + suffix + ":"


def build_photo_guide(manifest):
    plain = "사진 배치 안내 — 작성자용\n\n압축을 전부 푼 뒤 사진-배치안내.html을 열면 작은 사진과 정확한 위치를 함께 볼 수 있다.\n티스토리 기본 모드에서 아래 부제목과 문장을 찾고, 해당 문단·표·목록 뒤에 사진을 올린다. 안내 파일 자체는 블로그 본문에 붙여 넣지 않는다.\n\n"
    navigation = []
    sections = []
    for item in manifest:
        chapter = item["file"]
        navigation.append('<li><a href="#' + chapter + '">' + html.escape(item["title"]) + '</a></li>')
        plain += item["title"] + "\n"
        cards = []
        for photo in item["photos"]:
            instruction = placement_text(photo)
            plain += "\n파일: " + photo["file"] + "\n부제목: " + photo["section"] + "\n위치: " + instruction + "\n"
            if photo["after_text"]:
                plain += "“" + photo["after_text"] + "”\n"
            plain += "사진 설명: " + photo["caption"] + "\n"
            quote = '<blockquote>' + html.escape(photo["after_text"]) + '</blockquote>' if photo["after_text"] else ""
            cards.append(
                '<div class="photo-card"><a class="thumbnail" href="사진/' + photo["file"] + '" target="_blank"><img loading="lazy" src="사진/' + photo["file"] + '" alt="' + html.escape(photo["caption"], quote=True) + '"></a>'
                '<div class="details"><p class="label">올릴 파일</p><code class="filename">' + photo["file"] + '</code>'
                '<p><strong>부제목:</strong> ' + html.escape(photo["section"]) + '</p><p>' + html.escape(instruction) + '</p>' + quote
                + '<p class="caption">사진 설명: ' + html.escape(photo["caption"]) + '</p><a href="미리보기/' + chapter + '.html#photo-' + photo["file"][:5] + '">원고에서 이 사진 위치 보기 →</a></div></div>'
            )
        if not cards:
            cards.append('<p class="no-photo">이 글은 준비된 사진 없이 본문과 표로 올리면 된다.</p>')
            plain += "사진 없음\n"
        plain += "\n\n"
        sections.append('<section id="' + chapter + '"><h2>' + html.escape(item["title"]) + '</h2><hr>' + "".join(cards) + '</section>')
    page = '''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>A50 블로그 사진 배치 안내</title><style>
body{margin:0;background:#f4f7f7;color:#263b3d;font:17px/1.8 "Malgun Gothic",sans-serif}main{max-width:1040px;margin:auto;padding:36px 24px}h1{font-size:30px;line-height:1.4}h2{font-size:22px;line-height:1.6;margin:0 0 12px}h3{font-size:19px;margin-top:0}a{color:#176d74;text-underline-offset:3px}nav,section,.intro{background:white;padding:26px;border:1px solid #d9e5e5;border-radius:12px;margin-bottom:24px}nav li{margin:8px 0}hr{border:0;border-top:1px solid #cadada;margin:0 0 22px}.photo-card{display:grid;grid-template-columns:220px minmax(0,1fr);gap:28px;padding:26px 0;border-bottom:1px solid #e0e8e8}.photo-card:last-child{border-bottom:0}.thumbnail{display:block;align-self:start;text-align:center;background:#f5f7f7;padding:10px;border-radius:8px}.thumbnail img{max-width:100%;max-height:430px;height:auto;object-fit:contain}.details p{margin:10px 0}.label{color:#55777a;font-size:14px}.filename{display:block;background:#edf5f5;padding:10px 12px;overflow-wrap:anywhere;font:14px/1.7 Consolas,monospace}blockquote{margin:16px 0;padding:14px 18px;background:#f5f8f8;border-left:4px solid #6ed3d8;overflow-wrap:anywhere}.caption{font-size:14px;color:#55777a}.notice{font-weight:700}.no-photo{margin:0}section{scroll-margin-top:16px}@media(max-width:680px){main{padding:20px 12px}.photo-card{grid-template-columns:1fr;gap:16px}.thumbnail{max-width:250px;margin:auto}nav,section,.intro{padding:20px}h1{font-size:26px}}@media print{body{background:white}nav{display:none}section{break-inside:avoid}.photo-card{break-inside:avoid}}
</style></head><body><main><h1>블로그 사진, 여기에 넣으면 된다</h1><div class="intro"><p class="notice">작성자용 안내다. 이 파일을 블로그 본문으로 복사하지 않는다.</p><ol><li><code>본문</code> 폴더의 HTML을 티스토리 HTML 모드에 붙여 넣는다.</li><li>기본 모드로 돌아와 아래에 적은 <strong>부제목과 문장</strong>을 찾는다.</li><li>해당 문단·표·목록 끝 다음 줄에 커서를 놓고 <code>사진</code> 폴더의 파일을 올린다.</li></ol><p>사진이 연달아 있는 곳은 안내 순서대로 위에서 아래로 넣는다. 작은 사진을 누르면 원본을 크게 볼 수 있다. 사진 설명은 필요하면 사진 아래 캡션으로 넣는다.</p></div><nav><h3>올릴 글을 고른다</h3><ul>'''
    page += "".join(navigation) + '</ul></nav>' + "".join(sections) + '</main></body></html>'
    return plain, page


def trim_paragraph_indent(node):
    for i, child in enumerate(node.children):
        if isinstance(child, str) and child:
            node.children[i] = child.lstrip("　")
            return
        if isinstance(child, Element):
            trim_paragraph_indent(child)
            return


def style(node, parent=""):
    if isinstance(node, str):
        return
    if node.tag == "h2":
        node.tag = "h3"
    if node.tag in STYLES:
        node.attrs["style"] = STYLES[node.tag]
    if node.tag == "p":
        trim_paragraph_indent(node)
    if node.tag == "code" and parent != "pre":
        node.attrs["style"] += "background-color:#f3f3f3;padding:2px 4px;overflow-wrap:anywhere;"
    if node.tag == "p":
        node.attrs["data-ke-size"] = "size16"
    if node.tag == "h3":
        node.attrs["data-ke-size"] = "size23"
    for c in node.children:
        style(c, node.tag)


def photo_slots(node, publish, rows, index):
    if isinstance(node, str):
        return node
    if node.tag == "img":
        photo = rows[index[0]]
        index[0] += 1
        if publish:
            return Element("comment", children=[
                "사진 위치: " + photo["file"] + " / " + photo["caption"]
                + " / 티스토리 기본 모드에서 이 위치에 사진을 넣는다."
            ])
        image = copy.deepcopy(node)
        image.attrs["src"] = "../사진/" + photo["file"]
        if "family-app" in photo["source"]:
            image.attrs["style"] += "width:380px;"
        return Element("figure", {"id": "photo-" + photo["file"][:5]}, [image, Element("figcaption", children=[photo["caption"], Element("br"), Element("code", children=["올릴 파일: " + photo["file"]])])])
    children = [photo_slots(c, publish, rows, index) for c in node.children]
    if node.tag == "p" and any(isinstance(c, Element) and c.tag in {"figure", "comment"} for c in children):
        # Markdown wraps a standalone image in a paragraph. Remove that wrapper.
        meaningful = [c for c in children if not isinstance(c, str) or c.strip()]
        if len(meaningful) == 1:
            return meaningful[0]
    node.children = children
    return node


def wrap_tables(node):
    if isinstance(node, str):
        return
    children = []
    for child in node.children:
        wrap_tables(child)
        if isinstance(child, Element) and child.tag == "table":
            child = Element("div", {"style": "width:100%;overflow-x:auto;margin:0;"}, [child])
        children.append(child)
    node.children = children


def validate(body, expected_code, expected_images):
    parsed = DOM()
    parsed.feed(body)
    nodes = list(walk(parsed.root))
    if any(n.tag in {"img", "script", "iframe", "link", "html", "body", "h1"} for n in nodes):
        raise ValueError("Publication body contains local media or a page wrapper")
    for node in nodes:
        if "src" in node.attrs or ("href" in node.attrs and node.tag != "a"):
            raise ValueError("Publication body contains a file reference")
        if node.tag == "a" and node.attrs.get("href") != PUBLIC_CODE_URL:
            raise ValueError("Publication link must point to the public reader code")
    headings = [n for n in nodes if n.tag == "h3"]
    if any(re.match(r"\d+(?:편|[.\s])", text_of(n)) for n in headings):
        raise ValueError("Publication body has a numbered heading")
    if any("text-indent:1em" not in n.attrs.get("style", "") for n in nodes if n.tag == "p"):
        raise ValueError("Paragraph indentation missing")
    top = [n for n in parsed.root.children if isinstance(n, Element)]
    for i, n in enumerate(top):
        if n.tag == "h3" and (i + 1 == len(top) or top[i + 1].tag != "hr"):
            raise ValueError("Divider must immediately follow a subheading")
    actual_code = [text_of(n) for n in nodes if n.tag == "pre"]
    if actual_code != expected_code:
        raise ValueError("Code content changed during HTML rendering")
    if body.count("<!-- 사진 위치:") != expected_images:
        raise ValueError("Photo upload slot missing")
    return {"headings": len(headings), "paragraphs": sum(n.tag == "p" for n in nodes), "code_blocks": len(actual_code), "photo_slots": expected_images, "public_links": sum(n.tag == "a" for n in nodes)}


def previous_outputs(destination):
    """Return the files an earlier build recorded; refuse folders it did not create."""
    marker = destination / BUILD_MARKER
    if not marker.is_file():
        if (destination.exists() and any(destination.iterdir())) or destination.with_suffix(
            ".zip"
        ).exists():
            raise ValueError(
                "The output folder or its ZIP already exists without a build record; "
                "choose a new --output-dir"
            )
        return []
    recorded = []
    for name in json.loads(marker.read_text(encoding="utf-8"))["files"]:
        path = (destination / name).resolve()
        if path == marker.resolve() or not path.is_relative_to(destination):
            raise ValueError("The build record lists a path outside the output folder")
        recorded.append(path)
    return recorded


def write_marker(marker, files):
    record = {"tool": "build_tistory_bundle.py", "files": sorted(files)}
    marker.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def install_outputs(work, destination, previous):
    """Swap the previous build's files for this build's; other files stay untouched."""
    generated = sorted(
        path.relative_to(work)
        for path in work.rglob("*")
        if path.is_file() and ".stage" not in path.relative_to(work).parts
    )
    replaceable = set(previous)
    for relative in generated:
        target = destination / relative
        if target.exists() and target.resolve() not in replaceable:
            raise ValueError(
                "The output folder has a file this build did not create: " + relative.as_posix()
            )
    destination.mkdir(parents=True, exist_ok=True)
    marker = destination / BUILD_MARKER
    old = {path.relative_to(destination).as_posix() for path in previous}
    # Record old and new files first so an interrupted swap can simply be rerun.
    write_marker(marker, old | {relative.as_posix() for relative in generated})
    for path in previous:
        path.unlink(missing_ok=True)
    for folder in sorted({path.parent for path in previous}, key=lambda path: -len(path.parts)):
        while folder != destination and folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
            folder = folder.parent
    for relative in generated:
        (destination / relative).parent.mkdir(parents=True, exist_ok=True)
        os.replace(work / relative, destination / relative)
    write_marker(marker, [relative.as_posix() for relative in generated])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "tmp/mobile-app-tistory")
    parser.add_argument("--pwsh", default=shutil.which("pwsh"))
    args = parser.parse_args()
    if not args.pwsh:
        raise ValueError("PowerShell 7 with ConvertFrom-Markdown is required")
    final = args.output_dir.resolve()
    previous = previous_outputs(final)
    final.parent.mkdir(parents=True, exist_ok=True)
    # Build next to the output folder and swap files in only after every check
    # passed, so a failed build never removes the previous outputs.
    destination = Path(tempfile.mkdtemp(prefix="." + final.name + "-build-", dir=final.parent))
    pending_archive = destination.with_suffix(".zip")
    try:
        manifest, digest = build_outputs(destination, args.pwsh, pending_archive)
        install_outputs(destination, final, previous)
        archive = final.with_suffix(".zip")
        os.replace(pending_archive, archive)
        checksum = digest + "  " + archive.name + "\n"
        archive.with_suffix(".zip.sha256").write_text(checksum, encoding="utf-8")
    finally:
        shutil.rmtree(destination, ignore_errors=True)
        pending_archive.unlink(missing_ok=True)
    print("TISTORY_POSTS=" + str(len(manifest)) + " BODY_PUBLIC_LINKS=" + str(sum(i["public_links"] for i in manifest)) + " BODY_LOCAL_IMAGES=0")
    print("SUBHEADINGS=" + str(sum(i["headings"] for i in manifest)) + " CODE_BLOCKS=" + str(sum(i["code_blocks"] for i in manifest)) + " PHOTO_UPLOAD_SLOTS=" + str(sum(i["photo_slots"] for i in manifest)))
    print("TISTORY_ZIP_SHA256=" + digest + " PUBLISHED=False")


def build_outputs(destination, pwsh, archive):
    """Write every output into the empty folder destination and the ZIP to archive."""
    stage = destination / ".stage"
    for directory in ["본문", "제목", "미리보기", "사진"]:
        (destination / directory).mkdir(exist_ok=True)
    subprocess.run([
        pwsh, "-NoProfile", "-File", str(ROOT / "scripts/reader/render_tistory_markdown.ps1"),
        "-InputDirectory", str(DOCS), "-OutputDirectory", str(stage),
    ], check=True, capture_output=True, text=True, encoding="utf-8")
    manifest = []
    for chapter in CHAPTERS:
        dom = DOM()
        dom.feed((stage / (chapter + ".html")).read_text(encoding="utf-8"))
        title = text_of(next(n for n in walk(dom.root) if n.tag == "h1"))
        dom.root.children = [c for c in dom.root.children if not isinstance(c, Element) or c.tag != "h1"]
        positions = photo_positions(dom.root)
        photos = []
        for i, image in enumerate(n for n in walk(dom.root) if n.tag == "img"):
            source = (DOCS / image.attrs["src"]).resolve()
            if not source.is_relative_to(ROOT / "docs/assets") or not source.is_file():
                raise ValueError("Unapproved image source")
            name = chapter[:2] + "-" + str(i + 1).zfill(2) + "-" + source.name
            shutil.copyfile(source, destination / "사진" / name)
            position = positions[i].copy()
            if position["previous_photo"] is not None:
                position["previous_photo"] = photos[position["previous_photo"]]["file"]
            photos.append({"file": name, "source": source.relative_to(ROOT).as_posix(), "caption": image.attrs.get("alt", ""), **position})
        expected_code = [text_of(n) for n in walk(dom.root) if n.tag == "pre"]
        style(dom.root)
        wrap_tables(dom.root)
        pub = photo_slots(copy.deepcopy(dom.root), True, photos, [0])
        body = serialize(pub)
        counts = validate(body, expected_code, len(photos))
        (destination / "본문" / (chapter + ".html")).write_text(body + "\n", encoding="utf-8", newline="\n")
        (destination / "제목" / (chapter + ".txt")).write_text(title + "\n", encoding="utf-8", newline="\n")
        preview = photo_slots(copy.deepcopy(dom.root), False, photos, [0])
        page = '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + html.escape(title) + '</title><style>body{margin:0;color:#444;font:17px/1.9 "Malgun Gothic",sans-serif}article{max-width:700px;padding:35px 24px;margin:auto}h1{font-size:29px;line-height:1.5;margin:0 0 32px;word-break:keep-all}pre{font-size:14px}table td:first-child{background:#efefef}@media(max-width:600px){article{padding:24px 16px}h1{font-size:25px}}</style></head><body><article><h1>' + html.escape(title) + '</h1>' + serialize(preview) + '</article></body></html>'
        (destination / "미리보기" / (chapter + ".html")).write_text(page, encoding="utf-8", newline="\n")
        manifest.append({"file": chapter, "title": title, "photos": photos, **counts})
    instructions = (
        "티스토리에 붙여 넣는 원고\n\n"
        "압축을 전부 푼 뒤 미리보기.html을 열면 글과 사진 배치를 볼 수 있다.\n"
        "게시할 때는 제목 폴더의 TXT를 제목 칸에 넣는다. 본문 폴더의 HTML은 메모장으로 열고 전체 내용을 티스토리 HTML 모드에 붙여 넣는다. 미리보기 파일을 복사하지 않는다.\n"
        "사진은 자동으로 업로드되지 않는다. 사진-배치안내.html을 열면 작은 사진, 파일 이름, 부제목과 바로 앞 문장이 나온다. 기본 모드로 돌아가 그 문단·표·목록 뒤에 사진 폴더의 해당 파일을 직접 넣는다. 사진-배치표.txt에도 같은 위치를 적었다. 본문 HTML의 사진 위치 메모는 게시 화면에는 나타나지 않는다.\n"
        "첫 글의 본문에 공개 GitHub의 main/server 폴더 링크가 들어 있다. 독자는 링크를 열고 Code → Download ZIP으로 현재 저장소를 받은 뒤 그 안의 server 폴더를 사용한다. " + BUNDLE_NAME + "은 로컬 보관용으로 함께 넣었으며 블로그에 따로 첨부할 필요는 없다.\n"
        "본문에는 로컬 문서 링크, 이미지 src나 외부 CSS가 없다. 사진을 넣기 전에도 설명과 명령어, 중요한 실행 결과는 읽을 수 있다. 본문에는 전체 HTML 페이지의 head/body나 중복 글 제목을 넣지 않았다.\n"
        "붙여 넣은 뒤 제목 아래 줄과 문단 들여쓰기, 표와 코드를 티스토리 미리보기에서 확인한다. 실제 편집기 저장 과정에서 서식이 유지되는지는 게시 전에 확인할 부분이다.\n"
        "계정 이메일, 서버 주소, 인증키가 보이는 새 사진을 올릴 때는 직접 가린다. 이번 자료에는 이미 가린 공개용 사진만 넣었다.\n"
        "현재 작업은 원고와 자료 준비까지이며 티스토리에 게시하거나 예약하지 않았다.\n"
    )
    (destination / "읽는법.txt").write_text(instructions, encoding="utf-8", newline="\n")
    photo_guide, photo_page = build_photo_guide(manifest)
    (destination / "사진-배치표.txt").write_text(photo_guide, encoding="utf-8", newline="\n")
    (destination / "사진-배치안내.html").write_text(photo_page, encoding="utf-8", newline="\n")
    (destination / "목차.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    links = "".join('<li><a href="미리보기/' + i["file"] + '.html">' + html.escape(i["title"]) + '</a></li>' for i in manifest)
    index = '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>A50 티스토리 원고 미리보기</title><style>body{max-width:760px;margin:40px auto;padding:20px;font:17px/1.9 "Malgun Gothic",sans-serif}li{margin:15px 0}a{color:#247f85}</style></head><body><h1>A50 티스토리 원고 미리보기</h1><p>이 화면은 작성자용 미리보기다. 게시할 때는 본문 폴더의 HTML을 복사하고 사진을 직접 올린다. 코드는 첫 글에 넣은 공개 GitHub 링크로 받는다.</p><p><strong><a href="사진-배치안내.html">사진을 어디에 넣을지 먼저 보기 →</a></strong></p><ul>' + links + '</ul></body></html>'
    (destination / "미리보기.html").write_text(index, encoding="utf-8", newline="\n")
    build_reader(destination / BUNDLE_NAME)
    public_files = [p for p in destination.rglob("*") if p.is_file() and ".stage" not in p.relative_to(destination).parts and p.suffix != ".zip"]
    # The reader audit uses configured private values without printing them.
    audit([DOCS / (name + ".md") for name in CHAPTERS])
    sensitive_audit(public_files)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in sorted(destination.rglob("*")):
            if path.is_file() and ".stage" not in path.relative_to(destination).parts:
                item = zipfile.ZipInfo(path.relative_to(destination).as_posix(), date_time=(2026, 10, 4, 0, 0, 0))
                item.compress_type = zipfile.ZIP_DEFLATED
                output.writestr(item, path.read_bytes())
    return manifest, hashlib.sha256(archive.read_bytes()).hexdigest()


def sensitive_audit(files):
    # Audit artifact text and image metadata with the same private-value rules.
    from make_reader_bundle import find_private_metadata, private_values, text_privacy_issue
    from PIL import Image

    values = private_values()
    images = 0
    for path in files:
        if path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            with Image.open(path):
                images += 1
            if find_private_metadata(path):
                raise ValueError("Private image metadata in generated artifact")
            continue
        text = path.read_text(encoding="utf-8")
        if any(v in text for v in values):
            raise ValueError("Private configured value in generated artifact")
        # Every generated file is author or reader prose, so no address is allowed.
        issue = text_privacy_issue(text, prose=True)
        if issue:
            raise ValueError(issue + " in generated artifact")
    print("TISTORY_PRIVATE_VALUES_FOUND=0 PRIVATE_METADATA_COUNT=0 IMAGE_COUNT=" + str(images))


if __name__ == "__main__":
    main()
