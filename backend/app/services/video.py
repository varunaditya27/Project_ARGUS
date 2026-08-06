"""Frame sampling for uploaded video files.

OpenCV needs a file path, so the upload is spooled to disk first. Frames are
read sequentially rather than seeked to: CAP_PROP_POS_FRAMES is unreliable on
compressed formats, and sequential decoding is what the codec is optimised for.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import AsyncIterator

import cv2

from app.core.errors import InvalidRequestError
from app.core.logging import get_logger
from app.recognition.ports import Image

logger = get_logger(__name__)

#: Sampled frames decoded per thread hop.
_CHUNK = 8


async def sample_frames(
    payload: bytes, *, stride: int, max_frames: int
) -> AsyncIterator[tuple[int, Image, float]]:
    # Yield (frame_index, frame, fps) for every stride-th frame, up to max_frames.
    path = await asyncio.to_thread(_spool, payload)
    try:
        capture, fps = await asyncio.to_thread(_open, path)
        try:
            remaining, index = max_frames, -1
            while remaining > 0:
                chunk, index = await asyncio.to_thread(
                    _read_chunk, capture, index, stride, min(_CHUNK, remaining)
                )
                if not chunk:
                    break
                remaining -= len(chunk)
                for frame_index, frame in chunk:
                    yield frame_index, frame, fps
        finally:
            await asyncio.to_thread(capture.release)
    finally:
        await asyncio.to_thread(_cleanup, path)


def _spool(payload: bytes) -> str:
    # Write the upload to a temporary file OpenCV can open.
    with tempfile.NamedTemporaryFile(prefix="argus-video-", suffix=".bin", delete=False) as handle:
        handle.write(payload)
        return handle.name


def _cleanup(path: str) -> None:
    # Best-effort removal of the spooled file.
    try:
        os.unlink(path)
    except OSError:
        logger.warning("Could not delete temporary video %s", path)


def _open(path: str) -> tuple[cv2.VideoCapture, float]:
    # Open the container and settle on a usable frame rate.
    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        capture.release()
        raise InvalidRequestError(
            "The uploaded video could not be opened. Supported containers depend on the OpenCV "
            "build (MP4/AVI/MKV are typical)."
        )
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    # A malformed header can report 0 or NaN; fall back to a nominal rate so
    # frame timestamps stay monotonic instead of dividing by zero.
    return capture, fps if fps == fps and fps > 0 else 25.0


def _read_chunk(
    capture: cv2.VideoCapture, index: int, stride: int, limit: int
) -> tuple[list[tuple[int, Image]], int]:
    # Decode forward until `limit` sampled frames are collected or the file ends.
    frames: list[tuple[int, Image]] = []
    while len(frames) < limit:
        ok, frame = capture.read()
        if not ok:
            break
        index += 1
        if index % stride == 0:
            frames.append((index, frame))
    return frames, index
