import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path

import pytest
from PIL import Image, ImageCms, PngImagePlugin

from scripts import sanitize_blog_images
from scripts.sanitize_blog_images import find_private_metadata, sanitize

ROOT = Path(__file__).resolve().parents[1]


def _insert_png_chunk_before_iend(path: Path, chunk_type: bytes, payload: bytes) -> None:
    data = path.read_bytes()
    iend = data.rindex(b"IEND") - 4
    crc = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
    chunk = struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", crc)
    path.write_bytes(data[:iend] + chunk + data[iend:])


def test_sanitize_jpeg_removes_exif_and_preserves_orientation(tmp_path: Path) -> None:
    path = tmp_path / "photo.jpg"
    image = Image.new("RGB", (4, 2), "red")
    exif = Image.Exif()
    exif[0x010F] = "Example Phone"
    exif[0x0112] = 6
    image.save(path, format="JPEG", exif=exif)

    assert find_private_metadata(path)
    assert sanitize(path) is True
    assert find_private_metadata(path) == []
    with Image.open(path) as clean:
        assert clean.size == (2, 4)
        assert len(clean.getexif()) == 0


def test_sanitize_png_removes_text_chunks(tmp_path: Path) -> None:
    path = tmp_path / "image.png"
    image = Image.new("RGB", (4, 2), "blue")
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Location", "private")
    image.save(path, format="PNG", pnginfo=metadata)

    assert "tEXt" in find_private_metadata(path)
    assert sanitize(path) is True
    assert find_private_metadata(path) == []
    with Image.open(path) as clean:
        assert clean.size == (4, 2)
        assert "Location" not in clean.info


def test_clean_image_is_not_rewritten(tmp_path: Path) -> None:
    path = tmp_path / "clean.png"
    Image.new("RGB", (2, 2), "white").save(path, format="PNG")
    original = path.read_bytes()

    assert sanitize(path) is False
    assert path.read_bytes() == original


def test_server_copy_matches_root_script() -> None:
    root_copy = ROOT / "scripts/sanitize_blog_images.py"
    server_copy = ROOT / "server/scripts/sanitize_blog_images.py"
    assert server_copy.read_bytes() == root_copy.read_bytes()


@pytest.mark.parametrize("chunk_type", [b"caBX", b"prVW", b"mkBT", b"orNT"])
def test_png_unknown_ancillary_chunk_is_flagged_and_removed(
    tmp_path: Path, chunk_type: bytes
) -> None:
    path = tmp_path / "provenance.png"
    Image.new("RGB", (4, 2), "green").save(path, format="PNG")
    _insert_png_chunk_before_iend(path, chunk_type, b"c2pa.created urn:c2pa:fixture")

    assert chunk_type.decode("ascii") in find_private_metadata(path)
    assert sanitize(path) is True
    assert find_private_metadata(path) == []
    assert chunk_type not in path.read_bytes()


def test_png_rendering_chunks_are_not_flagged(tmp_path: Path) -> None:
    path = tmp_path / "rendering.png"
    image = Image.new("RGB", (4, 2), "white")
    image.save(path, format="PNG", dpi=(96, 96), icc_profile=b"fixture-profile")
    _insert_png_chunk_before_iend(path, b"gAMA", struct.pack(">I", 45455))

    assert find_private_metadata(path) == []


def test_png_trailer_after_iend_is_flagged_and_removed(tmp_path: Path) -> None:
    path = tmp_path / "trailer.png"
    Image.new("RGB", (4, 2), "white").save(path, format="PNG")
    clean_length = len(path.read_bytes())
    path.write_bytes(path.read_bytes() + b"GPS 37.5,127.0")

    assert find_private_metadata(path) == [f"TRAILER@{clean_length}"]
    assert sanitize(path) is True
    assert find_private_metadata(path) == []
    assert b"GPS" not in path.read_bytes()


def test_jpeg_trailer_after_eoi_is_flagged_and_removed(tmp_path: Path) -> None:
    path = tmp_path / "motion.jpg"
    Image.new("RGB", (8, 8), "red").save(path, format="JPEG")
    clean_length = len(path.read_bytes())
    path.write_bytes(path.read_bytes() + b"SEFH\x00Image_UTC_Data\x00MotionPhoto_Data\x00SEFT")

    assert find_private_metadata(path) == [f"TRAILER@{clean_length}"]
    assert sanitize(path) is True
    assert find_private_metadata(path) == []
    assert b"MotionPhoto_Data" not in path.read_bytes()


def test_progressive_jpeg_app1_between_scans_is_flagged(tmp_path: Path) -> None:
    path = tmp_path / "progressive.jpg"
    Image.effect_noise((32, 32), 64).convert("RGB").save(path, format="JPEG", progressive=True)
    data = path.read_bytes()
    second_scan = data.index(b"\xff\xda", data.index(b"\xff\xda") + 2)
    payload = b"Exif\x00\x00GPS fixture"
    segment = b"\xff\xe1" + (len(payload) + 2).to_bytes(2, "big") + payload
    path.write_bytes(data[:second_scan] + segment + data[second_scan:])

    assert f"APP1@{second_scan}" in find_private_metadata(path)
    assert sanitize(path) is True
    assert find_private_metadata(path) == []


