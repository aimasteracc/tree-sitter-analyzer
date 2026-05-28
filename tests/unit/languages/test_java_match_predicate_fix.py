"""
TDD tests for Java #match? predicate fix in execute_newest_api.

The bug: tree-sitter 0.25+ QueryCursor.matches() returns raw AST matches
WITHOUT applying custom predicates like #match?. This causes spring_controller,
jpa_entity, etc. to return 0 results (or all classes, depending on implementation).

Fix (Option A): Post-filter matches by manually applying #match? predicates
using re.search() in execute_newest_api.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Unit tests for _extract_match_predicates (new helper function)
# ---------------------------------------------------------------------------


class TestExtractMatchPredicates:
    """Unit tests for the predicate extraction helper."""

    def _extract(self, query_string: str) -> dict:
        from tree_sitter_analyzer.utils._tree_sitter_compat_helpers import (
            _extract_match_predicates,
        )

        return _extract_match_predicates(query_string)

    def test_single_predicate(self):
        q = '(identifier) @name\n(#match? @name "^Controller$")'
        result = self._extract(q)
        assert result == {"name": ["^Controller$"]}

    def test_multiple_predicates_same_capture(self):
        q = '(identifier) @name\n(#match? @name "^Controller$")\n(#match? @name "Rest")'
        result = self._extract(q)
        assert result == {"name": ["^Controller$", "Rest"]}

    def test_multiple_captures(self):
        q = '(identifier) @ann\n(#match? @ann "Controller")\n(identifier) @name'
        result = self._extract(q)
        assert "ann" in result
        assert result["ann"] == ["Controller"]

    def test_no_predicates(self):
        q = "(class_declaration name: (identifier) @name) @class"
        result = self._extract(q)
        assert result == {}

    def test_ignores_other_predicates(self):
        q = '(identifier) @name\n(#eq? @name "Foo")\n(#match? @name "Bar")'
        result = self._extract(q)
        # Only #match? should be extracted
        assert result == {"name": ["Bar"]}


# ---------------------------------------------------------------------------
# Unit tests for _apply_match_predicates (new helper function)
# ---------------------------------------------------------------------------


class TestApplyMatchPredicates:
    """Unit tests for predicate application helper."""

    def _apply(self, captures_dict: dict, predicates: dict) -> bool:
        from tree_sitter_analyzer.utils._tree_sitter_compat_helpers import (
            _apply_match_predicates,
        )

        return _apply_match_predicates(captures_dict, predicates)

    def _mock_node(self, text: str):
        """Create a minimal mock node with .text attribute."""

        class FakeNode:
            def __init__(self, t: str):
                self.text = t.encode("utf-8")

        return FakeNode(text)

    def test_passing_predicate(self):
        node = self._mock_node("Controller")
        assert self._apply({"ann": [node]}, {"ann": ["Controller"]}) is True

    def test_failing_predicate(self):
        node = self._mock_node("Service")
        assert self._apply({"ann": [node]}, {"ann": ["^Controller$"]}) is False

    def test_missing_capture_fails(self):
        # Predicate references a capture not in this match → reject
        assert self._apply({}, {"ann": ["Controller"]}) is False

    def test_empty_predicates_passes(self):
        node = self._mock_node("anything")
        assert self._apply({"name": [node]}, {}) is True

    def test_multiple_patterns_all_must_match(self):
        node = self._mock_node("RestController")
        # Both patterns must match for the predicate to pass
        assert self._apply({"ann": [node]}, {"ann": ["Controller", "Rest"]}) is True
        assert self._apply({"ann": [node]}, {"ann": ["Controller", "^Plain$"]}) is False


# ---------------------------------------------------------------------------
# Integration: execute_newest_api with real tree-sitter + Java grammar
# ---------------------------------------------------------------------------


SPRING_CONTROLLER_SRC = """\
import org.springframework.stereotype.Controller;
import org.springframework.stereotype.Service;

@Controller
public class OwnerController {
    public void list() {}
}

@Service
public class OwnerService {
    public void save() {}
}
"""

JPA_ENTITY_SRC = """\
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class Owner {
    @Id
    private Long id;
}
"""


@pytest.fixture
def java_lang():
    try:
        import tree_sitter
        import tree_sitter_java as java_ts

        lang = tree_sitter.Language(java_ts.language())
        # tracked: QueryCursor requires tree-sitter 0.25+; older installs skip gracefully
        if not hasattr(tree_sitter, "QueryCursor"):
            pytest.skip("QueryCursor (tree-sitter 0.25+) not available")
        return lang
    except ImportError:
        pytest.skip("tree_sitter_java not available")  # tracked: optional dev dep


@pytest.fixture
def java_tree(java_lang):
    import tree_sitter

    def _parse(src: str):
        parser = tree_sitter.Parser(java_lang)
        return parser.parse(src.encode("utf-8"))

    return _parse  # tracked: skipped by java_lang fixture when ts<0.25


class TestExecuteNewestApiMatchPredicate:
    """execute_newest_api must filter results by #match? predicates."""

    def test_spring_controller_query_returns_only_controller(
        self, java_lang, java_tree
    ):
        """spring_controller query must return only @Controller classes, not @Service."""
        import tree_sitter

        from tree_sitter_analyzer.queries.java import JAVA_QUERIES
        from tree_sitter_analyzer.utils._tree_sitter_compat_helpers import (
            execute_newest_api,
        )

        query_string = JAVA_QUERIES["spring_controller"]
        query = tree_sitter.Query(java_lang, query_string)
        tree = java_tree(SPRING_CONTROLLER_SRC)

        results = execute_newest_api(query, tree.root_node, query_string=query_string)

        # Should get captures — at least @controller_name
        controller_names = [
            node.text.decode() for node, cap in results if cap == "controller_name"
        ]
        assert controller_names, (
            f"No controller_name captures found. Got: {[(n.text, c) for n, c in results[:5]]}"
        )
        assert "OwnerController" in controller_names, (
            f"OwnerController not found in {controller_names}"
        )
        assert "OwnerService" not in controller_names, (
            f"@Service class OwnerService should be excluded by #match? predicate, "
            f"but found in {controller_names}"
        )

    def test_jpa_entity_query_returns_entity(self, java_lang, java_tree):
        """jpa_entity query must return @Entity classes."""
        import tree_sitter

        from tree_sitter_analyzer.queries.java import JAVA_QUERIES
        from tree_sitter_analyzer.utils._tree_sitter_compat_helpers import (
            execute_newest_api,
        )

        query_string = JAVA_QUERIES["jpa_entity"]
        query = tree_sitter.Query(java_lang, query_string)
        tree = java_tree(JPA_ENTITY_SRC)

        results = execute_newest_api(query, tree.root_node, query_string=query_string)
        entity_names = [
            node.text.decode() for node, cap in results if cap == "entity_name"
        ]
        assert "Owner" in entity_names, (
            f"Expected 'Owner' in entity_names, got {entity_names}"
        )

    def test_backward_compat_no_query_string(self, java_lang, java_tree):
        """execute_newest_api must work when query_string is omitted (no crash, but may not filter)."""
        import tree_sitter

        from tree_sitter_analyzer.utils._tree_sitter_compat_helpers import (
            execute_newest_api,
        )

        # Simple query without predicates
        query = tree_sitter.Query(java_lang, "(identifier) @id")
        tree = java_tree("class Foo {}")
        # Must not raise
        results = execute_newest_api(query, tree.root_node)
        assert isinstance(results, list)
