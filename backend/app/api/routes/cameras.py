"""Campus CCTV routes: list configured cameras, and proxy each as MJPEG.

RTSP has no browser support, so the browser never talks to a camera directly -
it only ever sees this proxy, which also keeps the RTSP credentials server-side.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.deps import CameraManagerDep, ContainerDep
from app.core.errors import NotFoundError
from app.schemas.camera import CameraInfo
from app.services.camera import MJPEG_BOUNDARY

router = APIRouter(tags=["cameras"])


@router.get("/cameras", response_model=list[CameraInfo])
async def list_cameras(cameras: CameraManagerDep) -> list[CameraInfo]:
    # Only cameras with an RTSP URL configured - an empty list just means none are set up yet.
    return [CameraInfo(camera_id=c.camera_id, label=c.label) for c in cameras.list_cameras()]


@router.get("/cameras/{camera_id}/mjpeg")
async def camera_mjpeg(
    camera_id: str, cameras: CameraManagerDep, container: ContainerDep
) -> StreamingResponse:
    frames = cameras.mjpeg_frames(camera_id, fps=container.settings.camera_mjpeg_fps)
    if frames is None:
        raise NotFoundError(f"No camera configured with id '{camera_id}'.")
    return StreamingResponse(
        frames, media_type=f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY}"
    )
