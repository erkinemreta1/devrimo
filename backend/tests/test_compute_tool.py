"""The compute tool's allowlist.

The rejection tests carry the weight here. This evaluator is fed by a model
that reads attacker-influenced announcements and email every turn, and it runs
inside the process holding every resident student's METU credentials — so
"everything not explicitly allowed is a syntax error" has to be true, not
mostly true.
"""

import pytest

from app.agents.tools.compute import ComputeError, compute, evaluate


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("2 + 3 * 4", 14),
        ("(1 + 2) / 4", 0.75),
        ("round(3.14159, 2)", 3.14),
        ("max(3, 7, 2)", 7),
        ("sum([1, 2, 3])", 6),
        ("7 // 2", 3),
        ("7 % 2", 1),
        ("2 ** 10", 1024),
        ("sorted([3, 1, 2])", [1, 2, 3]),
        ("len('CENG315')", 7),
        ("[1, 2, 3][1]", 2),
        ("{'a': 1}['a']", 1),
        ("3 if 1 < 2 else 4", 3),
        ("1 < 2 <= 3", True),
        ("abs(-4) + sqrt(9)", 7.0),
    ],
)
def test_arithmetic(expression, expected):
    assert evaluate(expression) == expected


def test_weighted_average_the_way_a_gpa_is_computed():
    expression = (
        "sum(c * g for c, g in [(3, 4.0), (4, 3.5), (3, 3.0)]) / sum(c for c, g in [(3, 4.0), (4, 3.5), (3, 3.0)])"
    )
    assert evaluate(expression) == pytest.approx(3.5)


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('id')",
        "import os",
        "().__class__",
        "(1).__class__.__bases__",
        "open('/etc/passwd')",
        "eval('1+1')",
        "exec('x=1')",
        "globals()",
        "lambda: 1",
        "x := 5",
        "[].append(1)",
        "'a'.upper()",
        "print(1)",
        "getattr(1, 'real')",
        "compile('1', '', 'eval')",
        "undefined_name",
        "f'{1}'.format()",
    ],
)
def test_dangerous_expressions_are_rejected(expression):
    with pytest.raises(ComputeError):
        evaluate(expression)


def test_attribute_access_is_impossible_even_on_allowed_values():
    with pytest.raises(ComputeError) as exc:
        evaluate("sum.__globals__")
    assert "not allowed" in str(exc.value).lower()


def test_call_position_must_be_a_plain_name():
    """Evaluating the callee would turn a function allowlist back into eval."""
    with pytest.raises(ComputeError):
        evaluate("(sorted if 1 else min)([2, 1])")


def test_exponent_is_capped():
    with pytest.raises(ComputeError) as exc:
        evaluate("9 ** 9999")
    assert "Exponents" in str(exc.value)


def test_division_by_zero_is_an_error_not_a_crash():
    assert "error" in compute("1 / 0")


def test_oversized_and_empty_input():
    with pytest.raises(ComputeError):
        evaluate("")
    with pytest.raises(ComputeError):
        evaluate("1 + " * 5000 + "1")


def test_comprehension_variables_do_not_leak_into_later_expressions():
    assert evaluate("sum(x for x in [1, 2, 3])") == 6
    with pytest.raises(ComputeError):
        evaluate("x")


def test_compute_returns_a_structured_error_rather_than_raising():
    result = compute("__import__('os')")
    assert result["expression"] == "__import__('os')"
    assert "error" in result and "result" not in result

    ok = compute("2 + 2")
    assert ok["result"] == 4
