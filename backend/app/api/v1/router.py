from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import classrooms, recognition, sessions, students, system

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(classrooms.router)
api_router.include_router(students.router)
api_router.include_router(sessions.router)
api_router.include_router(recognition.router)
