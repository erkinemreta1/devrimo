import ast
import math
import operator

OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def compute(expression: str) -> float:
    """Evaluate arithmetic without eval, names, attributes, or function calls."""
    if len(expression) > 500:
        raise ValueError("Expression is too long")
    tree = ast.parse(expression, mode="eval")

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            value = OPERATORS[type(node.op)](visit(node.left), visit(node.right))
        elif isinstance(node, ast.UnaryOp) and type(node.op) in OPERATORS:
            value = OPERATORS[type(node.op)](visit(node.operand))
        else:
            raise ValueError("Only arithmetic expressions are allowed")
        if not math.isfinite(float(value)) or abs(float(value)) > 1e100:
            raise ValueError("Result is outside the allowed range")
        return value

    return float(visit(tree))
