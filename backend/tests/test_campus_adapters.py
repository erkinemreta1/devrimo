"""Adapter parsing, against pages saved from the real METU sites.

Every fixture here is a byte-for-byte copy of a live page, because that is the
only thing these parsers can be wrong about. A synthetic fixture would encode
what the parser already assumes and pass forever while the real site drifted.

No test in this file touches the network.
"""

import pathlib
from datetime import date

import pytest

from app.campus.sources import htmlkit
from app.campus.sources.adapters import drupal_listing, html_table, page, rss
from app.campus.sources.models import SourceError

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "campus"

MIYS_LISTING_CONFIG = {
    "item_pattern": r"^/(tr|en)/(duyurular|announcements)/[^/]+$",
    "listing_region": {"tag": "main"},
    "node_region": {"tag": "main"},
}
CALENDAR_CONFIG = {"region": {"tag": "main"}, "table_index": 0, "date_column": 0, "text_column": 1}


def read(name: str) -> str:
    return FIXTURES.joinpath(name).read_bytes().decode("utf-8")


# --- The academic calendar, which is what "when is Add-Drop" depends on -----


def test_calendar_yields_the_add_drop_row_with_real_dates():
    items = html_table.parse_table(
        read("oidb_calendar_2026_2027.html"),
        CALENDAR_CONFIG,
        base_id="https://oidb.metu.edu.tr/tr/calendar",
        language="tr",
        academic_year="2026-2027",
    )
    add_drop = [item for item in items if "Ekleme" in item.title]
    assert len(add_drop) == 2, "the calendar has one Add-Drop row per semester"

    fall = add_drop[0]
    assert fall.extra["date_start"] == "2026-10-05"
    assert fall.extra["date_end"] == "2026-10-09"
    # The row itself says only "Ders Ekleme - Bırakma"; the semester comes from
    # the one-cell heading above it, and without it the two rows are
    # indistinguishable.
    assert fall.extra["section"] == "GÜZ DÖNEMİ"
    assert fall.extra["academic_year"] == "2026-2027"

    spring = add_drop[1]
    assert (spring.extra["date_start"], spring.extra["date_end"]) == ("2027-02-22", "2027-02-26")
    assert "BAHAR" in spring.extra["section"]


def test_calendar_parses_every_row_and_dates_all_of_them():
    items = html_table.parse_table(
        read("oidb_calendar_2026_2027.html"),
        CALENDAR_CONFIG,
        base_id="https://oidb.metu.edu.tr/tr/calendar",
        language="tr",
        academic_year="2026-2027",
    )
    assert len(items) == 153
    undated = [item for item in items if not item.extra["date_start"]]
    assert undated == [], "a row the date parser cannot read is a silent gap in the calendar"
    assert len({item.external_id for item in items}) == len(items)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # A range inside one month.
        ("05 - 09 EKİM 2026", (date(2026, 10, 5), date(2026, 10, 9))),
        # A range across two months, with the year printed once at the end.
        ("1 HAZİRAN- 12 TEMMUZ 2026", (date(2026, 6, 1), date(2026, 7, 12))),
        ("24 AĞUSTOS - 25 EYLÜL 2026", (date(2026, 8, 24), date(2026, 9, 25))),
        # Enumerated days rather than a range.
        ("09-10-11 EYLÜL 2026", (date(2026, 9, 9), date(2026, 9, 11))),
        ("30 AĞUSTOS 2026", (date(2026, 8, 30), date(2026, 8, 30))),
        # "the day is not fixed yet" — the whole month is the honest answer.
        ("+++ EYLÜL 2026", (date(2026, 9, 1), date(2026, 9, 30))),
        # Crossing the new year, with both years printed.
        ("28 ARALIK 2026 - 08 OCAK 2027", (date(2026, 12, 28), date(2027, 1, 8))),
        # ASCII spellings, which appear when a page loses its diacritics.
        ("22 - 26 SUBAT 2027", (date(2027, 2, 22), date(2027, 2, 26))),
        # Prose with no month at all must yield nothing rather than a guess.
        ("tarihler daha sonra duyurulacaktır", (None, None)),
        ("", (None, None)),
    ],
)
def test_turkish_date_shapes(text, expected):
    assert html_table.parse_turkish_dates(text) == expected


def test_year_rolls_over_when_the_range_runs_backwards():
    """"28 ARALIK - 08 OCAK 2027" prints one year and spans two."""
    start, end = html_table.parse_turkish_dates("28 ARALIK - 08 OCAK 2027")
    assert (start, end) == (date(2026, 12, 28), date(2027, 1, 8))


# --- Drupal 10, the common METU shape --------------------------------------


def test_drupal10_listing_returns_headlines_not_dates():
    """A teaser links the same node several times, one of them being its date.

    Picking the shortest link text would title every spormd announcement
    "21/07/2026", which is both wrong and unsearchable.
    """
    entries = drupal_listing.parse_listing(
        read("spormd_announcements_en.html"),
        "https://spormd.metu.edu.tr/en/announcements",
        MIYS_LISTING_CONFIG,
    )
    assert len(entries) == 9
    titles = [entry.title for entry in entries]
    assert "2026 SUMMER SPORTS ACTIVITY PROGRAM" in titles
    assert not any(title[:2].isdigit() and "/" in title[:6] for title in titles)
    assert entries[0].published_at is not None and entries[0].published_at.date() == date(2026, 7, 21)


