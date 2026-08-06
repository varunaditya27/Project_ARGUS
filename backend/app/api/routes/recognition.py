"""Recognition routes: one frame, a recorded video, an archive of stills, or live."""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile, WebSocket, WebSocketDisconnect

from app.api.deps import OfflineServiceDep, RecognitionServiceDep, get_container_ws
from app.container import Container
from app.core.errors import ArgusError, DependencyNotConfiguredError, error_body
from app.core.logging import get_logger
from app.schemas.recognition import FrameResult, OfflineRunResult

logger = get_logger(__name__)
router = APIRouter(tags=["recognition"])

#: Closing status for a condition that will not fix itself during the connection.
_WS_INTERNAL_ERROR = 1011


@router.post("/recognize", response_model=FrameResult)
async def recognize(
    service: RecognitionServiceDep,
    frame: UploadFile = File(description="JPEG/PNG frame to recognise."),
    session_id: uuid.UUID | None = Form(
        default=None, description="When set, a MATCH is buffered for that ACTIVE session."
    ),
    frame_id: str = Form(default="frame-0001"),
) -> FrameResult:
    # Recognise a single uploaded frame.
    return await service.recognize(await frame.read(), session_id=session_id, frame_id=frame_id)


@router.post("/recognize/video", response_model=OfflineRunResult)
async def recognize_video(
    service: OfflineServiceDep,
    video: UploadFile = File(description="Recorded video (MP4/AVI/MKV, subject to OpenCV)."),
    session_id: uuid.UUID | None = Form(default=None),
    recorded_at: dt.datetime | None = Form(
        default=None,
        description="Start of the recording. Each sampled frame is then timestamped at "
        "recorded_at + frame_index / fps instead of at upload time.",
    ),
) -> OfflineRunResult:
    """Offline attendance run over a recorded video.

    Every Nth frame is recognised and fed through the same capture buffer as the
    live stream, so absence is still only decided when the session is closed.
    """
    return await service.run_video(
        await video.read(), session_id=session_id, recorded_at=recorded_at
    )


@router.post("/recognize/batch", response_model=OfflineRunResult)
async def recognize_batch(
    service: OfflineServiceDep,
    archive: UploadFile = File(description="ZIP archive of still images."),
    session_id: uuid.UUID | None = Form(default=None),
    recorded_at: dt.datetime | None = Form(default=None),
) -> OfflineRunResult:
    # Offline attendance run over an archive of stills.
    return await service.run_archive(
        await archive.read(), session_id=session_id, recorded_at=recorded_at
    )


@router.websocket("/live")
async def live(
    websocket: WebSocket,
    container: Container = Depends(get_container_ws),
    session_id: uuid.UUID | None = None,
) -> None:
    """Live recognition stream.

    The client sends one binary frame and waits for the JSON result before
    sending the next, so no backlog of stale frames builds up. Frames are never
    stored.
    """
    await websocket.accept()
    try:
        service = container.services.recognition
    except ArgusError as exc:
        await websocket.send_json(error_body(exc.code, exc.message, exc.details))
        await websocket.close(code=_WS_INTERNAL_ERROR, reason=exc.code)
        return

    frame_number = 0
    try:
        while True:
            payload = await websocket.receive_bytes()
            frame_number += 1
            try:
                result = await service.recognize(
                    payload, session_id=session_id, frame_id=f"frame-{frame_number:06d}"
                )
            except DependencyNotConfiguredError as exc:
                # Not going to recover mid-connection: report once and close.
                await websocket.send_json(error_body(exc.code, exc.message, exc.details))
                await websocket.close(code=_WS_INTERNAL_ERROR, reason=exc.code)
                return
            except ArgusError as exc:
                await websocket.send_json(error_body(exc.code, exc.message, exc.details))
                continue
            await websocket.send_json(result.model_dump(mode="json"))
    except WebSocketDisconnect:
        logger.info("Live recognition socket closed after %d frames", frame_number)
