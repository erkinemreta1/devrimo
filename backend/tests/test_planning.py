"""The semester planner, against transcripts checked by hand.

Every expected number below was worked out on paper first. That is the point of
having an engine at all: "what is the maximum GPA I can reach" has one right
answer, and a plausible-looking wrong one is worse than no answer.
"""

import pytest

from app.agents.tools.planning import GradePolicy, current_average, plan_semester

# 3 credits of AA (4.0) = 12, 4 of BB (3.0) = 12, 3 of CC (2.0) = 6.
# 30 quality points over 10 credits = 3.00 exactly.
TRANSCRIPT = [
    {"code": "MATH119", "credits": 3, "grade": "AA"},
    {"code": "CENG111", "credits": 4, "grade": "BB"},
    {"code": "PHYS105", "credits": 3, "grade": "CC"},
]


def test_current_average_is_credit_weighted():
    standing = current_average(TRANSCRIPT, GradePolicy())
    assert standing["graded_credits"] == 10
    assert standing["quality_points"] == 30.0
    assert standing["gpa"] == 3.0


def test_non_graded_letters_are_excluded_from_the_average():
    """A withdrawn or exempt course carries neither points nor credits."""
    transcript = [
        *TRANSCRIPT,
        {"code": "HIST200", "credits": 4, "grade": "W"},
        {"code": "IS100", "credits": 3, "grade": "EX"},
    ]
    assert current_average(transcript, GradePolicy()) == current_average(TRANSCRIPT, GradePolicy())


def test_ects_basis_changes_the_weighting():
    transcript = [
        {"code": "A", "credits": 3, "ects": 6, "grade": "AA"},
        {"code": "B", "credits": 3, "ects": 3, "grade": "CC"},
    ]
    by_credit = current_average(transcript, GradePolicy(weight_basis="credit"))
    by_ects = current_average(transcript, GradePolicy(weight_basis="ects"))
    assert by_credit["gpa"] == 3.0
    # 6 ECTS of 4.0 plus 3 of 2.0 = 30 over 9 = 3.333.
    assert by_ects["gpa"] == pytest.approx(3.333, abs=0.001)


def test_taking_everything_at_the_top_grade_maximises_the_average():
    """With no retakes, more top-graded credits always move the average up."""
    result = plan_semester(
        completed=TRANSCRIPT,
        candidates=[{"code": "CENG213", "credits": 4}, {"code": "CENG223", "credits": 4}],
        max_credits=8,
    )
    assert result["assumptions"]["assumed_grade"] == "AA"
    assert {course["code"] for course in result["selected_courses"]} == {"CENG213", "CENG223"}
    # 30 + 32 = 62 quality points over 18 credits.
    assert result["projected_gpa"] == pytest.approx(62 / 18, abs=0.001)
    assert result["gpa_change"] > 0


def test_a_retake_can_beat_a_larger_new_course():
    """This is the case a greedy "take the most credits" heuristic gets wrong.

    Retaking the 3-credit CC removes 6 quality points and 3 credits from the
    record before adding 12 and 3 back: 36 points over 10 credits, a 3.60.
    Adding the 4-credit new course instead gives 46 over 14, a 3.29. The
    smaller course is the better one, and only because it is a retake.
    """
    result = plan_semester(
        completed=TRANSCRIPT,
        candidates=[{"code": "PHYS105", "credits": 3}, {"code": "CENG213", "credits": 4}],
        max_credits=4,
    )
    assert [course["code"] for course in result["selected_courses"]] == ["PHYS105"]
    assert result["selected_courses"][0]["is_retake"] is True
    assert result["selected_courses"][0]["replaces_grade"] == "CC"
    assert result["projected_gpa"] == pytest.approx(3.6, abs=0.001)


def test_retake_replacement_can_be_turned_off_by_policy():
    """Some regulations average attempts instead of replacing them."""
    policy = GradePolicy(retake_replaces=False)
    result = plan_semester(
        completed=TRANSCRIPT,
        candidates=[{"code": "PHYS105", "credits": 3}],
        max_credits=3,
        policy=policy,
    )
    # The old CC still counts: 30 + 12 = 42 over 13 credits.
    assert result["projected_gpa"] == pytest.approx(42 / 13, abs=0.001)


