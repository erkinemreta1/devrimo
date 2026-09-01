"""The admin surface for the campus knowledge layer.

The acceptance test for the whole design is
``test_a_non_conforming_department_is_added_by_configuration_alone``: adding
``ie.metu.edu.tr``, which shares almost nothing with the common METU site
shape, must be a form submission rather than a deploy.
"""

import pathlib

from sqlalchemy import select

from app.campus.sources import ingest
from app.campus.sources.fetch import FetchedPage
from app.config import get_settings
from app.db.models import AdminMembership, AdminRole, CampusCuratedEntry, CampusSource
from app.db.session import SessionLocal
from tests.conftest import auth_header, new_user_id

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "campus"


class CannedFetcher:
    """Serves saved pages. No test in this file opens a socket."""

    def __init__(self, pages: dict[str, bytes]) -> None:
        self.pages = pages
        self.requests_made = 0
        self.bytes_fetched = 0

    async def get(self, url: str, *, etag=None, last_modified=None) -> FetchedPage:
        from app.campus.sources.models import SourceError

        self.requests_made += 1
        body = self.pages.get(url)
        if body is None:
            raise SourceError("http_error", f"{url} returned HTTP 404")
        self.bytes_fetched += len(body)
        return FetchedPage(url=url, status=200, body=body, declared_charset="utf-8")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


async def grant(user_id, role: AdminRole) -> None:
    async with SessionLocal() as db:
        db.add(AdminMembership(user_id=user_id, role=role))
        await db.commit()


def source_body(**overrides) -> dict:
    body = {
        "slug": "psy-announcements",
        "name": "Psychology announcements",
        "adapter": "drupal_listing",
        "kind": "announcement",
        "base_url": "https://psy.metu.edu.tr",
        "config": {
            "listings": {"tr": "/tr/announcements"},
            "item_pattern": r"^/(tr|en)/announcements/[^/]+$",
        },
        "languages": ["tr"],
        "departments": ["psy"],
        "refresh_seconds": 10800,
        "reason": "Add the Psychology department",
    }
    body.update(overrides)
    return body


# --- Permissions ------------------------------------------------------------


async def test_a_plain_student_cannot_see_the_registry(client):
    response = await client.get("/api/v1/admin/sources", headers=auth_header(new_user_id()))
    assert response.status_code == 403


async def test_campus_admin_may_edit_sources_and_operator_may_not(client):
    campus_admin, operator = new_user_id(), new_user_id()
    await grant(campus_admin, AdminRole.campus_admin)
    await grant(operator, AdminRole.operator)

    # Curating campus content is the campus admin's job.
    created = await client.post("/api/v1/admin/sources", headers=auth_header(campus_admin), json=source_body())
    assert created.status_code == 201

    # An operator handles incidents: they can see the registry and force a
    # re-crawl, but not change what the corpus is built from.
    assert (await client.get("/api/v1/admin/sources", headers=auth_header(operator))).status_code == 200
    denied = await client.post("/api/v1/admin/sources", headers=auth_header(operator), json=source_body(slug="x-dept"))
    assert denied.status_code == 403


async def test_operator_can_force_a_run_but_not_a_reindex_without_the_permission(client, monkeypatch):
    operator = new_user_id()
    await grant(operator, AdminRole.operator)
    campus_admin = new_user_id()
    await grant(campus_admin, AdminRole.campus_admin)

    monkeypatch.setattr(ingest, "CampusFetcher", lambda *a, **k: CannedFetcher({}))
    listing = await client.get("/api/v1/admin/sources", headers=auth_header(operator))
    source_id = listing.json()["sources"][0]["id"]

    assert (
        await client.post(f"/api/v1/admin/sources/{source_id}/run", headers=auth_header(operator))
    ).status_code == 200
    # knowledge:manage is an operator permission; campus_admin does not have it.
    refused = await client.post(
        "/api/v1/admin/knowledge/reindex", headers=auth_header(campus_admin), json={"reason": "model change"}
    )
    assert refused.status_code == 403


