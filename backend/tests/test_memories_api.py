from app.agents.store import get_agno_db
from tests.conftest import auth_header, new_user_id


async def test_memories_are_visible_only_to_their_owner(client):
    owner = new_user_id()
    other = new_user_id()
    get_agno_db().upsert_learning(
        id=f"user_memory_{owner}",
        learning_type="user_memory",
        user_id=str(owner),
        content={"user_id": str(owner), "memories": [{"id": "pref-1", "content": "Prefers concise answers"}]},
    )

    mine = await client.get("/api/v1/memories", headers=auth_header(owner))
    theirs = await client.get("/api/v1/memories", headers=auth_header(other))

    assert mine.json() == {"memories": [{"id": "pref-1", "content": "Prefers concise answers"}]}
    assert theirs.json() == {"memories": []}


async def test_student_can_delete_all_memories(client):
    user_id = new_user_id()
    get_agno_db().upsert_learning(
        id=f"user_memory_{user_id}",
        learning_type="user_memory",
        user_id=str(user_id),
        content={"user_id": str(user_id), "memories": [{"id": "pref-1", "content": "Use Turkish"}]},
    )

    deleted = await client.delete("/api/v1/memories", headers=auth_header(user_id))
    after = await client.get("/api/v1/memories", headers=auth_header(user_id))

    assert deleted.json() == {"memories": []}
    assert after.json() == {"memories": []}
