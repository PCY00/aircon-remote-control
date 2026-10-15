"""Remove private camera metadata from images before publishing them."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import tempfile
from pathlib import Path

from PIL import Image, ImageOps, PngImagePlugin

JPEG_SUFFIXES = {".jpg", ".jpeg", ".jpe", ".jfif", ".mpo"}
SUPPORTED_SUFFIXES = JPEG_SUFFIXES | {".png"}
# Media that may carry EXIF/XMP/GPS but that this tool cannot inspect or rewrite.
UNCHECKED_MEDIA_SUFFIXES = {
    ".3gp",
    ".avif",
    ".dng",
    ".gif",
    ".heic",
    ".heif",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".tif",
    ".tiff",
    ".webm",
    ".webp",
}
# A checked-in list of unsupported media that a person reviewed, keyed by the
# path relative to the list's folder. An entry only counts while the file still
# has the recorded SHA-256, so new or edited media is reported again.
REVIEWED_MEDIA_LIST = ".sanitize-reviewed.json"
# Only chunks needed to render the pixels are kept. Every other chunk (text,
# eXIf, tIME, C2PA caBX, editor previews, unknown private chunks) is reported.
PNG_SAFE_CHUNKS = {
    b"IHDR",
    b"PLTE",
    b"IDAT",
    b"IEND",
    b"tRNS",
    b"gAMA",
    b"cHRM",
    b"sRGB",
    b"iCCP",
    b"sBIT",
    b"pHYs",
    b"bKGD",
    b"cICP",
}
# Colour chunks copied into a rewritten PNG (iCCP is written from icc_profile).
PNG_COLOUR_CHUNKS = (b"cHRM", b"cICP", b"gAMA", b"sRGB")
# An ICC colour profile is rendering data, like PNG iCCP; other APP2 data
# (for example MPF secondary images) is still reported.
JPEG_ICC_IDENTIFIER = b"ICC_PROFILE\x00"
# Modes whose transparency Pillow writes back as a PNG tRNS chunk.
PNG_TRANSPARENCY_MODES = {"1", "L", "I", "I;16", "P", "RGB"}
ICC_COLOUR_SPACES = {
    b"GRAY": {"1", "L", "LA", "I", "I;16", "I;16B"},
    b"RGB ": {"P", "RGB", "RGBA"},
}


def _jpeg_private_segments(path: Path) -> list[str]:
    """Return privacy-bearing JPEG segments, including those between scans and after EOI."""

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
        if marker == 0xD9:  # End of Image; appended bytes are a trailer (e.g. SEFT).
            if offset < len(data):
                findings.append(f"TRAILER@{offset}")
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
        # structural JFIF header and an APP2 ICC profile is colour data; both
        # are safe to retain.
        payload = data[offset + 2 : offset + segment_length]
        if marker == 0xE2 and payload.startswith(JPEG_ICC_IDENTIFIER):
            pass
        elif 0xE1 <= marker <= 0xEF:
            findings.append(f"APP{marker - 0xE0}@{marker_offset}")
        elif marker == 0xFE:
            findings.append(f"COMMENT@{marker_offset}")

        offset += segment_length
        if marker == 0xDA:
            # Skip entropy-coded data. Inside it 0xFF is only followed by a
            # stuffed 0x00 or a restart marker; any other marker ends the scan,
            # so progressive files are walked scan by scan.
            while True:
                offset = data.find(b"\xff", offset)
                if offset == -1 or offset + 1 >= len(data):
                    return findings
                following = data[offset + 1]
                if following == 0x00 or 0xD0 <= following <= 0xD7:
                    offset += 2
                    continue
                break

    return findings


def _png_chunks(data: bytes, path: Path):
    """Yield (type, payload, end offset) for each PNG chunk up to and including IEND."""

    offset = 8
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_end = offset + 12 + length
        if chunk_end > len(data):
            raise ValueError(f"Truncated PNG chunk: {path}")
        yield chunk_type, data[offset + 8 : offset + 8 + length], chunk_end
        offset = chunk_end
        if chunk_type == b"IEND":
            break


def _png_private_chunks(path: Path) -> list[str]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"Not a valid PNG file: {path}")

    findings: list[str] = []
    end = 8
    for chunk_type, _payload, chunk_end in _png_chunks(data, path):
        if chunk_type not in PNG_SAFE_CHUNKS:
            findings.append(chunk_type.decode("latin-1"))
        end = chunk_end
    if end < len(data):
        findings.append(f"TRAILER@{end}")
    return findings


def find_private_metadata(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix in JPEG_SUFFIXES:
        return _jpeg_private_segments(path)
    if suffix == ".png":
        return _png_private_chunks(path)
    raise ValueError(f"Unsupported image type: {path}")


def _copy_pixels_without_metadata(source: Image.Image) -> Image.Image:
    transposed = ImageOps.exif_transpose(source)
    transposed.load()

    if transposed.mode == "PA":
        transposed = transposed.convert("RGBA")

    mode = transposed.mode
    # 16-bit grayscale is copied as-is; converting it to RGB would clip values.
    if mode not in {"1", "L", "LA", "P", "RGB", "RGBA", "CMYK", "I", "I;16", "I;16B"}:
        transposed = transposed.convert("RGB")
        mode = "RGB"

    clean = Image.frombytes(mode, transposed.size, transposed.tobytes())
    if mode == "P" and transposed.getpalette() is not None:
        clean.putpalette(transposed.getpalette())
    # Rendering information only: the palette or colour-key transparency (tRNS)
    # and the colour profile. Everything else in info is left behind.
    if mode in PNG_TRANSPARENCY_MODES and "transparency" in transposed.info:
        clean.info["transparency"] = transposed.info["transparency"]
    if transposed.info.get("icc_profile"):
        clean.info["icc_profile"] = transposed.info["icc_profile"]
    return clean


def _matching_icc_profile(image: Image.Image) -> bytes | None:
    """Return the ICC profile only when it describes the colour space being written."""

    profile = image.info.get("icc_profile")
    if not profile or len(profile) < 20:
        return None
    return profile if image.mode in ICC_COLOUR_SPACES.get(profile[16:20], set()) else None


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
        if path.suffix.lower() in JPEG_SUFFIXES:
            # CMYK output always gains an Adobe APP14 marker, so write RGB.
            if clean.mode not in {"L", "RGB"}:
                converted = clean.convert("RGB")
                clean.close()
                clean = converted
            options = {"icc_profile": _matching_icc_profile(clean)}
            clean.save(
                temporary_path,
                format="JPEG",
                quality=95,
                optimize=True,
                **{key: value for key, value in options.items() if value is not None},
            )
        else:
            if clean.mode == "CMYK":
                converted = clean.convert("RGB")
                clean.close()
                clean = converted
            colour = PngImagePlugin.PngInfo()
            for chunk_type, payload, _end in _png_chunks(path.read_bytes(), path):
                if chunk_type in PNG_COLOUR_CHUNKS:
                    colour.add(chunk_type, payload)
            options = {"icc_profile": _matching_icc_profile(clean)}
            if clean.mode in PNG_TRANSPARENCY_MODES:
                options["transparency"] = clean.info.get("transparency")
            clean.save(
                temporary_path,
                format="PNG",
                optimize=True,
                pnginfo=colour,
                **{key: value for key, value in options.items() if value is not None},
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


def is_reviewed_media(path: Path) -> bool:
    """True when a REVIEWED_MEDIA_LIST in a parent folder records this exact file."""

    resolved = path.resolve()
    for folder in resolved.parents:
        listing = folder / REVIEWED_MEDIA_LIST
        if not listing.is_file():
            continue
        entries = json.loads(listing.read_text(encoding="utf-8")).get("files", {})
        entry = entries.get(resolved.relative_to(folder).as_posix())
        if entry is not None:
            return entry.get("sha256") == hashlib.sha256(resolved.read_bytes()).hexdigest()
    return False


def iter_unchecked_media(paths: list[Path]) -> list[Path]:
    """Return unreviewed media in the scanned folders whose metadata this tool cannot read."""

    return sorted(
        candidate
        for path in paths
        if path.is_dir()
        for candidate in path.rglob("*")
        if candidate.is_file()
        and candidate.suffix.lower() in UNCHECKED_MEDIA_SUFFIXES
        and not is_reviewed_media(candidate)
    )


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
    parser.add_argument(
        "--allow-unchecked",
        action="append",
        type=Path,
        default=[],
        metavar="PATH",
        help="A video or other unsupported media file whose metadata was reviewed by hand.",
    )
    args = parser.parse_args()

    images = iter_images(args.paths)
    reviewed = {path.resolve() for path in args.allow_unchecked}
    unchecked = [
        path for path in iter_unchecked_media(args.paths) if path.resolve() not in reviewed
    ]
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
    for media_path in unchecked:
        print(f"UNCHECKED={media_path.as_posix()}")

    print(f"IMAGE_COUNT={len(images)}")
    print(f"PRIVATE_METADATA_COUNT={affected}")
    print(f"UNCHECKED_COUNT={len(unchecked)}")
    if args.apply:
        print(f"SANITIZED_COUNT={changed}")
    elif affected or unchecked:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
