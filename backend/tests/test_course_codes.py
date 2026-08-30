from app.campus.course_codes import annotate_course_codes, display_course_code
from app.agents.scholar.hooks import _is_course_data_tool


def test_converts_known_numeric_course_code():
    assert display_course_code("5670201") == "EE201"


def test_annotates_known_codes_without_losing_source_identifier():
    result = {"courses": ["5670201", {"title": "5670201 Signals"}]}

    assert annotate_course_codes(result) == {
        "courses": ["5670201 (EE201)", {"title": "5670201 (EE201) Signals"}]
    }


def test_leaves_unknown_departments_and_longer_numbers_unchanged():
    assert display_course_code("9990201") is None
    assert annotate_course_codes("9990201 15670201 56702010") == "9990201 15670201 56702010"


def test_recognizes_mcp_prefixed_course_tools():
    assert _is_course_data_tool("sais_get_transcript") is True
    assert _is_course_data_tool("course_info_get_course_info") is True
    assert _is_course_data_tool("webmail_read_email") is False
