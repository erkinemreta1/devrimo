"""Deterministic semester planning: what a course set does to a student's GPA.

"What is the maximum GPA I can achieve next semester?" is not a retrieval
question and it is not one the model should answer by reasoning about numbers
in prose. It is a small optimisation over data the agent has already gathered —
the transcript from SAIS, the offered courses from the course catalog, the
prerequisites the student meets — and it has a right answer.

This module is that optimisation, as a **pure function of the data it is
given**. It does not scrape, does not query SAIS, and does not decide what a
student is eligible for: the agent gathers all of that through the campus MCP
servers, applies whatever extra conditions the student stated, and passes the
result in. That split is what keeps this testable against a hand-checked
transcript, and keeps one wrong answer from being a scraping bug.

The rules it applies are not compiled in. METU's letter scale, whether the
average weights METU credits or ECTS, and whether a retake replaces the earlier
attempt are set by regulation and change by regulation, so they arrive as a
:class:`GradePolicy` loaded from an admin-editable row.

The optimisation itself is a small dynamic program rather than a greedy pick,
because "take the highest-credit courses" is wrong whenever retakes are in
play: repeating a course the student failed removes its old contribution as
well as adding a new one, so a 3-credit retake of an FF can lift the average
more than a 4-credit new course.
"""

from dataclasses import dataclass, field
from typing import Any

# METU's scale, used when no policy row has been configured yet. Present as a
# fallback only — the admin-editable row is the authority.
DEFAULT_SCALE: dict[str, float] = {
    "AA": 4.0,
    "BA": 3.5,
    "BB": 3.0,
    "CB": 2.5,
    "CC": 2.0,
    "DC": 1.5,
    "DD": 1.0,
    "FD": 0.5,
    "FF": 0.0,
    "NA": 0.0,
}
# Grades that carry neither points nor credits toward the average.
DEFAULT_NON_GRADED: tuple[str, ...] = ("W", "EX", "S", "U", "I", "P", "NI", "T")
DEFAULT_PASSING: tuple[str, ...] = ("AA", "BA", "BB", "CB", "CC", "DC", "DD")


@dataclass(frozen=True)
class GradePolicy:
    """The grading rules in force, as configured."""

    scale: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_SCALE))
    non_graded: tuple[str, ...] = DEFAULT_NON_GRADED
    passing_grades: tuple[str, ...] = DEFAULT_PASSING
    weight_basis: str = "credit"
    retake_replaces: bool = True
    max_credits_per_semester: int = 40

    @property
    def top_grade(self) -> str:
        return max(self.scale, key=lambda letter: self.scale[letter]) if self.scale else "AA"

    @property
    def top_points(self) -> float:
        return max(self.scale.values()) if self.scale else 4.0

    def points_for(self, grade: str) -> float | None:
        """Points for a letter, or ``None`` if it does not count toward the average."""
        letter = (grade or "").strip().upper()
        if not letter or letter in {value.upper() for value in self.non_graded}:
            return None
        return self.scale.get(letter)


@dataclass
class _Course:
    code: str
    weight: float
    grade: str | None = None
    points: float | None = None


def _weight_of(entry: dict, basis: str) -> float:
    """Credits for one course under the configured weighting basis."""
    key = "ects" if basis == "ects" else "credits"
    value = entry.get(key)
    if value is None:
        # Falling back keeps a partly-filled transcript usable rather than
        # silently weighting those courses as zero.
        value = entry.get("credits") if key == "ects" else entry.get("ects")
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _normalise_completed(completed: list[dict], policy: GradePolicy) -> list[_Course]:
    courses: list[_Course] = []
    for entry in completed or []:
        code = str(entry.get("code") or entry.get("course_code") or "").strip().upper()
        if not code:
            continue
        grade = str(entry.get("grade") or "").strip().upper()
        courses.append(
            _Course(
                code=code,
                weight=_weight_of(entry, policy.weight_basis),
                grade=grade,
                points=policy.points_for(grade),
            )
        )
    return courses


def current_average(completed: list[dict], policy: GradePolicy) -> dict[str, float]:
    """The student's average as it stands, from graded courses only."""
    courses = _normalise_completed(completed, policy)
    graded = [course for course in courses if course.points is not None and course.weight > 0]
    total_weight = sum(course.weight for course in graded)
    total_points = sum(course.weight * (course.points or 0.0) for course in graded)
    return {
        "graded_credits": round(total_weight, 2),
        "quality_points": round(total_points, 3),
        "gpa": round(total_points / total_weight, 3) if total_weight else 0.0,
    }


