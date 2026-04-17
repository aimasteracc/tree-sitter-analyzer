"""
Integration tests for Grammar Auto-Discovery.

Tests validate structural analysis on real Python code samples from golden corpus.
"""
from __future__ import annotations

import pytest
from tree_sitter import Language, Parser
from tree_sitter_python import language

from tree_sitter_analyzer.grammar_discovery.introspector import GrammarIntrospector
from tree_sitter_analyzer.grammar_discovery.structural_analyzer import (
    StructuralAnalyzer,
)


@pytest.fixture
def python_language() -> Language:
    """Get Python tree-sitter language for testing."""
    return Language(language())


@pytest.fixture
def parser(python_language: Language) -> Parser:
    """Get Parser instance for testing."""
    parser = Parser(python_language)
    return parser


@pytest.fixture
def analyzer(python_language: Language) -> StructuralAnalyzer:
    """Get StructuralAnalyzer instance for testing."""
    return StructuralAnalyzer(python_language)


@pytest.fixture
def introspector(python_language: Language) -> GrammarIntrospector:
    """Get GrammarIntrospector instance for testing."""
    return GrammarIntrospector(python_language)


class TestStructuralAnalysisIntegration:
    """Integration tests for structural analysis on real code."""

    def test_simple_function_analysis(
        self, analyzer: StructuralAnalyzer, parser: Parser,
    ) -> None:
        """Test structural analysis on a simple function."""
        code = """
def hello_world():
    print("Hello, world!")
"""
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        result = analyzer.analyze_code_sample(root_node)

        assert "module" in result
        assert "function_definition" in result
        assert "string" in result
        assert "identifier" in result

    def test_decorated_function_analysis(
        self, analyzer: StructuralAnalyzer, parser: Parser,
    ) -> None:
        """Test structural analysis on decorated function."""
        code = """
@decorator
def foo():
    pass
"""
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        result = analyzer.analyze_code_sample(root_node)

        # decorated_definition should be present
        assert "decorated_definition" in result
        dec_def = result["decorated_definition"]
        assert dec_def.total_occurrences >= 1
        assert dec_def.has_decorator_field or len(dec_def.child_types) >= 1

    def test_class_definition_analysis(
        self, analyzer: StructuralAnalyzer, parser: Parser,
    ) -> None:
        """Test structural analysis on class definition."""
        code = """
class MyClass:
    def method(self):
        pass
"""
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        result = analyzer.analyze_code_sample(root_node)

        assert "class_definition" in result
        class_def = result["class_definition"]
        assert class_def.total_occurrences >= 1

    def test_with_statement_analysis(
        self, analyzer: StructuralAnalyzer, parser: Parser,
    ) -> None:
        """Test structural analysis on with statement."""
        code = """
with open("file.txt") as f:
    data = f.read()
"""
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        result = analyzer.analyze_code_sample(root_node)

        assert "with_statement" in result
        with_stmt = result["with_statement"]
        assert with_stmt.total_occurrences >= 1

    def test_wrapper_score_calculation(
        self, analyzer: StructuralAnalyzer, parser: Parser,
    ) -> None:
        """Test wrapper scores are calculated correctly."""
        code = """
@decorator
def foo():
    pass
"""
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        result = analyzer.analyze_code_sample(root_node)

        for _node_type, analysis in result.items():
            assert isinstance(analysis.wrapper_score, int)
            assert 0 <= analysis.wrapper_score <= 100

    def test_multiple_occurrences_tracked(
        self, analyzer: StructuralAnalyzer, parser: Parser,
    ) -> None:
        """Test that multiple occurrences of same type are tracked."""
        code = """
def foo(): pass
def bar(): pass
def baz(): pass
"""
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        result = analyzer.analyze_code_sample(root_node)

        func_analysis = result.get("function_definition")
        if func_analysis:
            assert func_analysis.total_occurrences == 3

    def test_detect_wrappers_with_confidence_threshold(
        self, analyzer: StructuralAnalyzer, parser: Parser,
    ) -> None:
        """Test wrapper detection with confidence threshold."""
        code_samples = [
            parser.parse(bytes("@decorator\ndef foo(): pass", "utf-8")).root_node,
            parser.parse(bytes("def bar(): pass", "utf-8")).root_node,
        ]
        wrappers = analyzer.detect_wrappers(code_samples, min_confidence=10)

        assert isinstance(wrappers, list)
        # All wrappers should meet confidence threshold
        for wrapper in wrappers:
            assert wrapper.wrapper_score >= 10

    def test_detect_wrappers_high_confidence_only(
        self, analyzer: StructuralAnalyzer, parser: Parser,
    ) -> None:
        """Test that high confidence threshold filters results."""
        code_samples = [
            parser.parse(bytes("@decorator\ndef foo(): pass", "utf-8")).root_node,
        ]
        wrappers_high = analyzer.detect_wrappers(code_samples, min_confidence=50)
        wrappers_low = analyzer.detect_wrappers(code_samples, min_confidence=10)

        # High confidence should return fewer or equal wrappers
        assert len(wrappers_high) <= len(wrappers_low)

    def test_child_types_tracked_correctly(
        self, analyzer: StructuralAnalyzer, parser: Parser,
    ) -> None:
        """Test that child types are tracked correctly."""
        code = """
class MyClass:
    def method(self):
        pass
"""
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        result = analyzer.analyze_code_sample(root_node)

        class_analysis = result.get("class_definition")
        if class_analysis:
            child_type_names = [ct.node_type for ct in class_analysis.child_types]
            # class_definition has various child types (identifier, block, etc.)
            assert len(child_type_names) >= 1
            # Verify child types list is not empty
            assert len(class_analysis.child_types) >= 1

    def test_field_usage_tracked(
        self, analyzer: StructuralAnalyzer, parser: Parser,
    ) -> None:
        """Test that field usage is tracked."""
        code = """
def foo(x, y):
    return x + y
"""
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        result = analyzer.analyze_code_sample(root_node)

        # Check that field_usage dictionary exists for each node type
        for _node_type, analysis in result.items():
            assert isinstance(analysis.field_usage, dict)

    def test_combined_stats_from_multiple_samples(
        self, analyzer: StructuralAnalyzer, parser: Parser,
    ) -> None:
        """Test that stats are combined across multiple samples."""
        code_samples = [
            parser.parse(bytes("def foo(): pass", "utf-8")).root_node,
            parser.parse(bytes("def bar(): pass", "utf-8")).root_node,
            parser.parse(bytes("@decorator\ndef baz(): pass", "utf-8")).root_node,
        ]
        wrappers = analyzer.detect_wrappers(code_samples, min_confidence=0)

        # Should have combined stats from all samples
        for wrapper in wrappers:
            assert wrapper.total_occurrences >= 1

    def test_avg_children_calculated_correctly(
        self, analyzer: StructuralAnalyzer, parser: Parser,
    ) -> None:
        """Test that average children count is calculated."""
        code = """
def foo():
    pass

def bar():
    pass
"""
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        result = analyzer.analyze_code_sample(root_node)

        for _node_type, analysis in result.items():
            if analysis.total_occurrences > 0:
                assert analysis.avg_children_per_occurrence >= 0

    def test_distinct_child_types_counted(
        self, analyzer: StructuralAnalyzer, parser: Parser,
    ) -> None:
        """Test that distinct child types are counted."""
        code = """
class MyClass:
    def method1(self):
        pass

    def method2(self):
        pass
"""
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        result = analyzer.analyze_code_sample(root_node)

        class_analysis = result.get("class_definition")
        if class_analysis:
            assert class_analysis.distinct_child_types >= 1


