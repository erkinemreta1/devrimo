"""The source registry and the ingest pipeline, without a network.

The seeding tests encode the rule that makes an admin-editable registry safe to
restart: seeds bootstrap an empty deployment and never converge an existing one
back to defaults. An admin who disabled a source because it was hammering a
university web team must find it still disabled tomorrow.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.campus.sources import ingest
from app.campus.sources.fetch import FetchedPage
from app.campus.sources.models import SourceSpec
from app.campus.sources.registry import (
    SEED_SOURCES,
    due_sources,
    ensure_seeded,
    load_specs,
    registry_revision,
    row_kwargs,
    spec_from_row,
)
from app.db.models import CampusCuratedEntry, CampusSource, CampusSourceRun
from app.db.session import SessionLocal


class FakeFetcher:
    """Answers from a dictionary of URL to bytes. Never opens a socket."""

    def __init__(self, pages: dict[str, bytes]) -> None:
        self.pages = pages
        self.requested: list[str] = []
        self.requests_made = 0
        self.bytes_fetched = 0

    async def get(self, url: str, *, etag=None, last_modified=None) -> FetchedPage:
        self.requested.append(url)
        self.requests_made += 1
        body = self.pages.get(url)
        if body is None:
            from app.campus.sources.models import SourceError

            raise SourceError("http_error", f"{url} returned HTTP 404")
        self.bytes_fetched += len(body)
        return FetchedPage(url=url, status=200, body=body, declared_charset="utf-8")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


# --- Seeding ----------------------------------------------------------------


async def test_seeding_creates_every_seed_once():
    async with SessionLocal() as db:
        added = await ensure_seeded(db)
        assert added == len(SEED_SOURCES)
        assert await ensure_seeded(db) == 0
        rows = (await db.execute(select(CampusSource))).scalars().all()
        assert {row.slug for row in rows} == {seed.slug for seed in SEED_SOURCES}


async def test_seeding_never_overwrites_an_admin_edit():
    async with SessionLocal() as db:
        await ensure_seeded(db)
        row = await db.scalar(select(CampusSource).where(CampusSource.slug == "faq-cc"))
        row.enabled = False
        row.refresh_seconds = 999_999
        row.name = "Disabled: too slow"
        await db.commit()

        await ensure_seeded(db)

        row = await db.scalar(select(CampusSource).where(CampusSource.slug == "faq-cc"))
        assert row.enabled is False
        assert row.refresh_seconds == 999_999
        assert row.name == "Disabled: too slow"


async def test_seeds_round_trip_through_a_row_unchanged():
    async with SessionLocal() as db:
        await ensure_seeded(db)
        for seed in SEED_SOURCES:
            row = await db.scalar(select(CampusSource).where(CampusSource.slug == seed.slug))
            assert spec_from_row(row) == seed


def test_every_seed_names_a_real_adapter():
    from app.campus.sources.adapters import ADAPTERS

    for seed in SEED_SOURCES:
        assert seed.adapter in ADAPTERS, f"{seed.slug} names an adapter that does not exist"


def test_no_seed_uses_rss_against_a_drupal_site():
    """Every METU Drupal host answers /rss.xml with an empty 200.

    A seed pointing the rss adapter at one would ingest nothing forever, so
    this guards the trap rather than trusting whoever adds the next seed.
    """
    drupal_hosts = ("oidb", "yurtlar", "spormd", "kim", "ceng", "faq.cc")
    for seed in SEED_SOURCES:
        if seed.adapter == "rss":
            assert not any(host in seed.base_url for host in drupal_hosts), seed.slug


def test_row_kwargs_covers_every_column_the_spec_carries():
    kwargs = row_kwargs(SEED_SOURCES[0])
    assert set(kwargs) >= {"slug", "adapter", "kind", "base_url", "config", "languages", "refresh_seconds"}


# --- Scheduling -------------------------------------------------------------


async def test_a_new_source_runs_on_the_next_tick():
    """``next_run_at IS NULL`` sorts first, so an admin sees it parse now."""
    async with SessionLocal() as db:
        now = datetime.now(UTC)
        db.add(CampusSource(**row_kwargs(SEED_SOURCES[0]), revision=1, next_run_at=now - timedelta(hours=1)))
        fresh = SEED_SOURCES[1]
        db.add(CampusSource(**row_kwargs(fresh), revision=1, next_run_at=None))
        await db.commit()

        due = await due_sources(db, now=now)
        assert due[0].slug == fresh.slug


async def test_sources_not_yet_due_and_disabled_ones_are_skipped():
    async with SessionLocal() as db:
        now = datetime.now(UTC)
        db.add(CampusSource(**{**row_kwargs(SEED_SOURCES[0]), "enabled": False}, revision=1, next_run_at=None))
        db.add(CampusSource(**row_kwargs(SEED_SOURCES[1]), revision=1, next_run_at=now + timedelta(hours=1)))
        await db.commit()
        assert await due_sources(db, now=now) == []


async def test_registry_revision_moves_when_any_source_changes():
    async with SessionLocal() as db:
        await ensure_seeded(db)
        before = await registry_revision(db)
        row = await db.scalar(select(CampusSource).where(CampusSource.slug == "spormd-announcements"))
        row.revision += 1
        await db.commit()
        assert await registry_revision(db) > before


async def test_load_specs_returns_only_enabled_by_default():
    async with SessionLocal() as db:
        await ensure_seeded(db)
        row = await db.scalar(select(CampusSource).where(CampusSource.slug == "haber-news"))
        row.enabled = False
        await db.commit()
        enabled = await load_specs(db)
        assert "haber-news" not in {spec.slug for spec in enabled}
        assert "haber-news" in {spec.slug for spec in await load_specs(db, enabled_only=False)}


# --- Ingest -----------------------------------------------------------------


LISTING = b"""<html><body><main>
  <a href="/tr/duyurular/a">Duyuru A</a>
  <a href="/tr/duyurular/a">01/09/2026</a>
  <a href="/tr/duyurular/b">Duyuru B</a>
