"""Classroom routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import ClassroomServiceDep, PageLimit, PageOffset
from app.schemas.classroom import ClassroomCreate, ClassroomDetail, ClassroomRead
from app.schemas.common import DEFAULT_PAGE_SIZE, OffsetPage

router = APIRouter(prefix="/classrooms", tags=["classrooms"])


@router.post("", response_model=ClassroomRead, status_code=status.HTTP_201_CREATED)
async def create_classroom(payload: ClassroomCreate, service: ClassroomServiceDep) -> ClassroomRead:
    # Create a classroom.
    return ClassroomRead.model_validate(await service.create(payload))


@router.get("", response_model=OffsetPage[ClassroomRead])
async def list_classrooms(
    service: ClassroomServiceDep,
    department: str | None = Query(default=None),
    semester: int | None = Query(default=None, ge=1, le=12),
    limit: PageLimit = DEFAULT_PAGE_SIZE,
    offset: PageOffset = 0,
) -> OffsetPage[ClassroomRead]:
    # Offset page of classrooms, optionally filtered.
    classrooms = await service.list(
        department=department, semester=semester, limit=limit, offset=offset
    )
    return OffsetPage(
        items=[ClassroomRead.model_validate(c) for c in classrooms], limit=limit, offset=offset
    )


@router.get("/{class_id}", response_model=ClassroomDetail)
async def get_classroom(class_id: uuid.UUID, service: ClassroomServiceDep) -> ClassroomDetail:
    # One classroom plus the number of students actually assigned to it.
    classroom, roster_count = await service.get_with_roster_count(class_id)
    return ClassroomDetail(
        **ClassroomRead.model_validate(classroom).model_dump(), roster_count=roster_count
    )
