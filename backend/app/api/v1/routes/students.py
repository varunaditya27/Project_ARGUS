from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, Query, UploadFile, status

from app.api.deps import (
    AttendanceServiceDep,
    PageLimit,
    PageOffset,
    RecognitionServiceDep,
    RegistrationImportServiceDep,
    StudentServiceDep,
)
from app.schemas.attendance import StudentAttendanceRecord
from app.schemas.common import DEFAULT_PAGE_SIZE, KeysetPage, OffsetPage
from app.schemas.recognition import EnrollmentResult
from app.schemas.registration import ImportReport
from app.schemas.student import StudentCreate, StudentRead, StudentTemplates

router = APIRouter(prefix="/students", tags=["students"])


@router.post("", response_model=StudentRead, status_code=status.HTTP_201_CREATED)
async def create_student(payload: StudentCreate, service: StudentServiceDep) -> StudentRead:
    return StudentRead.model_validate(await service.create(payload))


@router.post("/import", response_model=ImportReport)
async def import_students(
    service: RegistrationImportServiceDep,
    csv_file: UploadFile = File(
        description="UTF-8 CSV roster (a UTF-8 BOM is accepted). Header row required: "
        "student_name, roll_no, class_id, image_filename, image_url."
    ),
    images: UploadFile | None = File(
        default=None, description="ZIP archive holding the images named by image_filename."
    ),
    class_id: uuid.UUID | None = Form(
        default=None,
        description="Classroom for every row in the file. When supplied, the CSV class_id column "
        "becomes optional and is ignored.",
    ),
    dry_run: bool = Form(
        default=False,
        description="Validate and report without writing to PostgreSQL or uploading to R2.",
    ),
    # Both fields are also read from the query string: a `?dry_run=true` that was
    # silently ignored would perform the real import the caller was avoiding.
    class_id_param: uuid.UUID | None = Query(
        default=None, alias="class_id", include_in_schema=False
    ),
    dry_run_param: bool | None = Query(default=None, alias="dry_run", include_in_schema=False),
) -> ImportReport:
    """Register a whole roster from a CSV plus an archive of enrollment images.

    Valid rows are committed and invalid rows are skipped: the report names every
    skipped row, its roll number and the reason. Roll numbers that already exist
    are always errors, never updates.
    """
    return await service.import_students(
        csv_bytes=await csv_file.read(),
        # Passed as a file object rather than bytes: zipfile reads the archive
        # incrementally, so a large upload stays on disk instead of in memory.
        archive=images.file if images is not None else None,
        class_id=class_id or class_id_param,
        dry_run=dry_run or bool(dry_run_param),
    )


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