def test_clean_jpeg_is_not_flagged(tmp_path: Path) -> None:
    for name, options in [("baseline.jpg", {}), ("progressive.jpg", {"progressive": True})]:
        path = tmp_path / name
        Image.effect_noise((32, 32), 64).convert("RGB").save(path, format="JPEG", **options)
        assert find_private_metadata(path) == []


def test_sanitize_png_keeps_palette_transparency(tmp_path: Path) -> None:
    path = tmp_path / "palette.png"
    image = Image.new("P", (4, 4), 0)
    image.putpalette([0, 0, 0, 255, 0, 0] + [0] * (256 * 3 - 6))
    image.putpixel((0, 0), 1)
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Comment", "private")
    image.save(path, format="PNG", transparency=0, pnginfo=metadata)

    assert sanitize(path) is True
    with Image.open(path) as clean:
        assert clean.mode == "P"  # not inflated to RGBA
        rgba = clean.convert("RGBA")
        assert rgba.getpixel((1, 1))[3] == 0
        assert rgba.getpixel((0, 0)) == (255, 0, 0, 255)


def test_sanitize_png_keeps_colour_key_transparency(tmp_path: Path) -> None:
    path = tmp_path / "colour-key.png"
    image = Image.new("RGB", (2, 2), (255, 255, 255))
    image.putpixel((0, 0), (10, 20, 30))
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Comment", "private")
    image.save(path, format="PNG", transparency=(255, 255, 255), pnginfo=metadata)

    assert sanitize(path) is True
    with Image.open(path) as clean:
        rgba = clean.convert("RGBA")
        assert rgba.getpixel((1, 1)) == (255, 255, 255, 0)
        assert rgba.getpixel((0, 0)) == (10, 20, 30, 255)


def test_sanitize_cmyk_jpeg_does_not_raise(tmp_path: Path) -> None:
    path = tmp_path / "print.jpg"
    exif = Image.Exif()
    exif[0x010F] = "Example Scanner"
    Image.new("CMYK", (4, 4), (0, 255, 255, 0)).save(path, format="JPEG", exif=exif)

    assert sanitize(path) is True
    assert find_private_metadata(path) == []
    with Image.open(path) as clean:
        assert clean.mode == "RGB"
        red, green, blue = clean.getpixel((1, 1))
        assert red > 200 and green < 60 and blue < 60


def test_sanitize_16bit_png_keeps_values(tmp_path: Path) -> None:
    path = tmp_path / "depth.png"
    image = Image.new("I;16", (2, 2), 30000)
    image.putpixel((0, 0), 100)
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Comment", "private")
    image.save(path, format="PNG", pnginfo=metadata)

    assert sanitize(path) is True
    assert find_private_metadata(path) == []
    with Image.open(path) as clean:
        assert clean.mode.startswith("I")
        assert clean.getpixel((1, 1)) == 30000
        assert clean.getpixel((0, 0)) == 100


