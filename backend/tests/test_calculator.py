import pytest

from app.planning.calculator import compute


def test_compute_supports_bounded_arithmetic():
    assert compute("(12 + 8) / 4 + 2 ** 3") == 13.0


@pytest.mark.parametrize(
    "expression",
    [
        '"x" * 100000000',
        "9 ** 9 ** 9",
        "__import__('os')",
        "[1, 2, 3]",
        "1 if True else 2",
        "1 < 2",
    ],
)
def test_compute_rejects_non_numeric_or_expensive_expressions(expression):
    with pytest.raises(ValueError, match="arithmetic|allowed|outside"):
        compute(expression)
