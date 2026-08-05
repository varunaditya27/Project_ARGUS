from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Query, UploadFile, status

from app.api.deps import (
    AttendanceServiceDep,
    PageLimit,
    PageOffset,
    RecognitionServiceDep,
    StudentServiceDep,
)
from app.schemas.attendance import StudentAttendanceRecord
from app.schemas.common import DEFAULT_PAGE_SIZE, KeysetPage, OffsetPage
from app.schemas.recognition import EnrollmentResult
from app.schemas.student import StudentCreate, StudentRead, StudentTemplates

router = APIRouter(prefix="/students", tags=["students"])


@router.post("", response_model=StudentRead, status_code=status.HTTP_201_CREATED)
async def create_student(payload: StudentCreate, service: StudentServiceDep) -> StudentRead:
    return StudentRead.model_validate(await service.create(payload))


@router.get("", response_model=KeysetPage[StudentRead])
async def list_students(
    service: StudentServiceDep,
    class_id: uuid.UUID | None = Query(default=None),
    after: int | None = Query(
        default=None, description="Keyset cursor: return students with roll_no greater than this."
    ),
    limit: PageLimit = DEFAULT_PAGE_SIZE,
) -> KeysetPage[StudentRead]:
    students = await service.list(class_id=class_id, after_roll_no=after, limit=limit)
    items = [StudentRead.model_validate(s) for s in students]
    return KeysetPage(items=items, next_cursor=items[-1].roll_no if len(items) == limit else None)


@router.get("/{student_id}", response_model=StudentRead)
async def get_student(student_id: uuid.UUID, service: StudentServiceDep) -> StudentRead:
    return StudentRead.model_validate(await service.get(student_id))


@router.delete("/{student_id}", status_code=status.HTTP_200_OK)
async def delete_student(student_id: uuid.UUID, service: StudentServiceDep) -> dict[str, object]:
    removed = await service.delete(student_id)
    return {"student_id": str(student_id), "templates_removed": removed}


@router.post("/{student_id}/enroll", response_model=EnrollmentResult)
async def enroll_student(
    student_id: uuid.UUID,
    service: RecognitionServiceDep,
    image: UploadFile = File(description="Single-person unmasked JPEG/PNG photograph."),
) -> EnrollmentResult:
    """Create the unmasked template and its synthetic masked variants.

    Returns 503 until the SCRFD/ArcFace/MaskTheFace adapters are implemented.
    """
    return await service.enroll(student_id, await image.read())


@router.get("/{student_id}/templates", response_model=StudentTemplates)
async def list_templates(student_id: uuid.UUID, service: RecognitionServiceDep) -> StudentTemplates:
    return StudentTemplates(
        student_id=student_id, templates=await service.list_templates(student_id)
    )


@router.get("/{student_id}/attendance", response_model=OffsetPage[StudentAttendanceRecord])
async def student_attendance(
    student_id: uuid.UUID,
    students: StudentServiceDep,
    attendance: AttendanceServiceDep,
    limit: PageLimit = DEFAULT_PAGE_SIZE,
    offset: PageOffset = 0,
) -> OffsetPage[StudentAttendanceRecord]:
    await students.get(student_id)
    rows = await attendance.student_history(student_id, limit=limit, offset=offset)
    return OffsetPage(
        items=[
            StudentAttendanceRecord(
                session_id=class_session.session_id,
                subject=class_session.subject,
                faculty=class_session.faculty,
                date=class_session.date,
                start_time=class_session.start_time,
                end_time=class_session.end_time,
                timestamp=record.timestamp,
                confidence=record.confidence,
                status=record.status,
            )
            for record, class_session in rows
        ],
        limit=limit,
        offset=offset,
    )
