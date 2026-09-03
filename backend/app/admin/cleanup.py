import asyncio

from app.agents.store import get_agno_db


def _purge(user_id: str) -> None:
    db = get_agno_db()
    sessions = db.get_sessions(user_id=user_id, include_runs=False, deserialize=True)
    session_ids = [str(session.session_id) for session in sessions]
    if session_ids:
        db.delete_sessions(session_ids, user_id=user_id)
    memories = db.get_user_memories(user_id=user_id, limit=10000, deserialize=True)
    memory_ids = [str(memory.memory_id) for memory in memories if memory.memory_id]
    if memory_ids:
        db.delete_user_memories(memory_ids, user_id=user_id)
    db.delete_user_learnings(user_id=user_id)


async def purge_agno_user(user_id: str) -> None:
    await asyncio.to_thread(_purge, user_id)
