from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db.models import (
    CampusIngestionJob,
    CampusKnowledgeRecord,
    CourseOffering,
    CourseRule,
    StudentAcademicSnapshot,
)
from app.db.session import SessionLocal
from app.knowledge.adapters import adapter_for
from app.knowledge.fetcher import FetchPolicy, FetchRejected, fetch_document
from app.knowledge.ingestion import claim_job, process_job
from app.knowledge.types import FetchedDocument
from app.planning.service import upsert_academic_snapshot
from tests.conftest import auth_header, new_user_id


def test_pure_adapters_normalize_curated_json_and_ical():
    curated = adapter_for("curated").parse(
        None,
        {
            "defaults": {"record_type": "service_status", "language": "en"},
            "records": [{"title": "Pool closed", "content": "Closed for maintenance"}],
        },
    )
    assert curated[0].record_type == "service_status"
    assert curated[0].language == "en"
    assert len(curated[0].external_id) == 64

    document = FetchedDocument(
        "https://example.edu/calendar.ics",
        b"BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:add-drop\nSUMMARY:Add-Drop Week\n"
        b"DTSTART:20261005T060000Z\nDTEND:20261009T140000Z\nEND:VEVENT\nEND:VCALENDAR",
        "text/calendar; charset=utf-8",
    )
    calendar = adapter_for("ical").parse(document, {})
    assert calendar[0].external_id == "add-drop"
    assert calendar[0].starts_at == datetime(2026, 10, 5, 6, tzinfo=UTC)


async def test_fetcher_rejects_private_network_destinations():
    with pytest.raises(FetchRejected, match="Private"):
        await fetch_document(
            "http://127.0.0.1/internal",
            FetchPolicy(allowed_hosts=frozenset({"127.0.0.1"}), respect_robots=False),
        )


async def test_source_publish_ingest_search_and_personalized_updates(client, monkeypatch):
    admin_id = new_user_id()
    student_id = new_user_id()
    monkeypatch.setattr(get_settings(), "admin_bootstrap_user_ids", str(admin_id))
    await client.get("/api/v1/profile", headers=auth_header(admin_id))
    starts_at = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    created = await client.post(
        "/api/v1/admin/sources",
        headers=auth_header(admin_id),
        json={
            "name": "Registrar calendar",
            "kind": "curated",
            "language": "en",
            "authority": 100,
            "audience": {"department": "CENG", "degree_level": "undergraduate"},
            "schedule_seconds": 3600,
            "config": {
                "defaults": {
                    "record_type": "event",
                    "department": "CENG",
                    "degree_level": "undergraduate",
                },
                "records": [
                    {
                        "external_id": "add-drop-2026-fall",
                        "title": "Add-Drop Week",
                        "content": "Add-Drop Week begins Monday.",
                        "starts_at": starts_at,
                        "url": "https://oidb.metu.edu.tr/en/academic-calendar",
                    }
                ],
            },
        },
    )
    assert created.status_code == 201, created.text
    source_id = created.json()["id"]
    detail = await client.get(f"/api/v1/admin/sources/{source_id}", headers=auth_header(admin_id))
    revision_id = detail.json()["revision_history"][0]["id"]
    published = await client.post(
        f"/api/v1/admin/sources/{source_id}/revisions/{revision_id}/publish",
        headers=auth_header(admin_id),
    )
    assert published.status_code == 200, published.text

    async with SessionLocal() as db:
        job = await claim_job(db, "test-worker")
        assert job is not None
        assert await process_job(db, job) == 1
        record = (await db.execute(select(CampusKnowledgeRecord))).scalar_one()
        assert record.embedding is None
        assert record.is_current is True

    context = await client.put(
        "/api/v1/student/context",
        headers=auth_header(student_id),
        json={"department": "CENG", "degree_level": "undergraduate", "campus": "Ankara"},
    )
    assert context.status_code == 200
    preference = await client.put(
        "/api/v1/student/preferences/interests",
        headers=auth_header(student_id),
        json={"value": {"items": ["Add-Drop"]}},
    )
    assert preference.status_code == 200
    updates = await client.get("/api/v1/student/updates?digest=true", headers=auth_header(student_id))
    assert updates.status_code == 200, updates.text
    assert updates.json()["items"][0]["title"] == "Add-Drop Week"
    assert updates.json()["personalized_by"]["degree_level"] == "undergraduate"


