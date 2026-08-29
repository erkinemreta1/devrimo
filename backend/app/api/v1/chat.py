"""The hot path: proxy one turn of conversation into a user's Hermes
container and stream the response back untouched.

Session identity: the client (assistant-ui) mints its own thread id and
sends it as ``session_id``. We currently pass that id straight through as
Hermes's ``X-Hermes-Session-Id`` and record it verbatim in
``chat_sessions.hermes_session_id`` — the column exists separately so this
can be swapped for a create-then-adopt flow without a schema change, if
testing against a live container shows Hermes does not adopt an unseen id.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import manager
from app.auth.dependencies import get_current_user
from app.auth.jwt import AuthenticatedUser
from app.db.models import ChatSession
from app.db.session import SessionLocal, get_db
from app.hermes.client import HermesClient, HermesError
from app.logging import get_logger
from app.schemas import ChatCompletionsRequestIn

router = APIRouter()
logger = get_logger(__name__)

KEEPALIVE_SECONDS = 15


async def _get_or_create_chat_session(
    db: AsyncSession, user_id, agent_id, client_session_id: str | None
) -> ChatSession:
    if client_session_id:
        result = await db.execute(select(ChatSession).where(ChatSession.id == client_session_id))
        existing = result.scalar_one_or_none()
        if existing is not None:
            if existing.user_id != user_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat session not found")
            if existing.deleted_at is not None:
                existing.deleted_at = None
            return existing

    session_id = client_session_id or str(uuid4())
    session = ChatSession(id=session_id, user_id=user_id, agent_id=agent_id, hermes_session_id=session_id)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def _with_keepalive(source: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    """Interleave SSE comments so no proxy in the path times out a slow tool call."""
    iterator = source.__aiter__()
    while True:
        try:
            chunk = await asyncio.wait_for(iterator.__anext__(), timeout=KEEPALIVE_SECONDS)
        except StopAsyncIteration:
            return
        except TimeoutError:
            yield b": keep-alive\n\n"
            continue
        yield chunk


@router.post("/completions")
async def chat_completions(
    body: ChatCompletionsRequestIn,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    agent = await manager.get_agent_or_404(db, user.id)
    agent = await manager.ensure_running(db, agent)

    lock_owner = str(uuid4())
    if not await manager.acquire_turn_lock(db, agent, lock_owner):
        raise HTTPException(status.HTTP_409_CONFLICT, "Agent is busy with another message")

    try:
        chat_session = await _get_or_create_chat_session(db, user.id, agent.id, body.session_id)
    except Exception:
        await manager.release_turn_lock(db, agent, lock_owner)
        raise

    client = HermesClient(manager.endpoint_for(agent), manager.api_key_for(agent))
    messages = [m.model_dump() for m in body.messages]
    hermes_session_id = chat_session.hermes_session_id or chat_session.id
    chat_session_id = chat_session.id
    user_id = user.id

    async def stream() -> AsyncIterator[bytes]:
        try:
            async for chunk in _with_keepalive(client.stream_chat_completions(messages, hermes_session_id)):
                yield chunk
        except HermesError as exc:
            logger.error("hermes_stream_failed", user_id=str(user_id), status=exc.status_code, detail=exc.detail)
            yield f"data: {json.dumps({'error': exc.detail})}\n\n".encode()
            yield b"data: [DONE]\n\n"
        except Exception as exc:  # never let a broken stream leave the lock held
            logger.error("chat_stream_failed", user_id=str(user_id), error=str(exc))
            yield f"data: {json.dumps({'error': 'Chat stream failed'})}\n\n".encode()
            yield b"data: [DONE]\n\n"
        finally:
            await _finalize_turn(user_id, chat_session_id, lock_owner, messages)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


async def _finalize_turn(user_id, chat_session_id: str, lock_owner: str, messages: list[dict]) -> None:
    async with SessionLocal() as db:
        agent = await manager.get_agent(db, user_id)
        if agent is not None:
            await manager.release_turn_lock(db, agent, lock_owner)
            await manager.touch_last_active(db, agent)

        result = await db.execute(select(ChatSession).where(ChatSession.id == chat_session_id))
        session_row = result.scalar_one_or_none()
        if session_row is not None:
            session_row.message_count += 1
            if not session_row.title:
                first_user = next((m["content"] for m in messages if m["role"] == "user"), "")
                session_row.title = (first_user[:80] or None)
            await db.commit()
