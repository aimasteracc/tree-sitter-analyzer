"""Unit tests for language-aware test file discovery."""

import tempfile
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.utils.test_discovery import (
    detect_language_from_ext,
    find_test_files,
)


class TestDetectLanguageFromExt:
    def test_python(self):
        assert detect_language_from_ext(".py") == "python"

    def test_java(self):
        assert detect_language_from_ext(".java") == "java"

    def test_go(self):
        assert detect_language_from_ext(".go") == "go"

    def test_rust(self):
        assert detect_language_from_ext(".rs") == "rust"

    def test_javascript(self):
        assert detect_language_from_ext(".js") == "javascript"

    def test_typescript(self):
        assert detect_language_from_ext(".ts") == "typescript"

    def test_c(self):
        assert detect_language_from_ext(".c") == "c"

    def test_cpp(self):
        assert detect_language_from_ext(".cpp") == "cpp"

    def test_csharp(self):
        assert detect_language_from_ext(".cs") == "csharp"

    def test_kotlin(self):
        assert detect_language_from_ext(".kt") == "kotlin"

    def test_ruby(self):
        assert detect_language_from_ext(".rb") == "ruby"

    def test_php(self):
        assert detect_language_from_ext(".php") == "php"

    def test_unknown(self):
        assert detect_language_from_ext(".xyz") is None


