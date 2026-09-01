"""What sources exist, as rows first and seeds only as a starting point.

Follows :mod:`app.agents.runtime`: the database is the authority and the values
here are the fallback used to bootstrap an empty deployment. The one rule that
matters is that seeding never overwrites an edit — an admin who narrowed a
source, fixed a selector, or disabled a misbehaving site must not have that
undone by the next process restart.

Every seed below was checked against the live site rather than assumed, and
several of them are not the shape the site's name suggests:

* ``oidb.metu.edu.tr/tr/duyurular`` is a *single page* whose body holds the
  announcements inline, not a listing of nodes. Same for
  ``kim.metu.edu.tr/tr/etkinlikler``, which is where student-club events
  actually live, in plain text.
* ``yurtlar`` and ``spormd`` list at ``/{lang}/announcements`` but put their
  nodes under ``/tr/duyurular/…``, so the listing path and the item pattern
  have to be stated separately.
* ``faq.cc.metu.edu.tr`` is Drupal 7, Turkish only (``/en`` is a 404), and
  links all 405 of its articles from the single ``/tr`` index — so it is a
  listing with one page and a large item cap, not 405 configured pages.
* ``haber.metu.edu.tr`` is the only one of these with a real feed. Every METU
  Drupal site answers ``/rss.xml`` with an empty 200, which is why nothing else
  here uses the ``rss`` adapter.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.campus.sources.models import SourceSpec
from app.db.models import CampusSource
from app.logging import get_logger

logger = get_logger(__name__)

# Announcement node paths on the Drupal 10 "miys" theme. The listing alias and
# the node alias are different words on the same site, and both languages route
# to either, so this covers all four combinations.
_MIYS_ITEM_PATTERN = r"^/(tr|en)/(duyurular|announcements)/[^/]+$"
_MIYS_LISTINGS = {"tr": "/tr/announcements", "en": "/en/announcements"}


SEED_SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        slug="oidb-academic-calendar",
        name="Academic calendar (2026-2027)",
        adapter="html_table",
        kind="calendar",
        base_url="https://oidb.metu.edu.tr",
        config={
            "pages": {
                "tr": "/tr/odtu-ankara-ve-erdemli-kampusleri-2026-2027-akademik-takvim",
                "en": "/en/metu-ankara-and-erdemli-campuses-2026-2027-academic-year-calendar",
            },
            "region": {"tag": "main"},
            "table_index": 0,
            "date_column": 0,
            "text_column": 1,
            "academic_year": "2026-2027",
        },
        languages=("tr", "en"),
        # The calendar is republished per academic year at a new slug, so next
        # year is a new row rather than an edit — which keeps the old one
        # searchable for students asking about a term that already happened.
        audience_rules={
            "lisansüstü": "degree_level:graduate",
            "graduate": "degree_level:graduate",
            "lisans programlarına": "degree_level:undergraduate",
            "undergraduate": "degree_level:undergraduate",
            "temel i̇ngilizce": "audience:english_prep",
            "english preparatory": "audience:english_prep",
            "yks": "audience:new_students",
            "yaz okulu": "audience:summer_school",
            "summer school": "audience:summer_school",
        },
        refresh_seconds=86_400,
        max_items=400,
        priority=10,
    ),
    SourceSpec(
        slug="oidb-announcements",
        name="Registrar's Office announcements",
        adapter="page",
        kind="announcement",
        base_url="https://oidb.metu.edu.tr",
        # Verified: this is one page with the announcements in its body, not a
        # view of nodes. A drupal_listing here finds zero items and looks fine.
        config={"pages": {"tr": "/tr/duyurular", "en": "/en/announcements"}, "region": {"tag": "main"}},
        languages=("tr", "en"),
        refresh_seconds=10_800,
        priority=20,
    ),
    SourceSpec(
        slug="yurtlar-announcements",
        name="Dormitories announcements",
        adapter="drupal_listing",
        kind="announcement",
        base_url="https://yurtlar.metu.edu.tr",
        config={
            "listings": _MIYS_LISTINGS,
            "item_pattern": _MIYS_ITEM_PATTERN,
            "listing_region": {"tag": "main"},
            "node_region": {"tag": "main"},
        },
        languages=("tr", "en"),
        refresh_seconds=10_800,
        max_pages=2,
        priority=30,
    ),
    SourceSpec(
        slug="spormd-announcements",
        name="Sports Directorate announcements",
        adapter="drupal_listing",
        kind="announcement",
        base_url="https://spormd.metu.edu.tr",
        config={
            "listings": _MIYS_LISTINGS,
            "item_pattern": _MIYS_ITEM_PATTERN,
            "listing_region": {"tag": "main"},
            "node_region": {"tag": "main"},
        },
        languages=("tr", "en"),
        refresh_seconds=10_800,
        max_pages=2,
        priority=30,
    ),
    SourceSpec(
        slug="kim-events",
        name="Student club events",
        adapter="page",
        kind="announcement",
        base_url="https://kim.metu.edu.tr",
        # The Culture Office publishes club events as flat text on one page:
        # club name, date range, event title, venue. It is the only public,
        # non-social-media listing of what the 100+ clubs are actually running.
        config={"pages": {"tr": "/tr/etkinlikler", "en": "/en/events"}, "region": {"tag": "main"}},
        languages=("tr", "en"),
        refresh_seconds=10_800,
        priority=25,
    ),
    SourceSpec(
        slug="faq-cc",
        name="Computer Center FAQ",
        adapter="drupal_listing",
        kind="faq",
        base_url="https://faq.cc.metu.edu.tr",
        config={
            "listings": {"tr": "/tr"},
            "item_pattern": r"^/tr/sss/[^/]+$",
            "node_region": {"tag": "div", "attr": "id", "value": "content"},
            # robots.txt on this host asks for Crawl-delay: 10, and it is
            # honoured, so a full pass is slow by design. That is fine for a
            # weekly refresh of content that barely changes — but it needs a
            # budget larger than the default, or the run is cut off partway.
            "timeout_seconds": 7200,
        },
        # Turkish only: /en is a 404 on this host.
        languages=("tr",),
        refresh_seconds=604_800,
        max_pages=1,
        max_items=500,
        priority=40,
    ),
    SourceSpec(
        slug="haber-news",
        name="METU news",
        adapter="rss",
        kind="news",
        base_url="https://haber.metu.edu.tr",
        config={"feeds": {"tr": "/tr/feed/", "en": "/en/feed/"}},
        languages=("tr", "en"),
        refresh_seconds=10_800,
        max_items=40,
        priority=50,
    ),
    SourceSpec(
        slug="ceng-announcements",
        name="Computer Engineering announcements",
        adapter="drupal_listing",
        kind="announcement",
        base_url="https://ceng.metu.edu.tr",
        config={
            "listings": _MIYS_LISTINGS,
            "item_pattern": r"^/(tr|en)/announcements/[^/]+$",
            "listing_region": {"tag": "main"},
            "node_region": {"tag": "main"},
        },
        languages=("tr", "en"),
        # The worked example of a department source. Scoped so a CENG notice
        # does not surface for a Psychology student.
        departments=("CENG",),
        refresh_seconds=10_800,
        max_pages=2,
        priority=35,
    ),
    SourceSpec(
        slug="curated",
        name="Admin-curated entries",
        adapter="curated",
        kind="curated",
        base_url="https://devrimo.local/curated",
        config={},
        languages=("tr", "en"),
        # Cheap (one query, no network) and the entries are the ones students
        # notice fastest when stale, so this refreshes often.
        refresh_seconds=900,
        max_items=1000,
        priority=5,
    ),
)

SEEDS_BY_SLUG: dict[str, SourceSpec] = {seed.slug: seed for seed in SEED_SOURCES}


def spec_from_row(row: CampusSource) -> SourceSpec:
    """A database row as the pipeline's own value type."""
    return SourceSpec(
        slug=row.slug,
        name=row.name,
        adapter=row.adapter,
        kind=row.kind,
        base_url=row.base_url,
        config=dict(row.config or {}),
        encoding=row.encoding,
        languages=tuple(row.languages or ("tr",)),
        departments=tuple(row.departments or ()),
        degree_levels=tuple(row.degree_levels or ()),
        audience_rules=dict(row.audience_rules or {}),
        refresh_seconds=row.refresh_seconds,
        max_pages=row.max_pages,
        max_items=row.max_items,
        priority=row.priority,
        enabled=row.enabled,
    )


