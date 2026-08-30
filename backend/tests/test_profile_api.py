"""Onboarding progress: the state the wizard reads on load and writes per step."""

from tests.conftest import auth_header, new_user_id


async def test_profile_is_created_on_first_read(client):
    user_id = new_user_id()
    response = await client.get("/api/v1/profile", headers=auth_header(user_id))

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(user_id)
    assert body["onboarding_completed"] is False
    assert body["onboarding_step"] is None


async def test_patch_records_one_step_at_a_time(client):
    headers = auth_header(new_user_id())
    await client.patch("/api/v1/profile", headers=headers, json={"display_name": "Deniz"})
    response = await client.patch("/api/v1/profile", headers=headers, json={"onboarding_step": "tools"})

    body = response.json()
    # The later PATCH must not blank the earlier step's answer.
    assert body["display_name"] == "Deniz"
    assert body["onboarding_step"] == "tools"


async def test_completing_onboarding_stamps_a_time(client):
    headers = auth_header(new_user_id())
    response = await client.patch("/api/v1/profile", headers=headers, json={"onboarding_completed": True})

    body = response.json()
    assert body["onboarding_completed"] is True
    assert body["onboarding_completed_at"] is not None


async def test_recompleting_keeps_the_original_timestamp(client):
    headers = auth_header(new_user_id())
    first = await client.patch("/api/v1/profile", headers=headers, json={"onboarding_completed": True})
    second = await client.patch("/api/v1/profile", headers=headers, json={"onboarding_completed": True})

    assert first.json()["onboarding_completed_at"] == second.json()["onboarding_completed_at"]


async def test_onboarding_can_be_reopened(client):
    headers = auth_header(new_user_id())
    await client.patch("/api/v1/profile", headers=headers, json={"onboarding_completed": True})
    response = await client.patch("/api/v1/profile", headers=headers, json={"onboarding_completed": False})

    assert response.json()["onboarding_completed"] is False


async def test_unknown_locale_falls_back_rather_than_erroring(client):
    headers = auth_header(new_user_id())
    response = await client.patch("/api/v1/profile", headers=headers, json={"locale": "de"})
    assert response.json()["locale"] == "tr"


async def test_profiles_are_isolated_per_user(client):
    first, second = new_user_id(), new_user_id()
    await client.patch("/api/v1/profile", headers=auth_header(first), json={"display_name": "Deniz"})

    response = await client.get("/api/v1/profile", headers=auth_header(second))
    assert response.json()["display_name"] is None
