import pytest

from app.knowledge.embeddings import _response_vectors


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
