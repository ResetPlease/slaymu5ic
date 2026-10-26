import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    version: str = "1.0.0"
    base_path: str = ""
    max_upload_mb: int = 30
    max_duration_seconds: int = 300
    process_timeout_seconds: float = 60
    max_concurrent_jobs: int = 2
    log_level: str = "INFO"
    ffmpeg_binary: str = "ffmpeg"

    @classmethod
    def from_env(cls):
        settings = cls(
            version=os.getenv("APP_VERSION", "1.0.0"),
            base_path=os.getenv("APP_BASE_PATH", "").rstrip("/"),
            max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "30")),
            max_duration_seconds=int(os.getenv("MAX_DURATION_SECONDS", "300")),
            process_timeout_seconds=float(os.getenv("PROCESS_TIMEOUT_SECONDS", "60")),
            max_concurrent_jobs=int(os.getenv("MAX_CONCURRENT_JOBS", "2")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            ffmpeg_binary=os.getenv("FFMPEG_BINARY", "ffmpeg"),
        )
        if settings.base_path and (
            not settings.base_path.startswith("/")
            or any(
                c not in "/abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
                for c in settings.base_path
            )
        ):
            raise ValueError("APP_BASE_PATH must be an absolute URL path")
        if (
            min(
                settings.max_upload_mb,
                settings.max_duration_seconds,
                settings.process_timeout_seconds,
                settings.max_concurrent_jobs,
            )
            <= 0
        ):
            raise ValueError("Resource limits must be positive")
        return settings
