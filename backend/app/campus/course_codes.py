"""Deterministic conversion of METU's numeric course identifiers."""

import re
from typing import Any

# METU represents a course as DDD + 0 + CCC.  Keep this mapping deliberately
# explicit: an unknown department must never be guessed by the assistant.
DEPARTMENT_PREFIXES: dict[str, str] = {
    "567": "EE",
}

_COURSE_CODE = re.compile(r"(?<!\d)(?P<department>\d{3})0(?P<course>\d{3})(?!\d)")


def display_course_code(value: str) -> str | None:
    """Return the familiar department code (for example 5670201 -> EE201)."""
    match = _COURSE_CODE.fullmatch(value.strip())
    if match is None:
        return None
    prefix = DEPARTMENT_PREFIXES.get(match.group("department"))
    if prefix is None:
        return None
    return f'{prefix}{match.group("course")}'


def annotate_course_codes(value: Any) -> Any:
    """Add readable aliases to known course IDs without changing source IDs."""
    if isinstance(value, str):
        def replacement(match: re.Match[str]) -> str:
            raw = match.group(0)
            alias = display_course_code(raw)
            return f"{raw} ({alias})" if alias else raw

        return _COURSE_CODE.sub(replacement, value)
    if isinstance(value, list):
        return [annotate_course_codes(item) for item in value]
    if isinstance(value, tuple):
        return tuple(annotate_course_codes(item) for item in value)
    if isinstance(value, dict):
        return {key: annotate_course_codes(item) for key, item in value.items()}
    return value
