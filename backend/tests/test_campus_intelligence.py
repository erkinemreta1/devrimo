import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db.models import (
    CampusIngestionJob,
    CampusKnowledgeRecord,
    CampusSource,
    CampusSourceRevision,
    CourseOffering,
    CourseRule,
    KnowledgeEmbeddingSettings,
    Organization,
    StudentAcademicSnapshot,
    UserMailFact,
)
from app.db.session import SessionLocal
from app.knowledge.adapters import adapter_for
from app.knowledge.chunking import chunk_records, embedding_text, validate_chunk_config
from app.knowledge.fetcher import FetchPolicy, FetchRejected, fetch_document
from app.knowledge.ingestion import claim_job, process_job
from app.knowledge.retrieval import read_campus_page, search_knowledge
from app.knowledge.types import FetchedDocument, ParsedRecord
from app.planning.service import _prerequisite_met, upsert_academic_snapshot
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


def test_unknown_or_malformed_prerequisite_rules_fail_closed():
    assert _prerequisite_met({"faculty_approval": True}, {}, 3.0) == (
        False,
        "invalid or unsupported prerequisite rule",
    )
    assert _prerequisite_met({"all": "CENG111"}, {}, 3.0) == (False, "invalid prerequisite rule")
    assert _prerequisite_met({"min_cgpa": "not-a-number"}, {}, 3.0) == (False, "invalid prerequisite rule")


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

    debug_search = await client.get(
        "/api/v1/admin/knowledge/search?q=Add-Drop&limit=5",
        headers=auth_header(admin_id),
    )
    assert debug_search.status_code == 200, debug_search.text
    assert debug_search.json()["query"] == "Add-Drop"
    assert debug_search.json()["count"] == 1
    assert debug_search.json()["items"][0]["title"] == "Add-Drop Week"
    assert debug_search.json()["items"][0]["score"] > 0

    denied_search = await client.get(
        "/api/v1/admin/knowledge/search?q=Add-Drop",
        headers=auth_header(student_id),
    )
    assert denied_search.status_code == 403

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

    enabled = await client.patch(
        "/api/v1/profile",
        headers=auth_header(student_id),
        json={"mail_facts_enabled": True},
    )
    assert enabled.status_code == 200, enabled.text
    async with SessionLocal() as db:
        db.add(
            UserMailFact(
                user_id=student_id,
                external_id="mail-event-1",
                fact_type="event",
                title="Cinema club screening",
                summary="A structured event extracted while email facts were enabled.",
                sender_domain="metu.edu.tr",
                message_digest="a" * 64,
            )
        )
        await db.commit()
    with_mail = await client.get("/api/v1/student/updates", headers=auth_header(student_id))
    assert any(item["origin"] == "mail_fact" for item in with_mail.json()["items"])

    disabled = await client.patch(
        "/api/v1/profile",
        headers=auth_header(student_id),
        json={"mail_facts_enabled": False},
    )
    assert disabled.status_code == 200, disabled.text
    without_mail = await client.get("/api/v1/student/updates", headers=auth_header(student_id))
    assert all(item["origin"] != "mail_fact" for item in without_mail.json()["items"])

    bulk = await client.put(
        "/api/v1/admin/sources/bulk",
        headers=auth_header(admin_id),
        json={
            "source_ids": [source_id],
            "changes": {"authority": 85, "schedule_seconds": 7200, "language": "tr"},
        },
    )
    assert bulk.status_code == 200, bulk.text
    assert bulk.json()["updated"] == 1
    sources = await client.get("/api/v1/admin/sources", headers=auth_header(admin_id))
    assert sources.json()["items"][0]["authority"] == 85
    assert sources.json()["items"][0]["schedule_seconds"] == 7200

    missing_key = await client.put(
        "/api/v1/admin/embedding-settings",
        headers=auth_header(admin_id),
        json={
            "provider": "remote",
            "model": "remote-test",
            "base_url": "https://embedding.example/v1",
            "dimensions": 3,
            "batch_size": 2,
        },
    )
    assert missing_key.status_code == 422
    remote = await client.put(
        "/api/v1/admin/embedding-settings",
        headers=auth_header(admin_id),
        json={
            "provider": "remote",
            "model": "remote-test",
            "base_url": "https://embedding.example/v1",
            "dimensions": 3,
            "batch_size": 2,
            "api_key": "remote-secret-key",
        },
    )
    assert remote.status_code == 200, remote.text
    assert remote.json()["has_api_key"] is True
    assert "remote-secret-key" not in remote.text
    async with SessionLocal() as db:
        stored_remote = (await db.execute(select(KnowledgeEmbeddingSettings))).scalar_one()
        assert stored_remote.api_key_enc is not None
        assert b"remote-secret-key" not in stored_remote.api_key_enc

    local = await client.put(
        "/api/v1/admin/embedding-settings",
        headers=auth_header(admin_id),
        json={
            "provider": "local",
            "model": "local-test",
            "base_url": "http://embedding:11434/v1",
            "dimensions": 3,
            "batch_size": 2,
        },
    )
    assert local.status_code == 200, local.text
    assert local.json()["provider"] == "local"
    assert local.json()["has_api_key"] is False

    async def fake_embeddings(config, texts):
        assert config.provider == "local"
        return [[1.0, 0.5, 0.25] for _ in texts]

    monkeypatch.setattr("app.knowledge.embeddings._request_embeddings", fake_embeddings)
    reindex = await client.post("/api/v1/admin/embedding/reindex", headers=auth_header(admin_id))
    assert reindex.status_code == 202, reindex.text
    assert reindex.json()["queued"] == 1
    async with SessionLocal() as db:
        job = await claim_job(db, "embedding-worker")
        assert job is not None and job.kind == "reembed"
        assert await process_job(db, job) == 1
        record = (await db.execute(select(CampusKnowledgeRecord))).scalar_one()
        assert record.embedding is not None and len(record.embedding) == 1536
        assert record.embedding[:3] == [1.0, 0.5, 0.25]
        assert record.embedding_model == "local:local-test:3"
        stored_settings = (await db.execute(select(KnowledgeEmbeddingSettings))).scalar_one()
        assert stored_settings.api_key_enc is None  # Switching to local removes the remote secret.
    embedding_status = await client.get("/api/v1/admin/embedding-settings", headers=auth_header(admin_id))
    assert embedding_status.json()["current_model_records"] == 1
    jobs = await client.get("/api/v1/admin/ingestion-jobs", headers=auth_header(admin_id))
    embedding_job = jobs.json()["items"][0]
    assert embedding_job["kind"] == "reembed"
    assert embedding_job["phase"] == "completed"
    assert embedding_job["processed_records"] == 1
    assert embedding_job["embedded_records"] == 1

    # The admin API is the only place these instructions can be set, so a save
    # has to round-trip them: dropping them would silently retire every stored
    # vector, because the document prefix is part of the model label.
    prefixed = await client.put(
        "/api/v1/admin/embedding-settings",
        headers=auth_header(admin_id),
        json={
            "provider": "local",
            "model": "local-test",
            "base_url": "http://embedding:11434/v1",
            "dimensions": 3,
            "batch_size": 2,
            "query_prefix": "query: ",
            "document_prefix": "passage: ",
        },
    )
    assert prefixed.status_code == 200, prefixed.text
    assert prefixed.json()["query_prefix"] == "query: "
    assert prefixed.json()["document_prefix"] == "passage: "
    assert prefixed.json()["model_label"] != "local:local-test:3"
    assert prefixed.json()["current_model_records"] == 0
    reread = await client.get("/api/v1/admin/embedding-settings", headers=auth_header(admin_id))
    assert reread.json()["query_prefix"] == "query: "
    assert reread.json()["document_prefix"] == "passage: "


