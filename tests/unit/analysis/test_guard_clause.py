"""Tests for Guard Clause Opportunity Detector."""
from __future__ import annotations

import tempfile

import pytest

from tree_sitter_analyzer.analysis.guard_clause import (
    ISSUE_GUARD_CLAUSE,
    MIN_IF_BODY_STATEMENTS,
    GuardClauseAnalyzer,
    GuardClauseIssue,
    GuardClauseResult,
)

ANALYZER = GuardClauseAnalyzer()


def _analyze(code: str, ext: str = ".py") -> GuardClauseResult:
    with tempfile.NamedTemporaryFile(
        suffix=ext, mode="w", delete=False, encoding="utf-8",
    ) as f:
        f.write(code)
        f.flush()
        return ANALYZER.analyze_file(f.name)


# ── Classification tests ──────────────────────────────────────────────────


class TestClassification:
    def test_issue_type_constant(self) -> None:
        assert ISSUE_GUARD_CLAUSE == "guard_clause_opportunity"


# ── Dataclass tests ──────────────────────────────────────────────────────


class TestDataclasses:
    def test_issue_frozen(self) -> None:
        issue = GuardClauseIssue(
            line_number=5,
            issue_type=ISSUE_GUARD_CLAUSE,
            variable_name="if x:",
            severity="low",
            description="test",
            if_body_lines=5,
        )
        assert issue.line_number == 5
        with pytest.raises(AttributeError):
            issue.line_number = 10  # type: ignore[misc]

    def test_issue_to_dict(self) -> None:
        issue = GuardClauseIssue(
            line_number=3,
            issue_type=ISSUE_GUARD_CLAUSE,
            variable_name="if x:",
            severity="low",
            description="test",
            if_body_lines=4,
        )
        d = issue.to_dict()
        assert d["line_number"] == 3
        assert d["issue_type"] == ISSUE_GUARD_CLAUSE
        assert "suggestion" in d
        assert d["if_body_lines"] == 4

    def test_result_to_dict(self) -> None:
        issue = GuardClauseIssue(
            line_number=1,
            issue_type=ISSUE_GUARD_CLAUSE,
            variable_name="if x:",
            severity="low",
            description="test",
            if_body_lines=3,
        )
        result = GuardClauseResult(
            total_ifs=3,
            issues=(issue,),
            file_path="test.py",
        )
        d = result.to_dict()
        assert d["total_ifs"] == 3
        assert d["issue_count"] == 1

    def test_result_empty(self) -> None:
        result = GuardClauseResult(
            total_ifs=0,
            issues=(),
            file_path="test.py",
        )
        d = result.to_dict()
        assert d["total_ifs"] == 0
        assert d["issue_count"] == 0
        assert d["issues"] == []


# ── Detection tests (Python) ─────────────────────────────────────────────


class TestDetectPython:
    def test_simple_guard_clause_opportunity(self) -> None:
        code = """\
def process(data):
    if data is not None:
        result = transform(data)
        result = validate(result)
        result = format_output(result)
        return result
    else:
        return None
"""
        result = _analyze(code)
        assert result.total_ifs == 1
        assert len(result.issues) == 1
        assert result.issues[0].issue_type == ISSUE_GUARD_CLAUSE

    def test_else_return_in_function(self) -> None:
        code = """\
def handle(request):
    if request.is_valid():
        response = process_request(request)
        response = add_headers(response)
        response = log_response(response)
        return response
    else:
        return error_response("invalid")
"""
        result = _analyze(code)
        assert len(result.issues) == 1

    def test_else_raise_opportunity(self) -> None:
        code = """\
def authenticate(token):
    if token:
        user = decode_token(token)
        user = validate_user(user)
        user = refresh_session(user)
        return user
    else:
        raise AuthError("no token")
"""
        result = _analyze(code)
        assert len(result.issues) == 1

    def test_multiple_guard_opportunities(self) -> None:
        code = """\
def process(items):
    if items:
        first = items[0]
        first = normalize(first)
        first = validate(first)
        return first
    else:
        return None

def process_more(data):
    if data:
        result = transform(data)
        result = clean(result)
        result = format_output(result)
        return result
    else:
        return {}
"""
        result = _analyze(code)
        assert len(result.issues) == 2


# ── Exclusion tests ──────────────────────────────────────────────────────