def test_drupal10_node_takes_its_date_from_the_time_element():
    item = drupal_listing.parse_node(
        read("spormd_node_tr.html"),
        "https://spormd.metu.edu.tr/tr/duyurular/15-temmuz-spor-tesisleri-programi",
        MIYS_LISTING_CONFIG,
        fallback_title="15 TEMMUZ SPOR TESİSLERİ PROGRAMI",
    )
    assert item.title == "15 TEMMUZ SPOR TESİSLERİ PROGRAMI"
    assert item.published_at is not None
    assert item.published_at.date() == date(2026, 7, 13)
    assert "spor tesislerinin" in item.body
    # Site chrome repeats on every page; carrying it into each document would
    # make every page on a site look alike to the embedder.
    assert "Ana gezinti menüsü" not in item.body


# --- Drupal 7, the shape that proves configuration is doing the work -------


def test_drupal7_department_parses_from_configuration_alone():
    """``ie.metu.edu.tr`` shares nothing with the common shape but the CMS.

    Singular ``/en/announcement/``, listed at ``/en/tum-duyurular``, no
    ``<time>`` element, no ``<main>``. If this needs a code change, the registry
    is not actually configurable — so this test is the acceptance test for that
    claim, and it uses only a different ``item_pattern``.
    """
    entries = drupal_listing.parse_listing(
        read("ie_announcements_en.html"),
        "https://ie.metu.edu.tr/en/tum-duyurular",
        {"item_pattern": r"^/(tr|en)/announcement/[^/]+$"},
    )
    assert len(entries) > 100
    assert all(entry.url.startswith("https://ie.metu.edu.tr/en/announcement/") for entry in entries)
    # No <time> on this generation of Drupal, so the listing's dd/mm/yyyy is
    # the only publication date available at all.
    dated = [entry for entry in entries if entry.published_at is not None]
    assert len(dated) > 50


def test_faq_article_title_comes_from_the_content_region():
    """The FAQ site's first ``<h1>`` and its ``<title>`` are both the site name.

    Scoped to the content region the article's own question is found, which is
    what stops all 405 FAQ documents being titled identically.
    """
    item = page.parse_page(
        read("faq_meturoam_tr.html"),
        "https://faq.cc.metu.edu.tr/tr/sss/meturoam",
        {"region": {"tag": "div", "attr": "id", "value": "content"}},
    )
    assert item.title == "meturoam ağına nasıl bağlanabilirim?"
    assert "WPA2" in item.body
    assert "Android" in item.body


# --- Feeds ------------------------------------------------------------------


def test_wordpress_feed_parses():
    items = rss.parse_feed(FIXTURES.joinpath("haber_feed_tr.xml").read_bytes())
    assert len(items) == 10
    assert all(item.title for item in items)
    assert items[0].published_at is not None


def test_empty_drupal_feed_is_a_failure_not_a_quiet_week():
    """Every METU Drupal site serves an empty ``/rss.xml`` with HTTP 200.

    Treating that as success is how a feed-driven source ingests nothing for a
    year while every health check stays green.
    """
    empty = b'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title></channel></rss>'
    with pytest.raises(SourceError) as exc:
        rss.parse_feed(empty)
    assert exc.value.code == "empty_feed"


def test_feed_with_a_dtd_is_refused():
    hostile = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "b">]><rss><channel></channel></rss>'
    with pytest.raises(SourceError) as exc:
        rss.parse_feed(hostile)
    assert exc.value.code == "unsafe_xml"


# --- Encoding ---------------------------------------------------------------


def test_catalog_declares_iso8859_9_but_serves_utf8():
    """The legacy catalog's own charset declaration is wrong.

    Single-byte codecs never raise, so trusting the declaration first cannot
    fail over — it silently yields ``TÃ¼rkÃ§e``. Strict UTF-8 first is what
    distinguishes the two.
    """
    raw = FIXTURES.joinpath("catalog_course_math423.html").read_bytes()
    assert htmlkit.charset_from_meta(raw) == "iso8859-9"

    decoded = htmlkit.decode(raw, declared="iso8859-9")
    assert "Türkçe" in decoded
    assert "TÃ¼rkÃ§e" not in decoded

    # An explicit source-level override still wins; it is the admin's escape
    # hatch for whatever the heuristic gets wrong.
    assert "TÃ¼rkÃ§e" in htmlkit.decode(raw, declared="iso8859-9", override="iso8859-9")


def test_genuine_latin5_bytes_still_decode():
    raw = "Türkçe ders".encode("iso8859-9")
    assert htmlkit.decode(raw, declared="iso8859-9") == "Türkçe ders"


# --- htmlkit primitives -----------------------------------------------------


def test_region_scoping_excludes_content_after_the_region_closes():
    markup = "<body><main><p>inside</p></main><footer><p>outside</p></footer></body>"
    assert htmlkit.extract_text(markup, region=htmlkit.Region(tag="main")) == "inside"


def test_void_elements_do_not_corrupt_region_depth():
    """An unclosed ``<img>`` inside a region used to close it early."""
    markup = '<main><img src="a.png"><br><p>still inside</p></main>'
    assert "still inside" in htmlkit.extract_text(markup, region=htmlkit.Region(tag="main"))


def test_script_and_style_content_never_reaches_the_body():
    markup = "<main><script>var secret=1;</script><style>.a{}</style><p>text</p></main>"
    text = htmlkit.extract_text(markup, region=htmlkit.Region(tag="main"))
    assert text == "text"


def test_table_cells_keep_their_line_structure():
    markup = "<main><table><tr><td>1 EKİM 2026</td><td>Bir<br>İki</td></tr></table></main>"
    tables = htmlkit.extract_tables(markup, region=htmlkit.Region(tag="main"))
    assert tables == [[["1 EKİM 2026", "Bir\nİki"]]]