class TestFindTestFilesPython:
    def test_finds_python_test_in_unit_dir(self):
        """Finds tests/unit/module/test_file.py for file.py."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "src" / "module" / "calculator.py"
            source.parent.mkdir(parents=True)
            source.write_text("def add(): pass")

            test = root / "tests" / "unit" / "module" / "test_calculator.py"
            test.parent.mkdir(parents=True)
            test.write_text("def test_add(): pass")

            results = find_test_files(str(source), tmp)
            assert any("test_calculator.py" in r for r in results)

    def test_finds_python_test_in_tests_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "health_scorer.py"
            source.write_text("pass")
            test = root / "tests" / "test_health_scorer.py"
            test.parent.mkdir()
            test.write_text("pass")

            results = find_test_files(str(source), tmp)
            assert any("test_health_scorer" in r for r in results)

    def test_finds_python_prefixed_test_module_variant(self):
        """Finds test_cli_main_module.py for cli_main.py."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "tree_sitter_analyzer" / "cli_main.py"
            source.parent.mkdir(parents=True)
            source.write_text("def main(): pass")

            test = root / "tests" / "unit" / "cli" / "test_cli_main_module.py"
            test.parent.mkdir(parents=True)
            test.write_text("def test_main(): pass")

            results = find_test_files(str(source), tmp)
            assert any("test_cli_main_module.py" in r for r in results)

    def test_finds_python_language_plugin_package_tests(self):
        """Finds package-level tests for language plugin internals."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = (
                root
                / "tree_sitter_analyzer"
                / "languages"
                / "sql_plugin"
                / "extractor.py"
            )
            source.parent.mkdir(parents=True)
            source.write_text("class SQLElementExtractor: pass")

            test = root / "tests" / "unit" / "languages" / "test_sql_plugin_coverage.py"
            test.parent.mkdir(parents=True)
            test.write_text("def test_sql_plugin_extractor(): pass")

            results = find_test_files(str(source), tmp)
            assert "tests/unit/languages/test_sql_plugin_coverage.py" in results

    def test_finds_python_family_tests_for_extracted_modules(self):
        """Extracted helper modules should inherit the family's test module."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = (
                root
                / "tree_sitter_analyzer"
                / "mcp"
                / "tools"
                / "utils"
                / "change_impact_analysis.py"
            )
            source.parent.mkdir(parents=True)
            source.write_text("def analyze(): pass")

            test = root / "tests" / "unit" / "mcp" / "test_change_impact_tool.py"
            test.parent.mkdir(parents=True)
            test.write_text("def test_change_impact(): pass")

            results = find_test_files(str(source), tmp)
            assert "tests/unit/mcp/test_change_impact_tool.py" in results

    def test_finds_python_family_tests_for_git_modules(self):
        """Extracted git helpers should inherit the family's test module."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = (
                root
                / "tree_sitter_analyzer"
                / "mcp"
                / "tools"
                / "utils"
                / "change_impact_git.py"
            )
            source.parent.mkdir(parents=True)
            source.write_text("def changed_files(): pass")

            test = root / "tests" / "unit" / "mcp" / "test_change_impact_tool.py"
            test.parent.mkdir(parents=True)
            test.write_text("def test_change_impact(): pass")

            results = find_test_files(str(source), tmp)
            assert "tests/unit/mcp/test_change_impact_tool.py" in results

    def test_finds_python_family_tests_for_verification_modules(self):
        """Extracted verification helpers should inherit the family's test module."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = (
                root
                / "tree_sitter_analyzer"
                / "mcp"
                / "tools"
                / "utils"
                / "change_impact_verification.py"
            )
            source.parent.mkdir(parents=True)
            source.write_text("def verification(): pass")

            test = root / "tests" / "unit" / "mcp" / "test_change_impact_tool.py"
            test.parent.mkdir(parents=True)
            test.write_text("def test_change_impact(): pass")

            results = find_test_files(str(source), tmp)
            assert "tests/unit/mcp/test_change_impact_tool.py" in results

    def test_finds_python_family_tests_for_stem_modules(self):
        """Extracted stem helpers should inherit the family's test module."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = (
                root
                / "tree_sitter_analyzer"
                / "mcp"
                / "tools"
                / "utils"
                / "test_discovery_stems.py"
            )
            source.parent.mkdir(parents=True)
            source.write_text("def stems(): pass")

            test = root / "tests" / "unit" / "mcp" / "test_test_discovery.py"
            test.parent.mkdir(parents=True)
            test.write_text("def test_discovery(): pass")

            results = find_test_files(str(source), tmp)
            assert "tests/unit/mcp/test_test_discovery.py" in results

    def test_finds_python_family_tests_for_predicate_modules(self):
        """Extracted predicate helpers should inherit the family's test module."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = (
                root
                / "tree_sitter_analyzer"
                / "mcp"
                / "tools"
                / "utils"
                / "test_discovery_predicates.py"
            )
            source.parent.mkdir(parents=True)
            source.write_text("def is_test(): pass")

            test = root / "tests" / "unit" / "mcp" / "test_test_discovery.py"
            test.parent.mkdir(parents=True)
            test.write_text("def test_discovery(): pass")

            results = find_test_files(str(source), tmp)
            assert "tests/unit/mcp/test_test_discovery.py" in results

    def test_finds_python_family_tests_for_python_helper_modules(self):
        """Extracted Python-specific helpers should inherit the family's test module."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = (
                root
                / "tree_sitter_analyzer"
                / "mcp"
                / "tools"
                / "utils"
                / "test_discovery_python.py"
            )
            source.parent.mkdir(parents=True)
            source.write_text("def find_python_specific_tests(): pass")

            test = root / "tests" / "unit" / "mcp" / "test_test_discovery.py"
            test.parent.mkdir(parents=True)
            test.write_text("def test_discovery(): pass")

            results = find_test_files(str(source), tmp)
            assert "tests/unit/mcp/test_test_discovery.py" in results

    def test_finds_python_family_tests_for_language_helper_modules(self):
        """Extracted language helpers should inherit the family's test module."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = (
                root
                / "tree_sitter_analyzer"
                / "mcp"
                / "tools"
                / "utils"
                / "test_discovery_languages.py"
            )
            source.parent.mkdir(parents=True)
            source.write_text("def find_language_specific_tests(): pass")

            test = root / "tests" / "unit" / "mcp" / "test_test_discovery.py"
            test.parent.mkdir(parents=True)
            test.write_text("def test_discovery(): pass")

            results = find_test_files(str(source), tmp)
            assert "tests/unit/mcp/test_test_discovery.py" in results

    def test_finds_python_family_tests_for_file_health_helper_modules(self):
        """Extracted file-health helpers should inherit the family's test module."""
        helper_names = (
            "file_health_blocks.py",
            "file_health_response.py",
            "file_health_smells.py",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            test = root / "tests" / "unit" / "mcp" / "test_file_health_tool.py"
            test.parent.mkdir(parents=True)
            test.write_text("def test_file_health(): pass")

            for helper_name in helper_names:
                source = (
                    root
                    / "tree_sitter_analyzer"
                    / "mcp"
                    / "tools"
                    / "utils"
                    / helper_name
                )
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text("def helper(): pass")

                results = find_test_files(str(source), tmp)
                assert "tests/unit/mcp/test_file_health_tool.py" in results

    def test_finds_python_family_tests_for_safe_to_edit_risk_modules(self):
        """Extracted safe-to-edit helpers should inherit the family's test module."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = (
                root
                / "tree_sitter_analyzer"
                / "mcp"
                / "tools"
                / "utils"
                / "safe_to_edit_risk.py"
            )
            source.parent.mkdir(parents=True)
            source.write_text("def compute_risk(): pass")

            test = root / "tests" / "unit" / "mcp" / "test_safe_to_edit_tool.py"
            test.parent.mkdir(parents=True)
            test.write_text("def test_safe_to_edit(): pass")

            results = find_test_files(str(source), tmp)
            assert "tests/unit/mcp/test_safe_to_edit_tool.py" in results

    def test_finds_python_family_tests_for_refactoring_suggestion_helpers(self):
        """Extracted refactoring helpers should inherit the family's test module."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            test = (
                root / "tests" / "unit" / "mcp" / "test_refactoring_suggestions_tool.py"
            )
            test.parent.mkdir(parents=True)
            test.write_text("def test_refactoring_suggestions(): pass")

            for helper_name in (
                "refactoring_suggestions_classes.py",
                "refactoring_suggestions_helpers.py",
                "refactoring_suggestions_python.py",
                "refactoring_suggestions_treesitter.py",
            ):
                source = (
                    root
                    / "tree_sitter_analyzer"
                    / "mcp"
                    / "tools"
                    / "utils"
                    / helper_name
                )
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text("def helper(): pass")

                results = find_test_files(str(source), tmp)
                assert "tests/unit/mcp/test_refactoring_suggestions_tool.py" in results

    def test_finds_python_family_tests_for_refactoring_plan_builder(self):
        """The precise-plan builder should inherit refactoring suggestion tests."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = (
                root
                / "tree_sitter_analyzer"
                / "mcp"
                / "tools"
                / "_refactoring_plan_builder.py"
            )
            source.parent.mkdir(parents=True)
            source.write_text("def build_precise_plans(): pass")

            test = (
                root / "tests" / "unit" / "mcp" / "test_refactoring_suggestions_tool.py"
            )
            test.parent.mkdir(parents=True)
            test.write_text("def test_refactoring_suggestions(): pass")

            results = find_test_files(str(source), tmp)
            assert "tests/unit/mcp/test_refactoring_suggestions_tool.py" in results

    def test_finds_python_family_tests_for_stacked_search_content_helpers(self):
        """Stacked helper suffixes should peel back to the search_content family."""
        helper_names = (
            "search_content_agent_summary.py",
            "search_content_response_modes.py",
            "search_content_validation.py",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            test = root / "tests" / "unit" / "mcp" / "test_search_content_tool.py"
            test.parent.mkdir(parents=True)
            test.write_text("def test_search_content(): pass")

            for helper_name in helper_names:
                source = root / "tree_sitter_analyzer" / "mcp" / "tools" / helper_name
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text("def helper(): pass")

                results = find_test_files(str(source), tmp)
                assert "tests/unit/mcp/test_search_content_tool.py" in results

    def test_finds_python_family_tests_for_find_and_grep_execution_helper(self):
        """Execution helper modules should peel back to the find_and_grep family."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = (
                root
                / "tree_sitter_analyzer"
                / "mcp"
                / "tools"
                / "find_and_grep_execution.py"
            )
            source.parent.mkdir(parents=True)
            source.write_text("def helper(): pass")

            test = root / "tests" / "unit" / "mcp" / "test_find_and_grep_tool.py"
            test.parent.mkdir(parents=True)
            test.write_text("def test_find_and_grep(): pass")

            results = find_test_files(str(source), tmp)
            assert "tests/unit/mcp/test_find_and_grep_tool.py" in results

    def test_finds_python_family_tests_for_sources_helper(self):
        """r37q dogfood: ``parser_readiness_sources.py`` must inherit
        ``test_parser_readiness.py`` via the ``_sources`` family suffix.

        Caught by running ``--safe-to-edit`` on the file itself: it
        reported ``tests=no`` even though the parent module is well
        tested. Adding ``_sources`` to the suffix strip list fixes the
        family lookup.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = (
                root / "tree_sitter_analyzer" / "cli" / "parser_readiness_sources.py"
            )
            source.parent.mkdir(parents=True)
            source.write_text("def collect(): pass")

            test = root / "tests" / "unit" / "cli" / "test_parser_readiness.py"
            test.parent.mkdir(parents=True)
            test.write_text("def test_parser_readiness(): pass")

            results = find_test_files(str(source), tmp)
            assert "tests/unit/cli/test_parser_readiness.py" in results

    def test_finds_python_family_tests_for_records_helper(self):
        """r37q dogfood: ``parser_readiness_records.py`` must inherit
        ``test_parser_readiness.py`` via the ``_records`` family suffix.
        Same root cause as the ``_sources`` case above.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = (
                root / "tree_sitter_analyzer" / "cli" / "parser_readiness_records.py"
            )
            source.parent.mkdir(parents=True)
            source.write_text("def build(): pass")

            test = root / "tests" / "unit" / "cli" / "test_parser_readiness.py"
            test.parent.mkdir(parents=True)
            test.write_text("def test_parser_readiness(): pass")

            results = find_test_files(str(source), tmp)
            assert "tests/unit/cli/test_parser_readiness.py" in results

    def test_returns_python_test_file_itself_as_nearby_test(self):
        """A queried test module is its own runnable verification target."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            test = root / "tests" / "unit" / "languages" / "test_sql_plugin_80.py"
            test.parent.mkdir(parents=True)
            test.write_text("def test_sql_plugin(): pass")

            results = find_test_files(str(test), tmp)
            assert results[0] == "tests/unit/languages/test_sql_plugin_80.py"

    def test_does_not_treat_conftest_as_runnable_test_file(self):
        """conftest.py supports tests but should not be a direct test target."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conftest = root / "tests" / "conftest.py"
            conftest.parent.mkdir(parents=True)
            conftest.write_text("import pytest")

            results = find_test_files(str(conftest), tmp)
            assert "tests/conftest.py" not in results

    def test_does_not_treat_source_test_prefix_module_as_test(self):
        """Source modules named test_* outside test dirs are not auto-verified."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "tree_sitter_analyzer" / "test_support.py"
            source.parent.mkdir(parents=True)
            source.write_text("def helper(): pass")

            results = find_test_files(str(source), tmp)
            assert "tree_sitter_analyzer/test_support.py" not in results

    def test_finds_tests_for_python_fixture_project_files(self):
        """Fixture edits map to tests that name the fixture domain."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = (
                root
                / "tests"
                / "fixtures"
                / "project_graph"
                / "health_project"
                / "pyproject.toml"
            )
            fixture.parent.mkdir(parents=True)
            fixture.write_text("[project]\nname = 'fixture'\n")

            health_test = root / "tests" / "unit" / "test_health_scorer.py"
            graph_test = root / "tests" / "unit" / "test_project_graph.py"
            unrelated_test = root / "tests" / "unit" / "test_file_health_tool.py"
            health_test.parent.mkdir(parents=True)
            health_test.write_text("def test_health(): pass")
            graph_test.write_text("def test_graph(): pass")
            unrelated_test.write_text("def test_file_health(): pass")

            results = find_test_files(str(fixture), tmp)
            assert results == [
                "tests/unit/test_health_scorer.py",
                "tests/unit/test_project_graph.py",
            ]