@dataclass(frozen=True)
class _Option:
    """One candidate course, as the optimiser sees it."""

    code: str
    enrolled_weight: float
    weight_delta: float
    point_delta: float
    is_retake: bool
    replaced_grade: str | None


def _build_options(
    candidates: list[dict],
    completed: list[_Course],
    policy: GradePolicy,
    *,
    assumed_grade: str | None,
) -> list[_Option]:
    points = policy.scale.get((assumed_grade or policy.top_grade).upper(), policy.top_points)
    # Only the latest attempt of a repeated course is what a retake replaces.
    prior: dict[str, _Course] = {}
    for course in completed:
        if course.points is not None:
            prior[course.code] = course

    options: list[_Option] = []
    for entry in candidates or []:
        code = str(entry.get("code") or entry.get("course_code") or "").strip().upper()
        if not code:
            continue
        weight = _weight_of(entry, policy.weight_basis)
        previous = prior.get(code) if policy.retake_replaces else None
        removed_weight = previous.weight if previous else 0.0
        removed_points = (previous.weight * (previous.points or 0.0)) if previous else 0.0
        options.append(
            _Option(
                code=code,
                enrolled_weight=weight,
                weight_delta=weight - removed_weight,
                point_delta=weight * points - removed_points,
                is_retake=previous is not None,
                replaced_grade=previous.grade if previous else None,
            )
        )
    return options


def _best_combination(
    options: list[_Option],
    *,
    base_weight: float,
    base_points: float,
    max_enrolled: float,
    min_enrolled: float,
    max_courses: int | None,
    required: set[str],
) -> tuple[list[_Option], float]:
    """Choose the subset that maximises the resulting average.

    A dynamic program over (enrolled credits, weight delta) keeping the best
    achievable quality-point delta for each state. Both axes are bounded by the
    semester credit cap, so the state space is small; what it buys is
    correctness in the case a greedy heuristic gets wrong, where dropping an old
    FF matters more than adding another course.

    Weights are scaled to integers because credits come in halves and floating
    point keys would collide unpredictably.
    """
    scale = 2  # half-credit granularity
    required_options = [option for option in options if option.code in required]
    optional = [option for option in options if option.code not in required]

    forced_enrolled = sum(option.enrolled_weight for option in required_options)
    if forced_enrolled > max_enrolled:
        # The student asked for more than the cap allows; the caller reports it.
        return required_options, -1.0

    states: dict[tuple[int, int], tuple[float, list[_Option]]] = {
        (
            round(forced_enrolled * scale),
            round(sum(option.weight_delta for option in required_options) * scale),
        ): (sum(option.point_delta for option in required_options), list(required_options))
    }

    budget = round(max_enrolled * scale)
    for option in optional:
        enrolled_step = round(option.enrolled_weight * scale)
        weight_step = round(option.weight_delta * scale)
        for (enrolled, weight_delta), (point_delta, chosen) in list(states.items()):
            if enrolled + enrolled_step > budget:
                continue
            if max_courses is not None and len(chosen) + 1 > max_courses:
                continue
            key = (enrolled + enrolled_step, weight_delta + weight_step)
            candidate_points = point_delta + option.point_delta
            best = states.get(key)
            if best is None or candidate_points > best[0]:
                states[key] = (candidate_points, [*chosen, option])

    best_choice: list[_Option] = list(required_options)
    best_gpa = -1.0
    for (enrolled, weight_delta), (point_delta, chosen) in states.items():
        if enrolled < round(min_enrolled * scale):
            continue
        total_weight = base_weight + weight_delta / scale
        if total_weight <= 0:
            continue
        gpa = (base_points + point_delta) / total_weight
        if gpa > best_gpa:
            best_gpa, best_choice = gpa, chosen
    return best_choice, best_gpa


