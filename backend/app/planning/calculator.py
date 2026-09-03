import ast
import math
import operator

from simpleeval import SimpleEval

MAX_ABSOLUTE_RESULT = 1e100


def _number(value: object) -> int | float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("Arithmetic operands must be numbers")
    return value


def _binary(operation):
    def bounded(left: object, right: object) -> int | float:
        result = operation(_number(left), _number(right))
        if not math.isfinite(float(result)) or abs(result) > MAX_ABSOLUTE_RESULT:
            raise ValueError("Result is outside the allowed range")
        return result

    return bounded


def _unary(operation):
    return lambda value: operation(_number(value))


def _safe_power(base: int | float, exponent: int | float) -> int | float:
    """Reject powers whose result could consume unreasonable CPU or memory."""
    base = _number(base)
    exponent = _number(exponent)
    if abs(exponent) > 10_000:
        raise ValueError("Exponent is outside the allowed range")
    if base and exponent > 0 and exponent * math.log10(abs(base)) > math.log10(MAX_ABSOLUTE_RESULT):
        raise ValueError("Result is outside the allowed range")
    return operator.pow(base, exponent)


OPERATORS = {
    # Checking before each operation prevents non-numeric literals from doing
    # expensive work such as allocating a huge string through multiplication.
    ast.Add: _binary(operator.add),
    ast.Sub: _binary(operator.sub),
    ast.Mult: _binary(operator.mul),
    ast.Div: _binary(operator.truediv),
    ast.Pow: _safe_power,
    ast.USub: _unary(operator.neg),
    ast.UAdd: _unary(operator.pos),
}
_ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Constant,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.USub,
    ast.UAdd,
)


def compute(expression: str) -> float:
    """Evaluate a bounded arithmetic expression with a maintained parser."""
    if len(expression) > 500:
        raise ValueError("Expression is too long")
    try:
        syntax = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("Only bounded arithmetic expressions are allowed") from exc
    if any(not isinstance(node, _ALLOWED_NODES) for node in ast.walk(syntax)):
        raise ValueError("Only arithmetic expressions are allowed")
    if any(
        isinstance(node, ast.Constant)
        and (isinstance(node.value, bool) or not isinstance(node.value, int | float))
        for node in ast.walk(syntax)
    ):
        raise ValueError("Only numeric literals are allowed")
    evaluator = SimpleEval(operators=OPERATORS, functions={}, names={})
    try:
        value = evaluator.eval(expression)
    except Exception as exc:
        raise ValueError("Only bounded arithmetic expressions are allowed") from exc
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("Only arithmetic expressions are allowed")
    result = float(value)
    if not math.isfinite(result) or abs(result) > MAX_ABSOLUTE_RESULT:
        raise ValueError("Result is outside the allowed range")
    return result
