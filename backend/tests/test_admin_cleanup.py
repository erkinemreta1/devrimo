from types import SimpleNamespace

from app.admin import cleanup


def test_purge_uses_agno_typed_session_and_memory_contracts(monkeypatch):
    calls: list[tuple[str, object]] = []

    class FakeAgnoDb:
        def get_sessions(self, **kwargs):
            calls.append(("get_sessions", kwargs))
            return [SimpleNamespace(session_id="session-1")]

        def delete_sessions(self, session_ids, **kwargs):
            calls.append(("delete_sessions", (session_ids, kwargs)))

        def get_user_memories(self, **kwargs):
            calls.append(("get_user_memories", kwargs))
            return [SimpleNamespace(memory_id="memory-1")]

        def delete_user_memories(self, memory_ids, **kwargs):
            calls.append(("delete_user_memories", (memory_ids, kwargs)))

        def delete_user_learnings(self, **kwargs):
            calls.append(("delete_user_learnings", kwargs))

    monkeypatch.setattr(cleanup, "get_agno_db", FakeAgnoDb)

    cleanup._purge("user-1")

    assert calls == [
        (
            "get_sessions",
            {"user_id": "user-1", "include_runs": False, "deserialize": True},
        ),
        ("delete_sessions", (["session-1"], {"user_id": "user-1"})),
        (
            "get_user_memories",
            {"user_id": "user-1", "limit": 10000, "deserialize": True},
        ),
        ("delete_user_memories", (["memory-1"], {"user_id": "user-1"})),
        ("delete_user_learnings", {"user_id": "user-1"}),
    ]
