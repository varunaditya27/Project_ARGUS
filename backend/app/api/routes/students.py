"""Student routes: roster CRUD, bulk import, enrollment and attendance history."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, Query, UploadFile, status

from app.api.deps import (
    AttendanceServiceDep,
    ObjectStorageDep,
    PageLimit,
    PageOffset,
    RecognitionServiceDep,
    RosterImportServiceDep,
    StudentServiceDep,
)
from app.schemas.attendance import StudentAttendanceRecord
from app.schemas.common import DEFAULT_PAGE_SIZE, KeysetPage, OffsetPage
from app.schemas.recognition import EnrollmentResult
from app.schemas.registration import ImportReport
from app.schemas.student import StudentCreate, StudentRead, StudentTemplates, UploadedImage

router = APIRouter(prefix="/students", tags=["students"])


@router.post("", response_model=StudentRead, status_code=status.HTTP_201_CREATED)
async def create_student(payload: StudentCreate, service: StudentServiceDep) -> StudentRead:
    # Register one student whose image is already hosted.
    return StudentRead.model_validate(await service.create(payload))


@router.post("/import", response_model=ImportReport)
async def import_students(
    service: RosterImportServiceDep,
    csv_file: UploadFile = File(
        description="UTF-8 CSV roster. Header required: "
        "student_name, roll_no, class_id, image_filename, image_url."
    ),
    images: UploadFile | None = File(
        default=None, description="ZIP archive holding the images named by image_filename."
    ),
    class_id: uuid.UUID | None = Form(
        default=None,
        description="Classroom for every row; the CSV class_id column is then ignored.",
    ),
    dry_run: bool = Form(default=False, description="Validate only; no writes and no uploads."),
) -> ImportReport:
    """Register a whole roster from a CSV plus an archive of enrollment images.

    Valid rows are committed and invalid rows are skipped: the report names every
    skipped row, its roll number and the reason.
    """
    return await service.import_students(
        csv_bytes=await csv_file.read(),
        # The file object, not bytes: zipfile reads the archive incrementally so
        # a large upload stays on disk instead of in memory.
        archive=images.file if images is not None else None,
        class_id=class_id,
        dry_run=dry_run,
    )


@router.post("/image", response_model=UploadedImage)
async def upload_enrollment_image(
    storage: ObjectStorageDep,
    image: UploadFile = File(description="Photograph to store for a student about to be created."),
) -> UploadedImage:
    # Park an image in object storage and hand back the URL POST /students needs.
    stored = await storage.put_image(
        await image.read(), namespace="uploads", filename=image.filename
    )
    return UploadedImage(key=stored.key, url=stored.url)


@router.get("", response_model=KeysetPage[StudentRead])
async def list_students(
    service: StudentServiceDep,
    class_id: uuid.UUID | None = Query(default=None),
    after: int | None = Query(default=None, description="Return students after this roll_no."),
    limit: PageLimit = DEFAULT_PAGE_SIZE,
) -> KeysetPage[StudentRead]:
    # Keyset page of the roster, ordered by roll number.
    students = await service.list(class_id=class_id, after_roll_no=after, limit=limit)
    items = [StudentRead.model_validate(s) for s in students]
    return KeysetPage(items=items, next_cursor=items[-1].roll_no if len(items) == limit else None)


@router.get("/{student_id}", response_model=StudentRead)
async def get_student(student_id: uuid.UUID, service: StudentServiceDep) -> StudentRead:
    # One student.
    return StudentRead.model_validate(await service.get(student_id))


@router.delete("/{student_id}")
async def delete_student(student_id: uuid.UUID, service: StudentServiceDep) -> dict[str, object]:
    # Remove the student, their templates and their attendance rows.
    removed = await service.delete(student_id)
    return {"student_id": str(student_id), "templates_removed": removed}


@router.post("/{student_id}/enroll", response_model=EnrollmentResult)
async def enroll_student(
    student_id: uuid.UUID,
    service: RecognitionServiceDep,
    image: UploadFile = File(description="Single-person unmasked JPEG/PNG photograph."),
) -> EnrollmentResult:
    # Store the unmasked template and its synthetic masked variants.
    return await service.enroll(student_id, await image.read())


@router.get("/{student_id}/templates", response_model=StudentTemplates)
async def list_templates(student_id: uuid.UUID, service: RecognitionServiceDep) -> StudentTemplates:
    # Which mask variants are enrolled for this student.
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
    # One student's attendance across sessions, newest first.
    await students.get(student_id)
    rows = await attendance.student_history(student_id, limit=limit, offset=offset)
    return OffsetPage(
        items=[
            StudentAttendanceRecord(
                session_id=class_session.session_id,
                subject=class_session.subject,
                date=class_session.date,
                timestamp=record.timestamp,
                confidence=record.confidence,
                status=record.status,
            )
            for record, class_session in rows
        ],
        limit=limit,
        offset=offset,
    )