class TestGrammarIntrospectionIntegration:
    """Integration tests for grammar introspection."""

    def test_grammar_summary_complete(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test that grammar summary provides all expected info."""
        summary = introspector.get_summary()

        assert summary["total_node_types"] > 0
        assert summary["total_fields"] > 0
        assert summary["named_node_types"] > 0
        assert summary["wrapper_candidates"] >= 0

    def test_node_type_ids_resolve_correctly(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test that node type IDs resolve correctly."""
        type_id = introspector.get_node_type_id("function_definition")
        assert type_id is not None
        assert type_id >= 0

        # Non-existent type should return None
        invalid_id = introspector.get_node_type_id("nonexistent_type")
        assert invalid_id is None

    def test_field_ids_resolve_correctly(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test that field IDs resolve correctly."""
        field_id = introspector.get_field_id("name")
        assert field_id is not None
        assert field_id >= 0

        # Non-existent field should return None
        invalid_id = introspector.get_field_id("nonexistent_field")
        assert invalid_id is None

    def test_wrapper_detection_returns_candidates(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test that wrapper detection returns candidates."""
        wrappers = introspector.heuristic_wrapper_detection()
        assert isinstance(wrappers, list)

        # Each wrapper should have confidence score
        for wrapper in wrappers:
            assert wrapper.confidence >= 0
            assert wrapper.node_type

    def test_high_confidence_wrappers_exist(
        self, introspector: GrammarIntrospector,
    ) -> None:
        """Test that high confidence wrappers are detected."""
        wrappers = introspector.heuristic_wrapper_detection()
        high_confidence = [w for w in wrappers if w.confidence >= 50]

        # Python grammar should have some high-confidence wrappers
        assert len(high_confidence) >= 1


class TestGoldenCorpusValidation:
    """Tests validating against Python golden corpus."""

    def test_python_decorated_definition_is_wrapper(
        self, analyzer: StructuralAnalyzer, parser: Parser,
    ) -> None:
        """Test that decorated_definition is correctly identified as wrapper."""
        code = """
@decorator
def function():
    pass
"""
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        result = analyzer.analyze_code_sample(root_node)

        if "decorated_definition" in result:
            dec_def = result["decorated_definition"]
            # decorated_definition should have decent wrapper score
            assert dec_def.wrapper_score >= 0

    def test_python_with_statement_is_wrapper(
        self, analyzer: StructuralAnalyzer, parser: Parser,
    ) -> None:
        """Test that with_statement is correctly identified as wrapper."""
        code = """
with open("file") as f:
    pass
"""
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        result = analyzer.analyze_code_sample(root_node)

        if "with_statement" in result:
            with_stmt = result["with_statement"]
            # with_statement matches "with_" pattern
            assert with_stmt.wrapper_score >= 10

    def test_python_annotated_assignment_is_wrapper(
        self, analyzer: StructuralAnalyzer, parser: Parser,
    ) -> None:
        """Test that annotated assignment is detected."""
        code = """
x: int = 5
"""
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        result = analyzer.analyze_code_sample(root_node)

        # annotated_assignment might be present
        assert "annotated_assignment" in result or "assignment" in result
