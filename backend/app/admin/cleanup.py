import asyncio

from app.agents.store import get_agno_db


def _purge(user_id: str) -> None:
    db = get_agno_db()
    sessions = db.get_sessions(user_id=user_id, include_runs=False)
    if isinstance(sessions, tuple):
        sessions = sessions[0]
    session_ids = [
        str(session.get("session_id") if isinstance(session, dict) else session.session_id)
        for session in sessions
    ]
    if session_ids:
        db.delete_sessions(session_ids, user_id=user_id)
    memories, _ = db.get_user_memory_stats(user_id=user_id, limit=10000)
    memory_ids = [str(memory.get("memory_id") or memory.get("id")) for memory in memories]
    memory_ids = [memory_id for memory_id in memory_ids if memory_id not in {"None", ""}]
    if memory_ids:
        db.delete_user_memories(memory_ids, user_id=user_id)
    db.delete_user_learnings(user_id=user_id)


async def purge_agno_user(user_id: str) -> None:
    await asyncio.to_thread(_purge, user_id)
