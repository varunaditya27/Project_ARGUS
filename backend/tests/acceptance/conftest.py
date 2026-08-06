"""Fixtures for the acceptance tier.

These run the real thing: the ONNX pack from ``models/buffalo_l``, a Chroma
store and a PostgreSQL database, driven only through HTTP. They skip, loudly,
when any of that is missing rather than passing vacuously.

The thresholds below are provisional. Calibration is a separate exercise
(``evaluation/calibrate_thresholds.py``); these values exist so the decision
layer can be exercised at all, and no test here asserts an accuracy figure.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.container import Container
from app.main import create_app
from tests.conftest import (
    MODEL_ROOT,
    TEST_DATABASE_URL,
    make_settings,
    requires_database,
    requires_models,
    reset_database,
)
from tests.images import sample_face_bytes

pytestmark = [pytest.mark.acceptance, requires_database, requires_models]

#: Provisional decision thresholds, see the module docstring.
CALIBRATION = {"match_threshold": 0.45, "review_threshold": 0.30, "minimum_margin": 0.05}
#: Quality gates are off by default. Enabled here so AT-09 can exercise them;
#: the sample portrait measures ~98px across and ~59 blur variance, the derived
#: probes ~12px and ~2, so these sit between the two by a wide margin.
QUALITY_GATES = {"enrollment_min_face_pixels": 60, "enrollment_min_blur_variance": 15.0}

LECTURE = {
    "subject": "Computer Vision",
    "faculty": "Dr. Placeholder",
    "date": "2026-08-06",
    "start_time": "09:00:00",
    "end_time": "10:00:00",
}


@dataclass(slots=True)
class Stack:
    """The running system plus the handle needed to force a capture flush."""

    client: AsyncClient
    container: Container

    async def flush(self) -> int:
        # The interval flusher's tick; the lifespan task does not run under ASGI.
        assert self.container.flusher is not None
        return await self.container.flusher.flush_once()

    async def classroom(self, name: str = "CSE-A", strength: int = 3) -> str:
        response = await self.client.post(
            "/api/v1/classrooms",
            json={"class_name": name, "department": "CSE", "semester": 5, "strength": strength},
        )
        assert response.status_code == 201, response.text
        return response.json()["class_id"]

    async def student(self, class_id: str, roll_no: int = 1) -> str:
        response = await self.client.post(
            "/api/v1/students",
            json={
                "student_name": f"Student {roll_no}",
                "roll_no": roll_no,
                "class_id": class_id,
                "image_url": f"https://images.example.test/{roll_no}.jpg",
            },
        )
        assert response.status_code == 201, response.text
        return response.json()["student_id"]

    async def session(self, class_id: str) -> str:
        response = await self.client.post(
            "/api/v1/sessions", json={**LECTURE, "class_id": class_id}
        )
        assert response.status_code == 201, response.text
        return response.json()["session_id"]

    async def enroll(self, student_id: str, image: bytes | None = None):
        return await self.client.post(
            f"/api/v1/students/{student_id}/enroll",
            files={"image": ("face.jpg", image or sample_face_bytes(), "image/jpeg")},
        )

    async def recognize(self, frame: bytes, session_id: str | None = None):
        data = {"session_id": session_id} if session_id else {}
        return await self.client.post(
            "/api/v1/recognize", files={"frame": ("frame.jpg", frame, "image/jpeg")}, data=data
        )


async def build(tmp_path: Path, **overrides: object) -> AsyncIterator[Stack]:
    # One application with real models, a private Chroma store and local media.
    assert TEST_DATABASE_URL
    await reset_database(TEST_DATABASE_URL)
    configuration: dict[str, object] = {
        "database_url": TEST_DATABASE_URL,
        "chroma_mode": "persistent",
        "chroma_path": tmp_path / "chroma",
        "object_storage_mode": "local",
        "local_storage_path": tmp_path / "media",
        "local_public_base_url": "http://testserver/media",
        "model_root": MODEL_ROOT,
        **CALIBRATION,
        **QUALITY_GATES,
        **overrides,
    }
    settings = make_settings(**configuration)
    app = create_app(settings)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield Stack(client=client, container=app.state.container)
    await app.state.container.shutdown()


@pytest_asyncio.fixture
async def stack(tmp_path: Path) -> AsyncIterator[Stack]:
    async for value in build(tmp_path):
        yield value


@pytest_asyncio.fixture
async def uncalibrated(tmp_path: Path) -> AsyncIterator[Stack]:
    # Same stack with the thresholds cleared, which is the shipped default.
    async for value in build(
        tmp_path, match_threshold=None, review_threshold=None, minimum_margin=None
    ):
        yield value
