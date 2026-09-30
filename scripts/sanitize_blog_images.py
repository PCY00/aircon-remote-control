"""Remove private camera metadata from images before publishing them."""

from __future__ import annotations

import argparse
import os
import struct
import tempfile
from pathlib import Path

from PIL import Image, ImageOps, PngImagePlugin

SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png"}
PNG_PRIVATE_CHUNKS = {b"eXIf", b"iTXt", b"tEXt", b"tIME", b"zTXt"}


def _jpeg_private_segments(path: Path) -> list[str]:
    """Return privacy-bearing JPEG segments found before the image scan."""

    data = path.read_bytes()
    if not data.startswith(b"\xff\xd8"):
        raise ValueError(f"Not a valid JPEG file: {path}")

    findings: list[str] = []
    offset = 2
    while offset < len(data):
        if data[offset] != 0xFF:
            raise ValueError(f"Invalid JPEG marker at byte {offset}: {path}")

        marker_offset = offset
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            break

        marker = data[offset]
        offset += 1
        if marker == 0xDA:  # Start of Scan; the rest is compressed image data.
            break
        if marker == 0xD9:
            break
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(data):
            raise ValueError(f"Truncated JPEG segment: {path}")

        segment_length = int.from_bytes(data[offset : offset + 2], "big")
        if segment_length < 2 or offset + segment_length > len(data):
            raise ValueError(f"Invalid JPEG segment length: {path}")

        # APP1 contains EXIF and XMP. Other APP segments may contain proprietary
        # phone metadata, embedded previews or unique identifiers. APP0 is the
        # structural JFIF header and is safe to retain.
        if 0xE1 <= marker <= 0xEF:
            findings.append(f"APP{marker - 0xE0}@{marker_offset}")
        elif marker == 0xFE:
            findings.append(f"COMMENT@{marker_offset}")

        offset += segment_length

    return findings


def _png_private_chunks(path: Path) -> list[str]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"Not a valid PNG file: {path}")

    findings: list[str] = []
    offset = 8
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_end = offset + 12 + length
        if chunk_end > len(data):
            raise ValueError(f"Truncated PNG chunk: {path}")
        if chunk_type in PNG_PRIVATE_CHUNKS:
            findings.append(chunk_type.decode("ascii"))
        offset = chunk_end
        if chunk_type == b"IEND":
            break
    return findings


def find_private_metadata(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return _jpeg_private_segments(path)
    if suffix == ".png":
        return _png_private_chunks(path)
    raise ValueError(f"Unsupported image type: {path}")


def _copy_pixels_without_metadata(source: Image.Image) -> Image.Image:
    transposed = ImageOps.exif_transpose(source)
    transposed.load()

    mode = transposed.mode
    if mode not in {"1", "L", "LA", "P", "RGB", "RGBA", "CMYK"}:
        transposed = transposed.convert("RGB")
        mode = "RGB"

    clean = Image.frombytes(mode, transposed.size, transposed.tobytes())
    if mode == "P" and transposed.getpalette() is not None:
        clean.putpalette(transposed.getpalette())
    return clean


def sanitize(path: Path) -> bool:
    findings = find_private_metadata(path)
    if not findings:
        return False

    with Image.open(path) as source:
        if getattr(source, "is_animated", False):
            raise ValueError(f"Animated images require manual review: {path}")
        clean = _copy_pixels_without_metadata(source)

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem}-sanitized-", suffix=path.suffix, dir=path.parent
    )
    os.close(fd)
    temporary_path = Path(temporary_name)
    try:
        if path.suffix.lower() in {".jpg", ".jpeg"}:
            if clean.mode not in {"L", "RGB", "CMYK"}:
                clean = clean.convert("RGB")
            clean.save(temporary_path, format="JPEG", quality=95, optimize=True)
        else:
            clean.save(
                temporary_path,
                format="PNG",
                optimize=True,
                pnginfo=PngImagePlugin.PngInfo(),
            )

        if find_private_metadata(temporary_path):
            raise RuntimeError(f"Sanitized file still contains private metadata: {path}")
        with Image.open(temporary_path) as verified:
            verified.verify()
        os.replace(temporary_path, path)
    finally:
        clean.close()
        temporary_path.unlink(missing_ok=True)
    return True


def iter_images(paths: list[Path]) -> list[Path]:
    images: set[Path] = set()
    for path in paths:
        if path.is_dir():
            images.update(
                candidate
                for candidate in path.rglob("*")
                if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_SUFFIXES
            )
        elif path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            images.add(path)
        else:
            raise FileNotFoundError(f"Image path does not exist or is unsupported: {path}")
    return sorted(images)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check or remove EXIF, GPS, XMP, comments and proprietary image metadata."
    )
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Rewrite affected images in place. The default is a read-only check.",
    )
    args = parser.parse_args()

    images = iter_images(args.paths)
    affected = 0
    changed = 0
    for image_path in images:
        findings = find_private_metadata(image_path)
        if not findings:
            continue
        affected += 1
        if args.apply:
            sanitize(image_path)
            changed += 1
            print(f"SANITIZED={image_path.as_posix()}")
        else:
            print(f"PRIVATE_METADATA={image_path.as_posix()} TYPES={','.join(findings)}")

    print(f"IMAGE_COUNT={len(images)}")
    print(f"PRIVATE_METADATA_COUNT={affected}")
    if args.apply:
        print(f"SANITIZED_COUNT={changed}")
    elif affected:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
