from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile, WebSocket, WebSocketDisconnect

from app.api.deps import RecognitionServiceDep, get_container_ws
from app.container import Container
from app.core.errors import ArgusError, DependencyNotConfiguredError, error_body
from app.core.logging import get_logger
from app.schemas.recognition import FrameResult

logger = get_logger(__name__)
router = APIRouter(tags=["recognition"])

#: Closing status for a condition that will not fix itself during the connection.
_WS_INTERNAL_ERROR = 1011


@router.post("/recognize", response_model=FrameResult)
async def recognize(
    service: RecognitionServiceDep,
    frame: UploadFile = File(description="JPEG/PNG frame to recognise."),
    session_id: uuid.UUID | None = Form(
        default=None,
        description="When supplied and the decision is MATCH, the recognition is recorded as an "
        "attendance observation for that ACTIVE session.",
    ),
    frame_id: str = Form(default="frame-0001"),
) -> FrameResult:
    """Single-frame recognition.

    Returns 503 until the SCRFD/ArcFace adapters and the Chroma collection exist.
    """
    return await service.recognize(await frame.read(), session_id=session_id, frame_id=frame_id)


@router.websocket("/live")
async def live(
    websocket: WebSocket,
    container: Container = Depends(get_container_ws),
    session_id: uuid.UUID | None = None,
) -> None:
    """Live recognition stream.

    Protocol: the client sends one binary frame and waits for the JSON result
    before sending the next one, so no backlog of stale frames can build up
    (docs/design.md, frame handling). Frames are never stored.
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
