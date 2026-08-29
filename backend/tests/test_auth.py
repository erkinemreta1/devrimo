import time

import jwt as pyjwt

from tests.conftest import new_user_id


async def test_expired_token_is_401(client):
    token = pyjwt.encode(
        {"sub": str(new_user_id()), "aud": "authenticated", "exp": int(time.time()) - 10},
        "test-secret-not-for-production",
        algorithm="HS256",
    )
    response = await client.get("/api/v1/agents/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_wrong_signature_is_401(client):
    token = pyjwt.encode(
        {"sub": str(new_user_id()), "aud": "authenticated", "exp": int(time.time()) + 3600},
        "not-the-real-secret",
        algorithm="HS256",
    )
    response = await client.get("/api/v1/agents/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_garbage_bearer_is_401(client):
    response = await client.get("/api/v1/agents/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401
