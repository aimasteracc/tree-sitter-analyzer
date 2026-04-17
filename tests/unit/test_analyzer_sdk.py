"""
TDD tests for the public SDK facade.

The Analyzer class provides a synchronous Python API for tree-sitter-analyzer,
enabling easy embedding into applications without MCP protocol overhead.
"""
from __future__ import annotations


class TestAnalyzerInit:
    """Analyzer initialization and configuration."""

    def test_create_with_project_root(self, tmp_path) -> None:
        from tree_sitter_analyzer.sdk import Analyzer

        analyzer = Analyzer(project_root=str(tmp_path))
        assert analyzer.project_root == str(tmp_path)

    def test_create_without_project_root_uses_cwd(self) -> None:
        import os

        from tree_sitter_analyzer.sdk import Analyzer

        analyzer = Analyzer()
        assert analyzer.project_root == os.getcwd()

    def test_set_project_path(self, tmp_path) -> None:
        from tree_sitter_analyzer.sdk import Analyzer

        sub = tmp_path / "sub"
        sub.mkdir()
        analyzer = Analyzer(project_root=str(tmp_path))
        analyzer.set_project_path(str(sub))
        assert analyzer.project_root == str(sub)

    def test_close_cleans_up_loop(self, tmp_path) -> None:
        from tree_sitter_analyzer.sdk import Analyzer

        analyzer = Analyzer(project_root=str(tmp_path))
        # Trigger loop creation
        loop = analyzer._get_loop()
        assert loop is not None
        analyzer.close()
        assert analyzer._loop is None


class TestAnalyzerCallCheckCodeScale:
    """Synchronous wrapper for check_code_scale."""

    def test_check_code_scale(self, tmp_path) -> None:
        from tree_sitter_analyzer.sdk import Analyzer

        java_file = tmp_path / "Test.java"
        java_file.write_text("public class Test { }\n")

        analyzer = Analyzer(project_root=str(tmp_path))
        result = analyzer.check_code_scale(file_path=str(java_file))

        assert isinstance(result, dict)
        assert result.get("success") is True


class TestAnalyzerAnalyzeCodeStructure:
    """Synchronous wrapper for analyze_code_structure."""

    def test_analyze_code_structure(self, tmp_path) -> None:
        from tree_sitter_analyzer.sdk import Analyzer

        java_file = tmp_path / "Hello.java"
        java_file.write_text("public class Hello { void greet() {} }\n")

        analyzer = Analyzer(project_root=str(tmp_path))
        result = analyzer.analyze_code_structure(file_path=str(java_file))

        assert isinstance(result, dict)
        assert result.get("success") is True


class TestAnalyzerGetCodeOutline:
    """Synchronous wrapper for get_code_outline."""

    def test_get_code_outline(self, tmp_path) -> None:
        from tree_sitter_analyzer.sdk import Analyzer

        java_file = tmp_path / "Outline.java"
        java_file.write_text("public class Outline { void a() {} void b() {} }\n")

        analyzer = Analyzer(project_root=str(tmp_path))
        result = analyzer.get_code_outline(file_path=str(java_file))

        assert isinstance(result, dict)


class TestAnalyzerQueryCode:
    """Synchronous wrapper for query_code."""

    def test_query_with_key(self, tmp_path) -> None:
        from tree_sitter_analyzer.sdk import Analyzer

        java_file = tmp_path / "Query.java"
        java_file.write_text("public class Query { void run() {} }\n")

        analyzer = Analyzer(project_root=str(tmp_path))
        result = analyzer.query_code(file_path=str(java_file), query_key="methods")

        assert isinstance(result, dict)

    def test_query_with_custom_string(self, tmp_path) -> None:
        from tree_sitter_analyzer.sdk import Analyzer

        java_file = tmp_path / "Query2.java"
        java_file.write_text("public class Query2 { int x; }\n")

        analyzer = Analyzer(project_root=str(tmp_path))
        result = analyzer.query_code(
            file_path=str(java_file), query_string="(field_declaration) @fd"
        )

        assert isinstance(result, dict)


class TestAnalyzerExtractCodeSection:
    """Synchronous wrapper for extract_code_section."""

    def test_extract_section(self, tmp_path) -> None:
        from tree_sitter_analyzer.sdk import Analyzer

        java_file = tmp_path / "Extract.java"
        java_file.write_text("line1\nline2\nline3\n")

        analyzer = Analyzer(project_root=str(tmp_path))
        result = analyzer.extract_code_section(
            file_path=str(java_file), start_line=1, end_line=2
        )

        assert isinstance(result, dict)


class TestAnalyzerTraceImpact:
    """Synchronous wrapper for trace_impact."""

    def test_trace_symbol(self, tmp_path) -> None:
        from tree_sitter_analyzer.sdk import Analyzer

        java_file = tmp_path / "Trace.java"
        java_file.write_text("public class Trace { void useIt() { Helper.call(); } }\n")

        analyzer = Analyzer(project_root=str(tmp_path))
        result = analyzer.trace_impact(symbol="Trace", file_path=str(java_file))

        assert isinstance(result, dict)


class TestAnalyzerModificationGuard:
    """Synchronous wrapper for modification_guard."""

    def test_modification_guard(self, tmp_path) -> None:
        from tree_sitter_analyzer.sdk import Analyzer

        java_file = tmp_path / "Guard.java"
        java_file.write_text("public class Guard { void safe() {} }\n")

        analyzer = Analyzer(project_root=str(tmp_path))
        result = analyzer.modification_guard(
            file_path=str(java_file), symbol_name="safe",
            modification_type="delete"
        )

        assert isinstance(result, dict)


class TestAnalyzerSearchContent:
    """Synchronous wrapper for search_content."""

    def test_search_content(self, tmp_path) -> None:
        from tree_sitter_analyzer.sdk import Analyzer

        java_file = tmp_path / "Search.java"
        java_file.write_text("public class Search { }\n")

        analyzer = Analyzer(project_root=str(tmp_path))
        result = analyzer.search_content(query="Search", roots=[str(tmp_path)])

        assert isinstance(result, dict)


class TestAnalyzerGetProjectSummary:
    """Synchronous wrapper for get_project_summary."""

    def test_project_summary(self, tmp_path) -> None:
        from tree_sitter_analyzer.sdk import Analyzer

        java_file = tmp_path / "Sum.java"
        java_file.write_text("public class Sum { }\n")

        analyzer = Analyzer(project_root=str(tmp_path))
        result = analyzer.get_project_summary()

        assert isinstance(result, dict)


class TestAnalyzerContextManager:
    """Analyzer supports context manager for resource cleanup."""

    def test_context_manager(self, tmp_path) -> None:
        from tree_sitter_analyzer.sdk import Analyzer

        with Analyzer(project_root=str(tmp_path)) as analyzer:
            assert analyzer.project_root == str(tmp_path)
