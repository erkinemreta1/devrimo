"""The hot path: run one turn on the user's Agno agent and stream it back.

Under Hermes this route was a byte proxy — it forwarded an upstream SSE stream
untouched, which meant the only thing the frontend could ever render was text.
Now the broker owns the loop, so this module owns the wire format, and the
translation from Agno's run events to OpenAI ``chat.completion.chunk`` objects
happens here.

That translation is deliberately additive. ``frontend/lib/api/chat.ts`` reads
``choices[0].delta.content`` and ignores everything else, so tool activity is
emitted as ordinary chunks carrying an empty delta plus a ``devrimo`` extension
object. Today's frontend skips them; the assistant-ui tool components can be
wired to them without changing anything on this side.

Message history is *not* taken from the request body. The client re-sends the
whole thread on every turn, but Agno reloads it from the database against
``session_id`` — replaying the body as well would double every prior turn in
the model's context. Only the newest user message is passed in.
"""

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import manager
from app.auth.dependencies import get_current_user
from app.auth.jwt import AuthenticatedUser
from app.config import get_settings
from app.db.models import ChatSession
from app.db.session import SessionLocal, get_db
from app.logging import get_logger
from app.schemas import ChatCompletionsRequestIn

router = APIRouter()
logger = get_logger(__name__)

KEEPALIVE_SECONDS = 15


def _chunk(model: str, *, delta: dict | None = None, extension: dict | None = None, finish: str | None = None) -> bytes:
    payload: dict = {
        "id": f"chatcmpl-{uuid4().hex}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish}],
    }
    if extension is not None:
        # Namespaced so it can never be mistaken for an OpenAI field, and so a
        # client that doesn't know about it simply sees an empty delta.
        payload["devrimo"] = extension
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


def _tool_name(event) -> str | None:
    tool = getattr(event, "tool", None)
    if tool is None:
        return None
    return getattr(tool, "tool_name", None) or getattr(tool, "name", None)


async def _serialize_run(agno_agent, text: str, session_id: str, user_id: str, model: str) -> AsyncIterator[bytes]:
    """Agno run events -> OpenAI-compatible SSE."""
    from agno.run.agent import RunEvent

    stream = agno_agent.arun(
        input=text,
        session_id=session_id,
        user_id=user_id,
        stream=True,
        stream_events=True,
    )

    async for event in stream:
        name = getattr(event, "event", None)

        if name == RunEvent.run_content.value:
            content = getattr(event, "content", None)
            if isinstance(content, str) and content:
                yield _chunk(model, delta={"role": "assistant", "content": content})

        elif name == RunEvent.tool_call_started.value:
            yield _chunk(model, extension={"type": "tool_call_started", "tool": _tool_name(event)})

        elif name == RunEvent.tool_call_completed.value:
            yield _chunk(model, extension={"type": "tool_call_completed", "tool": _tool_name(event)})

        elif name == RunEvent.run_error.value:
            detail = getattr(event, "content", None) or "The agent could not complete this turn."
            logger.error("agent_run_error", user_id=user_id, detail=str(detail))
            yield _chunk(model, extension={"type": "error", "message": str(detail)}, finish="stop")
            return

    yield _chunk(model, delta={}, finish="stop")


async def _with_keepalive(source: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    """Interleave SSE comments so no proxy in the path times out a slow tool call.

    Uses a queue so ``asyncio.wait_for`` only ever cancels a ``queue.get()``,
    never the source generator — cancelling an async generator's ``__anext__``
    throws ``CancelledError`` into it and finalises it, silently killing the
    stream mid-tool-call.
    """
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def _drain() -> None:
        try:
            async for chunk in source:
                await queue.put(chunk)
        finally:
            await queue.put(None)  # sentinel

    task = asyncio.create_task(_drain())
    try:
        while True:
            try:
                chunk = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
            except TimeoutError:
                yield b": keep-alive\n\n"
                continue
            if chunk is None:
                return
            yield chunk
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


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
    session = ChatSession(id=session_id, user_id=user_id, agent_id=agent_id, agno_session_id=session_id)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.post("/completions")
async def chat_completions(
    body: ChatCompletionsRequestIn,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    agent = await manager.get_agent_or_404(db, user.id)
    resident = await manager.resident_for(db, agent)

    latest_user_message = next(
        (m.content for m in reversed(body.messages) if m.role == "user"),
        None,
    )
    if not latest_user_message:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No user message to respond to")

    lock_owner = str(uuid4())
    if not await manager.acquire_turn_lock(db, agent, lock_owner):
        raise HTTPException(status.HTTP_409_CONFLICT, "Agent is busy with another message")

    try:
        chat_session = await _get_or_create_chat_session(db, user.id, agent.id, body.session_id)
    except Exception:
        await manager.release_turn_lock(db, agent, lock_owner)
        raise

    model = get_settings().agent_model
    agno_agent = manager.agno_agent_for(resident)
    agno_session_id = chat_session.agno_session_id or chat_session.id
    chat_session_id = chat_session.id
    user_id = user.id

    async def stream() -> AsyncIterator[bytes]:
        try:
            source = _serialize_run(agno_agent, latest_user_message, agno_session_id, str(user_id), model)
            async for chunk in _with_keepalive(source):
                yield chunk
        except Exception as exc:  # never let a broken stream leave the lock held
            logger.error("chat_stream_failed", user_id=str(user_id), error=str(exc))
            yield _chunk(model, extension={"type": "error", "message": "Chat stream failed"}, finish="stop")
        finally:
            yield b"data: [DONE]\n\n"
            await _finalize_turn(user_id, chat_session_id, lock_owner, latest_user_message)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


async def _finalize_turn(user_id, chat_session_id: str, lock_owner: str, first_user_text: str) -> None:
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
                session_row.title = first_user_text[:80] or None
            await db.commit()
