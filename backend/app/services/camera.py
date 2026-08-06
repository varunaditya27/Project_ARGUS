"""Proxies campus CCTV RTSP feeds as MJPEG over HTTP, so the browser (which has no
native RTSP support) can display them with a plain <img> tag and the frontend can
capture frames from that tag through /recognize exactly like it already does for
the webcam.

Each camera gets one background thread holding one RTSP connection, shared by every
viewer - most CCTV DVRs/NVRs cap concurrent RTSP sessions per channel to one or two,
so per-request connections would fight each other instead of just serving cached frames.
Threads (not asyncio) because cv2.VideoCapture.read() blocks on decode.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass

import cv2

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_JPEG_QUALITY = 80
_BOUNDARY = b"argus-camera-frame"


@dataclass(frozen=True, slots=True)
class CameraConfig:
    camera_id: str
    label: str
    rtsp_url: str


class CameraStream:
    """One camera's background capture loop; always holds the most recent JPEG frame."""

    def __init__(self, config: CameraConfig, *, reconnect_seconds: float) -> None:
        self._config = config
        self._reconnect_seconds = reconnect_seconds
        self._lock = threading.Lock()
        self._latest_jpeg: bytes | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name=f"camera-{self._config.camera_id}", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._thread = None

    def latest_jpeg(self) -> bytes | None:
        with self._lock:
            return self._latest_jpeg

    def _run(self) -> None:
        while not self._stop_event.is_set():
            capture = cv2.VideoCapture(self._config.rtsp_url, cv2.CAP_FFMPEG)
            if not capture.isOpened():
                logger.warning(
                    "camera %s: could not open RTSP stream, retrying", self._config.camera_id
                )
                capture.release()
                self._stop_event.wait(self._reconnect_seconds)
                continue

            logger.info("camera %s: connected", self._config.camera_id)
            while not self._stop_event.is_set():
                ok, frame = capture.read()
                if not ok:
                    logger.warning("camera %s: read failed, reconnecting", self._config.camera_id)
                    break
                ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY])
                if ok:
                    with self._lock:
                        self._latest_jpeg = encoded.tobytes()
            capture.release()
            if not self._stop_event.is_set():
                self._stop_event.wait(self._reconnect_seconds)


class CameraManager:
    """Registry of configured cameras; streams start lazily on first viewer, not at boot -
    the campus LAN (172.16.x.x) may be unreachable from wherever the backend happens to be
    running, and a dependency that isn't being watched shouldn't spend a thread on it.
    """

    def __init__(self, configs: list[CameraConfig], *, reconnect_seconds: float) -> None:
        self._configs = {c.camera_id: c for c in configs}
        self._reconnect_seconds = reconnect_seconds
        self._streams: dict[str, CameraStream] = {}
        self._lock = threading.Lock()

    def list_cameras(self) -> list[CameraConfig]:
        return list(self._configs.values())

    def get_config(self, camera_id: str) -> CameraConfig | None:
        return self._configs.get(camera_id)

    def _stream_for(self, camera_id: str) -> CameraStream | None:
        config = self._configs.get(camera_id)
        if config is None:
            return None
        with self._lock:
            stream = self._streams.get(camera_id)
            if stream is None:
                stream = CameraStream(config, reconnect_seconds=self._reconnect_seconds)
                stream.start()
                self._streams[camera_id] = stream
        return stream

    def mjpeg_frames(self, camera_id: str, *, fps: float) -> Iterator[bytes] | None:
        stream = self._stream_for(camera_id)
        if stream is None:
            return None
        interval = 1.0 / fps

        def generate() -> Iterator[bytes]:
            while True:
                frame = stream.latest_jpeg()
                if frame is not None:
                    yield (
                        b"--" + _BOUNDARY + b"\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: "
                        + str(len(frame)).encode()
                        + b"\r\n\r\n"
                        + frame
                        + b"\r\n"
                    )
                time.sleep(interval)

        return generate()

    def shutdown(self) -> None:
        for stream in self._streams.values():
            stream.stop()


def build_camera_manager(settings: Settings) -> CameraManager:
    configs = []
    if settings.camera_steps_rtsp_url:
        configs.append(
            CameraConfig("steps", settings.camera_steps_label, settings.camera_steps_rtsp_url)
        )
    if settings.camera_wall_rtsp_url:
        configs.append(
            CameraConfig("wall", settings.camera_wall_label, settings.camera_wall_rtsp_url)
        )
    return CameraManager(configs, reconnect_seconds=settings.camera_reconnect_seconds)


MJPEG_BOUNDARY = _BOUNDARY.decode()