def row_kwargs(spec: SourceSpec) -> dict:
    """Seed values as column arguments, for inserting a missing source."""
    return {
        "slug": spec.slug,
        "name": spec.name,
        "adapter": spec.adapter,
        "kind": spec.kind,
        "base_url": spec.base_url,
        "config": dict(spec.config),
        "encoding": spec.encoding,
        "languages": list(spec.languages),
        "departments": list(spec.departments),
        "degree_levels": list(spec.degree_levels),
        "audience_rules": dict(spec.audience_rules),
        "refresh_seconds": spec.refresh_seconds,
        "max_pages": spec.max_pages,
        "max_items": spec.max_items,
        "priority": spec.priority,
        "enabled": spec.enabled,
    }


async def ensure_seeded(db: AsyncSession) -> int:
    """Insert seed sources that do not exist yet. Never touches existing rows.

    An admin who disabled ``faq-cc`` because it was hammering the site, or who
    corrected a listing path, keeps that decision across restarts. The seeds are
    a starting point, not a desired state to converge on.
    """
    existing = set((await db.execute(select(CampusSource.slug))).scalars().all())
    added = 0
    for seed in SEED_SOURCES:
        if seed.slug in existing:
            continue
        db.add(CampusSource(**row_kwargs(seed), revision=1))
        added += 1
    if added:
        await db.commit()
        logger.info("campus_sources_seeded", added=added)
    return added


