"""Render a sanitized terminal transcript as a blog-ready PNG."""

from __future__ import annotations

import argparse
import textwrap
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH = 1800
PADDING = 58
HEADER_HEIGHT = 82
FONT_SIZE = 27
LINE_SPACING = 13
BACKGROUND = "#0d1117"
HEADER = "#161b22"
FOREGROUND = "#e6edf3"
MUTED = "#8b949e"


def contains_hangul(text: str) -> bool:
    return any("\uac00" <= character <= "\ud7a3" for character in text)


def load_font(
    size: int, text: str = ""
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if contains_hangul(text):
        candidates = (
            Path("C:/Windows/Fonts/malgun.ttf"),
            Path("C:/Windows/Fonts/gulim.ttc"),
        )
    else:
        candidates = (
            Path("C:/Windows/Fonts/consola.ttf"),
            Path("C:/Windows/Fonts/lucon.ttf"),
        )
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


WRAP_OPTIONS = dict(replace_whitespace=False, drop_whitespace=False, subsequent_indent="    ")


class MeasuredWrapper(textwrap.TextWrapper):
    """TextWrapper that measures each candidate line with ``measure``.

    With ``len`` it wraps exactly like textwrap; with a pixel measure it keeps
    proportional text inside a drawn width. Only the options in WRAP_OPTIONS
    (no max_lines, whitespace kept) are supported.
    """

    def __init__(self, measure: Callable[[str], float], **options: object) -> None:
        super().__init__(**options)
        self.measure = measure

    def _wrap_chunks(self, chunks: list[str]) -> list[str]:
        lines: list[str] = []
        chunks.reverse()
        while chunks:
            indent = self.subsequent_indent if lines else self.initial_indent
            line = indent
            while chunks and self.measure(line + chunks[-1]) <= self.width:
                line += chunks.pop()
            if chunks and self.measure(indent + chunks[-1]) > self.width:
                line = self._break_long_word(chunks, line, indent)
            if line != indent:
                lines.append(line)
        return lines

    def _break_long_word(self, reversed_chunks: list[str], line: str, indent: str) -> str:
        chunk = reversed_chunks[-1]
        end = 0
        while end < len(chunk) and self.measure(line + chunk[: end + 1]) <= self.width:
            end += 1
        if end == 0 and line == indent:
            end = 1  # Always make progress, even if one character is too wide.
        if self.break_on_hyphens and end < len(chunk):
            hyphen = chunk.rfind("-", 0, end)
            if hyphen > 0 and any(character != "-" for character in chunk[:hyphen]):
                end = hyphen + 1
        reversed_chunks[-1] = chunk[end:]
        return line + chunk[:end]


def wrap_transcript(
    text: str,
    width: int = 104,
    measure: Callable[[str], float] | None = None,
    limit: float = 0,
) -> list[str]:
    """Wrap at ``width`` characters, as the existing captures were wrapped.

    When ``measure`` gives the drawn width of a line, a source line whose
    character wrap would be wider than ``limit`` is wrapped again by measured
    width. Lines drawn in proportional Hangul fonts then stay inside the image,
    and every line that already fits keeps exactly the same wrap.
    """
    columns = MeasuredWrapper(len, width=width, **WRAP_OPTIONS)
    pixels = MeasuredWrapper(measure, width=limit, **WRAP_OPTIONS) if measure else None
    lines: list[str] = []
    for line in text.rstrip().splitlines():
        if not line:
            lines.append("")
            continue
        wrapped = columns.wrap(line) or [""]
        if pixels and any(pixels.measure(part) > limit for part in wrapped):
            wrapped = pixels.wrap(line) or [""]
        lines.extend(wrapped)
    return lines


def render(source: Path, output: Path, title: str) -> None:
    transcript = source.read_text(encoding="utf-8")
    font = load_font(FONT_SIZE)
    hangul_font = load_font(FONT_SIZE, "한글")

    def drawn_width(line: str) -> float:
        return (hangul_font if contains_hangul(line) else font).getlength(line)

    lines = wrap_transcript(transcript, measure=drawn_width, limit=WIDTH - 2 * PADDING)
    title_font = load_font(23, title)
    line_height = FONT_SIZE + LINE_SPACING
    height = HEADER_HEIGHT + (PADDING * 2) + max(1, len(lines)) * line_height

    image = Image.new("RGB", (WIDTH, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, HEADER_HEIGHT), fill=HEADER)

    for x, color in ((34, "#ff5f56"), (70, "#ffbd2e"), (106, "#27c93f")):
        draw.ellipse((x, 28, x + 24, 52), fill=color)

    draw.text((156, 25), title, font=title_font, fill=MUTED)

    y = HEADER_HEIGHT + PADDING
    for line in lines:
        color = MUTED if line.startswith("# ") else FOREGROUND
        line_font = hangul_font if contains_hangul(line) else font
        draw.text((PADDING, y), line, font=line_font, fill=color)
        y += line_height

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--title", default="SANITIZED TERMINAL RECORD")
    args = parser.parse_args()
    render(args.source, args.output, args.title)


if __name__ == "__main__":
    main()