class TestFindTestFilesJava:
    def test_finds_java_test_maven_structure(self):
        """Finds src/test/java for src/main/java source."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "src" / "main" / "java" / "com" / "Calculator.java"
            source.parent.mkdir(parents=True)
            source.write_text("class Calculator {}")

            test = root / "src" / "test" / "java" / "com" / "CalculatorTest.java"
            test.parent.mkdir(parents=True)
            test.write_text("class CalculatorTest {}")

            results = find_test_files(str(source), tmp)
            assert any("CalculatorTest.java" in r for r in results)


class TestFindTestFilesPythonPublicSymbolReferences:
    def test_finds_tests_referencing_public_symbols_even_when_filename_differs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "src" / "format_helper.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                "def apply_toon_format_to_response(data):\n"
                "    return data\n\n"
                "def _private_helper():\n"
                "    return None\n",
                encoding="utf-8",
            )

            exact_test = root / "tests" / "test_output_cost_invariants.py"
            exact_test.parent.mkdir(parents=True)
            exact_test.write_text(
                "from src.format_helper import apply_toon_format_to_response\n\n"
                "def test_budget():\n"
                "    assert apply_toon_format_to_response({}) == {}\n",
                encoding="utf-8",
            )
            private_only = root / "tests" / "test_private_only.py"
            private_only.write_text(
                "def test_private_name_text():\n"
                "    assert '_private_helper' in 'doc only'\n",
                encoding="utf-8",
            )

            results = find_test_files(str(source), tmp)

            assert "tests/test_output_cost_invariants.py" in results
            assert "tests/test_private_only.py" not in results

    def test_symbol_reference_scan_skips_unreadable_test_files(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "src" / "format_helper.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                "def apply_toon_format_to_response(data):\n    return data\n",
                encoding="utf-8",
            )

            readable = root / "tests" / "test_output_cost_invariants.py"
            unreadable = root / "tests" / "test_unreadable.py"
            readable.parent.mkdir(parents=True)
            readable.write_text(
                "def test_budget():\n"
                "    assert apply_toon_format_to_response({}) == {}\n",
                encoding="utf-8",
            )
            unreadable.write_text(
                "def test_unreadable():\n"
                "    assert apply_toon_format_to_response({}) == {}\n",
                encoding="utf-8",
            )

            original_read_text = Path.read_text

            def fake_read_text(path: Path, *args: Any, **kwargs: Any) -> str:
                if path == unreadable:
                    raise OSError("permission denied")
                return original_read_text(path, *args, **kwargs)

            monkeypatch.setattr(Path, "read_text", fake_read_text)

            results = find_test_files(str(source), tmp)

            assert "tests/test_output_cost_invariants.py" in results
            assert "tests/test_unreadable.py" not in results

    def test_symbol_reference_scan_treats_unreadable_source_as_no_symbols(
        self, monkeypatch
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "src" / "format_helper.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                "def apply_toon_format_to_response(data):\n    return data\n",
                encoding="utf-8",
            )
            test = root / "tests" / "test_output_cost_invariants.py"
            test.parent.mkdir(parents=True)
            test.write_text(
                "def test_budget():\n"
                "    assert apply_toon_format_to_response({}) == {}\n",
                encoding="utf-8",
            )

            original_read_text = Path.read_text

            def fake_read_text(path: Path, *args: Any, **kwargs: Any) -> str:
                if path == source:
                    raise OSError("permission denied")
                return original_read_text(path, *args, **kwargs)

            monkeypatch.setattr(Path, "read_text", fake_read_text)

            results = find_test_files(str(source), tmp)

            assert "tests/test_output_cost_invariants.py" not in results


class TestFindTestFilesGo:
    def test_finds_go_colocated_test(self):
        """Finds _test.go file co-located with source."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "handler.go"
            source.write_text("package main")

            test = root / "handler_test.go"
            test.write_text("package main")

            results = find_test_files(str(source), tmp)
            assert any("handler_test.go" in r for r in results)