</main></body></html>"""
NODE_A = (
    b'<html><body><main><h1>Duyuru A</h1>'
    b'<time datetime="2026-09-01T10:00:00+03:00"></time><p>Govde A</p></main></body></html>'
)
NODE_B = b"<html><body><main><h1>Duyuru B</h1><p>Govde B</p></main></body></html>"

SPEC = SourceSpec(
    slug="test-dept",
    name="Test department",
    adapter="drupal_listing",
    kind="announcement",
    base_url="https://ceng.metu.edu.tr",
    config={
        "listings": {"tr": "/tr/announcements"},
        "item_pattern": r"^/tr/duyurular/[^/]+$",
        "listing_region": {"tag": "main"},
        "node_region": {"tag": "main"},
    },
    languages=("tr",),
    max_pages=1,
)

PAGES = {
    "https://ceng.metu.edu.tr/tr/announcements": LISTING,
    "https://ceng.metu.edu.tr/tr/duyurular/a": NODE_A,
    "https://ceng.metu.edu.tr/tr/duyurular/b": NODE_B,
}


@pytest.fixture
def fake_fetcher(monkeypatch):
    fetcher = FakeFetcher(PAGES)
    monkeypatch.setattr(ingest, "CampusFetcher", lambda *args, **kwargs: fetcher)
    return fetcher


async def test_collect_walks_the_listing_and_then_the_nodes(fake_fetcher):
    items, stats = await ingest.collect_items(SPEC)
    assert [item.title for item in items] == ["Duyuru A", "Duyuru B"]
    assert items[0].published_at.year == 2026
    assert stats.items_seen == 2
    assert stats.requests_made == 3


async def test_max_items_counts_distinct_items_not_double(fake_fetcher):
    """The cap is the number of items, in every language combined.

    Counting an accepted item once per language would silently halve a
    bilingual source's cap, which looks like the site having fewer
    announcements than it does.
    """
    capped = SourceSpec(**{**SPEC.__dict__, "max_items": 1})
    items, _ = await ingest.collect_items(capped)
    assert len(items) == 1


async def test_a_missing_translation_does_not_lose_the_other_language(monkeypatch):
    """METU's bilingual sites are not reliably bilingual."""
    monkeypatch.setattr(ingest, "CampusFetcher", lambda *a, **k: FakeFetcher(PAGES))
    bilingual = SourceSpec(
        **{
            **SPEC.__dict__,
            "languages": ("tr", "en"),
            "config": {**SPEC.config, "listings": {"tr": "/tr/announcements", "en": "/en/announcements"}},
        }
    )
    items, _ = await ingest.collect_items(bilingual)
    assert [item.title for item in items] == ["Duyuru A", "Duyuru B"]


async def test_every_language_failing_is_still_a_failure(monkeypatch):
    from app.campus.sources.models import SourceError

    monkeypatch.setattr(ingest, "CampusFetcher", lambda *a, **k: FakeFetcher({}))
    with pytest.raises(SourceError):
        await ingest.collect_items(SPEC)


async def test_pagination_past_the_last_page_ends_the_walk(monkeypatch):
    """Some sites 404 past the end of a view instead of returning it empty."""
    monkeypatch.setattr(ingest, "CampusFetcher", lambda *a, **k: FakeFetcher(PAGES))
    paged = SourceSpec(**{**SPEC.__dict__, "max_pages": 4})
    items, stats = await ingest.collect_items(paged)
    assert [item.title for item in items] == ["Duyuru A", "Duyuru B"]
    assert stats.items_seen == 2


