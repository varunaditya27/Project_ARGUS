"""One configured CCTV camera, as exposed to the frontend - never the RTSP credentials."""

from __future__ import annotations

from app.schemas.common import ApiModel


class CameraInfo(ApiModel):
    camera_id: str
    label: str