class TestFindTestFilesRuby:
    def test_finds_ruby_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lib" / "parser.rb"
            source.parent.mkdir(parents=True)
            source.write_text("class Parser; end")

            test = root / "test" / "test_parser.rb"
            test.parent.mkdir(parents=True)
            test.write_text("require 'test/unit'")

            results = find_test_files(str(source), tmp)
            assert any("test_parser.rb" in r for r in results)


class TestFindTestFilesJavascript:
    def test_finds_js_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "src" / "utils.js"
            source.parent.mkdir(parents=True)
            source.write_text("export function foo() {}")

            test = root / "tests" / "utils.test.js"
            test.parent.mkdir(parents=True)
            test.write_text("test('foo', () => {})")

            results = find_test_files(str(source), tmp)
            assert any("utils.test.js" in r for r in results)


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("handler_test.go", ["handler_test.go"]),
        ("lib_test.rs", ["lib_test.rs"]),
        ("CalcTest.java", ["CalcTest.java"]),
        ("app.test.js", ["app.test.js"]),
        ("app.test.ts", ["app.test.ts"]),
        ("test_util.c", ["test_util.c"]),
        ("test_util.cpp", ["test_util.cpp"]),
        ("CalcTest.cs", ["CalcTest.cs"]),
        ("CalcTest.kt", ["CalcTest.kt"]),
        ("calc_test.rb", ["calc_test.rb"]),
        ("CalcTest.php", ["CalcTest.php"]),
    ],
)
def test_certified_test_files_cross_language_conventions(
    target: str, expected: list[str]
) -> None:
    """Round-6 (C27): a test-named target counts in every language."""
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _certified_test_files,
    )

    found = _certified_test_files(frozenset({target}), target)
    assert found == expected


