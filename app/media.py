import os
import io
import json
import logging
import hashlib
import subprocess
import tempfile
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple, Optional
from PIL import Image

logger = logging.getLogger(__name__)


class MediaValidationError(Exception):
    """Custom exception raised when media validation fails."""
    pass


@dataclass
class ProcessedFile:
    """Represents a validated and processed uploaded file."""
    original_filename: str
    file_type: str  # 'image' or 'video'
    mime_type: str
    size_bytes: int
    content_bytes: bytes
    temp_path: Optional[str] = None
    duration_seconds: Optional[float] = None
    extracted_frames: Optional[List[str]] = None
    transcript: str = ""


# Magic byte signatures for supported formats
def detect_file_type_and_mime(data: bytes) -> Tuple[Optional[str], Optional[str]]:
    """
    Detect media type ('image' | 'video') and MIME type from raw file signatures (magic bytes).
    Does not rely on user-supplied file extensions or MIME headers.
    """
    if len(data) < 12:
        return None, None

    # JPEG / JPG: Starts with 0xFF 0xD8 0xFF
    if data[:3] == b"\xff\xd8\xff":
        return "image", "image/jpeg"

    # PNG: Starts with 0x89 'P' 'N' 'G' 0x0D 0x0A 0x1A 0x0A
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image", "image/png"

    # GIF: Starts with 'GIF87a' or 'GIF89a'
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image", "image/gif"

    # WebP: 'RIFF' .... 'WEBP'
    if data[:4] == b"RIFF" and len(data) >= 12 and data[8:12] == b"WEBP":
        return "image", "image/webp"

    # WebM: EBML header 0x1A 0x45 0xDF 0xA3
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "video", "video/webm"

    # MP4 / QuickTime MOV: Box header with 'ftyp' or 'moov' at offset 4
    if len(data) >= 12 and data[4:8] in (b"ftyp", b"moov"):
        subtype = data[8:12]
        if subtype == b"qt  ":
            return "video", "video/quicktime"
        return "video", "video/mp4"

    return None, None


def compute_deterministic_hash(files_bytes_list: List[bytes], caption: str) -> str:
    """
    Generate a SHA-256 hash from:
    - Uploaded file bytes, in a deterministic order (sorted by each file's SHA-256 digest).
    - Normalized caption text.
    """
    file_hashes = [hashlib.sha256(b).hexdigest() for b in files_bytes_list]
    file_hashes.sort()

    hasher = hashlib.sha256()
    for h in file_hashes:
        hasher.update(h.encode("utf-8"))

    normalized_caption = (caption or "").strip()
    hasher.update(b"||caption||")
    hasher.update(normalized_caption.encode("utf-8"))

    return hasher.hexdigest()


