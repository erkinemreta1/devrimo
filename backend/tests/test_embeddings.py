from uuid import uuid4

import pytest

from app.knowledge.embeddings import (
    EmbeddingConfig,
    EmbeddingResponseError,
    _response_vectors,
    embed_query,
    embed_texts,
)


def test_response_vectors_accepts_openai_indexes_and_restores_input_order():
    payload = {
        "data": [
            {"index": 1, "embedding": [2.0]},
            {"index": 0, "embedding": [1.0]},
        ]
    }

    assert _response_vectors(payload, 2) == [[1.0], [2.0]]


def test_response_vectors_accepts_gemini_ordered_rows_without_indexes():
    payload = {
        "data": [
            {"object": "embedding", "embedding": [1.0]},
            {"object": "embedding", "embedding": [2.0]},
        ]
    }

    assert _response_vectors(payload, 2) == [[1.0], [2.0]]


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"data": [{"index": 0, "embedding": [1.0]}]}, "incomplete batch"),
        (
            {"data": [{"index": 0, "embedding": [1.0]}, {"embedding": [2.0]}]},
            "inconsistent indexes",
        ),
        (
            {"data": [{"index": 0, "embedding": [1.0]}, {"index": 0, "embedding": [2.0]}]},
            "invalid indexes",
        ),
        (
            {"data": [{"index": 0, "embedding": [1.0]}, {"index": 2, "embedding": [2.0]}]},
            "incomplete indexes",
        ),
        ({"data": [{"index": 0}, {"index": 1, "embedding": [2.0]}]}, "malformed batch"),
    ],
)
def test_response_vectors_rejects_ambiguous_or_incomplete_batches(payload, message):
    with pytest.raises(ValueError, match=message):
        _response_vectors(payload, 2)


async def test_batch_response_pairing_error_retries_single_inputs(monkeypatch):
    calls: list[list[str]] = []

    async def fake_request(_config, texts):
        calls.append(list(texts))
        if len(texts) > 1:
            raise EmbeddingResponseError("Embedding provider returned inconsistent indexes")
        return [[float(ord(texts[0][0]))]]

    monkeypatch.setattr("app.knowledge.embeddings._request_embeddings", fake_request)
    config = EmbeddingConfig(
        provider="local",
        model="test",
        base_url="http://embedding.test/v1",
        dimensions=1,
        batch_size=8,
    )
    vectors = await embed_texts(None, uuid4(), ["a", "b"], config=config)  # type: ignore[arg-type]

    assert calls == [["a", "b"], ["a"], ["b"]]
    assert [vector[0] for vector in vectors if vector] == [97.0, 98.0]


async def test_query_and_document_use_their_configured_instructions(monkeypatch):
    """A query and the passage answering it must not be embedded identically."""
    calls: list[list[str]] = []

    async def fake_request(_config, texts):
        calls.append(list(texts))
        return [[1.0] for _ in texts]

    monkeypatch.setattr("app.knowledge.embeddings._request_embeddings", fake_request)
    config = EmbeddingConfig(
        provider="local",
        model="test",
        base_url="http://embedding.test/v1",
        dimensions=1,
        batch_size=8,
        query_prefix="query: ",
        document_prefix="passage: ",
    )

    await embed_texts(None, uuid4(), ["kütüphane saatleri"], config=config)  # type: ignore[arg-type]
    await embed_query(None, uuid4(), "kütüphane kaçta açılıyor", config=config)  # type: ignore[arg-type]

    assert calls == [["passage: kütüphane saatleri"], ["query: kütüphane kaçta açılıyor"]]


def test_document_instruction_is_part_of_the_model_identity():
    """Changing the document prefix must retire vectors from the old space."""
    base = dict(provider="local", model="test", base_url="http://e.test/v1", dimensions=8, batch_size=4)
    plain = EmbeddingConfig(**base)
    prefixed = EmbeddingConfig(**base, document_prefix="passage: ")
    other = EmbeddingConfig(**base, document_prefix="belge: ")

    # An unconfigured prefix keeps the existing label so indexed corpora stay valid.
    assert plain.model_label == "local:test:8"
    assert prefixed.model_label != plain.model_label
    assert prefixed.model_label != other.model_label
    # The query instruction does not change what a stored vector means.
    assert EmbeddingConfig(**base, query_prefix="query: ").model_label == plain.model_label