def _symbol_reference_conn(
    rows: list[tuple[str, str, str]],
    edges: list[tuple[str, str, str, str]] | None = None,
) -> Any:
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, symbols_json TEXT, imports_json TEXT)"
    )
    conn.executemany("INSERT INTO ast_index VALUES (?, ?, ?)", rows)
    if edges is not None:
        conn.execute(
            "CREATE TABLE edges (file_path TEXT, callee_name TEXT, kind TEXT, "
            "callee_resolved_file TEXT)"
        )
        conn.executemany("INSERT INTO edges VALUES (?, ?, ?, ?)", edges)
    return conn


def _symbol_payload(*names: str) -> str:
    import json

    return json.dumps({"symbols": [{"name": name} for name in names]})


def _import_payload(text: str) -> str:
    import json

    return json.dumps([{"text": text, "line": 1}])


def _certified_refs(
    conn: Any,
    inventory: set[str],
    target: str = "pkg/impl.py",
    language: str = "python",
) -> list[str]:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _certified_symbol_reference_tests,
    )

    return _certified_symbol_reference_tests(
        conn, frozenset(inventory), target, language
    )


def test_certified_symbol_reference_tests_find_imported_symbols() -> None:
    conn = _symbol_reference_conn(
        [
            ("pkg/impl.py", _symbol_payload("public_fn"), "[]"),
            (
                "pkg/__init__.py",
                "{}",
                _import_payload("from .impl import public_fn"),
            ),
            (
                "tests/test_behavior.py",
                "{}",
                _import_payload("from pkg import public_fn"),
            ),
            ("tests/test_unrelated.py", "{}", _import_payload("import os")),
        ]
    )

    assert _certified_refs(
        conn,
        {
            "pkg/impl.py",
            "pkg/__init__.py",
            "tests/test_behavior.py",
            "tests/test_unrelated.py",
        },
    ) == ["tests/test_behavior.py"]


def test_certified_symbol_reference_tests_reject_missing_schema() -> None:
    import sqlite3

    conn = sqlite3.connect(":memory:")
    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        _certified_refs(conn, set())


