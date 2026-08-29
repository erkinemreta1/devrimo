from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import manager
from app.auth.dependencies import get_current_user
from app.auth.jwt import AuthenticatedUser
from app.db.models import ChatSession
from app.db.session import get_db
from app.hermes.client import HermesClient, HermesError
from app.logging import get_logger
from app.schemas import ChatMessageOut, ChatSessionDetailOut, ChatSessionListOut, ChatSessionOut

router = APIRouter()
logger = get_logger(__name__)


async def _get_owned_session(db: AsyncSession, user_id, session_id: str) -> ChatSession:
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
            ChatSession.deleted_at.is_(None),
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat session not found")
    return session


@router.get("", response_model=ChatSessionListOut)
async def list_sessions(
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatSessionListOut:
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user.id, ChatSession.deleted_at.is_(None))
        .order_by(ChatSession.updated_at.desc())
    )
    sessions = result.scalars().all()
    return ChatSessionListOut(sessions=[ChatSessionOut.from_model(s) for s in sessions])


@router.get("/{session_id}", response_model=ChatSessionDetailOut)
async def get_session(
    session_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatSessionDetailOut:
    session = await _get_owned_session(db, user.id, session_id)
    agent = await manager.get_agent_or_404(db, user.id)
    agent = await manager.ensure_running(db, agent)

    client = HermesClient(manager.endpoint_for(agent), manager.api_key_for(agent))
    try:
        raw_messages = await client.list_messages(session.hermes_session_id or session.id)
    except HermesError as exc:
        logger.error("list_messages_failed", user_id=str(user.id), status=exc.status_code, detail=exc.detail)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not load messages from the agent") from exc

    return ChatSessionDetailOut(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[ChatMessageOut(**m) for m in raw_messages],
    )


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    session = await _get_owned_session(db, user.id, session_id)

    agent = await manager.get_agent(db, user.id)
    if agent is not None:
        try:
            state = await manager.get_runtime().state(manager.spec_for(agent))
            if state.running:
                client = HermesClient(manager.endpoint_for(agent), manager.api_key_for(agent))
                await client.delete_session(session.hermes_session_id or session.id)
        except HermesError as exc:
            logger.warning("upstream_delete_failed", user_id=str(user.id), detail=exc.detail)

    session.deleted_at = datetime.now(UTC)
    await db.commit()
    return {"ok": True}
