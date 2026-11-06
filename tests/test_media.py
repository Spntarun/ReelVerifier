import io
import os
from PIL import Image
from werkzeug.datastructures import FileStorage
from app.media import (
    detect_file_type_and_mime,
    compute_deterministic_hash,
    MediaProcessor,
    MediaValidationError,
    TemporaryMediaManager,
)
from config import Config


def create_test_image_bytes(format="JPEG", size=(100, 100)):
    """Helper to create valid image bytes using Pillow."""
    img = Image.new("RGB", size, color="blue")
    buf = io.BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()


def test_magic_bytes_detection():
    """Verify file type and MIME detection by actual magic bytes."""
    # JPEG
    jpeg_bytes = create_test_image_bytes(format="JPEG")
    ftype, mime = detect_file_type_and_mime(jpeg_bytes)
    assert ftype == "image"
    assert mime == "image/jpeg"

    # PNG
    png_bytes = create_test_image_bytes(format="PNG")
    ftype, mime = detect_file_type_and_mime(png_bytes)
    assert ftype == "image"
    assert mime == "image/png"

    # GIF
    gif_bytes = create_test_image_bytes(format="GIF")
    ftype, mime = detect_file_type_and_mime(gif_bytes)
    assert ftype == "image"
    assert mime == "image/gif"

    # WebP
    webp_bytes = create_test_image_bytes(format="WEBP")
    ftype, mime = detect_file_type_and_mime(webp_bytes)
    assert ftype == "image"
    assert mime == "image/webp"

    # MP4 (ftyp box)
    fake_mp4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
    ftype, mime = detect_file_type_and_mime(fake_mp4)
    assert ftype == "video"
    assert mime == "video/mp4"

    # WebM
    fake_webm = b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01\x42\xf7\x81\x01"
    ftype, mime = detect_file_type_and_mime(fake_webm)
    assert ftype == "video"
    assert mime == "video/webm"

    # Unsupported / random text
    random_bytes = b"Hello, this is just plain text content!"
    ftype, mime = detect_file_type_and_mime(random_bytes)
    assert ftype is None
    assert mime is None


def test_file_validation_with_media_processor():
    """Verify validation of file size and integrity."""
    processor = MediaProcessor(Config)
    jpeg_bytes = create_test_image_bytes()

    # Valid image
    file_storage = FileStorage(
        stream=io.BytesIO(jpeg_bytes),
        filename="screenshot.jpg",
        content_type="image/jpeg",
    )
    result = processor.validate_file_content(file_storage, max_image_size=5000000, max_video_size=60000000)
    assert result.file_type == "image"
    assert result.mime_type == "image/jpeg"
    assert result.size_bytes == len(jpeg_bytes)

    # Corrupted image bytes with valid JPEG magic header
    corrupted_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 20
    bad_storage = FileStorage(
        stream=io.BytesIO(corrupted_bytes),
        filename="corrupted.jpg",
        content_type="image/jpeg",
    )
    try:
        processor.validate_file_content(bad_storage, max_image_size=5000000, max_video_size=60000000)
        assert False, "Should have raised MediaValidationError for corrupted image"
    except MediaValidationError:
        pass


def test_deterministic_hash_order_independence():
    """Test that file hashing produces identical hashes regardless of upload ordering."""
    file_a = b"File Content A - 123456789"
    file_b = b"File Content B - 987654321"
    caption = "  Apply now on careers.google.com!  "

    hash1 = compute_deterministic_hash([file_a, file_b], caption)
    hash2 = compute_deterministic_hash([file_b, file_a], caption)
    hash_trimmed_caption = compute_deterministic_hash([file_a, file_b], "Apply now on careers.google.com!")

    assert hash1 == hash2, "File order must not alter deterministic hash"
    assert hash1 == hash_trimmed_caption, "Whitespace in caption must be normalized"

    # Different caption -> different hash
    hash3 = compute_deterministic_hash([file_a, file_b], "Different caption text")
    assert hash1 != hash3


def test_temporary_media_manager_cleanup():
    """Ensure TemporaryMediaManager deletes files completely upon exit."""
    created_path = None
    with TemporaryMediaManager() as temp_dir:
        created_path = temp_dir
        assert os.path.exists(temp_dir)
        test_file = os.path.join(temp_dir, "sample.txt")
        with open(test_file, "w") as f:
            f.write("temporary data")
        assert os.path.exists(test_file)

    # After exiting context, directory must be deleted
    assert not os.path.exists(created_path)