async def test_knowledge_retrieval_is_scoped_to_organization():
    first_org = Organization(id=uuid4(), slug="first-campus", name="First Campus")
    second_org = Organization(id=uuid4(), slug="second-campus", name="Second Campus")
    first_source = CampusSource(
        id=uuid4(),
        organization_id=first_org.id,
        name="First announcements",
        kind="curated",
        status="published",
        enabled=True,
    )
    second_source = CampusSource(
        id=uuid4(),
        organization_id=second_org.id,
        name="Second announcements",
        kind="curated",
        status="published",
        enabled=True,
    )
    first_revision = CampusSourceRevision(
        id=uuid4(),
        source_id=first_source.id,
        revision=1,
        status="published",
        config={},
        validation={"ok": True},
    )
    second_revision = CampusSourceRevision(
        id=uuid4(),
        source_id=second_source.id,
        revision=1,
        status="published",
        config={},
        validation={"ok": True},
    )
    shared_url = "https://example.edu/shared-announcement"
    first_record = CampusKnowledgeRecord(
        source_id=first_source.id,
        source_revision_id=first_revision.id,
        external_id="first-record",
        record_type="announcement",
        title="Tenant boundary first",
        content="Only the first organization may retrieve this tenant boundary record.",
        url=shared_url,
        content_hash="1" * 64,
    )
    second_record = CampusKnowledgeRecord(
        source_id=second_source.id,
        source_revision_id=second_revision.id,
        external_id="second-record",
        record_type="announcement",
        title="Tenant boundary second",
        content="Only the second organization may retrieve this tenant boundary record.",
        url=shared_url,
        content_hash="2" * 64,
    )
    async with SessionLocal() as db:
        db.add_all([first_org, second_org])
        await db.flush()
        db.add_all([first_source, second_source])
        await db.flush()
        db.add_all([first_revision, second_revision])
        await db.flush()
        db.add_all([first_record, second_record])
        await db.commit()

        first_results = await search_knowledge(db, "tenant boundary", organization_id=first_org.id)
        assert [item["source"] for item in first_results] == ["First announcements"]
        first_page = await read_campus_page(db, shared_url, organization_id=first_org.id)
        assert first_page is not None
        assert first_page["source"] == "First announcements"


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
            "course_code": "CENG213",
            "section": "1",
            "invite_url": "https://chat.whatsapp.com/test-invite",
            "eligibility": {},
        },
    )
    assert group.status_code == 201, group.text
    assert "term" not in group.json()
    listed_groups = await client.get("/api/v1/admin/course-groups", headers=auth_header(admin_id))
    assert "term" not in listed_groups.json()["items"][0]
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
    assert "phase" in CampusIngestionJob.__table__.columns
    assert "provider" in KnowledgeEmbeddingSettings.__table__.columns


