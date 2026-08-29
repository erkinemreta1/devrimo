from fastapi import APIRouter

from app.api.v1 import agents, chat, health, sessions

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(agents.router, prefix="/agents", tags=["agents"])
router.include_router(chat.router, prefix="/chat", tags=["chat"])
router.include_router(sessions.router, prefix="/chat/sessions", tags=["sessions"])
