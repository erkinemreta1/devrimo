from fastapi import APIRouter

from app.api.v1 import admin, agents, campus, chat, health, knowledge_admin, memories, profile, sessions, student

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(agents.router, prefix="/agents", tags=["agents"])
router.include_router(chat.router, prefix="/chat", tags=["chat"])
router.include_router(sessions.router, prefix="/chat/sessions", tags=["sessions"])
router.include_router(profile.router, prefix="/profile", tags=["profile"])
router.include_router(campus.router, prefix="/campus", tags=["campus"])
router.include_router(memories.router, prefix="/memories", tags=["memories"])
router.include_router(student.router, prefix="/student", tags=["student"])
router.include_router(admin.router, prefix="/admin", tags=["admin"])
router.include_router(knowledge_admin.router, prefix="/admin", tags=["knowledge-admin"])