# --- Off-turn SAIS context read ---------------------------------------------


class _FakeFunction:
    """One MCP function, shaped the way ``_payload`` unwraps a result."""

    def __init__(self, payload):
        self._payload = payload

    async def entrypoint(self):
        return self._payload


class _FakeToolkit:
    def __init__(self, functions):
        self.functions = functions


def _fake_campus_session(monkeypatch, functions):
    from contextlib import asynccontextmanager

    from app.planning import mcp_bridge

    @asynccontextmanager
    async def _session(user_id):
        yield [_FakeToolkit(functions)]

    monkeypatch.setattr(mcp_bridge, "_campus_session", _session)
    return mcp_bridge


async def test_sais_context_sync_stores_a_verified_but_unconfirmed_context(client, monkeypatch):
    """Turkish and English field names both map onto the typed context.

    The student still has to confirm it: a value read from SAIS is verified,
    which is not the same as agreed to.
    """
    from app.student import service as student_service

    user_id = new_user_id()
    bridge = _fake_campus_session(
        monkeypatch,
        {
            "sais_get_student_info": _FakeFunction(
                {
                    "bolum": "Computer Engineering",
                    "degree_level": "undergraduate",
                    "program": "571",
                    "yerleske": "Ankara",
                }
            )
        },
    )

    assert await bridge.sync_student_context_from_sais(user_id) is True

    async with SessionLocal() as db:
        context = await student_service.get_context(db, user_id)
    assert context.department == "Computer Engineering"
    assert context.degree_level == "undergraduate"
    assert context.program_code == "571"
    assert context.campus == "Ankara"
    assert context.source == "sais"
    assert context.verified_at is not None
    assert context.confirmed_at is None


async def test_sais_context_sync_reports_failure_when_the_tool_is_absent(client, monkeypatch):
    """A student without the SAIS tool enabled is a no-op, not an error."""
    user_id = new_user_id()
    bridge = _fake_campus_session(monkeypatch, {})

    assert await bridge.sync_student_context_from_sais(user_id) is False


async def test_sais_context_sync_never_reads_the_transcript(client, monkeypatch):
    """Scope guard: this path has no term, and the profile never shows grades."""
    called: list[str] = []

    class _Recording(_FakeFunction):
        def __init__(self, name, payload):
            super().__init__(payload)
            self._name = name

        async def entrypoint(self):
            called.append(self._name)
            return await super().entrypoint()

    user_id = new_user_id()
    bridge = _fake_campus_session(
        monkeypatch,
        {
            "sais_get_student_info": _Recording("sais_get_student_info", {"department": "Physics"}),
            "sais_get_transcript": _Recording("sais_get_transcript", {"cgpa": "3.9"}),
        },
    )

    assert await bridge.sync_student_context_from_sais(user_id) is True
    assert called == ["sais_get_student_info"]

    async with SessionLocal() as db:
        snapshots = (await db.execute(select(StudentAcademicSnapshot))).scalars().all()
    assert [s for s in snapshots if s.user_id == user_id] == []


