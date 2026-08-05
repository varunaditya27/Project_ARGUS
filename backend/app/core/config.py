"""Application settings.

Every value is overridable through an ``ARGUS_``-prefixed environment variable or
a ``.env`` file. Values that require empirical calibration (recognition
thresholds, image quality gates) default to ``None`` and the code paths that
consume them degrade explicitly instead of guessing a number.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

CsvList = Annotated[list[str], NoDecode]

Environment = Literal["local", "staging", "production"]
ChromaMode = Literal["disabled", "persistent", "http"]
ObjectStorageMode = Literal["disabled", "r2"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ARGUS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------------------------------------------------------------- runtime
    app_name: str = "Project ARGUS Attendance API"
    app_version: str = "0.1.0"
    environment: Environment = "local"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    log_json: bool = False
    cors_origins: CsvList = Field(default_factory=list)

    # --------------------------------------------------------------- database
    database_url: str | None = None
    db_pool_size: int = Field(default=10, ge=1)
    db_max_overflow: int = Field(default=20, ge=0)
    db_pool_recycle_seconds: int = Field(default=1800, ge=60)
    db_statement_timeout_ms: int = Field(default=15_000, ge=100)
    db_echo: bool = False

    # ------------------------------------------------------- attendance capture
    # Attendance is written continuously while a session is ACTIVE: detections
    # are coalesced per interval and flushed as one bulk statement.
    capture_interval_seconds: float = Field(default=15.0, gt=0)
    capture_flush_chunk_size: int = Field(default=2_000, ge=1)
    capture_max_buffered_sessions: int = Field(default=256, ge=1)

    # ------------------------------------------------------- recognition thresholds
    # docs/design.md keeps these null until validation-set calibration is done.
    # While any of them is null the decision layer can only return
    # HUMAN_REVIEW / UNKNOWN -- it never auto-marks attendance.
    match_threshold: float | None = Field(default=None, ge=-1.0, le=1.0)
    review_threshold: float | None = Field(default=None, ge=-1.0, le=1.0)
    minimum_margin: float | None = Field(default=None, ge=0.0, le=2.0)

    # ------------------------------------------------------------ model adapters
    detector_model_path: Path | None = None
    embedder_model_path: Path | None = None
    mask_synthesizer_root: Path | None = None
    embedding_dim: int = Field(default=512, ge=1)
    mask_variants: CsvList = Field(
        default_factory=lambda: [
            "surgical_blue",
            "surgical_white",
            "cloth_black",
            "cloth_colored",
            "n95",
            "improper_low",
        ]
    )

    # Enrollment image quality gates (docs/design.md step 2). Null = gate is
    # reported as uncalibrated and skipped rather than applied with a guessed value.
    enrollment_min_face_pixels: int | None = Field(default=None, ge=1)
    enrollment_min_blur_variance: float | None = Field(default=None, ge=0.0)
    enrollment_max_image_bytes: int = Field(default=8 * 1024 * 1024, ge=1024)
    recognition_max_frame_bytes: int = Field(default=4 * 1024 * 1024, ge=1024)

    # ------------------------------------------------------------ vector index
    chroma_mode: ChromaMode = "disabled"
    chroma_path: Path | None = None
    chroma_host: str | None = None
    chroma_port: int | None = Field(default=None, ge=1, le=65535)
    chroma_collection: str = "argus_templates"
    chroma_search_k: int = Field(default=10, ge=1, le=200)

    # ---------------------------------------------------------- object storage
    # Enrollment images live in Cloudflare R2 (docs/db.md). The backend stores
    # only the resulting URL in students.image_url.
    object_storage_mode: ObjectStorageMode = "disabled"
    r2_public_base_url: str | None = None

    @field_validator("cors_origins", "mask_variants", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _validate_dependencies(self) -> Settings:
        if self.chroma_mode == "persistent" and self.chroma_path is None:
            raise ValueError("ARGUS_CHROMA_PATH is required when ARGUS_CHROMA_MODE=persistent")
        if self.chroma_mode == "http" and not (self.chroma_host and self.chroma_port):
            raise ValueError(
                "ARGUS_CHROMA_HOST and ARGUS_CHROMA_PORT are required when ARGUS_CHROMA_MODE=http"
            )
        if self.object_storage_mode == "r2" and not self.r2_public_base_url:
            raise ValueError(
                "ARGUS_R2_PUBLIC_BASE_URL is required when ARGUS_OBJECT_STORAGE_MODE=r2"
            )
        thresholds = (self.match_threshold, self.review_threshold, self.minimum_margin)
        if all(value is not None for value in thresholds):
            assert self.match_threshold is not None and self.review_threshold is not None
            if self.review_threshold > self.match_threshold:
                raise ValueError("ARGUS_REVIEW_THRESHOLD must be <= ARGUS_MATCH_THRESHOLD")
        return self

    @property
    def thresholds_calibrated(self) -> bool:
        return None not in (self.match_threshold, self.review_threshold, self.minimum_margin)


@lru_cache
def get_settings() -> Settings:
    return Settings()