async def load_specs(db: AsyncSession, *, enabled_only: bool = True) -> list[SourceSpec]:
    statement = select(CampusSource).order_by(CampusSource.priority, CampusSource.slug)
    if enabled_only:
        statement = statement.where(CampusSource.enabled.is_(True))
    return [spec_from_row(row) for row in (await db.execute(statement)).scalars().all()]


async def due_sources(db: AsyncSession, *, now: datetime | None = None, limit: int = 5) -> list[CampusSource]:
    """Enabled sources whose refresh interval has elapsed, most urgent first.

    ``next_run_at IS NULL`` sorts first so a newly added source runs on the very
    next tick rather than after its own refresh interval — an admin who just
    added a department wants to see whether it parses now, not in six hours.
    """
    now = now or datetime.now(UTC)
    statement = (
        select(CampusSource)
        .where(CampusSource.enabled.is_(True))
        .where((CampusSource.next_run_at.is_(None)) | (CampusSource.next_run_at <= now))
        .order_by(CampusSource.next_run_at.is_(None).desc(), CampusSource.priority, CampusSource.next_run_at)
        .limit(limit)
    )
    return list((await db.execute(statement)).scalars().all())


async def registry_revision(db: AsyncSession) -> int:
    """One number that changes whenever any source does.

    Used the way ``AgentRuntimeSettings.revision`` is: something holding a
    cached view of the registry compares against it instead of re-reading every
    row on each turn.
    """
    total = await db.scalar(select(func.coalesce(func.sum(CampusSource.revision), 0)))
    return int(total or 0)


async def get_by_id(db: AsyncSession, source_id: UUID) -> CampusSource | None:
    return await db.get(CampusSource, source_id)