def test_directory_scan_reports_unsupported_media(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    Image.new("RGB", (2, 2), "white").save(tmp_path / "clean.png", format="PNG")
    video = tmp_path / "clip.webp"
    video.write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8 ")

    monkeypatch.setattr(sys, "argv", ["sanitize", str(tmp_path)])
    with pytest.raises(SystemExit) as failure:
        sanitize_blog_images.main()
    assert failure.value.code == 1
    output = capsys.readouterr().out
    assert f"UNCHECKED={video.as_posix()}" in output
    assert "PRIVATE_METADATA_COUNT=0" in output
    assert "UNCHECKED_COUNT=1" in output

    monkeypatch.setattr(sys, "argv", ["sanitize", str(tmp_path), "--allow-unchecked", str(video)])
    sanitize_blog_images.main()
    assert "UNCHECKED_COUNT=0" in capsys.readouterr().out


def _png_chunk_types(path: Path) -> list[bytes]:
    data = path.read_bytes()
    types, offset = [], 8
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        types.append(data[offset + 4 : offset + 8])
        offset += 12 + length
    return types


def _text_metadata() -> PngImagePlugin.PngInfo:
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Comment", "private")
    return metadata


def _rgb_profile() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def test_sanitize_16bit_png_keeps_transparency_key(tmp_path: Path) -> None:
    path = tmp_path / "depth-key.png"
    image = Image.new("I;16", (2, 2), 30000)
    image.putpixel((0, 0), 1000)
    image.save(path, format="PNG", transparency=1000, pnginfo=_text_metadata())

    assert sanitize(path) is True
    with Image.open(path) as clean:
        assert clean.mode == "I;16"
        assert clean.info["transparency"] == 1000
        assert clean.getpixel((1, 1)) == 30000


def test_sanitize_palette_alpha_table_stays_palette(tmp_path: Path) -> None:
    path = tmp_path / "palette-alpha.png"
    image = Image.new("P", (2, 1), 0)
    image.putpalette([0, 0, 0, 255, 0, 0] + [0] * (256 * 3 - 6))
    image.putpixel((1, 0), 1)
    image.save(path, format="PNG", transparency=b"\x00\x80", pnginfo=_text_metadata())

    assert sanitize(path) is True
    with Image.open(path) as clean:
        assert clean.mode == "P"
        assert clean.convert("RGBA").getpixel((1, 0)) == (255, 0, 0, 128)


def test_sanitize_png_keeps_colour_profile_and_gamma(tmp_path: Path) -> None:
    profile = _rgb_profile()
    with_profile = tmp_path / "display-p3.png"
    metadata = _text_metadata()
    metadata.add(b"gAMA", struct.pack(">I", 45455))
    metadata.add(b"cHRM", bytes(32))
    Image.new("RGB", (2, 2), "red").save(
        with_profile, format="PNG", icc_profile=profile, pnginfo=metadata
    )
    srgb_only = tmp_path / "srgb.png"
    metadata = _text_metadata()
    metadata.add(b"sRGB", b"\x00")
    Image.new("RGB", (2, 2), "red").save(srgb_only, format="PNG", pnginfo=metadata)

    assert sanitize(with_profile) is True
    assert sanitize(srgb_only) is True
    assert {b"iCCP", b"gAMA", b"cHRM"} <= set(_png_chunk_types(with_profile))
    assert b"sRGB" in _png_chunk_types(srgb_only)
    with Image.open(with_profile) as clean:
        assert clean.info["icc_profile"] == profile


def test_jpeg_icc_profile_is_kept_but_other_app2_is_flagged(tmp_path: Path) -> None:
    profile = _rgb_profile()
    path = tmp_path / "wide-gamut.jpg"
    exif = Image.Exif()
    exif[0x010F] = "Example Phone"
    Image.new("RGB", (8, 8), "blue").save(path, format="JPEG", exif=exif, icc_profile=profile)

    assert [finding.split("@")[0] for finding in find_private_metadata(path)] == ["APP1"]
    assert sanitize(path) is True
    assert find_private_metadata(path) == []
    with Image.open(path) as clean:
        assert clean.info["icc_profile"] == profile

    data = path.read_bytes()
    payload = b"MPF\x00secondary image"
    mpf = b"\xff\xe2" + (len(payload) + 2).to_bytes(2, "big") + payload
    path.write_bytes(data[:2] + mpf + data[2:])
    assert find_private_metadata(path) == ["APP2@2"]


def test_cmyk_profile_is_not_attached_to_rgb_output(tmp_path: Path) -> None:
    profile = bytearray(_rgb_profile())
    profile[16:20] = b"CMYK"
    path = tmp_path / "print-profile.jpg"
    exif = Image.Exif()
    exif[0x010F] = "Example Scanner"
    Image.new("CMYK", (4, 4), (0, 255, 255, 0)).save(
        path, format="JPEG", exif=exif, icc_profile=bytes(profile)
    )

    assert sanitize(path) is True
    with Image.open(path) as clean:
        assert clean.mode == "RGB"
        assert "icc_profile" not in clean.info


@pytest.mark.parametrize("suffix", [".jfif", ".jpe", ".mpo"])
def test_other_jpeg_suffixes_are_checked_and_cleaned(tmp_path: Path, suffix: str) -> None:
    path = tmp_path / ("photo" + suffix)
    exif = Image.Exif()
    exif[0x010F] = "Example Phone"
    Image.new("RGB", (8, 8), "blue").save(path, format="JPEG", exif=exif)

    assert sanitize_blog_images.iter_images([tmp_path]) == [path]
    assert find_private_metadata(path)
    assert sanitize(path) is True
    assert find_private_metadata(path) == []


def test_reviewed_media_list_only_covers_the_recorded_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    video = tmp_path / "hardware/clip.mp4"
    video.parent.mkdir()
    video.write_bytes(b"\x00\x00\x00\x08ftyp")
    other = tmp_path / "hardware/new.mov"
    other.write_bytes(b"\x00\x00\x00\x08ftyp")
    (tmp_path / sanitize_blog_images.REVIEWED_MEDIA_LIST).write_text(
        json.dumps(
            {
                "files": {
                    "hardware/clip.mp4": {
                        "sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
                        "reason": "fixture",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["sanitize", str(tmp_path)])
    with pytest.raises(SystemExit):
        sanitize_blog_images.main()
    output = capsys.readouterr().out
    assert f"UNCHECKED={other.as_posix()}" in output
    assert "clip.mp4" not in output and "UNCHECKED_COUNT=1" in output

    other.unlink()
    sanitize_blog_images.main()
    assert "UNCHECKED_COUNT=0" in capsys.readouterr().out

    video.write_bytes(video.read_bytes() + b"\x00\x00\x00\x08udta")  # edited after review
    with pytest.raises(SystemExit):
        sanitize_blog_images.main()
    assert f"UNCHECKED={video.as_posix()}" in capsys.readouterr().out


def test_repository_gate_passes_with_reviewed_media(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["sanitize", str(ROOT / "docs/assets")])
    sanitize_blog_images.main()
    output = capsys.readouterr().out
    assert "PRIVATE_METADATA_COUNT=0" in output and "UNCHECKED_COUNT=0" in output
