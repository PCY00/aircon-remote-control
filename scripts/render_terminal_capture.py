"""Render a sanitized terminal transcript as a blog-ready PNG."""

from __future__ import annotations

import argparse
import textwrap
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


def wrap_transcript(text: str, width: int = 104) -> list[str]:
    lines: list[str] = []
    for line in text.rstrip().splitlines():
        if not line:
            lines.append("")
            continue
        lines.extend(
            textwrap.wrap(
                line,
                width=width,
                replace_whitespace=False,
                drop_whitespace=False,
                subsequent_indent="    ",
            )
            or [""]
        )
    return lines


def render(source: Path, output: Path, title: str) -> None:
    transcript = source.read_text(encoding="utf-8")
    lines = wrap_transcript(transcript)
    font = load_font(FONT_SIZE)
    hangul_font = load_font(FONT_SIZE, "한글")
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
