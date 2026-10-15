import re
import textwrap
from pathlib import Path

import pytest
from PIL import Image, ImageFont

from scripts import render_terminal_capture as capture

ROOT = Path(__file__).resolve().parents[1]
LIMIT = capture.WIDTH - 2 * capture.PADDING
KOREAN_NOTE = (
    "위 결과는 실제 실행 출력에서 가져왔다. 압축 파일의 체크섬과 설치한 앱의 버전을 "
    "다시 확인했고, 개인 주소와 계정 정보는 지운 뒤 원문과 같은 화면으로 남겼다. "
    "같은 명령을 다시 실행해도 결과가 같은지 한 번 더 확인했다."
)


def old_wrap(line: str) -> list[str]:
    return textwrap.wrap(
        line,
        width=104,
        replace_whitespace=False,
        drop_whitespace=False,
        subsequent_indent="    ",
    )


def columns(line: str) -> int:
    """A stand-in measure: Hangul takes two columns, everything else one."""
    return sum(2 if capture.contains_hangul(character) else 1 for character in line)


def test_server_copy_matches_root_script() -> None:
    root_copy = ROOT / "scripts/render_terminal_capture.py"
    server_copy = ROOT / "server/scripts/render_terminal_capture.py"
    assert server_copy.read_bytes() == root_copy.read_bytes()


@pytest.mark.parametrize(
    "line",
    [
        "short line",
        "word " * 40,
        "x" * 250,
        "python -m pytest -q tests/test_a50_public_tunnel.py " + "--very-long-option-name " * 6,
        "self-contained-hyphenated-" * 8,
        "\tindented\twith\ttabs " * 10,
        "C:/smart-home-reader/" + "a" * 120 + "/end",
        "짧은 한글 줄도 그대로 " * 4,
    ],
)
def test_lines_that_fit_wrap_exactly_like_textwrap(line: str) -> None:
    expected = [*old_wrap(line), "next"]
    assert capture.wrap_transcript(line + "\nnext") == expected
    assert capture.wrap_transcript(line + "\nnext", measure=len, limit=104) == expected


def test_overflowing_line_is_rewrapped_by_measured_width() -> None:
    text = KOREAN_NOTE + " " + "가" * 120
    lines = capture.wrap_transcript(text, measure=columns, limit=104)
    assert len(lines) > len(old_wrap(text))
    assert all(columns(line) <= 104 for line in lines)
    assert "".join(line.removeprefix("    ") for line in lines) == text


def test_render_wraps_long_hangul_lines_within_canvas(tmp_path: Path) -> None:
    font = capture.load_font(capture.FONT_SIZE)
    hangul_font = capture.load_font(capture.FONT_SIZE, "한글")
    if not isinstance(hangul_font, ImageFont.FreeTypeFont):
        pytest.skip("Malgun Gothic or Gulim is needed to measure Hangul text")
    source = tmp_path / "note.txt"
    source.write_text(
        "$ echo done\n"
        + KOREAN_NOTE
        + "\n"
        + "가나다라 " * 30
        + "\n"
        + "결과 PRIVATE_METADATA_COUNT=0 UNCHECKED_COUNT=0 SANITIZED_COUNT=0 MODE=PREVIEW "
        + "WWWWWWWWWWMMMMMMMMMM\n"
        + "상태 "
        + "─→" * 40
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "note.png"

    capture.render(source, output, "TEST")

    def drawn_width(line: str) -> float:
        return (hangul_font if capture.contains_hangul(line) else font).getlength(line)

    lines = capture.wrap_transcript(
        source.read_text(encoding="utf-8"), measure=drawn_width, limit=LIMIT
    )
    for line in lines:
        assert drawn_width(line) <= LIMIT, line
    with Image.open(output) as image:
        assert image.width == capture.WIDTH
        expected_height = capture.HEADER_HEIGHT + 2 * capture.PADDING
        expected_height += len(lines) * (capture.FONT_SIZE + capture.LINE_SPACING)
        assert image.height == expected_height


REDACTED_CAPTURES = (
    "200-a50-tunnel-local-checks-initial",
    "265-a50-pi-installer-windows-symlink-failure",
)
# pytest temp folders carry the login account after this prefix; the literal is
# split so a repository-wide search for the prefix finds only the captures.
PYTEST_TEMP_PREFIX = "pytest-of" "-"


def test_terminal_captures_hide_the_account_in_pytest_temp_folders() -> None:
    redacted = set()
    for path in sorted((ROOT / "docs/assets/terminal").glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        assert not re.search(PYTEST_TEMP_PREFIX + r"(?!\[REDACTED_USER\])", text), path.name
        if PYTEST_TEMP_PREFIX + "[REDACTED_USER]" in text:
            redacted.add(path.stem)
    assert set(REDACTED_CAPTURES) <= redacted


@pytest.mark.parametrize("name", REDACTED_CAPTURES)
def test_redacted_captures_were_rendered_again_from_their_text(name: str) -> None:
    font = capture.load_font(capture.FONT_SIZE)
    hangul_font = capture.load_font(capture.FONT_SIZE, "한글")
    if not all(isinstance(f, ImageFont.FreeTypeFont) for f in (font, hangul_font)):
        pytest.skip("Consolas and Malgun Gothic are needed to measure the rendered lines")
    source = ROOT / "docs/assets/terminal" / f"{name}.txt"

    def drawn_width(line: str) -> float:
        return (hangul_font if capture.contains_hangul(line) else font).getlength(line)

    lines = capture.wrap_transcript(
        source.read_text(encoding="utf-8"), measure=drawn_width, limit=LIMIT
    )
    with Image.open(source.with_suffix(".png")) as image:
        line_height = capture.FONT_SIZE + capture.LINE_SPACING
        expected_height = capture.HEADER_HEIGHT + 2 * capture.PADDING + len(lines) * line_height
        assert image.size == (capture.WIDTH, expected_height)
