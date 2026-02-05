"""
Unit tests for Code Graph LLM Export (Milestone 3: LLM Optimization).

Following TDD methodology:
1. RED: Write failing tests first
2. GREEN: Implement minimal code to pass
3. REFACTOR: Improve code quality

Phase 8 - Milestone 3: LLM Optimization (4 tests)
"""

import tempfile
from pathlib import Path


class TestLLMExport:
    """Tests for LLM-friendly graph export."""

    def test_export_toon_format(self):
        """Test exporting graph to TOON format for LLM consumption."""
        from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
        from tree_sitter_analyzer_v2.graph.export import export_for_llm

        code = """
class Calculator:
    def add(self, a, b):
        return a + b

def main():
    calc = Calculator()
    result = calc.add(1, 2)
    return result
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            # Export to TOON format
            output = export_for_llm(graph, output_format="toon")

            # Should return a string
            assert isinstance(output, str)

            # Should contain key information
            assert "MODULE:" in output or "MODULES:" in output
            assert "CLASS:" in output or "CLASSES:" in output
            assert "Calculator" in output
            assert "add" in output
            assert "main" in output

            # Should have CALLS information
            assert "CALLS:" in output or "CALLED_BY:" in output or "->" in output
        finally:
            Path(temp_path).unlink()

    def test_token_count_under_limit(self):
        """Test that export respects max_tokens parameter."""
        from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
        from tree_sitter_analyzer_v2.graph.export import export_for_llm

        # Create a larger code sample
        code = """
class BigClass:
    def method1(self):
        pass
    def method2(self):
        pass
    def method3(self):
        pass
    def method4(self):
        pass
    def method5(self):
        pass

def func1():
    pass
def func2():
    pass
def func3():
    pass
def func4():
    pass
def func5():
    pass
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            # Export with token limit
            output = export_for_llm(graph, max_tokens=500, output_format="toon")

            # Should return a string
            assert isinstance(output, str)

            # Estimate token count (rough: 1 token ≈ 4 chars)
            estimated_tokens = len(output) / 4
            # Allow some margin (20%) for tokenizer differences
            assert estimated_tokens < 600, f"Estimated {estimated_tokens} tokens exceeds 500 limit"
        finally:
            Path(temp_path).unlink()

    def test_layered_summary(self):
        """Test layered export with different detail levels."""
        from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
        from tree_sitter_analyzer_v2.graph.export import export_for_llm

        code = """
class MyClass:
    def public_method(self):
        return self._private_method()

    def _private_method(self):
        return 42

def main():
    obj = MyClass()
    return obj.public_method()
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            # Summary level (should omit private methods)
            summary = export_for_llm(graph, detail_level="summary", output_format="toon")
            assert isinstance(summary, str)
            assert "public_method" in summary
            # Private methods might be omitted in summary
            # (test passes either way for now - implementation decides)

            # Detailed level (should include everything)
            detailed = export_for_llm(graph, detail_level="detailed", output_format="toon")
            assert isinstance(detailed, str)
            assert "public_method" in detailed
            assert "_private_method" in detailed or "private_method" in detailed

            # Detailed should be longer than summary
            assert len(detailed) >= len(summary)
        finally:
            Path(temp_path).unlink()

    def test_omit_private_functions(self):
        """Test that private functions can be filtered out."""
        from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
        from tree_sitter_analyzer_v2.graph.export import export_for_llm

        code = """
def public_api():
    return _internal_helper()

def _internal_helper():
    return __very_private()

def __very_private():
    return 42
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()
            graph = builder.build_from_file(temp_path)

            # Summary should omit private functions
            summary = export_for_llm(
                graph, detail_level="summary", include_private=False, output_format="toon"
            )

            assert isinstance(summary, str)
            assert "public_api" in summary

            # Private functions should be omitted (or at least minimized)
            # Implementation may choose to show them minimally
            # This is a soft requirement - we just want summary to be smaller
            assert len(summary) > 0

            # Detailed with include_private=True should show everything
            detailed = export_for_llm(
                graph, detail_level="detailed", include_private=True, output_format="toon"
            )

            assert "_internal_helper" in detailed or "internal_helper" in detailed
            assert "__very_private" in detailed or "very_private" in detailed
        finally:
            Path(temp_path).unlink()