def test_certified_symbol_reference_tests_reject_invalid_target_json() -> None:
    conn = _symbol_reference_conn([("pkg/impl.py", "not-json", "[]")])

    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        _certified_refs(conn, {"pkg/impl.py"})


def test_certified_symbol_reference_tests_ignore_private_symbols() -> None:
    conn = _symbol_reference_conn([("pkg/impl.py", _symbol_payload("_hidden"), "[]")])

    assert _certified_refs(conn, {"pkg/impl.py"}) == []


def test_certified_symbol_reference_tests_reject_missing_target_row() -> None:
    conn = _symbol_reference_conn([("other.py", "{}", "[]")])

    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        _certified_refs(conn, {"tests/test_x.py"})


def test_certified_symbol_reference_tests_reject_mid_query_failure() -> None:
    import sqlite3

    real = _symbol_reference_conn(
        [
            ("pkg/impl.py", _symbol_payload("run"), "[]"),
            ("tests/test_impl.py", "{}", _import_payload("import run")),
        ]
    )

    class _FlakyConn:
        def __init__(self) -> None:
            self.calls = 0

        def execute(self, sql: str, params: tuple[str, ...] = ()) -> Any:
            self.calls += 1
            if self.calls == 2:
                raise sqlite3.OperationalError("schema drift")
            return real.execute(sql, params)

    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        _certified_refs(_FlakyConn(), {"pkg/impl.py", "tests/test_impl.py"})


def test_certified_symbol_reference_tests_use_identifier_boundaries() -> None:
    conn = _symbol_reference_conn(
        [
            ("text.py", _symbol_payload("text", "get"), "[]"),
            ("tests/test_any.py", "{}", _import_payload("import widget")),
        ]
    )

    assert (
        _certified_refs(conn, {"text.py", "tests/test_any.py"}, target="text.py") == []
    )


def test_certified_symbol_reference_tests_include_resolved_calls() -> None:
    conn = _symbol_reference_conn(
        [
            ("pkg/impl.py", _symbol_payload("run"), "[]"),
            ("tests/test_calls.py", "{}", "[]"),
        ],
        [("tests/test_calls.py", "run", "calls", "pkg/impl.py")],
    )

    assert _certified_refs(conn, {"pkg/impl.py", "tests/test_calls.py"}) == [
        "tests/test_calls.py"
    ]


def test_certified_symbol_reference_tests_exclude_calls_resolved_elsewhere() -> None:
    conn = _symbol_reference_conn(
        [
            ("pkg/impl.py", _symbol_payload("run"), "[]"),
            ("tests/test_other.py", "{}", "[]"),
        ],
        [("tests/test_other.py", "run", "calls", "pkg/other.py")],
    )

    assert _certified_refs(conn, {"pkg/impl.py", "tests/test_other.py"}) == []


def test_certified_symbol_reference_tests_bind_python_imports_to_modules() -> None:
    conn = _symbol_reference_conn(
        [
            ("pkg/impl.py", _symbol_payload("run"), "[]"),
            ("other.py", _symbol_payload("run"), "[]"),
            ("pkg/__init__.py", "{}", _import_payload("from .impl import run")),
            ("tests/test_other.py", "{}", _import_payload("from other import run")),
            ("tests/test_pkg.py", "{}", _import_payload("from pkg import run")),
        ]
    )
    inventory = {
        "pkg/impl.py",
        "other.py",
        "pkg/__init__.py",
        "tests/test_other.py",
        "tests/test_pkg.py",
    }

    assert _certified_refs(conn, inventory) == ["tests/test_pkg.py"]


def test_certified_symbol_reference_tests_bind_esm_imports_to_modules() -> None:
    conn = _symbol_reference_conn(
        [
            ("src/impl.ts", _symbol_payload("run"), "[]"),
            ("src/other.ts", _symbol_payload("run"), "[]"),
            (
                "tests/impl.test.ts",
                "{}",
                _import_payload("import { run } from '../src/impl'"),
            ),
            (
                "tests/other.test.ts",
                "{}",
                _import_payload("import { run } from '../src/other'"),
            ),
        ]
    )
    inventory = {
        "src/impl.ts",
        "src/other.ts",
        "tests/impl.test.ts",
        "tests/other.test.ts",
    }

    assert _certified_refs(
        conn, inventory, target="src/impl.ts", language="typescript"
    ) == ["tests/impl.test.ts"]


def test_file_defines_any_matches_indexed_symbols() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _file_defines_any,
    )

    conn = _symbol_reference_conn([("pkg/impl.py", _symbol_payload("run"), "[]")])

    assert _file_defines_any(conn, "pkg/impl.py", ["run"]) is True
    assert _file_defines_any(conn, "pkg/impl.py", ["other"]) is False


def test_file_defines_any_rejects_missing_schema() -> None:
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _file_defines_any,
    )

    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        _file_defines_any(sqlite3.connect(":memory:"), "ghost.py", ["run"])


