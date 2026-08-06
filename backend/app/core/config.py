"""Settings, all overridable through ARGUS_-prefixed environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

CsvList = Annotated[list[str], NoDecode]

ChromaMode = Literal["disabled", "persistent", "http"]
ObjectStorageMode = Literal["disabled", "local", "r2"]

DEFAULT_MASK_VARIANTS = (
    "surgical_blue",
    "surgical_white",
    "cloth_black",
    "cloth_colored",
    "n95",
    "improper_low",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ARGUS_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Project ARGUS Attendance API"
    app_version: str = "0.1.0"
    environment: Literal["local", "staging", "production"] = "local"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    log_json: bool = False
    cors_origins: CsvList = Field(default_factory=list)

    database_url: str | None = None
    db_pool_size: int = Field(default=10, ge=1)
    db_max_overflow: int = Field(default=20, ge=0)
    db_pool_recycle_seconds: int = Field(default=1800, ge=60)
    db_statement_timeout_ms: int = Field(default=15_000, ge=100)
    db_echo: bool = False

    # Attendance is written while the session is ACTIVE: detections are coalesced
    # per interval and flushed as one statement.
    capture_interval_seconds: float = Field(default=15.0, gt=0)
    capture_flush_chunk_size: int = Field(default=2_000, ge=1)
    capture_max_buffered_sessions: int = Field(default=256, ge=1)

    # Null until calibrated against a validation set. While any is null the
    # decision layer can only return HUMAN_REVIEW / UNKNOWN.
    match_threshold: float | None = Field(default=None, ge=-1.0, le=1.0)
    review_threshold: float | None = Field(default=None, ge=-1.0, le=1.0)
    minimum_margin: float | None = Field(default=None, ge=0.0, le=2.0)

    # Directory holding the InsightFace buffalo_l ONNX pack; the explicit paths
    # below override it.
    model_root: Path | None = None
    detector_model_path: Path | None = None
    embedder_model_path: Path | None = None
    embedding_dim: int = Field(default=512, ge=1)
    mask_variants: CsvList = Field(default_factory=lambda: list(DEFAULT_MASK_VARIANTS))

    onnx_providers: CsvList = Field(default_factory=lambda: ["CPUExecutionProvider"])
    onnx_intra_op_threads: int = Field(default=0, ge=0)
    detection_input_size: int = Field(default=640, ge=128, le=1920)
    detection_score_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    detection_nms_iou: float = Field(default=0.4, ge=0.0, le=1.0)
    detection_max_faces: int = Field(default=100, ge=1)

    recognition_max_frame_bytes: int = Field(default=4 * 1024 * 1024, ge=1024)
    enrollment_max_image_bytes: int = Field(default=8 * 1024 * 1024, ge=1024)
    enrollment_min_face_pixels: int | None = Field(default=None, ge=1)
    enrollment_min_blur_variance: float | None = Field(default=None, ge=0.0)

    video_max_bytes: int = Field(default=256 * 1024 * 1024, ge=1024)
    video_frame_stride: int = Field(default=5, ge=1)
    video_max_frames: int = Field(default=5_000, ge=1)
    batch_max_archive_bytes: int = Field(default=256 * 1024 * 1024, ge=1024)
    batch_max_files: int = Field(default=2_000, ge=1)

    import_max_csv_bytes: int = Field(default=16 * 1024 * 1024, ge=1024)
    import_max_archive_bytes: int = Field(default=1024 * 1024 * 1024, ge=1024)
    import_max_rows: int = Field(default=50_000, ge=1)

    chroma_mode: ChromaMode = "disabled"
    chroma_path: Path | None = None
    chroma_host: str | None = None
    chroma_port: int | None = Field(default=None, ge=1, le=65535)
    chroma_collection: str = "argus_templates"
    chroma_search_k: int = Field(default=10, ge=1, le=200)

    object_storage_mode: ObjectStorageMode = "disabled"
    storage_key_prefix: str = "enrollment"
    # mode=local: images are written here, mounted at media_url_path, and the URL
    # stored in students.image_url is local_public_base_url + key.
    local_storage_path: Path = Path("./.media")
    media_url_path: str = "/media"
    local_public_base_url: str = "http://localhost:8000/media"
    r2_endpoint_url: str | None = None
    r2_bucket: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_public_base_url: str | None = None

    @field_validator("cors_origins", "mask_variants", "onnx_providers", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        # Comma-separated environment values become lists.
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper(cls, value: object) -> object:
        # Accept "debug" as well as "DEBUG".
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _validate(self) -> Settings:
        # Refuse a half-configured dependency instead of failing at first use.
        if self.chroma_mode == "persistent" and self.chroma_path is None:
            raise ValueError("ARGUS_CHROMA_PATH is required when ARGUS_CHROMA_MODE=persistent")
        if self.chroma_mode == "http" and not (self.chroma_host and self.chroma_port):
            raise ValueError(
                "ARGUS_CHROMA_HOST and ARGUS_CHROMA_PORT are required when ARGUS_CHROMA_MODE=http"
            )
        if self.object_storage_mode == "r2":
            required = {
                "ARGUS_R2_ENDPOINT_URL": self.r2_endpoint_url,
                "ARGUS_R2_BUCKET": self.r2_bucket,
                "ARGUS_R2_ACCESS_KEY_ID": self.r2_access_key_id,
                "ARGUS_R2_SECRET_ACCESS_KEY": self.r2_secret_access_key,
                "ARGUS_R2_PUBLIC_BASE_URL": self.r2_public_base_url,
            }
            missing = sorted(name for name, value in required.items() if not value)
            if missing:
                raise ValueError(f"{', '.join(missing)} required when ARGUS_OBJECT_STORAGE_MODE=r2")
        if (
            self.match_threshold is not None
            and self.review_threshold is not None
            and self.review_threshold > self.match_threshold
        ):
            raise ValueError("ARGUS_REVIEW_THRESHOLD must be <= ARGUS_MATCH_THRESHOLD")
        return self

    def model_file(self, explicit: Path | None, filename: str) -> Path | None:
        # Explicit path wins, otherwise fall back to the buffalo_l pack layout.
        if explicit is not None:
            return explicit
        return self.model_root / filename if self.model_root is not None else None


@lru_cache
def get_settings() -> Settings:
    # Cached so the whole process shares one parsed configuration.
    return Settings()