# --- The configurability claim ---------------------------------------------


async def test_a_non_conforming_department_is_added_by_configuration_alone(client, monkeypatch):
    """``ie.metu.edu.tr`` is Drupal 7, singular ``/announcement/``, no ``<main>``.

    If making it work needed a code change, the registry would not be
    configurable in any meaningful sense. Everything that differs from the
    common shape is expressed in the submitted ``config``.
    """
    admin_id = new_user_id()
    monkeypatch.setattr(get_settings(), "admin_bootstrap_user_ids", str(admin_id))
    monkeypatch.setattr(
        ingest,
        "CampusFetcher",
        lambda *a, **k: CannedFetcher(
            {"https://ie.metu.edu.tr/en/tum-duyurular": FIXTURES.joinpath("ie_announcements_en.html").read_bytes()}
        ),
    )

    body = source_body(
        slug="ie-announcements",
        name="Industrial Engineering announcements",
        base_url="https://ie.metu.edu.tr",
        config={
            "listings": {"en": "/en/tum-duyurular"},
            "item_pattern": r"^/(tr|en)/announcement/[^/]+$",
            "fetch_nodes": False,
        },
        languages=["en"],
        departments=["IE"],
        max_items=200,
        reason="Industrial Engineering does not follow the common shape",
    )

    preview = await client.post(
        "/api/v1/admin/sources/preview", headers=auth_header(admin_id), json={**body, "limit": 5}
    )
    assert preview.status_code == 200
    assert preview.json()["ok"] is True
    assert preview.json()["items_seen"] > 100
    assert len(preview.json()["items"]) == 5

    created = await client.post("/api/v1/admin/sources", headers=auth_header(admin_id), json=body)
    assert created.status_code == 201
    assert created.json()["departments"] == ["IE"]


async def test_preview_reports_a_configuration_that_parses_nothing(client, monkeypatch):
    admin_id = new_user_id()
    monkeypatch.setattr(get_settings(), "admin_bootstrap_user_ids", str(admin_id))
    monkeypatch.setattr(
        ingest,
        "CampusFetcher",
        lambda *a, **k: CannedFetcher(
            {"https://ie.metu.edu.tr/en/tum-duyurular": FIXTURES.joinpath("ie_announcements_en.html").read_bytes()}
        ),
    )
    body = source_body(
        base_url="https://ie.metu.edu.tr",
        config={"listings": {"en": "/en/tum-duyurular"}, "item_pattern": r"^/never-matches/"},
        languages=["en"],
    )
    response = await client.post("/api/v1/admin/sources/preview", headers=auth_header(admin_id), json=body)
    assert response.json()["ok"] is False
    assert response.json()["error_code"] == "empty_result"


# --- CRUD and audit ---------------------------------------------------------


