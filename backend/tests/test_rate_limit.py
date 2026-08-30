from datetime import UTC, datetime

from sqlalchemy import select

from app.agents.rate_limit import TurnUsage, current_hour, record_token_usage
from app.config import get_settings
from app.db.models import UserTokenUsage
from app.db.session import SessionLocal
from tests.conftest import auth_header, new_user_id


async def test_usage_is_accumulated_in_one_hourly_bucket():
    user_id = new_user_id()
    async with SessionLocal() as db:
        await record_token_usage(db, user_id, 120)
        await record_token_usage(db, user_id, 80)
        rows = (await db.execute(select(UserTokenUsage).where(UserTokenUsage.user_id == user_id))).scalars().all()

    assert len(rows) == 1
    assert rows[0].total_tokens == 200
    assert rows[0].request_count == 2
    assert rows[0].bucket_start.replace(tzinfo=UTC) == current_hour(datetime.now(UTC))


async def test_chat_is_rejected_after_hourly_budget(client):
    user_id = new_user_id()
    headers = auth_header(user_id)
    await client.post("/api/v1/agents/provision", headers=headers)

    async with SessionLocal() as db:
        await record_token_usage(db, user_id, get_settings().user_token_limit_per_hour)

    response = await client.post(
        "/api/v1/chat/completions",
        headers=headers,
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


async def test_oversized_message_is_rejected_before_model_run(client):
    user_id = new_user_id()
    headers = auth_header(user_id)
    await client.post("/api/v1/agents/provision", headers=headers)

    response = await client.post(
        "/api/v1/chat/completions",
        headers=headers,
        json={
            "messages": [
                {"role": "user", "content": "x" * (get_settings().chat_max_input_characters + 1)}
            ]
        },
    )

    assert response.status_code == 413


def test_turn_usage_prefers_provider_metrics_and_has_failure_fallback():
    class Metrics:
        total_tokens = 321

    class Event:
        metrics = Metrics()

    usage = TurnUsage(input_characters=40)
    usage.observe_content("x" * 20)
    assert usage.billable_tokens == 15
    usage.observe_event(Event())
    assert usage.billable_tokens == 321
