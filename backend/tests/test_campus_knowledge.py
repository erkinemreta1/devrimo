"""Document construction and per-student retrieval scoping.

The scoping tests describe what "tailored to the student's department and
degree level" actually means, including the two cases where it must *not*
narrow: a document that names no audience is university-wide, and a student
whose profile is incomplete must be shown everything rather than nothing.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.campus.sources.documents import audience_tags, content_hash, lower_tr, to_document, to_documents
from app.campus.sources.models import SourceItem, SourceSpec
from app.knowledge.retrieval import StudentScope, format_hit, matches_scope, rank_key
from app.knowledge.store import SearchHit

CALENDAR = SourceSpec(
    slug="oidb-academic-calendar",
    name="Academic calendar",
    adapter="html_table",
    kind="calendar",
    base_url="https://oidb.metu.edu.tr",
    audience_rules={
        "lisansüstü": "degree_level:graduate",
        "temel i̇ngilizce": "audience:english_prep",
        "yks": "audience:new_students",
    },
)
CENG = SourceSpec(
    slug="ceng-announcements",
    name="Computer Engineering announcements",
    adapter="drupal_listing",
    kind="announcement",
    base_url="https://ceng.metu.edu.tr",
    departments=("CENG",),
)


# --- Turkish casing, which the audience rules depend on ---------------------


def test_turkish_lowercasing_handles_the_dotted_letters():
    """``"İ".lower()`` adds a combining dot and breaks a plain substring match."""
    assert lower_tr("İNGİLİZCE") == "ingilizce"
    assert lower_tr("LİSANSÜSTÜ") == "lisansüstü"
    assert lower_tr("IŞIK") == "ışık"


def test_audience_tags_match_turkish_prose_case_insensitively():
    tags = audience_tags("Lisansüstü programlara kabul edilen adayların ön kayıt işlemleri", CALENDAR.audience_rules)
    assert tags == ["degree_level:graduate"]


def test_audience_tags_are_empty_for_a_universal_row():
    assert audience_tags("Ders Ekleme - Bırakma", CALENDAR.audience_rules) == []


# --- Documents --------------------------------------------------------------


def test_add_drop_stays_university_wide():
    """The row every student needs must not be narrowed to anyone."""
    item = SourceItem(
        external_id="https://oidb.metu.edu.tr/tr/calendar#row-30",
        title="Ders Ekleme - Bırakma",
        body="GÜZ DÖNEMİ\n05 - 09 EKİM 2026\nDers Ekleme - Bırakma",
        language="tr",
        extra={"date_start": "2026-10-05", "date_end": "2026-10-09", "section": "GÜZ DÖNEMİ"},
    )
    document = to_document(CALENDAR, item)
    assert document.meta_data["degree_levels"] == []
    assert document.meta_data["departments"] == []
    assert document.meta_data["date_start"] == "2026-10-05"
    assert document.meta_data["kind"] == "calendar"
    # The title is repeated into the content: a title-only match is exactly the
    # case that has to work for "Ders Ekleme - Bırakma".
    assert document.content.startswith("Ders Ekleme - Bırakma")


def test_a_graduate_only_row_is_tagged_even_on_a_universal_source():
    item = SourceItem(
        external_id="row-7",
        title="Lisansüstü programlara ön kayıt",
        body="Lisansüstü programlara kabul edilen adayların çevrim içi ön kayıt işlemleri",
    )
    document = to_document(CALENDAR, item)
    assert "degree_level:graduate" in document.meta_data["audience_tags"]
    # The finer-grained statement wins over the source-level default, which is
    # what stops the row being shown to undergraduates.
    assert document.meta_data["degree_levels"] == ["graduate"]


def test_a_department_source_scopes_its_documents():
    document = to_document(CENG, SourceItem(external_id="x", title="CENG240 information", body="..."))
    assert document.meta_data["departments"] == ["CENG"]


def test_content_hash_ignores_whitespace_reflow():
    """Drupal re-indents on every deploy; that must not read as a change."""
    assert content_hash("T", "a  b\n\nc") == content_hash("T", "a b c")
    assert content_hash("T", "a b") != content_hash("T", "a c")


def test_document_ids_are_stable_and_per_source():
    first = to_document(CALENDAR, SourceItem(external_id="row-1", title="A", body="b"))
    again = to_document(CALENDAR, SourceItem(external_id="row-1", title="A", body="b"))
    other_source = to_document(CENG, SourceItem(external_id="row-1", title="A", body="b"))
    assert first.doc_id == again.doc_id
    assert first.doc_id != other_source.doc_id


def test_duplicate_and_empty_items_are_dropped():
    items = [
        SourceItem(external_id="a", title="One", body="body"),
        SourceItem(external_id="a", title="One", body="body"),
        SourceItem(external_id="b", title="   ", body="  "),
    ]
    assert len(to_documents(CALENDAR, items)) == 1


# --- Scoping ----------------------------------------------------------------


def meta(**overrides) -> dict:
    base = {"departments": [], "degree_levels": [], "language": "tr", "published_at": "2026-09-01"}
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    ("document", "scope", "expected"),
    [
        # University-wide content matches everybody. This is Add-Drop.
        (meta(), StudentScope(department="CENG", degree_level="undergraduate"), True),
        # A department's own announcement reaches that department.
        (meta(departments=["CENG"]), StudentScope(department="CENG"), True),
        (meta(departments=["CENG"]), StudentScope(department="PSY"), False),
        # An incomplete profile must not empty the corpus.
        (meta(departments=["CENG"]), StudentScope(), True),
        (meta(degree_levels=["graduate"]), StudentScope(), True),
        # Degree level narrows the calendar rows that state one.
        (meta(degree_levels=["graduate"]), StudentScope(degree_level="graduate"), True),
        (meta(degree_levels=["graduate"]), StudentScope(degree_level="undergraduate"), False),
        # Case is not a filter.
        (meta(departments=["ceng"]), StudentScope(department="CENG"), True),
    ],
)
def test_scope_matching(document, scope, expected):
    assert matches_scope(document, scope) is expected


def test_expired_curated_entries_are_not_returned():
    """A dead WhatsApp invite is worse than no answer at all."""
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    assert matches_scope(meta(valid_until=past), StudentScope()) is False
    assert matches_scope(meta(valid_until=future), StudentScope()) is True
    assert matches_scope(meta(valid_until="not-a-date"), StudentScope()) is True


def test_department_specific_and_same_language_results_sort_first():
    scope = StudentScope(department="CENG", degree_level="undergraduate", language="tr")
    universal = meta(published_at="2026-09-01")
    departmental = meta(departments=["CENG"], published_at="2026-01-01")
    translated = meta(language="en", published_at="2026-09-02")
    ordered = sorted([universal, translated, departmental], key=lambda item: rank_key(item, scope))
    assert ordered[0] is departmental
    assert ordered[-1] is translated


def test_newer_documents_sort_before_older_ones():
    scope = StudentScope()
    older = meta(published_at="2026-01-01")
    newer = meta(published_at="2026-09-01")
    assert sorted([older, newer], key=lambda item: rank_key(item, scope))[0] is newer


def test_scope_is_read_from_the_run_dependencies():
    scope = StudentScope.from_dependencies(
        {"department": "ceng", "degree_level": "graduate", "locale": "en", "display_name": "X"}
    )
    assert scope == StudentScope(department="CENG", degree_level="graduate", language="en")
    assert StudentScope.from_dependencies(None) == StudentScope()


async def test_retrieval_end_to_end_scopes_the_calendar_to_the_student(monkeypatch):
    """The Add-Drop question, from documents to what the model is handed.

    Three calendar rows all match "ekle-sil" equally well; only two of them are
    about an undergraduate. Handing all three over and hoping the model picks
    correctly is not "tailored to the student's department and degree level".
    """
    from app.knowledge import retrieval

    def document(title: str, **meta) -> SearchHit:
        return SearchHit(content=title, meta_data=meta | {"title": title, "source_name": "Academic calendar"})

    corpus = [
        document("Ders Ekleme - Bırakma", departments=[], degree_levels=[], language="tr", date_start="2026-10-05"),
        document("Lisansüstü ders ekleme", departments=[], degree_levels=["graduate"], language="tr"),
        document("CENG kayıt duyurusu", departments=["CENG"], degree_levels=[], language="tr"),
        document("PSY kayıt duyurusu", departments=["PSY"], degree_levels=[], language="tr"),
    ]

    async def fake_search(query, *, limit):
        return corpus

    monkeypatch.setattr(retrieval, "knowledge_available", lambda: True)
    monkeypatch.setattr(retrieval, "search", fake_search)

    results = await retrieval.retrieve(
        "ekle sil haftası",
        scope=StudentScope(department="CENG", degree_level="undergraduate", language="tr"),
    )
    titles = [result["title"] for result in results]
    assert "Lisansüstü ders ekleme" not in titles, "a graduate-only row must not reach an undergraduate"
    assert "PSY kayıt duyurusu" not in titles, "another department's notice must not reach this student"
    assert "Ders Ekleme - Bırakma" in titles, "university-wide content reaches everybody"
    # Department-specific content outranks university-wide for that department.
    assert titles[0] == "CENG kayıt duyurusu"


async def test_retrieval_returns_nothing_when_no_corpus_is_configured(monkeypatch):
    from app.knowledge import retrieval

    monkeypatch.setattr(retrieval, "knowledge_available", lambda: False)
    assert await retrieval.retrieve("anything", scope=StudentScope()) == []


async def test_a_failing_corpus_does_not_take_the_turn_down(monkeypatch):
    """The student still has their campus MCP tools if retrieval is broken."""
    from app.knowledge import retrieval

    async def boom(query, *, limit):
        raise RuntimeError("pgvector is unreachable")

    monkeypatch.setattr(retrieval, "knowledge_available", lambda: True)
    monkeypatch.setattr(retrieval, "search", boom)

    retriever = retrieval.build_retriever()
    assert await retriever("ekle sil", 5, None) == []


def test_formatted_results_carry_their_provenance_and_a_trust_label():
    """The persona has to name the source and its retrieval time."""
    hit = SearchHit(
        content="Ders Ekleme - Bırakma",
        meta_data=meta(
            title="Ders Ekleme - Bırakma",
            source_name="Academic calendar",
            url="https://oidb.metu.edu.tr/tr/calendar",
            fetched_at="2026-09-01T08:00:00+00:00",
            date_start="2026-10-05",
        ),
    )
    formatted = format_hit(hit)
    assert formatted["source"] == "Academic calendar"
    assert formatted["retrieved_at"] == "2026-09-01T08:00:00+00:00"
    assert formatted["url"].startswith("https://oidb.metu.edu.tr")
    assert formatted["date_start"] == "2026-10-05"
    # Scraped text is data, never instructions, and the model is told so.
    assert formatted["trust"] == "untrusted_campus_content"