async def test_planner_owns_inputs_and_protected_group_checks_enrollment(client, monkeypatch):
    admin_id = new_user_id()
    student_id = new_user_id()
    monkeypatch.setattr(get_settings(), "admin_bootstrap_user_ids", str(admin_id))
    await client.get("/api/v1/profile", headers=auth_header(admin_id))
    term = "2026-2027-fall"
    catalog = await client.put(
        "/api/v1/admin/planning/catalog",
        headers=auth_header(admin_id),
        json={
            "reason": "Load verified test catalog data",
            "offerings": [
                {
                    "term": term,
                    "course_code": "CENG213",
                    "section": "1",
                    "title": "Data Structures",
                    "credits": 4,
                    "schedule": [{"day": "monday", "start": "09:00", "end": "10:50"}],
                    "source_url": "https://oibs2.metu.edu.tr/",
                },
                {
                    "term": term,
                    "course_code": "CENG223",
                    "section": "1",
                    "title": "Discrete Structures",
                    "credits": 3,
                    "schedule": [{"day": "tuesday", "start": "09:00", "end": "10:50"}],
                    "source_url": "https://oibs2.metu.edu.tr/",
                },
            ],
            "rules": [
                {
                    "course_code": "CENG213",
                    "prerequisites": {"course": "CENG111", "min_grade": "DD"},
                    "catalog_url": "https://catalog.metu.edu.tr/course.php?course_code=5710213",
                },
                {"course_code": "CENG223", "prerequisites": {}},
            ],
        },
    )
    assert catalog.status_code == 200, catalog.text
    async with SessionLocal() as db:
        await upsert_academic_snapshot(
            db,
            student_id,
            term,
            completed_courses=[{"course_code": "CENG111", "grade": "BB"}],
            enrolled_courses=[{"course_code": "CENG213", "section": "1"}],
            current_credits=60,
            current_grade_points=180,
        )

    plan = await client.post(
        "/api/v1/student/plan",
        headers=auth_header(student_id),
        json={"term": term, "required_courses": ["CENG213"], "max_credits": 7},
    )
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["maximum_semester_gpa"] == 4.0
    assert payload["projected_cumulative_gpa"] > payload["current_cumulative_gpa"]
    assert {item["course_code"] for item in payload["courses"]} == {"CENG213", "CENG223"}

    group = await client.post(
        "/api/v1/admin/course-groups",
        headers=auth_header(admin_id),
        json={
            "term": term,
            "course_code": "CENG213",
            "section": "1",
            "invite_url": "https://chat.whatsapp.com/test-invite",
            "eligibility": {},
        },
    )
    assert group.status_code == 201, group.text
    resolved = await client.post(
        "/api/v1/student/course-group",
        headers=auth_header(student_id),
        json={"term": term, "course_code": "CENG213", "section": "1"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["invite_url"] == "https://chat.whatsapp.com/test-invite"

    outsider = uuid4()
    denied = await client.post(
        "/api/v1/student/course-group",
        headers=auth_header(outsider),
        json={"term": term, "course_code": "CENG213", "section": "1"},
    )
    assert denied.status_code == 200
    assert denied.json()["status"] == "not_eligible"


async def test_private_records_are_not_embedding_candidates():
    assert "embedding" not in StudentAcademicSnapshot.__table__.columns
    assert "embedding" not in CourseOffering.__table__.columns
    assert "embedding" not in CourseRule.__table__.columns
    assert "embedding" in CampusKnowledgeRecord.__table__.columns
    assert "status" in CampusIngestionJob.__table__.columns