def test_file_defines_any_rejects_missing_row() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _file_defines_any,
    )

    conn = _symbol_reference_conn([("pkg/impl.py", _symbol_payload("run"), "[]")])

    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        _file_defines_any(conn, "ghost.py", ["run"])


def test_certified_symbol_reference_tests_accept_unbound_symbol_record() -> None:
    conn = _symbol_reference_conn(
        [
            ("pkg/impl.py", _symbol_payload("run"), "[]"),
            ("tests/test_impl.py", "{}", _import_payload("run")),
        ]
    )

    assert _certified_refs(conn, {"pkg/impl.py", "tests/test_impl.py"}) == [
        "tests/test_impl.py"
    ]


@pytest.mark.parametrize("text", ["import run", "from third_party import run"])
def test_certified_symbol_reference_tests_reject_unresolved_python_imports(
    text: str,
) -> None:
    conn = _symbol_reference_conn(
        [
            ("pkg/impl.py", _symbol_payload("run"), "[]"),
            ("tests/test_impl.py", "{}", _import_payload(text)),
        ]
    )

    assert _certified_refs(conn, {"pkg/impl.py", "tests/test_impl.py"}) == []


def test_certified_symbol_reference_tests_reject_unresolved_java_imports() -> None:
    conn = _symbol_reference_conn(
        [
            ("src/main/java/com/acme/Util.java", _symbol_payload("Util"), "[]"),
            (
                "src/test/java/com/acme/UtilTest.java",
                "{}",
                _import_payload("import third.party.Util;"),
            ),
        ]
    )
    inventory = {
        "src/main/java/com/acme/Util.java",
        "src/test/java/com/acme/UtilTest.java",
    }

    assert (
        _certified_refs(
            conn,
            inventory,
            target="src/main/java/com/acme/Util.java",
            language="java",
        )
        == []
    )


def test_certified_symbol_reference_tests_resolve_java_static_owner() -> None:
    conn = _symbol_reference_conn(
        [
            ("src/main/java/com/acme/Util.java", _symbol_payload("helper"), "[]"),
            (
                "src/test/java/com/acme/UtilTest.java",
                "{}",
                _import_payload("import static com.acme.Util.helper;"),
            ),
        ]
    )
    inventory = {
        "src/main/java/com/acme/Util.java",
        "src/test/java/com/acme/UtilTest.java",
    }

    assert _certified_refs(
        conn,
        inventory,
        target="src/main/java/com/acme/Util.java",
        language="java",
    ) == ["src/test/java/com/acme/UtilTest.java"]


@pytest.mark.parametrize(
    ("target", "dependent"),
    [
        ("src/lib.js", "tests/lib.test.ts"),
        ("src/util.h", "tests/test_util.cpp"),
        (
            "src/main/java/com/acme/Util.java",
            "src/test/java/com/acme/TestUtil.java",
        ),
    ],
)
def test_certified_exercising_tests_use_dependent_language(
    target: str, dependent: str
) -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _certified_exercising_tests,
    )

    conn = _symbol_reference_conn(
        [(target, _symbol_payload(), "[]"), (dependent, "{}", "[]")]
    )
    inventory = frozenset({target, dependent})

    assert _certified_exercising_tests(
        conn, target, [dependent], inventory=inventory
    ) == [dependent]


def test_certified_symbol_reference_tests_resolve_relative_from_importer() -> None:
    conn = _symbol_reference_conn(
        [
            ("pkg/impl.py", _symbol_payload("run"), "[]"),
            ("tests/other.py", _symbol_payload("run"), "[]"),
            ("tests/test_other.py", "{}", _import_payload("from .other import run")),
        ]
    )

    assert (
        _certified_refs(conn, {"pkg/impl.py", "tests/other.py", "tests/test_other.py"})
        == []
    )


def test_certified_symbol_reference_tests_reject_missing_test_row() -> None:
    conn = _symbol_reference_conn([("pkg/impl.py", _symbol_payload("public_fn"), "[]")])

    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        _certified_refs(conn, {"pkg/impl.py", "tests/test_ghost.py"})


@pytest.mark.parametrize(
    ("target_symbols", "test_imports"),
    [
        ("[]", "[]"),
        ('{"symbols": {}}', "[]"),
        ('{"symbols": [42]}', "[]"),
        ('{"symbols": [{"name": "run"}]}', "not-json"),
        ('{"symbols": [{"name": "run"}]}', "{}"),
        ('{"symbols": [{"name": "run"}]}', '["not-a-record"]'),
        ('{"symbols": [{"name": "run"}]}', '[{"text": 42}]'),
    ],
)
def test_certified_symbol_reference_tests_reject_malformed_projections(
    target_symbols: str, test_imports: str
) -> None:
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _certified_symbol_reference_tests,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, symbols_json TEXT, imports_json TEXT)"
    )
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?, ?)",
        [
            ("pkg/impl.py", target_symbols, "[]"),
            ("tests/test_impl.py", "{}", test_imports),
        ],
    )

    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        _certified_symbol_reference_tests(
            conn,
            frozenset({"pkg/impl.py", "tests/test_impl.py"}),
            "pkg/impl.py",
            "python",
        )