async def test_batch_create_sources(client, monkeypatch):
    admin_id = new_user_id()
    monkeypatch.setattr(get_settings(), "admin_bootstrap_user_ids", str(admin_id))
    await client.get("/api/v1/profile", headers=auth_header(admin_id))

    payload = {
        "items": [
            {
                "name": "Cafeteria Lunch Menu",
                "kind": "drupal",
                "url": "https://kafeterya.metu.edu.tr",
                "language": "tr",
                "authority": 95,
                "schedule_seconds": 10800,
                "config": {
                    "item_selector": ".views-row, article",
                    "defaults": {"record_type": "announcement"},
                },
            },
            {
                "name": "METU Library Hours",
                "kind": "html_page",
                "url": "https://lib.metu.edu.tr/hours",
                "language": "en",
                "authority": 90,
                "schedule_seconds": 3600,
                "config": {
                    "content_selector": "main",
                    "defaults": {"record_type": "service_status"},
                },
            },
        ]
    }

    res = await client.post(
        "/api/v1/admin/sources/batch",
        headers=auth_header(admin_id),
        json=payload,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["count"] == 2
    assert len(body["items"]) == 2
    assert body["items"][0]["name"] == "Cafeteria Lunch Menu"
    assert body["items"][0]["revision"] == 1
    assert body["items"][0]["validation"]["ok"] is True
    assert body["items"][1]["name"] == "METU Library Hours"
    assert body["items"][1]["revision"] == 1
    assert body["items"][1]["validation"]["ok"] is True

    # Check that secrets are rejected in batch
    secret_payload = {
        "items": [
            {
                "name": "Bad Source",
                "kind": "json",
                "url": "https://api.metu.edu.tr/data",
                "config": {"api_key": "supersecret"},
            }
        ]
    }
    secret_res = await client.post(
        "/api/v1/admin/sources/batch",
        headers=auth_header(admin_id),
        json=secret_payload,
    )
    assert secret_res.status_code == 422

    # Check empty items validation
    empty_res = await client.post(
        "/api/v1/admin/sources/batch",
        headers=auth_header(admin_id),
        json={"items": []},
    )
    assert empty_res.status_code == 422


async def test_batch_publish_sources(client, monkeypatch) -> None:
    admin_id = new_user_id()
    monkeypatch.setattr(get_settings(), "admin_bootstrap_user_ids", str(admin_id))
    await client.get("/api/v1/profile", headers=auth_header(admin_id))

    # 1. Create a batch of 2 sources
    create_payload = {
        "items": [
            {
                "name": "Batch Publish Test 1",
                "kind": "curated",
                "authority": 80,
                "config": {"records": []},
            },
            {
                "name": "Batch Publish Test 2",
                "kind": "curated",
                "authority": 85,
                "config": {"records": []},
            },
        ]
    }
    create_res = await client.post(
        "/api/v1/admin/sources/batch",
        headers=auth_header(admin_id),
        json=create_payload,
    )
    assert create_res.status_code == 201
    created_items = create_res.json()["items"]
    source_ids = [item["id"] for item in created_items]

    # 2. Batch publish them
    publish_res = await client.post(
        "/api/v1/admin/sources/batch/publish",
        headers=auth_header(admin_id),
        json={"source_ids": source_ids},
    )
    assert publish_res.status_code == 200
    publish_data = publish_res.json()
    assert publish_data["count"] == 2
    assert len(publish_data["published"]) == 2
    assert len(publish_data["failed"]) == 0
    assert {p["source_id"] for p in publish_data["published"]} == set(source_ids)

    # 3. Verify each source is now published
    for sid in source_ids:
        source_res = await client.get(
            f"/api/v1/admin/sources/{sid}",
            headers=auth_header(admin_id),
        )
        assert source_res.status_code == 200
        data = source_res.json()
        assert data["status"] == "published"
        assert data["active_revision_id"] is not None

    # 4. Try publishing an invalid non-existent source ID
    non_existent_id = str(new_user_id())
    mixed_res = await client.post(
        "/api/v1/admin/sources/batch/publish",
        headers=auth_header(admin_id),
        json={"source_ids": [non_existent_id]},
    )
    assert mixed_res.status_code == 200
    mixed_data = mixed_res.json()
    assert mixed_data["count"] == 0
    assert len(mixed_data["failed"]) == 1
    assert mixed_data["failed"][0]["source_id"] == non_existent_id


async def _publish_turkish_records(contents: dict[str, str]) -> Organization:
    """Index one record per entry, keyed by external id, and return the org."""
    org = Organization(id=uuid4(), slug=f"tr-{uuid4().hex[:8]}", name="Turkish campus")
    source = CampusSource(
        id=uuid4(),
        organization_id=org.id,
        name="Turkish announcements",
        kind="curated",
        status="published",
        enabled=True,
    )
    revision = CampusSourceRevision(
        id=uuid4(), source_id=source.id, revision=1, status="published", config={}
    )
    records = [
        CampusKnowledgeRecord(
            source_id=source.id,
            source_revision_id=revision.id,
            external_id=external_id,
            record_type="announcement",
            title=content.split(".")[0],
            content=content,
            language="tr",
            content_hash=hashlib.sha256(external_id.encode()).hexdigest(),
        )
        for external_id, content in contents.items()
    ]
    async with SessionLocal() as db:
        db.add(org)
        await db.flush()
        db.add(source)
        await db.flush()
        db.add(revision)
        await db.flush()
        db.add_all(records)
        await db.commit()
    return org


async def test_turkish_search_matches_across_inflection_and_case():
    """Turkish is agglutinative and its dotted/dotless I breaks naive lowering.

    Both are the database's job here: Postgres' Turkish snowball configuration
    handles the case folding and most suffixes, and the trigram index covers the
    bare-noun forms Snowball over-stems.
    """
    org = await _publish_turkish_records(
        {
            "library": "Kütüphaneye yeni kitaplar geldi ve çalışma saatleri uzatıldı.",
            "permit": "İZİN BELGESİ başvuruları bu hafta içinde tamamlanmalıdır.",
            "dorm": "Yurtta kalan öğrenciler için yemekhane menüsü güncellendi.",
            "unrelated": "Mezuniyet töreni için akademik kıyafet dağıtımı yapılacaktır.",
        }
    )
    async with SessionLocal() as db:
        for query, expected in (
            ("kütüphane", "library"),
            ("kütüphanenin", "library"),
            ("izin", "permit"),
            ("yurt", "dorm"),
        ):
            results = await search_knowledge(db, query, organization_id=org.id, limit=4)
            assert results, f"{query!r} returned nothing"
            assert results[0]["document_id"] == expected, f"{query!r} -> {results[0]['document_id']}"


async def test_search_ranks_by_relevance_not_by_scan_order():
    """Every candidate must be reachable, regardless of insertion order."""
    org = await _publish_turkish_records(
        {f"filler-{index}": f"Genel duyuru metni numara {index}." for index in range(40)}
        | {"target": "Burs başvurusu sonuçları öğrenci işleri tarafından açıklandı."}
    )
    async with SessionLocal() as db:
        results = await search_knowledge(db, "burs başvurusu", organization_id=org.id, limit=5)
        assert results
        assert results[0]["document_id"] == "target"


async def test_authority_and_recency_cannot_outrank_a_better_match():
    """Priors settle near-ties; they must not reorder the actual ranking.

    Reciprocal Rank Fusion produces scores in a narrow band, so an additive
    authority/freshness bonus that is large relative to one rank step becomes
    the primary sort key. That regression put a maximum-authority, freshly
    published announcement above the only document that mentioned the query.
    """
    org = Organization(id=uuid4(), slug=f"rank-{uuid4().hex[:8]}", name="Ranking campus")
    loud = CampusSource(
        id=uuid4(),
        organization_id=org.id,
        name="Loud but irrelevant",
        kind="curated",
        status="published",
        enabled=True,
    )
    quiet = CampusSource(
        id=uuid4(),
        organization_id=org.id,
        name="Quiet but relevant",
        kind="curated",
        status="published",
        enabled=True,
    )
    revisions = [
        CampusSourceRevision(id=uuid4(), source_id=source.id, revision=1, status="published", config={})
        for source in (loud, quiet)
    ]
    records = [
        CampusKnowledgeRecord(
            source_id=loud.id,
            source_revision_id=revisions[0].id,
            external_id="loud",
            record_type="announcement",
            title="Genel duyurular",
            content="Mezuniyet töreni ve yemekhane menüsü hakkinda genel duyurular yayinlandi.",
            language="tr",
            authority=100,
            published_at=datetime.now(UTC),
            content_hash=hashlib.sha256(b"loud").hexdigest(),
        ),
        CampusKnowledgeRecord(
            source_id=quiet.id,
            source_revision_id=revisions[1].id,
            external_id="quiet",
            record_type="guide",
            title="Kablosuz ag rehberi",
            content="Meturoam kablosuz ag baglantisi icin kurulum adimlari ve sorun giderme.",
            language="tr",
            authority=10,
            published_at=datetime.now(UTC) - timedelta(days=400),
            content_hash=hashlib.sha256(b"quiet").hexdigest(),
        ),
    ]
    async with SessionLocal() as db:
        db.add(org)
        await db.flush()
        db.add_all([loud, quiet])
        await db.flush()
        db.add_all(revisions)
        await db.flush()
        db.add_all(records)
        await db.commit()

        results = await search_knowledge(db, "meturoam", organization_id=org.id, limit=5)
        assert results, "the relevant document was not returned at all"
        assert results[0]["document_id"] == "quiet", (
            f"authority {results[0]['authority']} outranked the matching document: "
            f"{[(r['document_id'], r['score']) for r in results]}"
        )


def test_long_pages_split_into_section_aware_chunks_that_rebuild_losslessly():
    """A page must be indexed as retrieval-sized pieces, not one vector.

    Each chunk owns its text exactly once so the document can be reconstructed
    verbatim, while the overlap that helps embedding quality is carried in
    metadata rather than duplicated into the stored content.
    """
    # Distinct sentences, so "appears exactly once" is a meaningful assertion.
    opening = [f"Kutuphane {index} numarali calisma salonu sabah acilir." for index in range(14)]
    exams = [f"Sinav doneminde {index} numarali salon gece yarisina kadar aciktir." for index in range(14)]
    body = "\n".join(["# Kutuphane", *opening, "## Sinav donemi", *exams])
    record = ParsedRecord(
        external_id="library-page",
        record_type="guide",
        title="Kutuphane rehberi",
        content=body,
        url="https://lib.metu.edu.tr/",
    )

    chunks = chunk_records([record], {"chunk_max_chars": 600})
    assert len(chunks) > 1, "a long page was left as a single record"
    assert all(len(chunk.content) <= 600 for chunk in chunks)

    # Every chunk is addressable, ordered, and knows how many siblings it has.
    assert [chunk.metadata["chunk_index"] for chunk in chunks] == list(range(len(chunks)))
    assert {chunk.metadata["chunk_count"] for chunk in chunks} == {len(chunks)}
    assert all(chunk.metadata["parent_external_id"] == "library-page" for chunk in chunks)
    assert len({chunk.external_id for chunk in chunks}) == len(chunks)
    assert {chunk.metadata.get("section") for chunk in chunks} & {"Kutuphane", "Kutuphane \u203a Sinav donemi"}

    # Stored content is partitioned, not overlapped: reconstruction is lossless
    # and no sentence is indexed twice.
    combined = "\n\n".join(chunk.content for chunk in chunks)
    for sentence in opening + exams:
        assert combined.count(sentence) == 1, f"{sentence!r} was not stored exactly once"

    # The overlap that helps embedding quality lives in metadata only.
    assert any(chunk.metadata.get("context_before") for chunk in chunks[1:])

    # The text handed to the embedder is enriched; the stored chunk is not.
    enriched = embedding_text(
        title=chunks[1].title,
        summary=None,
        content=chunks[1].content,
        metadata=chunks[1].metadata,
    )
    assert chunks[1].content in enriched
    assert "Document: Kutuphane rehberi" in enriched
    assert len(enriched) > len(chunks[1].content)


def test_chunking_rejects_out_of_range_configuration():
    """Admin-supplied chunk sizes are validated before a revision publishes."""
    assert validate_chunk_config({"chunk_max_chars": 1800}) == []
    assert validate_chunk_config({"chunk_max_chars": 10}), "an absurd size must be rejected"
    assert validate_chunk_config({"chunk_max_chars": "big"}), "a non-integer must be rejected"
