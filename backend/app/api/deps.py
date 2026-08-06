"""FastAPI dependencies: thin accessors over the container built at startup."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query, Request
from starlette.websockets import WebSocket

from app.container import Container
from app.schemas.common import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.services.attendance import AttendanceService
from app.services.classroom import ClassroomService
from app.services.recognition import RecognitionService
from app.services.registration_import import RegistrationImportService
from app.services.session import SessionService
from app.services.student import StudentService


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_container_ws(websocket: WebSocket) -> Container:
    return websocket.app.state.container


def get_classroom_service(
    container: Annotated[Container, Depends(get_container)],
) -> ClassroomService:
    return container.services.classrooms


def get_student_service(
    container: Annotated[Container, Depends(get_container)],
) -> StudentService:
    return container.services.students


def get_session_service(
    container: Annotated[Container, Depends(get_container)],
) -> SessionService:
    return container.services.sessions


def get_attendance_service(
    container: Annotated[Container, Depends(get_container)],
) -> AttendanceService:
    return container.services.attendance


def get_recognition_service(
    container: Annotated[Container, Depends(get_container)],
) -> RecognitionService:
    return container.services.recognition


def get_registration_import_service(
    container: Annotated[Container, Depends(get_container)],
) -> RegistrationImportService:
    return container.services.registration_import


PageLimit = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE, description="Maximum items to return.")]
PageOffset = Annotated[int, Query(ge=0)]

ContainerDep = Annotated[Container, Depends(get_container)]
ClassroomServiceDep = Annotated[ClassroomService, Depends(get_classroom_service)]
StudentServiceDep = Annotated[StudentService, Depends(get_student_service)]
SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
AttendanceServiceDep = Annotated[AttendanceService, Depends(get_attendance_service)]
RecognitionServiceDep = Annotated[RecognitionService, Depends(get_recognition_service)]
RegistrationImportServiceDep = Annotated[
    RegistrationImportService, Depends(get_registration_import_service)
]

__all__ = [
    "DEFAULT_PAGE_SIZE",
    "AttendanceServiceDep",
    "ClassroomServiceDep",
    "ContainerDep",
    "PageLimit",
    "PageOffset",
    "RecognitionServiceDep",
    "RegistrationImportServiceDep",
    "SessionServiceDep",
    "StudentServiceDep",
    "get_container_ws",
]
