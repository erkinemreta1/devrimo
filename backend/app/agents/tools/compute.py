"""Arithmetic the model can trust, without giving it a Python interpreter.

Language models are unreliable at multi-step arithmetic, and every question
about credits, averages, or how many ECTS a plan adds up to is multi-step. So
the model needs a calculator.

What it must not get is Agno's ``PythonTools``, or anything else built on
``exec``. This code runs inside the broker process, which holds every resident
student's METU password in the environment of the MCP subprocesses it spawned
and its own ``SECRET_ENCRYPTION_KEY`` in memory. A sandbox escape is not the
risk to weigh here — arbitrary execution in this process *is* the breach, and
the only text that reaches this tool has passed through a model that reads
attacker-controlled announcements and email every turn.

So this is an allowlist evaluator over an AST: literals, arithmetic,
comparisons, comprehensions, and a fixed set of numeric builtins. There is no
attribute access, no name that is not a listed function or a comprehension
variable, no import, no call to anything unlisted. Everything not explicitly
permitted is a syntax error, which is the only safe default for a parser fed by
a model.
"""

import ast
import math
from typing import Any

# Numeric helpers worth having. Nothing here can reach the filesystem, the
# network, or another object: they are pure functions of their arguments.
ALLOWED_FUNCTIONS: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "len": len,
    "sorted": sorted,
    "pow": pow,
    "int": int,
    "float": float,
    "any": any,
    "all": all,
    "divmod": divmod,
    "sqrt": math.sqrt,
    "floor": math.floor,
    "ceil": math.ceil,
    "fabs": math.fabs,
    "log": math.log,
    "exp": math.exp,
}

_BIN_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a**b,
}
_COMPARE_OPS = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

MAX_EXPRESSION_CHARS = 4_000
MAX_NODES = 2_000
# ``9**9**9`` is a one-line denial of service against a process that is also
# serving chat turns, and no legitimate campus arithmetic needs it.
MAX_EXPONENT = 64
MAX_SEQUENCE_LENGTH = 10_000


class ComputeError(ValueError):
    """The expression was rejected, or could not be evaluated."""


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise ComputeError(message)


