"""FastAPI dependencies: thin accessors over the container built at startup."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query, Request
from starlette.websockets import WebSocket

from app.container import Container
from app.core.errors import DependencyNotConfiguredError
from app.schemas.common import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.services.attendance import AttendanceService
from app.services.classroom import ClassroomService
from app.services.offline import OfflineRecognitionService
from app.services.recognition import RecognitionService
from app.services.roster_import import RosterImportService
from app.services.session import SessionService
from app.services.student import StudentService
from app.storage.ports import ObjectStorage


def get_container(request: Request) -> Container:
    # The container built once at startup.
    return request.app.state.container


def get_container_ws(websocket: WebSocket) -> Container:
    # Same container, for the WebSocket route.
    return websocket.app.state.container


ContainerDep = Annotated[Container, Depends(get_container)]


def classrooms(container: ContainerDep) -> ClassroomService:
    return container.services.classrooms


def students(container: ContainerDep) -> StudentService:
    return container.services.students


def sessions(container: ContainerDep) -> SessionService:
    return container.services.sessions


def attendance(container: ContainerDep) -> AttendanceService:
    return container.services.attendance


def recognition(container: ContainerDep) -> RecognitionService:
    return container.services.recognition


def offline(container: ContainerDep) -> OfflineRecognitionService:
    return container.services.offline


def roster_import(container: ContainerDep) -> RosterImportService:
    return container.services.roster_import


def object_storage(container: ContainerDep) -> ObjectStorage:
    # Needs no database, so it is resolved from the container directly.
    if container.storage is None:
        raise DependencyNotConfiguredError(
            "Object storage is not configured, so images cannot be uploaded.",
            details={
                "component": "object_storage",
                "required": "ARGUS_OBJECT_STORAGE_MODE=local or r2",
            },
        )
    return container.storage


PageLimit = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE, description="Maximum items to return.")]
PageOffset = Annotated[int, Query(ge=0)]

ClassroomServiceDep = Annotated[ClassroomService, Depends(classrooms)]
StudentServiceDep = Annotated[StudentService, Depends(students)]
SessionServiceDep = Annotated[SessionService, Depends(sessions)]
AttendanceServiceDep = Annotated[AttendanceService, Depends(attendance)]
RecognitionServiceDep = Annotated[RecognitionService, Depends(recognition)]
OfflineServiceDep = Annotated[OfflineRecognitionService, Depends(offline)]
RosterImportServiceDep = Annotated[RosterImportService, Depends(roster_import)]
ObjectStorageDep = Annotated[ObjectStorage, Depends(object_storage)]

__all__ = [
    "DEFAULT_PAGE_SIZE",
    "AttendanceServiceDep",
    "ClassroomServiceDep",
    "ContainerDep",
    "ObjectStorageDep",
    "OfflineServiceDep",
    "PageLimit",
    "PageOffset",
    "RecognitionServiceDep",
    "RosterImportServiceDep",
    "SessionServiceDep",
    "StudentServiceDep",
    "get_container_ws",
]