class TestExclusion:
    def test_if_body_too_short(self) -> None:
        """If body has fewer than MIN_IF_BODY_STATEMENTS, not flagged."""
        code = """\
def process(data):
    if data:
        return transform(data)
    else:
        return None
"""
        result = _analyze(code)
        assert len(result.issues) == 0

    def test_if_body_exactly_min(self) -> None:
        """If body has exactly MIN_IF_BODY_STATEMENTS meaningful stmts, flagged."""
        code = """\
def process(data):
    if data:
        x = transform(data)
        x = validate(x)
        x = format_output(x)
        return x
    else:
        return None
"""
        result = _analyze(code)
        assert len(result.issues) == 1
        assert result.issues[0].if_body_lines >= MIN_IF_BODY_STATEMENTS

    def test_elif_chain_excluded(self) -> None:
        """elif chains should not be flagged."""
        code = """\
def classify(x):
    if x > 10:
        result = "high"
        result = normalize(result)
        result = format_output(result)
        return result
    elif x > 5:
        return "medium"
    else:
        return "low"
"""
        result = _analyze(code)
        assert len(result.issues) == 0

    def test_else_body_not_single_terminal(self) -> None:
        """If else body has more than one statement, not flagged."""
        code = """\
def process(data):
    if data:
        result = transform(data)
        result = validate(result)
        result = format_output(result)
        return result
    else:
        log_error("invalid data")
        return None
"""
        result = _analyze(code)
        assert len(result.issues) == 0

    def test_no_else_branch(self) -> None:
        """if without else is not a guard clause opportunity."""
        code = """\
def process(data):
    if data:
        result = transform(data)
        result = validate(result)
        result = format_output(result)
        return result
"""
        result = _analyze(code)
        assert len(result.issues) == 0

    def test_already_guard_clause(self) -> None:
        """If the if-body is already a guard clause (short), not flagged."""
        code = """\
def process(data):
    if not data:
        return None
    result = transform(data)
    result = validate(result)
    result = format_output(result)
    return result
"""
        result = _analyze(code)
        assert len(result.issues) == 0

    def test_else_continue_not_return(self) -> None:
        """else with continue should also be detected."""
        code = """\
def process_list(items):
    for item in items:
        if item.is_valid():
            result = transform(item)
            result = validate(result)
            result = format_output(result)
            results.append(result)
        else:
            continue
"""
        result = _analyze(code)
        assert len(result.issues) == 1


# ── Multi-language tests ─────────────────────────────────────────────────


class TestMultiLanguage:
    def test_javascript_guard_clause(self) -> None:
        code = """\
function process(data) {
    if (data !== null) {
        let result = transform(data);
        result = validate(result);
        result = formatOutput(result);
        return result;
    } else {
        return null;
    }
}
"""
        result = _analyze(code, ".js")
        assert len(result.issues) == 1

    def test_typescript_guard_clause(self) -> None:
        code = """\
function process(data: string | null): string {
    if (data !== null) {
        let result = transform(data);
        result = validate(result);
        result = formatOutput(result);
        return result;
    } else {
        return "";
    }
}
"""
        result = _analyze(code, ".ts")
        assert len(result.issues) == 1

    def test_java_guard_clause(self) -> None:
        code = """\
public String process(String data) {
    if (data != null) {
        String result = transform(data);
        result = validate(result);
        result = formatOutput(result);
        return result;
    } else {
        return "";
    }
}
"""
        result = _analyze(code, ".java")
        assert len(result.issues) == 1

    def test_go_guard_clause(self) -> None:
        code = """\
func process(data *Data) string {
    if data != nil {
        result := transform(data)
        result = validate(result)
        result = formatOutput(result)
        return result
    } else {
        return ""
    }
}
"""
        result = _analyze(code, ".go")
        assert len(result.issues) == 1

    def test_non_python_no_false_positive(self) -> None:
        """Short if-body in JS should not be flagged."""
        code = """\
function process(data) {
    if (data) {
        return transform(data);
    } else {
        return null;
    }
}
"""
        result = _analyze(code, ".js")
        assert len(result.issues) == 0


# ── Edge cases ────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_file(self) -> None:
        result = ANALYZER.analyze_file("/nonexistent/path.py")
        assert result.total_ifs == 0
        assert len(result.issues) == 0

    def test_unsupported_extension(self) -> None:
        result = ANALYZER.analyze_file("test.rb")
        assert result.total_ifs == 0
        assert len(result.issues) == 0

    def test_empty_file(self) -> None:
        code = ""
        result = _analyze(code)
        assert result.total_ifs == 0
        assert len(result.issues) == 0

    def test_file_with_no_if(self) -> None:
        code = """\
def process(data):
    return data
"""
        result = _analyze(code)
        assert result.total_ifs == 0
        assert len(result.issues) == 0

    def test_nested_if_outer_only(self) -> None:
        """Only the outer if should be flagged if it meets criteria."""
        code = """\
def process(data):
    if data:
        inner = transform(data)
        inner = validate(inner)
        inner = format_output(inner)
        if inner.special:
            return inner.special_value
        else:
            return inner.value
    else:
        return None
"""
        result = _analyze(code)
        # Outer if has guard clause opportunity
        assert len(result.issues) >= 1
        # Inner if body is too short (1 statement), so not flagged
        outer_issues = [i for i in result.issues if i.line_number == 2]
        assert len(outer_issues) == 1

    def test_else_break_in_loop(self) -> None:
        """else with break should be detected as terminal."""
        code = """\
def process(items):
    for item in items:
        if item.is_valid():
            result = transform(item)
            result = validate(result)
            result = format_output(result)
            yield result
        else:
            break
"""
        result = _analyze(code)
        assert len(result.issues) == 1