class MediaProcessor:
    """Handles media validation, video inspection, frame extraction, and transcription."""

    def __init__(self, config):
        self.config = config
        self.ffmpeg_bin = config.get("FFMPEG_BINARY", "ffmpeg") if hasattr(config, "get") else getattr(config, "FFMPEG_BINARY", "ffmpeg")
        self.ffprobe_bin = config.get("FFPROBE_BINARY", "ffprobe") if hasattr(config, "get") else getattr(config, "FFPROBE_BINARY", "ffprobe")
        self.whisper_model = None
        self._whisper_initialized = False

    def validate_file_content(self, file_storage, max_image_size: int, max_video_size: int) -> ProcessedFile:
        """
        Read file bytes, validate magic bytes, file integrity, and size limits.
        """
        filename = file_storage.filename or "upload"
        content = file_storage.read()

        if not content or len(content) == 0:
            raise MediaValidationError(f"File '{filename}' is empty.")

        file_type, mime_type = detect_file_type_and_mime(content)
        if not file_type or not mime_type:
            raise MediaValidationError(
                f"Unsupported file format for '{filename}'. Allowed formats: JPEG, PNG, WebP, GIF, MP4, MOV, WebM."
            )

        # Check file sizes
        file_size = len(content)
        if file_type == "image":
            if file_size > max_image_size:
                raise MediaValidationError(
                    f"Image '{filename}' ({file_size / (1024*1024):.1f}MB) exceeds the maximum limit of {max_image_size // (1024*1024)}MB."
                )
            # Verify image integrity using Pillow
            try:
                img = Image.open(io.BytesIO(content))
                img.verify()
            except Exception as e:
                raise MediaValidationError(f"Image '{filename}' is corrupted or unreadable: {e}")

        elif file_type == "video":
            if file_size > max_video_size:
                raise MediaValidationError(
                    f"Video '{filename}' ({file_size / (1024*1024):.1f}MB) exceeds the maximum limit of {max_video_size // (1024*1024)}MB."
                )

        return ProcessedFile(
            original_filename=filename,
            file_type=file_type,
            mime_type=mime_type,
            size_bytes=file_size,
            content_bytes=content,
        )

    def probe_video_duration(self, video_path: str) -> float:
        """Use ffprobe to inspect video duration and verify the video stream."""
        cmd = [
            self.ffprobe_bin,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=20,
                check=True,
            )
            output = result.stdout.strip()
            duration = float(output)
            return duration
        except (subprocess.CalledProcessError, ValueError) as e:
            logger.error(f"FFprobe failed on {video_path}: {e}")
            raise MediaValidationError("Could not read video metadata. The video file may be corrupted or unreadable.")
        except FileNotFoundError:
            logger.warning(f"FFprobe binary '{self.ffprobe_bin}' not found on system PATH.")
            # If ffprobe is not installed, fallback duration
            return 30.0

    def extract_video_frames(self, video_path: str, duration: float, output_dir: str) -> List[str]:
        """
        Extract up to 10 evenly spaced frames scaled to max width 720px while maintaining aspect ratio.
        Preserves chronological order.
        """
        num_frames = min(10, max(1, int(duration)))
        extracted_paths = []

        for i in range(num_frames):
            timestamp = (i + 0.5) * (duration / num_frames)
            frame_filename = f"frame_{i:02d}_{timestamp:.2f}s.jpg"
            frame_path = os.path.join(output_dir, frame_filename)

            # Scale to max width 720, aspect ratio preserved, -2 ensures height is an even number
            cmd = [
                self.ffmpeg_bin,
                "-y",
                "-ss", f"{timestamp:.3f}",
                "-i", video_path,
                "-frames:v", "1",
                "-vf", "scale='min(720,iw)':-2",
                "-q:v", "2",
                frame_path,
            ]
            try:
                res = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=20,
                )
                if res.returncode == 0 and os.path.exists(frame_path) and os.path.getsize(frame_path) > 0:
                    extracted_paths.append(frame_path)
            except (subprocess.SubprocessError, FileNotFoundError) as e:
                logger.warning(f"Failed to extract frame at {timestamp}s: {e}")

        return extracted_paths

    def _get_config_val(self, key, default):
        if hasattr(self.config, "get"):
            return self.config.get(key, default)
        return getattr(self.config, key, default)

    def _get_whisper_model(self):
        """Lazy-load and cache the faster-whisper model."""
        if not self._whisper_initialized:
            self._whisper_initialized = True
            try:
                from faster_whisper import WhisperModel
                size = self._get_config_val("WHISPER_MODEL_SIZE", "base")
                # Default to CPU with int8 for light memory usage unless CUDA specified
                device = "cuda" if self._get_config_val("VISION_DEVICE", "cpu") == "cuda" else "cpu"
                compute_type = "float16" if device == "cuda" else "int8"
                logger.info(f"Loading faster-whisper model '{size}' on {device} ({compute_type})...")
                self.whisper_model = WhisperModel(size, device=device, compute_type=compute_type)
            except Exception as e:
                logger.warning(f"faster-whisper could not be loaded: {e}. Audio transcription disabled.")
                self.whisper_model = None
        return self.whisper_model

    def transcribe_video_audio(self, video_path: str, temp_dir: str) -> str:
        """
        Extract audio using FFmpeg and transcribe with faster-whisper.
        Returns transcribed text or empty string.
        """
        if not self._get_config_val("ENABLE_TRANSCRIPTION", True):
            return ""

        audio_path = os.path.join(temp_dir, "extracted_audio.wav")
        # Extract audio track to 16kHz mono WAV
        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            "-f", "wav",
            audio_path,
        ]
        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )
            if res.returncode != 0 or not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
                logger.info("Video has no audio track or audio extraction failed.")
                return ""
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.warning(f"Audio extraction skipped (FFmpeg error): {e}")
            return ""

        # Run transcription
        model = self._get_whisper_model()
        if not model:
            return ""

        try:
            segments, info = model.transcribe(audio_path, beam_size=2)
            transcript_parts = [segment.text.strip() for segment in segments]
            transcript = " ".join(transcript_parts).strip()
            logger.info(f"Audio transcribed ({info.language}, {info.duration:.1f}s): {transcript[:80]}...")
            return transcript
        except Exception as e:
            logger.warning(f"Transcription failed: {e}")
            return ""


class TemporaryMediaManager:
    """Context manager to ensure all temporary media files are securely cleaned up."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir
        self.temp_dir = None

    def __enter__(self):
        self.temp_dir = tempfile.mkdtemp(prefix="reel_verifier_", dir=self.base_dir)
        return self.temp_dir

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
            except Exception as e:
                logger.error(f"Failed to clean up temporary directory {self.temp_dir}: {e}")