@pytest.mark.parametrize(
    "symbols_json", ["not-json", "[]", '{"symbols": {}}', '{"symbols": [42]}']
)
def test_file_defines_any_rejects_malformed_projection(symbols_json: str) -> None:
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _file_defines_any,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE ast_index (file_path TEXT, symbols_json TEXT)")
    conn.execute("INSERT INTO ast_index VALUES ('pkg/impl.py', ?)", (symbols_json,))

    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        _file_defines_any(conn, "pkg/impl.py", ["run"])


def test_looks_like_test_name_unknown_language_is_false() -> None:
    """An unknown language is never treated as a test-name convention."""
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _looks_like_test_name,
    )

    assert _looks_like_test_name("test_x.py", "futurelang") is False
    assert _looks_like_test_name("test_x.py", "python") is True
    assert _looks_like_test_name("app.py", "python") is False
    # C63: JSX/TSX spec conventions count.
    assert _looks_like_test_name("component.spec.jsx", "javascript") is True
    assert _looks_like_test_name("component.spec.tsx", "typescript") is True
    # C63: JSX/TSX spec conventions count.
    assert _looks_like_test_name("component.spec.jsx", "javascript") is True
    assert _looks_like_test_name("component.spec.tsx", "typescript") is True


def test_certified_test_files_rejects_non_test_target() -> None:
    """A non-test target is not its own test file."""
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _certified_test_files,
    )

    assert _certified_test_files(frozenset({"app.py"}), "app.py") == []


def test_certified_test_files_walk_inventory_only() -> None:
    """Codex P1 (#1299 round-3/4): certified discovery walks the inventory."""
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _certified_test_files,
    )

    inventory = frozenset(
        {
            "src/app.py",
            "tests/test_app.py",
            "tests/test_other.py",
            "tests/unit/test_app.py",  # nested indexed test counts
            "src/test_app.py",  # colocated with the target
        }
    )
    found = _certified_test_files(inventory, "src/app.py")
    assert found == [
        "tests/test_app.py",
        "tests/unit/test_app.py",
        "src/test_app.py",
    ]

    # No inventory-covered test for the target -> empty.
    assert _certified_test_files(frozenset({"src/app.py"}), "src/app.py") == []

    # C47: a root-level target's colocated test matches the normalized key.
    root_colocated = _certified_test_files(
        frozenset({"app.py", "test_app.py"}), "app.py"
    )
    assert root_colocated == ["test_app.py"]

    # Glob patterns (test_{stem}_*.py) match conventional suffixed tests.
    globbed = _certified_test_files(
        frozenset({"tests/test_app_behavior.py", "src/app.py"}), "src/app.py"
    )
    assert globbed == ["tests/test_app_behavior.py"]

    # Go's co-located convention (test_dirs=["."]) accepts inventory paths.
    go_tests = _certified_test_files(
        frozenset({"handler.go", "handler_test.go"}), "handler.go"
    )
    assert go_tests == ["handler_test.go"]

    # Round-8 (C36): package-family tests (test_<plugin>.py) match.
    package_tests = _certified_test_files(
        frozenset(
            {
                "languages/python_plugin/extract.py",
                "tests/test_python_plugin.py",
                "tests/test_python_plugin_behavior.py",
            }
        ),
        "languages/python_plugin/extract.py",
    )
    assert package_tests == [
        "tests/test_python_plugin.py",
        "tests/test_python_plugin_behavior.py",
    ]

    # Round-6 (C27): a target that is itself a test file counts, and
    # inventory-covered dependents matching the test patterns count
    # (symbol-reference mode over certified inputs).
    self_test = _certified_test_files(
        frozenset({"tests/test_app.py", "src/app.py"}), "tests/test_app.py"
    )
    assert self_test == ["tests/test_app.py"]
    dep_tests = _certified_test_files(
        frozenset({"src/app.py", "tests/test_app.py", "tests/test_routes.py"}),
        "src/app.py",
        dependents=["tests/test_routes.py"],
    )
    assert dep_tests == ["tests/test_app.py", "tests/test_routes.py"]
    # C54: a dependent outside the inventory is never a certified test.
    outside_dep = _certified_test_files(
        frozenset({"src/app.py", "tests/test_app.py"}),
        "src/app.py",
        dependents=["tests/test_routes.py"],
    )
    assert outside_dep == ["tests/test_app.py"]