class _Evaluator(ast.NodeVisitor):
    def __init__(self) -> None:
        # Comprehension variables only. Nothing else can ever bind a name.
        self.scope: dict[str, Any] = {}

    def generic_visit(self, node: ast.AST) -> Any:
        raise ComputeError(f"{type(node).__name__} is not allowed in a computation")

    def visit_Expression(self, node: ast.Expression) -> Any:
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> Any:
        _check(isinstance(node.value, (int, float, complex, bool, str, type(None))), "Unsupported constant")
        return node.value

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id in self.scope:
            return self.scope[node.id]
        if node.id in ALLOWED_FUNCTIONS:
            return ALLOWED_FUNCTIONS[node.id]
        raise ComputeError(f"Unknown name {node.id!r}; only numbers and the listed functions are available")

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        operation = _BIN_OPS.get(type(node.op))
        _check(operation is not None, f"Operator {type(node.op).__name__} is not allowed")
        left, right = self.visit(node.left), self.visit(node.right)
        if isinstance(node.op, ast.Pow):
            _check(
                isinstance(right, (int, float)) and abs(right) <= MAX_EXPONENT,
                f"Exponents are limited to {MAX_EXPONENT}",
            )
        if isinstance(node.op, ast.Mult) and isinstance(left, (str, list, tuple)):
            _check(
                isinstance(right, int) and abs(right) * max(len(left), 1) <= MAX_SEQUENCE_LENGTH,
                "Sequence repetition is too large",
            )
        try:
            return operation(left, right)
        except ZeroDivisionError as exc:
            raise ComputeError("Division by zero") from exc

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        value = self.visit(node.operand)
        if isinstance(node.op, ast.USub):
            return -value
        if isinstance(node.op, ast.UAdd):
            return +value
        if isinstance(node.op, ast.Not):
            return not value
        raise ComputeError(f"Operator {type(node.op).__name__} is not allowed")

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        values = [self.visit(value) for value in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)

    def visit_Compare(self, node: ast.Compare) -> Any:
        left = self.visit(node.left)
        for operator, comparator in zip(node.ops, node.comparators, strict=True):
            operation = _COMPARE_OPS.get(type(operator))
            _check(operation is not None, f"Comparison {type(operator).__name__} is not allowed")
            right = self.visit(comparator)
            if not operation(left, right):
                return False
            left = right
        return True

    def visit_IfExp(self, node: ast.IfExp) -> Any:
        return self.visit(node.body) if self.visit(node.test) else self.visit(node.orelse)

    def visit_List(self, node: ast.List) -> Any:
        return [self.visit(element) for element in node.elts]

    def visit_Tuple(self, node: ast.Tuple) -> Any:
        return tuple(self.visit(element) for element in node.elts)

    def visit_Set(self, node: ast.Set) -> Any:
        return {self.visit(element) for element in node.elts}

    def visit_Dict(self, node: ast.Dict) -> Any:
        return {
            self.visit(key) if key is not None else None: self.visit(value)
            for key, value in zip(node.keys, node.values, strict=True)
        }

    def visit_Subscript(self, node: ast.Subscript) -> Any:
        container = self.visit(node.value)
        _check(isinstance(container, (list, tuple, dict, str)), "Only sequences and mappings can be indexed")
        key = self.visit(node.slice)
        try:
            return container[key]
        except (KeyError, IndexError, TypeError) as exc:
            raise ComputeError(f"Invalid index: {exc}") from exc

    def visit_Slice(self, node: ast.Slice) -> Any:
        return slice(
            self.visit(node.lower) if node.lower else None,
            self.visit(node.upper) if node.upper else None,
            self.visit(node.step) if node.step else None,
        )

    def visit_Call(self, node: ast.Call) -> Any:
        # Resolved by *name*, never by evaluating the callee: allowing an
        # arbitrary expression in call position is how an allowlist of
        # functions turns back into arbitrary execution.
        _check(isinstance(node.func, ast.Name), "Only the listed functions may be called")
        name = node.func.id
        _check(name in ALLOWED_FUNCTIONS, f"Function {name!r} is not available")
        _check(not node.keywords, "Keyword arguments are not supported")
        return ALLOWED_FUNCTIONS[name](*[self.visit(argument) for argument in node.args])

    @staticmethod
    def _target_names(target: ast.expr) -> tuple[str, ...]:
        """The names one comprehension target binds.

        Tuple targets are supported because ``for credits, grade in [...]`` is
        how a weighted average is naturally written, and requiring index access
        instead would make every GPA calculation harder to read and to check.
        """
        if isinstance(target, ast.Name):
            return (target.id,)
        if isinstance(target, ast.Tuple) and all(isinstance(element, ast.Name) for element in target.elts):
            return tuple(element.id for element in target.elts)  # type: ignore[union-attr]
        raise ComputeError("Only names and flat tuples of names may be comprehension variables")

    def _bind(self, names: tuple[str, ...], value: Any) -> None:
        if len(names) == 1:
            self.scope[names[0]] = value
            return
        _check(isinstance(value, (list, tuple)), "Cannot unpack that value")
        _check(len(value) == len(names), f"Expected {len(names)} values to unpack, got {len(value)}")
        for name, item in zip(names, value, strict=True):
            self.scope[name] = item

    def _comprehend(self, node, emit):
        results: list[Any] = []

        def recurse(index: int) -> None:
            if index == len(node.generators):
                results.append(emit())
                return
            generator = node.generators[index]
            _check(not generator.is_async, "Async comprehensions are not allowed")
            names = self._target_names(generator.target)
            iterable = self.visit(generator.iter)
            _check(isinstance(iterable, (list, tuple, set, str, range)), "Cannot iterate that value")
            _check(len(iterable) <= MAX_SEQUENCE_LENGTH, "Comprehension source is too large")
            missing = object()
            saved = {name: self.scope.get(name, missing) for name in names}
            for value in iterable:
                self._bind(names, value)
                if all(self.visit(condition) for condition in generator.ifs):
                    recurse(index + 1)
            for name, previous in saved.items():
                if previous is missing:
                    self.scope.pop(name, None)
                else:
                    self.scope[name] = previous

        recurse(0)
        return results

    def visit_ListComp(self, node: ast.ListComp) -> Any:
        return self._comprehend(node, lambda: self.visit(node.elt))

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> Any:
        # Materialised rather than lazy: a generator escaping this evaluator
        # would be evaluated later, outside these checks.
        return self._comprehend(node, lambda: self.visit(node.elt))

    def visit_SetComp(self, node: ast.SetComp) -> Any:
        return set(self._comprehend(node, lambda: self.visit(node.elt)))

    def visit_DictComp(self, node: ast.DictComp) -> Any:
        return dict(self._comprehend(node, lambda: (self.visit(node.key), self.visit(node.value))))


def evaluate(expression: str) -> Any:
    """Evaluate one arithmetic expression under the allowlist above."""
    _check(isinstance(expression, str) and expression.strip() != "", "An expression is required")
    _check(len(expression) <= MAX_EXPRESSION_CHARS, f"Expression exceeds {MAX_EXPRESSION_CHARS} characters")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ComputeError(f"Could not parse the expression: {exc.msg}") from exc
    _check(sum(1 for _ in ast.walk(tree)) <= MAX_NODES, "Expression is too complex")
    return _Evaluator().visit(tree)


def compute(expression: str) -> dict:
    """Evaluate an arithmetic expression exactly and return the result.

    Use this for every calculation rather than doing arithmetic yourself:
    weighted averages, credit and ECTS totals, percentages, and date maths on
    numbers. Supports ``+ - * / // % **``, comparisons, lists, tuples, dicts,
    comprehensions, and the functions ``abs round min max sum len sorted pow
    int float any all divmod sqrt floor ceil fabs log exp``.

    Example: ``sum(c * g for c, g in [(3, 4.0), (4, 3.5)]) / sum(c for c, _ in [(3, 4.0), (4, 3.5)])``

    Args:
        expression: A single Python-syntax arithmetic expression. No
            assignments, imports, attribute access, or function definitions.

    Returns:
        ``{"expression": ..., "result": ...}`` on success, or
        ``{"expression": ..., "error": ...}`` if it was rejected.
    """
    try:
        return {"expression": expression, "result": evaluate(expression)}
    except ComputeError as exc:
        return {"expression": expression, "error": str(exc)}
    except Exception as exc:  # arithmetic that raised something unexpected
        return {"expression": expression, "error": f"{exc.__class__.__name__}: {exc}"}
