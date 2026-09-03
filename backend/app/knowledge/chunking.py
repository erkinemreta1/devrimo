"""Deterministic, retrieval-sized chunks for canonical public records."""

from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from typing import Any

from app.knowledge.types import ParsedRecord

DEFAULT_CHUNK_MAX_CHARS = 1800
DEFAULT_CHUNK_CONTEXT_CHARS = 240
MIN_CHUNK_MAX_CHARS = 500
MAX_CHUNK_MAX_CHARS = 8000

_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def _normalized_lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip() for line in text.replace("\r", "\n").split("\n")]


def _split_long_text(text: str, max_chars: int) -> list[str]:
    """Split an oversized paragraph at sentences, then words as a fallback."""
    sentences = [item.strip() for item in _SENTENCE_BOUNDARY.split(text) if item.strip()]
    if not sentences:
        sentences = [text]
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        candidates = [sentence]
        if len(sentence) > max_chars:
            words = sentence.split()
            candidates = []
            word_piece = ""
            for word in words:
                if word_piece and len(word_piece) + len(word) + 1 > max_chars:
                    candidates.append(word_piece)
                    word_piece = word
                else:
                    word_piece = f"{word_piece} {word}".strip()
            if word_piece:
                candidates.append(word_piece)
        for candidate in candidates:
            if current and len(current) + len(candidate) + 1 > max_chars:
                pieces.append(current)
                current = candidate
            else:
                current = f"{current} {candidate}".strip()
    if current:
        pieces.append(current)
    if len(pieces) > 1 and len(pieces[-1]) < max_chars // 3:
        combined = f"{pieces[-2]} {pieces[-1]}"
        midpoint = len(combined) // 2
        split_at = combined.rfind(" ", 0, midpoint + 1)
        if split_at <= 0:
            split_at = combined.find(" ", midpoint)
        if split_at > 0:
            pieces[-2:] = [combined[:split_at].strip(), combined[split_at + 1 :].strip()]
    return pieces


def _sections(text: str, max_chars: int) -> list[tuple[str | None, str]]:
    headings: list[str] = []
    units: list[tuple[str | None, str]] = []
    for line in _normalized_lines(text):
        if not line:
            continue
        match = _HEADING.match(line)
        if match:
            level = len(match.group(1))
            headings = headings[: level - 1]
            headings.append(match.group(2).strip())
            continue
        section = " › ".join(headings) or None
        units.extend((section, piece) for piece in _split_long_text(line, max_chars))
    return units


def _chunk_content(text: str, max_chars: int) -> list[tuple[str | None, str]]:
    units = _sections(text, max_chars)
    if not units:
        return []
    chunks: list[tuple[str | None, str]] = []
    current: list[str] = []
    current_section: str | None = None
    for section, unit in units:
        separator = 2 if current else 0
        if current and sum(len(item) for item in current) + separator * len(current) + len(unit) > max_chars:
            chunks.append((current_section, "\n\n".join(current)))
            current = []
            current_section = None
        if not current:
            current_section = section
        current.append(unit)
    if current:
        chunks.append((current_section, "\n\n".join(current)))
    return chunks


def _config_int(config: dict[str, Any], key: str, default: int, minimum: int, maximum: int) -> int:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{key} must be an integer between {minimum} and {maximum}")
    return value


def validate_chunk_config(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        max_chars = _config_int(
            config,
            "chunk_max_chars",
            DEFAULT_CHUNK_MAX_CHARS,
            MIN_CHUNK_MAX_CHARS,
            MAX_CHUNK_MAX_CHARS,
        )
        _config_int(
            config,
            "chunk_context_chars",
            DEFAULT_CHUNK_CONTEXT_CHARS,
            0,
            max_chars // 2,
        )
    except ValueError as exc:
        errors.append(str(exc))
    return errors


def chunk_records(records: list[ParsedRecord], config: dict[str, Any]) -> list[ParsedRecord]:
    """Split long records without duplicating overlap in stored source text.

    Each stored chunk owns unique content. A short tail from the prior chunk is
    kept only as embedding context in metadata, so semantic boundaries retain
    context while page reconstruction remains lossless and non-duplicative.
    """
    max_chars = _config_int(
        config,
        "chunk_max_chars",
        DEFAULT_CHUNK_MAX_CHARS,
        MIN_CHUNK_MAX_CHARS,
        MAX_CHUNK_MAX_CHARS,
    )
    context_chars = _config_int(
        config,
        "chunk_context_chars",
        DEFAULT_CHUNK_CONTEXT_CHARS,
        0,
        max_chars // 2,
    )
    result: list[ParsedRecord] = []
    for record in records:
        chunks = _chunk_content(record.content, max_chars) or [(None, record.content)]
        parent_id = record.external_id
        count = len(chunks)
        previous = ""
        for index, (section, content) in enumerate(chunks):
            metadata = {
                **record.metadata,
                "parent_external_id": parent_id,
                "chunk_index": index,
                "chunk_count": count,
                "chunked": count > 1,
            }
            if section:
                metadata["section"] = section
            if previous and context_chars:
                context = previous[-context_chars:]
                first_space = context.find(" ")
                metadata["context_before"] = context[first_space + 1 :] if first_space >= 0 else context
            if count == 1:
                external_id = parent_id
            else:
                digest = hashlib.sha256(f"{section or ''}\x1f{content}".encode()).hexdigest()[:12]
                external_id = f"{parent_id}::chunk:{index + 1:04d}:{digest}"
            result.append(replace(record, external_id=external_id, content=content, metadata=metadata))
            previous = content
    return result


def embedding_text(*, title: str, summary: str | None, content: str, metadata: dict[str, Any] | None) -> str:
    """Build contextual text while keeping the searchable chunk itself focused."""
    metadata = metadata if isinstance(metadata, dict) else {}
    parts = [f"Document: {title}"]
    if section := metadata.get("section"):
        parts.append(f"Section: {section}")
    if summary:
        parts.append(f"Summary: {summary}")
    if context := metadata.get("context_before"):
        parts.append(f"Previous context: {context}")
    parts.append(content)
    return "\n".join(str(part) for part in parts if str(part).strip())[:12000]
