from pathlib import Path

from PIL import Image, PngImagePlugin

from scripts.sanitize_blog_images import find_private_metadata, sanitize


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
