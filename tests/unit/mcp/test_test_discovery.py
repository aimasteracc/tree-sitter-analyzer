"""Unit tests for language-aware test file discovery."""

import tempfile
from pathlib import Path

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
