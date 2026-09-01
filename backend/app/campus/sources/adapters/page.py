"""A fixed list of pages, each one document.

For content that is not a feed and not a list: the "how do I connect to
meturoam" article, a regulations page, a facility-hours page. The FAQ site is
*not* this adapter — its 405 articles are enumerable from one index, so it is a
``drupal_listing`` with a single page and an ``item_pattern`` of ``^/tr/sss/``,
which is exactly the reuse the registry exists to allow.

Config:

```json
{"pages": {"tr": ["/tr/sss/meturoam"], "en": ["/en/faq/meturoam"]},
 "region": {"tag": "main"}}
```

A bare string is accepted where a list is expected, because "one page" is the
common case and making an admin type brackets to say it is a papercut.
"""

from app.campus.sources.adapters import AdapterContext, per_language
from app.campus.sources.htmlkit import Region, decode, extract_text, first_datetime, page_title
from app.campus.sources.models import SourceItem


def parse_page(markup: str, url: str, config: dict, *, language: str = "tr") -> SourceItem:
    region = Region.from_config(config.get("region") or {"tag": "main"})
    body = extract_text(markup, region=region) or extract_text(markup)
    return SourceItem(
        external_id=url,
        title=page_title(markup, region=region)[:500],
        body=body,
        url=url,
        language=language,
        published_at=first_datetime(markup),
    )


def _as_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


async def collect(context: AdapterContext) -> list[SourceItem]:
    spec, fetcher = context.spec, context.fetcher
    pages = spec.config.get("pages") or {}

    async def for_language(language: str) -> list[SourceItem]:
        collected: list[SourceItem] = []
        for path in _as_list(pages.get(language))[: spec.max_items]:
            fetched = await fetcher.get(spec.absolute(path))
            markup = decode(fetched.body, declared=fetched.declared_charset, override=spec.encoding)
            collected.append(parse_page(markup, fetched.url, spec.config, language=language))
        return collected

    return await per_language(spec, for_language)