def test_credit_ceiling_is_respected():
    result = plan_semester(
        completed=TRANSCRIPT,
        candidates=[{"code": "A", "credits": 4}, {"code": "B", "credits": 4}, {"code": "C", "credits": 4}],
        max_credits=8,
    )
    assert result["selected_credits"] <= 8


def test_required_courses_are_always_included():
    """A condition the student stated is a constraint, not a preference.

    DD501 lowers the average, so an optimiser left to itself would drop it.
    """
    result = plan_semester(
        completed=TRANSCRIPT,
        candidates=[{"code": "CENG213", "credits": 4}, {"code": "DD501", "credits": 3}],
        max_credits=7,
        required_courses=["DD501"],
        assumed_grade="DD",
    )
    assert "DD501" in {course["code"] for course in result["selected_courses"]}


def test_a_required_course_that_is_not_a_candidate_is_reported():
    result = plan_semester(
        completed=TRANSCRIPT,
        candidates=[{"code": "CENG213", "credits": 4}],
        required_courses=["CENG315"],
    )
    assert any("CENG315" in warning for warning in result["warnings"])


def test_course_count_limit_is_respected():
    result = plan_semester(
        completed=TRANSCRIPT,
        candidates=[{"code": f"C{index}", "credits": 3} for index in range(6)],
        max_credits=30,
        max_courses=2,
    )
    assert len(result["selected_courses"]) == 2


def test_minimum_credits_is_honoured():
    result = plan_semester(
        completed=TRANSCRIPT,
        candidates=[{"code": "A", "credits": 3}, {"code": "B", "credits": 4}, {"code": "C", "credits": 3}],
        max_credits=10,
        min_credits=9,
    )
    assert result["selected_credits"] >= 9


def test_an_assumed_grade_other_than_the_top_is_used():
    result = plan_semester(
        completed=TRANSCRIPT,
        candidates=[{"code": "CENG213", "credits": 4}],
        max_credits=4,
        assumed_grade="BB",
    )
    assert result["assumptions"]["assumed_grade"] == "BB"
    assert result["assumptions"]["assumed_grade_points"] == 3.0
    # 30 + 12 = 42 over 14 credits.
    assert result["projected_gpa"] == pytest.approx(3.0, abs=0.001)


def test_no_candidates_is_reported_rather_than_answered():
    result = plan_semester(completed=TRANSCRIPT, candidates=[])
    assert result["selected_courses"] == []
    assert any("No candidate" in warning for warning in result["warnings"])
    assert result["current"]["gpa"] == 3.0


def test_an_empty_transcript_does_not_divide_by_zero():
    result = plan_semester(completed=[], candidates=[{"code": "A", "credits": 3}], max_credits=3)
    assert result["current"]["gpa"] == 0.0
    assert result["projected_gpa"] == 4.0


def test_a_custom_scale_from_policy_is_used():
    """The scale is the university's, and it is configuration."""
    policy = GradePolicy(scale={"A": 10.0, "B": 5.0}, passing_grades=("A", "B"))
    result = plan_semester(
        completed=[{"code": "X", "credits": 2, "grade": "B"}],
        candidates=[{"code": "Y", "credits": 2}],
        max_credits=2,
        policy=policy,
    )
    assert result["assumptions"]["assumed_grade"] == "A"
    assert result["current"]["gpa"] == 5.0
    assert result["projected_gpa"] == 7.5


def test_the_result_states_what_it_assumed():
    """The agent has to report these; they are not implementation detail."""
    result = plan_semester(completed=TRANSCRIPT, candidates=[{"code": "A", "credits": 3}], max_credits=3)
    assumptions = result["assumptions"]
    assert assumptions["weight_basis"] == "credit"
    assert assumptions["retake_replaces"] is True
    assert assumptions["eligibility_checked_by_caller"] is True
