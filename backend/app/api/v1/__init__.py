from fastapi import APIRouter

from app.api.v1 import admin, admin_sources, agents, campus, chat, health, memories, profile, sessions

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(agents.router, prefix="/agents", tags=["agents"])
router.include_router(chat.router, prefix="/chat", tags=["chat"])
router.include_router(sessions.router, prefix="/chat/sessions", tags=["sessions"])
router.include_router(profile.router, prefix="/profile", tags=["profile"])
router.include_router(campus.router, prefix="/campus", tags=["campus"])
router.include_router(memories.router, prefix="/memories", tags=["memories"])
router.include_router(admin.router, prefix="/admin", tags=["admin"])
# Same prefix, separate module: the campus knowledge surface is a large enough
# body of routes that folding it into admin.py would make that file the place
# nobody wants to open.
router.include_router(admin_sources.router, prefix="/admin", tags=["admin", "campus-knowledge"])
