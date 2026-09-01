"""Row-per-item tables. In practice: the academic calendar.

``oidb.metu.edu.tr`` publishes each year's calendar as one table of 155 rows,
two cells wide — a Turkish date range and a description — with the occasional
one-cell row acting as a section heading (``GÜZ DÖNEMİ``, ``BAHAR DÖNEMİ``).
That structure is worth parsing properly rather than embedding as one wall of
text: "when is Add-Drop" wants *one* row with real dates on it, not a
similarity match somewhere inside a year of deadlines.

The dates are the hard part. The column is written for humans and every row is
a different shape:

    05 - 09 EKİM 2026            a range inside one month
    1 HAZİRAN- 12 TEMMUZ 2026    a range across two months
    09-10-11 EYLÜL 2026          enumerated days
    30 AĞUSTOS 2026              a single day
    +++ EYLÜL 2026               a month with no day fixed yet

:func:`parse_turkish_dates` handles all of them by finding month names and
attributing the numbers around them, rather than by matching a list of formats
that the next academic year would break.

Config:

```json
{
  "pages": {"tr": "/tr/…-2026-2027-akademik-takvim", "en": "/en/…"},
  "region": {"tag": "main"},
  "table_index": 0, "date_column": 0, "text_column": 1,
  "academic_year": "2026-2027"
}
```
"""

import calendar
import re
from datetime import date

from app.campus.sources.adapters import AdapterContext, per_language
from app.campus.sources.htmlkit import Region, decode, extract_tables
from app.campus.sources.models import SourceItem

# Turkish month names, including the dotted-capital forms that appear when a
# site upper-cases them (``İ`` vs ``I``) and the common ASCII spellings.
_MONTHS: dict[str, int] = {
    "OCAK": 1,
    "ŞUBAT": 2,
    "SUBAT": 2,
    "MART": 3,
    "NİSAN": 4,
    "NISAN": 4,
    "MAYIS": 5,
    "HAZİRAN": 6,
    "HAZIRAN": 6,
    "TEMMUZ": 7,
    "AĞUSTOS": 8,
    "AGUSTOS": 8,
    "EYLÜL": 9,
    "EYLUL": 9,
    "EKİM": 10,
    "EKIM": 10,
    "KASIM": 11,
    "ARALIK": 12,
}
_MONTH_RE = re.compile("|".join(sorted(_MONTHS, key=len, reverse=True)))
_NUMBER_RE = re.compile(r"\d{1,4}")


def _upper_tr(value: str) -> str:
    """Upper-case without letting ``i`` become ``I`` and lose its dot.

    ``"ekim".upper()`` is ``"EKIM"`` under the C locale but ``"EKİM"`` in
    Turkish, and the calendar uses the Turkish form. Mapping the two dotted
    letters by hand is simpler and more predictable than depending on a locale
    being installed in the container.
    """
    return value.replace("i", "İ").replace("ı", "I").upper()


def parse_turkish_dates(text: str) -> tuple[date | None, date | None]:
    """``(start, end)`` for one calendar date cell, or ``(None, None)``.

    Works by locating month names and reading the numbers around them, so a row
    shape nobody anticipated degrades to a single date or to no date at all,
    rather than to a wrong one.
    """
    normalised = _upper_tr(text or "").replace("–", "-").replace("—", "-")
    months = [(match.start(), _MONTHS[match.group(0)]) for match in _MONTH_RE.finditer(normalised)]
    if not months:
        return None, None

    numbers = [(match.start(), int(match.group(0))) for match in _NUMBER_RE.finditer(normalised)]
    years = [value for _, value in numbers if 1900 <= value <= 2200]
    default_year = years[0] if years else None
    if default_year is None:
        return None, None

    def days_between(low: int, high: int) -> list[int]:
        return [value for position, value in numbers if low <= position < high and 1 <= value <= 31]

    def year_for(position: int, fallback: int) -> int:
        after = [value for pos, value in numbers if pos >= position and 1900 <= value <= 2200]
        return after[0] if after else fallback

    def safe(year: int, month: int, day: int) -> date | None:
        try:
            return date(year, month, day)
        except ValueError:
            return None

    if len(months) == 1:
        position, month = months[0]
        year = year_for(position, default_year)
        days = days_between(0, position)
        if not days:
            # "+++ EYLÜL 2026": the month is announced, the day is not. The
            # whole month is the honest answer, and the description says so.
            return safe(year, month, 1), safe(year, month, calendar.monthrange(year, month)[1])
        return safe(year, month, min(days)), safe(year, month, max(days))

    (first_position, first_month), (second_position, second_month) = months[0], months[1]
    start_days = days_between(0, first_position)
    end_days = days_between(first_position, second_position)
    # With one year printed at the end, a range that runs backwards through the
    # months has crossed the new year — "28 ARALIK - 08 OCAK 2027".
    second_year = year_for(second_position, default_year)
    first_year = second_year - 1 if second_month < first_month and len(years) < 2 else default_year
    start = safe(first_year, first_month, min(start_days)) if start_days else safe(first_year, first_month, 1)
    end = (
        safe(second_year, second_month, max(end_days))
        if end_days
        else safe(second_year, second_month, calendar.monthrange(second_year, second_month)[1])
    )
    return start, end


def parse_table(
    markup: str, config: dict, *, base_id: str, language: str, academic_year: str | None
) -> list[SourceItem]:
    """Every usable row of the configured table, as items."""
    region = Region.from_config(config.get("region") or {"tag": "main"})
    tables = extract_tables(markup, region=region)
    if not tables:
        return []
    index = int(config.get("table_index", 0))
    if index >= len(tables):
        return []
    table = tables[index]

    date_column = int(config.get("date_column", 0))
    text_column = int(config.get("text_column", 1))
    section = ""
    items: list[SourceItem] = []
    for row_number, row in enumerate(table):
        if len(row) == 1:
            # A one-cell row is a heading. Carrying it forward is what lets a
            # student's "when is Add-Drop" be answered with the right semester,
            # since the row itself says only "Ders Ekleme - Bırakma".
            section = row[0].strip()
            continue
        if len(row) <= max(date_column, text_column):
            continue
        raw_date = row[date_column].strip()
        description = row[text_column].strip()
        if not description and not raw_date:
            continue
        start, end = parse_turkish_dates(raw_date)
        headline = description.split("\n", 1)[0][:500]
        body_parts = [part for part in (section, raw_date, description) if part]
        items.append(
            SourceItem(
                external_id=f"{base_id}#row-{row_number}",
                title=headline or raw_date[:500],
                body="\n".join(body_parts),
                url=base_id,
                language=language,
                extra={
                    "section": section,
                    "date_text": raw_date,
                    "date_start": start.isoformat() if start else None,
                    "date_end": end.isoformat() if end else None,
                    "academic_year": academic_year,
                    "row": row_number,
                },
            )
        )
    return items


async def collect(context: AdapterContext) -> list[SourceItem]:
    spec, fetcher = context.spec, context.fetcher
    config = spec.config
    pages: dict[str, str] = config.get("pages") or {}
    academic_year = config.get("academic_year")

    async def for_language(language: str) -> list[SourceItem]:
        path = pages.get(language)
        if not path:
            return []
        page = await fetcher.get(spec.absolute(path))
        markup = decode(page.body, declared=page.declared_charset, override=spec.encoding)
        return parse_table(markup, config, base_id=page.url, language=language, academic_year=academic_year)[
            : spec.max_items
        ]

    return await per_language(spec, for_language)
