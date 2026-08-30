"""Run with: python -m evals [--tag smoke|campus|safety]."""

from agno.eval.suite import cli

from app.agents.models import build_model
from app.agents.store import get_agno_db
from evals.cases import build_cases


def main() -> int:
    return cli(
        build_cases(),
        db=get_agno_db(),
        judge_model=build_model(),
        default_timeout=120,
    )


if __name__ == "__main__":
    raise SystemExit(main())