async def test_creating_editing_and_deleting_a_source_is_audited(client, monkeypatch):
    admin_id = new_user_id()
    monkeypatch.setattr(get_settings(), "admin_bootstrap_user_ids", str(admin_id))

    created = await client.post("/api/v1/admin/sources", headers=auth_header(admin_id), json=source_body())
    source_id = created.json()["id"]
    assert created.json()["revision"] == 1
    assert created.json()["departments"] == ["PSY"], "department codes are normalised upper-case"

    updated = await client.put(
        f"/api/v1/admin/sources/{source_id}",
        headers=auth_header(admin_id),
        json=source_body(name="Psychology (tr+en)", languages=["tr", "en"], reason="Add the English listing"),
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2
    # An edit schedules an immediate re-crawl: the admin just changed how this
    # site is parsed and wants to see the effect.
    assert updated.json()["next_run_at"] is None

    deleted = await client.request(
        "DELETE",
        f"/api/v1/admin/sources/{source_id}",
        headers=auth_header(admin_id),
        json={"reason": "Superseded by a combined source"},
    )
    assert deleted.status_code == 200

    audit = await client.get("/api/v1/admin/audit", headers=auth_header(admin_id))
    actions = [item["action"] for item in audit.json()["items"]]
    assert {"campus_source.create", "campus_source.update", "campus_source.delete"} <= set(actions)


async def test_duplicate_slugs_are_rejected(client, monkeypatch):
    admin_id = new_user_id()
    monkeypatch.setattr(get_settings(), "admin_bootstrap_user_ids", str(admin_id))
    await client.post("/api/v1/admin/sources", headers=auth_header(admin_id), json=source_body())
    again = await client.post("/api/v1/admin/sources", headers=auth_header(admin_id), json=source_body())
    assert again.status_code == 409


async def test_an_unknown_adapter_is_refused(client, monkeypatch):
    admin_id = new_user_id()
    monkeypatch.setattr(get_settings(), "admin_bootstrap_user_ids", str(admin_id))
    response = await client.post(
        "/api/v1/admin/sources", headers=auth_header(admin_id), json=source_body(adapter="scrapy")
    )
    assert response.status_code == 422


async def test_a_refresh_interval_below_the_floor_is_refused(client, monkeypatch):
    """Re-crawling faster than a minute is a denial of service from our IP."""
    admin_id = new_user_id()
    monkeypatch.setattr(get_settings(), "admin_bootstrap_user_ids", str(admin_id))
    response = await client.post(
        "/api/v1/admin/sources", headers=auth_header(admin_id), json=source_body(refresh_seconds=5)
    )
    assert response.status_code == 422


async def test_listing_seeds_the_registry_on_first_view(client, monkeypatch):
    admin_id = new_user_id()
    monkeypatch.setattr(get_settings(), "admin_bootstrap_user_ids", str(admin_id))
    response = await client.get("/api/v1/admin/sources", headers=auth_header(admin_id))
    assert response.status_code == 200
    slugs = {source["slug"] for source in response.json()["sources"]}
    assert {"oidb-academic-calendar", "yurtlar-announcements", "spormd-announcements", "curated"} <= slugs
    assert "drupal_listing" in response.json()["adapters"]
    assert response.json()["editable"] is True


# --- Curated entries --------------------------------------------------------


async def test_a_whatsapp_group_is_curated_and_its_key_normalised(client, monkeypatch):
    """The question this table exists for: no page anywhere lists these."""
    admin_id = new_user_id()
    monkeypatch.setattr(get_settings(), "admin_bootstrap_user_ids", str(admin_id))

    created = await client.post(
        "/api/v1/admin/curated",
        headers=auth_header(admin_id),
        json={
            "kind": "whatsapp_group",
            "entry_key": "ceng 315",
            "title": "CENG315 Algorithms WhatsApp group",
            "body": "Student-run. Read the pinned rules before posting.",
            "url": "https://chat.whatsapp.com/example",
            "departments": ["CENG"],
            "reason": "Requested by the CENG student council",
        },
    )
    assert created.status_code == 201
    # Students type course codes every way imaginable, so the key is normalised
    # on the way in rather than matched loosely on the way out.
    assert created.json()["entry_key"] == "CENG315"

    listed = await client.get("/api/v1/admin/curated", headers=auth_header(admin_id))
    assert len(listed.json()["entries"]) == 1

    async with SessionLocal() as db:
        rows = (await db.execute(select(CampusCuratedEntry))).scalars().all()
        assert rows[0].kind == "whatsapp_group"


async def test_a_curated_url_must_be_http(client, monkeypatch):
    admin_id = new_user_id()
    monkeypatch.setattr(get_settings(), "admin_bootstrap_user_ids", str(admin_id))
    response = await client.post(
        "/api/v1/admin/curated",
        headers=auth_header(admin_id),
        json={"kind": "note", "title": "x", "url": "javascript:alert(1)", "reason": "test"},
    )
    assert response.status_code == 422


# --- Grading policy ---------------------------------------------------------


async def test_the_grade_scale_is_editable_and_seeded_with_metus(client, monkeypatch):
    admin_id = new_user_id()
    monkeypatch.setattr(get_settings(), "admin_bootstrap_user_ids", str(admin_id))

    current = await client.get("/api/v1/admin/grade-policy", headers=auth_header(admin_id))
    assert current.status_code == 200
    assert current.json()["scale"]["AA"] == 4.0
    assert current.json()["weight_basis"] == "credit"

    updated = await client.put(
        "/api/v1/admin/grade-policy",
        headers=auth_header(admin_id),
        json={
            "scale": {"AA": 4.0, "BA": 3.5, "BB": 3.0, "FF": 0.0},
            "non_graded": ["W", "EX"],
            "passing_grades": ["AA", "BA", "BB"],
            "weight_basis": "ects",
            "retake_replaces": False,
            "max_credits_per_semester": 30,
            "reason": "Regulation change effective this academic year",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["weight_basis"] == "ects"
    assert updated.json()["retake_replaces"] is False

    audit = await client.get("/api/v1/admin/audit", headers=auth_header(admin_id))
    assert "grade_policy.update" in [item["action"] for item in audit.json()["items"]]


async def test_an_empty_or_implausible_grade_scale_is_refused(client, monkeypatch):
    admin_id = new_user_id()
    monkeypatch.setattr(get_settings(), "admin_bootstrap_user_ids", str(admin_id))
    for scale in ({}, {"AA": 400}):
        response = await client.put(
            "/api/v1/admin/grade-policy",
            headers=auth_header(admin_id),
            json={"scale": scale, "reason": "should not apply"},
        )
        assert response.status_code == 422


async def test_a_policy_change_rebuilds_resident_agents(client, monkeypatch):
    """Agents are constructed with the scale, so a stale one keeps planning wrong."""
    admin_id = new_user_id()
    monkeypatch.setattr(get_settings(), "admin_bootstrap_user_ids", str(admin_id))
    from app.agents.pool import get_pool

    closed: list[bool] = []

    async def record_close():
        closed.append(True)

    monkeypatch.setattr(get_pool(), "close_all", record_close)
    await client.put(
        "/api/v1/admin/grade-policy",
        headers=auth_header(admin_id),
        json={"scale": {"AA": 4.0}, "reason": "Correct the scale"},
    )
    assert closed == [True]


# --- Knowledge overview -----------------------------------------------------


async def test_knowledge_overview_reports_an_unconfigured_corpus_plainly(client, monkeypatch):
    """No embeddings is an ordinary state, not an error."""
    admin_id = new_user_id()
    monkeypatch.setattr(get_settings(), "admin_bootstrap_user_ids", str(admin_id))
    response = await client.get("/api/v1/admin/knowledge", headers=auth_header(admin_id))
    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert response.json()["documents_total"] == 0
    assert response.json()["reindex_required_after_model_change"] is True


async def test_source_runs_are_listed_after_a_manual_run(client, monkeypatch):
    admin_id = new_user_id()
    monkeypatch.setattr(get_settings(), "admin_bootstrap_user_ids", str(admin_id))
    monkeypatch.setattr(
        ingest,
        "CampusFetcher",
        lambda *a, **k: CannedFetcher(
            {
                "https://oidb.metu.edu.tr/tr/odtu-ankara-ve-erdemli-kampusleri-2026-2027-akademik-takvim": (
                    FIXTURES.joinpath("oidb_calendar_2026_2027.html").read_bytes()
                )
            }
        ),
    )
    async with SessionLocal() as db:
        from app.campus.sources.registry import ensure_seeded

        await ensure_seeded(db)
        row = await db.scalar(select(CampusSource).where(CampusSource.slug == "oidb-academic-calendar"))
        source_id = str(row.id)

    run = await client.post(f"/api/v1/admin/sources/{source_id}/run", headers=auth_header(admin_id))
    assert run.status_code == 200
    assert run.json()["items_seen"] == 153

    runs = await client.get(f"/api/v1/admin/sources/{source_id}/runs", headers=auth_header(admin_id))
    assert runs.json()["runs"][0]["items_seen"] == 153