async def test_preview_writes_nothing_and_reports_what_it_parsed(fake_fetcher):
    async with SessionLocal() as db:
        result = await ingest.preview_source(SPEC, db=db, limit=5)
        assert result["ok"] is True
        assert result["items_seen"] == 2
        assert result["items"][0]["title"] == "Duyuru A"
        assert (await db.execute(select(CampusSourceRun))).scalars().all() == []


async def test_preview_says_so_when_a_configuration_parses_nothing(monkeypatch):
    """An adapter that finds nothing is the failure this whole module exists for."""
    monkeypatch.setattr(ingest, "CampusFetcher", lambda *a, **k: FakeFetcher(PAGES))
    wrong = SourceSpec(**{**SPEC.__dict__, "config": {**SPEC.config, "item_pattern": r"^/nope/"}})
    result = await ingest.preview_source(wrong)
    assert result["ok"] is False
    assert result["error_code"] == "empty_result"


async def test_a_run_is_recorded_and_the_source_is_rescheduled(fake_fetcher):
    async with SessionLocal() as db:
        row = CampusSource(**row_kwargs(SPEC), revision=1)
        db.add(row)
        await db.commit()

        result = await ingest.run_source(db, row)
        # Without embeddings configured the parse still happened, and its item
        # count is the useful signal.
        assert result.status == "parsed_only"
        assert result.stats.items_seen == 2

        runs = (await db.execute(select(CampusSourceRun))).scalars().all()
        assert len(runs) == 1 and runs[0].items_seen == 2
        assert row.next_run_at is not None
        assert row.last_status == "parsed_only"


async def test_a_failing_source_backs_off_rather_than_retrying_every_tick(monkeypatch):
    monkeypatch.setattr(ingest, "CampusFetcher", lambda *a, **k: FakeFetcher({}))
    async with SessionLocal() as db:
        row = CampusSource(**row_kwargs(SPEC), revision=1)
        db.add(row)
        await db.commit()

        result = await ingest.run_source(db, row)
        assert result.status == "failed"
        assert row.last_error
        # A quarter of the interval, floored at five minutes: a site that is
        # down stays down for a while, and hammering it helps nobody.
        expected = max(300, row.refresh_seconds // 4)
        assert (row.next_run_at - datetime.now(UTC)).total_seconds() == pytest.approx(expected, abs=30)


async def test_an_adapter_crash_fails_one_source_not_the_loop(monkeypatch):
    async def boom(context):
        raise RuntimeError("adapter exploded")

    monkeypatch.setattr(ingest, "get_adapter", lambda name: boom)
    monkeypatch.setattr(ingest, "CampusFetcher", lambda *a, **k: FakeFetcher(PAGES))
    async with SessionLocal() as db:
        row = CampusSource(**row_kwargs(SPEC), revision=1)
        db.add(row)
        await db.commit()
        result = await ingest.run_source(db, row)
    assert result.status == "failed"
    assert result.error_code == "adapter_error"


async def test_an_empty_curated_table_is_not_reported_as_a_broken_source():
    """A fresh deployment has no curated entries, and that is not a failure.

    For a scraped site, zero items means the page changed shape and the source
    silently stopped working. For the curated adapter it means an admin has not
    added anything yet, and flagging it trains operators to ignore the signal.
    """
    async with SessionLocal() as db:
        row = CampusSource(
            **row_kwargs(
                SourceSpec(
                    slug="curated",
                    name="Curated",
                    adapter="curated",
                    kind="curated",
                    base_url="https://devrimo.local/curated",
                )
            ),
            revision=1,
        )
        db.add(row)
        await db.commit()
        result = await ingest.run_source(db, row)

    assert result.status != "failed"
    assert result.stats.items_seen == 0


async def test_curated_entries_become_items_and_expired_ones_do_not():
    async with SessionLocal() as db:
        db.add(
            CampusCuratedEntry(
                kind="whatsapp_group",
                entry_key="CENG315",
                title="CENG315 WhatsApp group",
                body="Ask before joining.",
                url="https://chat.whatsapp.com/example",
                valid_until=datetime.now(UTC) + timedelta(days=30),
            )
        )
        db.add(
            CampusCuratedEntry(
                kind="whatsapp_group",
                entry_key="CENG111",
                title="Expired group",
                valid_until=datetime.now(UTC) - timedelta(days=1),
            )
        )
        await db.commit()

        spec = SourceSpec(
            slug="curated", name="Curated", adapter="curated", kind="curated", base_url="https://devrimo.local/curated"
        )
        items, _ = await ingest.collect_items(spec, db=db)

    assert [item.extra["entry_key"] for item in items] == ["CENG315"]
    assert "https://chat.whatsapp.com/example" in items[0].body
