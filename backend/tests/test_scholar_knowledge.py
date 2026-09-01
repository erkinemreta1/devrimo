"""How the campus corpus and the general tools reach the Scholar agent.

The load-bearing case is the one where the corpus is *not* available. Three
ordinary situations produce it — no embedding key, SQLite, an admin toggle —
and in all of them Scholar has to come up exactly as it did before this
feature, without a search tool and without instructions describing one. A model
told it can search a corpus that does not exist will claim it looked something
up.
"""

import pytest

from app.agents.runtime import AgentRuntimeConfig, default_runtime_config
from app.agents.scholar.build import build_scholar_agent
from app.agents.scholar.prompt import build_instructions
from app.agents.tools.planning import GradePolicy
from app.knowledge import store as knowledge_store


@pytest.fixture
def corpus_available(monkeypatch):
    monkeypatch.setattr(knowledge_store, "knowledge_available", lambda: True)
    monkeypatch.setattr("app.agents.scholar.build.knowledge_available", lambda: True)


def tool_names(agent) -> set[str]:
    names = set()
    for entry in agent.tools or []:
        name = getattr(entry, "__name__", None) or getattr(entry, "name", None)
        if name:
            names.add(name)
    return names


def test_the_general_tools_are_always_attached():
    agent = build_scholar_agent([])
    assert {"compute", "read_campus_page", "plan_semester"} <= tool_names(agent)


def test_the_search_tool_is_absent_when_no_corpus_is_configured():
    """SQLite and no embedding key is the test suite's own situation."""
    agent = build_scholar_agent([])
    assert agent.knowledge_retriever is None
    assert agent.search_knowledge is False
    assert agent.add_search_knowledge_instructions is False


def test_the_retriever_is_attached_when_the_corpus_is_configured(corpus_available):
    agent = build_scholar_agent([])
    assert agent.knowledge_retriever is not None
    assert agent.search_knowledge is True
    # JSON keeps the source and retrieval time intact; the YAML default reflows
    # Turkish text and quotes it inconsistently.
    assert agent.references_format == "json"


def test_an_admin_toggle_takes_the_corpus_away_without_a_deploy(corpus_available):
    runtime = AgentRuntimeConfig(**{**default_runtime_config().__dict__, "knowledge_enabled": False})
    agent = build_scholar_agent([], runtime)
    assert agent.knowledge_retriever is None


def test_a_feature_flag_can_take_the_corpus_away_mid_incident(corpus_available, monkeypatch):
    monkeypatch.setattr("app.agents.scholar.build.flag_enabled", lambda key, default: False)
    agent = build_scholar_agent([])
    assert agent.knowledge_retriever is None


def test_the_configured_grade_scale_reaches_the_planner():
    """A regulation change is a settings edit, not a deploy."""
    policy = GradePolicy(scale={"A": 10.0, "B": 5.0}, passing_grades=("A", "B"))
    runtime = AgentRuntimeConfig(**{**default_runtime_config().__dict__, "grade_policy": policy})
    agent = build_scholar_agent([], runtime)
    plan = next(entry for entry in agent.tools if getattr(entry, "__name__", "") == "plan_semester")

    result = plan(completed=[{"code": "X", "credits": 2, "grade": "B"}], candidates=[{"code": "Y", "credits": 2}])
    assert result["assumptions"]["assumed_grade"] == "A"
    assert result["projected_gpa"] == 7.5


def test_the_planner_tool_does_not_expose_policy_as_an_argument():
    """The grading rules are the university's, not a conversation's to choose."""
    import inspect

    agent = build_scholar_agent([])
    plan = next(entry for entry in agent.tools if getattr(entry, "__name__", "") == "plan_semester")
    assert "policy" not in inspect.signature(plan).parameters


def test_a_policy_change_invalidates_a_resident_agent():
    base = default_runtime_config()
    changed = AgentRuntimeConfig(**{**base.__dict__, "policy_revision": base.policy_revision + 1})
    assert base.cache_key != changed.cache_key


def test_runtime_config_dict_omits_the_whole_letter_scale():
    """Audit records should show what changed, not bury it under the scale."""
    data = default_runtime_config().as_dict()
    assert "grade_policy" not in data
    assert data["knowledge_enabled"] is True


# --- Instructions -----------------------------------------------------------


def test_corpus_instructions_appear_only_when_the_corpus_does():
    without = " ".join(build_instructions([], corpus_enabled=False))
    with_corpus = " ".join(build_instructions([], corpus_enabled=True))
    assert "search_knowledge_base" not in without
    assert "search_knowledge_base" in with_corpus


def test_the_model_is_told_not_to_answer_dates_from_memory():
    text = " ".join(build_instructions([], corpus_enabled=True))
    assert "Never answer those from memory" in text
    assert "retrieved_at" in text


def test_general_tool_instructions_are_always_present():
    text = " ".join(build_instructions([], corpus_enabled=False))
    assert "compute" in text
    assert "plan_semester" in text
    # Eligibility is gathered by the agent, not invented by the planner.
    assert "prerequisites" in text


def test_an_unconnected_student_is_still_told_public_questions_work():
    """Without METU credentials the agent can still say when Add-Drop is."""
    with_corpus = " ".join(build_instructions([], corpus_enabled=True))
    assert "still answer public campus questions" in with_corpus

    without = " ".join(build_instructions([], corpus_enabled=False))
    assert "still answer public campus questions" not in without
