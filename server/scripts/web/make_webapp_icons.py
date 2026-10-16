"""Draw the family web app's home-screen icons (house + snowflake on the app background).

    python -I server/scripts/web/make_webapp_icons.py

Writes icon-192.png, icon-512.png, icon-maskable-512.png and apple-touch-icon.png (180x180, opaque)
into central_server/webapp/. The PNGs carry no text or time chunks.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

WEBAPP = Path(__file__).resolve().parents[2] / "services/central-server/central_server/webapp"
BACKGROUND = (0x0F, 0x17, 0x24, 255)
ACCENT = (0x37, 0xA8, 0xDD, 255)
INK = (0xE6, 0xED, 0xF7, 255)
SCALE = 4  # draw large, then shrink for smooth edges


def stroke(draw: ImageDraw.ImageDraw, points, width: float, colour) -> None:
    draw.line(points, fill=colour, width=round(width), joint="curve")
    radius = width / 2
    for x, y in (points[0], points[-1]):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=colour)


def icon(size: int, content: float) -> Image.Image:
    """`content` is the share of the side the drawing may use (smaller for maskable icons)."""
    big = size * SCALE
    image = Image.new("RGBA", (big, big), BACKGROUND)
    draw = ImageDraw.Draw(image)
    box = big * content
    left = top = (big - box) / 2

    def at(x: float, y: float):
        return (left + x * box, top + y * box)

    line = box * 0.075
    stroke(draw, [at(0.06, 0.47), at(0.5, 0.1), at(0.94, 0.47)], line, ACCENT)
    stroke(draw, [at(0.17, 0.4), at(0.17, 0.92), at(0.83, 0.92), at(0.83, 0.4)], line, ACCENT)
    centre_x, centre_y, arm = 0.5, 0.635, 0.2
    thin = box * 0.05
    for index in range(6):
        angle = math.radians(index * 60 - 90)
        dx, dy = math.cos(angle), math.sin(angle)

        def arm_point(along: float, across: float):
            # Same proportions as the app's snowflake icon: spoke plus a chevron near its tip.
            return at(centre_x + (dx * along - dy * across) * arm, centre_y + (dy * along + dx * across) * arm)

        stroke(draw, [arm_point(0, 0), arm_point(1, 0)], thin, INK)
        stroke(draw, [arm_point(0.78, -0.26), arm_point(0.53, 0), arm_point(0.78, 0.26)], thin, INK)
    return image.resize((size, size), Image.LANCZOS).convert("RGB")


def save(image: Image.Image, name: str) -> None:
    path = WEBAPP / name
    image.save(path, format="PNG", optimize=True)  # no pnginfo: no tEXt/iTXt/tIME chunks
    print(f"{name}: {image.size[0]}x{image.size[1]} {path.stat().st_size} bytes")


def main() -> None:
    save(icon(192, 0.74), "icon-192.png")
    save(icon(512, 0.74), "icon-512.png")
    # Maskable: everything inside the central 80% circle (safe zone), so the launcher may crop.
    save(icon(512, 0.56), "icon-maskable-512.png")
    # iOS rounds the corners itself and shows transparency as black, so this one is opaque.
    save(icon(180, 0.7), "apple-touch-icon.png")


if __name__ == "__main__":
    main()