def plan_semester(
    completed: list[dict],
    candidates: list[dict],
    max_credits: float | None = None,
    min_credits: float = 0,
    max_courses: int | None = None,
    required_courses: list[str] | None = None,
    assumed_grade: str | None = None,
    policy: GradePolicy | None = None,
) -> dict[str, Any]:
    """Compute the best achievable GPA for a set of candidate courses.

    Call this instead of doing the arithmetic in prose. Gather ``completed``
    from the SAIS transcript and ``candidates`` from the courses the student is
    actually eligible for and that are actually offered — check offerings and
    prerequisites with the campus tools *first*, and pass only eligible courses
    in. Every constraint the student stated must be passed through, not applied
    afterwards.

    Args:
        completed: Courses already taken, as
            ``[{"code": "MATH119", "credits": 5, "ects": 7.5, "grade": "BB"}]``.
        candidates: Courses that could be taken next semester, same shape
            without ``grade``.
        max_credits: Credit ceiling for the semester. Defaults to the
            configured maximum.
        min_credits: Minimum credits the plan must reach, if the student said one.
        max_courses: Cap on the number of courses, if the student said one.
        required_courses: Course codes that must be in the plan.
        assumed_grade: Grade to assume for every chosen course. Defaults to the
            highest grade on the scale, which is what "maximum GPA" means.
        policy: Grading rules. Defaults to the configured policy.

    Returns:
        Current standing, the chosen courses, the resulting GPA, and the
        assumptions the result depends on.
    """
    policy = policy or GradePolicy()
    ceiling = float(max_credits if max_credits is not None else policy.max_credits_per_semester)
    required = {str(code).strip().upper() for code in (required_courses or []) if str(code).strip()}

    standing = current_average(completed, policy)
    completed_courses = _normalise_completed(completed, policy)
    options = _build_options(candidates, completed_courses, policy, assumed_grade=assumed_grade)

    unknown_required = required - {option.code for option in options}
    chosen, projected = _best_combination(
        options,
        base_weight=standing["graded_credits"],
        base_points=standing["quality_points"],
        max_enrolled=ceiling,
        min_enrolled=float(min_credits or 0),
        max_courses=max_courses,
        required=required,
    )

    grade = (assumed_grade or policy.top_grade).upper()
    enrolled = sum(option.enrolled_weight for option in chosen)
    warnings: list[str] = []
    if unknown_required:
        warnings.append(f"Required courses not among the candidates: {', '.join(sorted(unknown_required))}")
    if projected < 0:
        warnings.append("No combination satisfies the constraints; try relaxing the credit limits.")
    if not options:
        warnings.append("No candidate courses were supplied, so nothing could be planned.")

    return {
        "current": standing,
        "assumptions": {
            "assumed_grade": grade,
            "assumed_grade_points": policy.scale.get(grade, policy.top_points),
            "weight_basis": policy.weight_basis,
            "retake_replaces": policy.retake_replaces,
            "max_credits": ceiling,
            "min_credits": min_credits,
            "max_courses": max_courses,
            "required_courses": sorted(required),
            "eligibility_checked_by_caller": True,
        },
        "selected_courses": [
            {
                "code": option.code,
                "credits": option.enrolled_weight,
                "is_retake": option.is_retake,
                "replaces_grade": option.replaced_grade,
            }
            for option in sorted(chosen, key=lambda option: option.code)
        ],
        "selected_credits": round(enrolled, 2),
        "projected_gpa": round(projected, 3) if projected >= 0 else None,
        "gpa_change": round(projected - standing["gpa"], 3) if projected >= 0 else None,
        "warnings": warnings,
    }


def make_plan_semester_tool(policy: GradePolicy):
    """Bind the configured policy into the tool the model actually sees.

    A closure rather than a ``partial`` because Agno builds the tool schema by
    inspecting the signature, and the model must not be offered a ``policy``
    parameter it could fill in — the grading rules are the university's, not
    something a conversation gets to choose.
    """

    def plan_semester_tool(
        completed: list[dict],
        candidates: list[dict],
        max_credits: float | None = None,
        min_credits: float = 0,
        max_courses: int | None = None,
        required_courses: list[str] | None = None,
        assumed_grade: str | None = None,
    ) -> dict:
        return plan_semester(
            completed=completed,
            candidates=candidates,
            max_credits=max_credits,
            min_credits=min_credits,
            max_courses=max_courses,
            required_courses=required_courses,
            assumed_grade=assumed_grade,
            policy=policy,
        )

    plan_semester_tool.__name__ = "plan_semester"
    plan_semester_tool.__doc__ = plan_semester.__doc__
    return plan_semester_tool
