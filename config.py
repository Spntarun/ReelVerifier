import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env if present
basedir = Path(__file__).resolve().parent
load_dotenv(basedir / ".env")


def str_to_bool(value, default=False) -> bool:
    """Helper to convert environment variable string to boolean."""
    if value is None:
        return default
    return str(value).strip().lower() in ("true", "1", "t", "yes", "y")


class Config:
    """Application configuration loaded from environment variables."""

    # Base directory
    BASE_DIR = basedir

    # Flask & Security
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-secret-key-change-in-production")
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    DEBUG = FLASK_ENV == "development"

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{basedir / 'app.db'}")
    # Handle postgres:// vs postgresql:// if needed for Render / Railway
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Authentication & Email Access
    ALLOWED_EMAIL_DOMAINS = [
        d.strip().lower()
        for d in os.getenv("ALLOWED_EMAIL_DOMAINS", "").split(",")
        if d.strip()
    ]

    # Session Cookie Security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = FLASK_ENV == "production"

    # Upload Limits
    # 4 files max: videos up to 60MB, images up to 5MB
    MAX_CONTENT_LENGTH = 250 * 1024 * 1024  # 250 MB total upload limit
    MAX_FILES_PER_REQUEST = 4
    MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024   # 5 MB
    MAX_VIDEO_SIZE_BYTES = 60 * 1024 * 1024  # 60 MB
    MAX_VIDEO_DURATION_SECONDS = 120         # 120 seconds
    MAX_CAPTION_LENGTH = 2000                # 2,000 characters

    # Daily Analysis Limit per User
    DAILY_LIMIT_PER_USER = int(os.getenv("DAILY_LIMIT_PER_USER", 10))

    # Gemini API Configuration
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # Local Vision Model (Hugging Face)
    VISION_MODEL = os.getenv("VISION_MODEL", "Qwen/Qwen3-VL-8B-Instruct")
    VISION_DEVICE = os.getenv("VISION_DEVICE", "cuda")
    ENABLE_LOCAL_VISION = str_to_bool(os.getenv("ENABLE_LOCAL_VISION", "true"), default=True)
    VISION_QUANTIZATION = os.getenv("VISION_QUANTIZATION", "").strip().lower() or None

    # Audio Transcription
    ENABLE_TRANSCRIPTION = str_to_bool(os.getenv("ENABLE_TRANSCRIPTION", "true"), default=True)
    WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")

    # Media Binaries
    FFMPEG_BINARY = os.getenv("FFMPEG_BINARY", "ffmpeg")
    FFPROBE_BINARY = os.getenv("FFPROBE_BINARY", "ffprobe")

    # Temporary directory for media processing
    TEMP_MEDIA_DIR = os.getenv("TEMP_MEDIA_DIR", None)

