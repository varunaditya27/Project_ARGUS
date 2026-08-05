from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import AttendanceServiceDep, PageLimit, PageOffset, SessionServiceDep
from app.domain.enums import AttendanceStatus, SessionStatus
from app.schemas.attendance import AttendanceRecord, AttendanceSummary
from app.schemas.common import DEFAULT_PAGE_SIZE, KeysetPage, OffsetPage
from app.schemas.session import SessionCloseReport, SessionCreate, SessionRead

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(payload: SessionCreate, service: SessionServiceDep) -> SessionRead:
    """Open a lecture session. At most one ACTIVE session per classroom."""
    return SessionRead.model_validate(await service.create(payload))


@router.get("", response_model=OffsetPage[SessionRead])
async def list_sessions(
    service: SessionServiceDep,
    class_id: uuid.UUID | None = Query(default=None),
    session_status: SessionStatus | None = Query(default=None, alias="status"),
    date_from: dt.date | None = Query(default=None),
    date_to: dt.date | None = Query(default=None),
    limit: PageLimit = DEFAULT_PAGE_SIZE,
    offset: PageOffset = 0,
) -> OffsetPage[SessionRead]:
    sessions = await service.list(
        class_id=class_id,
        status=session_status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return OffsetPage(
        items=[SessionRead.model_validate(s) for s in sessions], limit=limit, offset=offset
    )


@router.get("/{session_id}", response_model=SessionRead)
async def get_session(session_id: uuid.UUID, service: SessionServiceDep) -> SessionRead:
    return SessionRead.model_validate(await service.get(session_id))


@router.post("/{session_id}/close", response_model=SessionCloseReport)
async def close_session(
    session_id: uuid.UUID, attendance: AttendanceServiceDep
) -> SessionCloseReport:
    """Finalise a session.

    Flushes whatever is still buffered, writes `Absent` for every roster member
    that was never recognised, and flips the status to CLOSED - one transaction,
    with the session row locked so a concurrent close cannot double-run it.
    """
    return await attendance.close_session(session_id)


@router.get("/{session_id}/attendance", response_model=KeysetPage[AttendanceRecord])
async def session_register(
    session_id: uuid.UUID,
    attendance: AttendanceServiceDep,
    attendance_status: AttendanceStatus | None = Query(default=None, alias="status"),
    after: int | None = Query(
        default=None, description="Keyset cursor: return rows with roll_no greater than this."
    ),
    limit: PageLimit = DEFAULT_PAGE_SIZE,
) -> KeysetPage[AttendanceRecord]:
    rows = await attendance.register(
        session_id, status=attendance_status, after_roll_no=after, limit=limit
    )
    items = [
        AttendanceRecord(
            attendance_id=record.attendance_id,
            student_id=record.student_id,
            student_name=student_name,
            roll_no=roll_no,
            timestamp=record.timestamp,
            confidence=record.confidence,
            status=record.status,
        )
        for record, student_name, roll_no in rows
    ]
    return KeysetPage(items=items, next_cursor=items[-1].roll_no if len(items) == limit else None)


@router.get("/{session_id}/attendance/summary", response_model=AttendanceSummary)
async def session_summary(
    session_id: uuid.UUID, attendance: AttendanceServiceDep
) -> AttendanceSummary:
    return await attendance.summary(session_id)
