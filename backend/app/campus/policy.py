"""The university's grading rules, loaded from the admin-editable row.

Same shape as :mod:`app.agents.runtime`: the database is the authority and the
constants in :mod:`app.agents.tools.planning` are only the fallback for a
deployment that has never been configured. Keeping the scale out of code is not
tidiness — a regulation change would otherwise make "what is the maximum GPA I
can reach" a deploy, and a wrong answer a code bug instead of a settings fix.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.planning import DEFAULT_NON_GRADED, DEFAULT_PASSING, DEFAULT_SCALE, GradePolicy
from app.db.models import CampusGradePolicy

POLICY_ID = "default"


def policy_from_row(row: CampusGradePolicy | None) -> GradePolicy:
    if row is None:
        return GradePolicy()
    scale = {str(letter).upper(): float(points) for letter, points in (row.scale or {}).items()}
    return GradePolicy(
        scale=scale or dict(DEFAULT_SCALE),
        non_graded=tuple(row.non_graded or DEFAULT_NON_GRADED),
        passing_grades=tuple(row.passing_grades or DEFAULT_PASSING),
        weight_basis=row.weight_basis or "credit",
        retake_replaces=bool(row.retake_replaces),
        max_credits_per_semester=int(row.max_credits_per_semester or 40),
    )


async def load_grade_policy(db: AsyncSession) -> tuple[GradePolicy, int]:
    """The policy in force and its revision, for cache invalidation."""
    row = await db.get(CampusGradePolicy, POLICY_ID)
    return policy_from_row(row), (row.revision if row else 0)


async def ensure_policy_seeded(db: AsyncSession) -> bool:
    """Write METU's scale on first run, and never overwrite an edit."""
    if await db.get(CampusGradePolicy, POLICY_ID) is not None:
        return False
    db.add(
        CampusGradePolicy(
            id=POLICY_ID,
            scale=dict(DEFAULT_SCALE),
            non_graded=list(DEFAULT_NON_GRADED),
            passing_grades=list(DEFAULT_PASSING),
            weight_basis="credit",
            retake_replaces=True,
            max_credits_per_semester=40,
            revision=1,
            notes="METU 4.00 letter scale. Verify against the current Registrar's regulations.",
        )
    )
    await db.commit()
    return True


def policy_as_dict(policy: GradePolicy) -> dict:
    return {
        "scale": dict(policy.scale),
        "non_graded": list(policy.non_graded),
        "passing_grades": list(policy.passing_grades),
        "weight_basis": policy.weight_basis,
        "retake_replaces": policy.retake_replaces,
        "max_credits_per_semester": policy.max_credits_per_semester,
    }
