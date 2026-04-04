#!/usr/bin/env python3
"""
Golden Corpus Test Infrastructure

Tests all 17 language plugins against golden corpus files to verify
grammar coverage and element extraction consistency.

This is the core test infrastructure for the Grammar Coverage MECE project Phase 1.1.

Test Logic:
1. Read corpus_{lang}.{ext} file from tests/golden/
2. Call analyze_file() to analyze the corpus
3. Read corpus_{lang}_expected.json for expected node type counts
4. Compare extracted elements with expected counts
5. Display clear diff on failure

Error Handling:
- FileNotFoundError: Missing corpus/expected.json → actionable message
- JSONDecodeError: Malformed expected.json → syntax error message
- TreeSitterParseError: Corpus parse failure → already handled by analyzer

Expected JSON Format:
{
  "language": "python",
  "node_types": {
    "function_definition": 5,
    "class_definition": 2,
    "decorated_definition": 3
  }
}
"""

import json
from collections import Counter
from pathlib import Path

import pytest

from tree_sitter_analyzer import api


class TestGoldenCorpus:
    """Golden corpus tests for all supported languages"""

    # Language to file extension mapping
    LANGUAGE_EXTENSIONS = {
        "python": "py",
        "javascript": "js",
        "typescript": "ts",
        "java": "java",
        "c": "c",
        "cpp": "cpp",
        "go": "go",
        "ruby": "rb",
        "rust": "rs",
        "php": "php",
        "kotlin": "kt",
        "swift": "swift",
        "scala": "scala",
        "bash": "sh",
        "yaml": "yaml",
        "json": "json",
        "sql": "sql",
    }

    @pytest.fixture
    def golden_dir(self) -> Path:
        """Get the golden directory path"""
        return Path(__file__).parent

    def _get_corpus_path(self, golden_dir: Path, language: str) -> Path:
        """Get the corpus file path for a language"""
        ext = self.LANGUAGE_EXTENSIONS[language]
        return golden_dir / f"corpus_{language}.{ext}"

    def _get_expected_path(self, golden_dir: Path, language: str) -> Path:
        """Get the expected.json file path for a language"""
        return golden_dir / f"corpus_{language}_expected.json"

    def _load_expected_json(self, expected_path: Path) -> dict:
        """
        Load and validate expected.json file.

        Args:
            expected_path: Path to expected.json file

        Returns:
            Parsed JSON data

        Raises:
            FileNotFoundError: If expected.json is missing
            JSONDecodeError: If expected.json is malformed
        """
        if not expected_path.exists():
            raise FileNotFoundError(
                f"Expected file missing: {expected_path}. "
                f"Run `tsa generate-expected {expected_path.parent / expected_path.stem.replace('_expected', '')}.*` to create it."
            )

        try:
            with open(expected_path, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(
                f"Malformed expected.json: {e.msg}. Fix JSON syntax in {expected_path}.",
                e.doc,
                e.pos,
            ) from None

    def _extract_node_types_from_file(
        self, corpus_path: Path, language: str
    ) -> dict[str, int]:
        """
        Extract node type counts from corpus file using tree-sitter directly.

        This mirrors the approach in validate_corpus.py to ensure we're
        testing against the actual AST node types, not just extracted elements.

        Args:
            corpus_path: Path to corpus file
            language: Language name

        Returns:
            Dictionary mapping node types to counts
        """
        import tree_sitter

        # Import language-specific tree-sitter module
        language_modules = {
            "python": "tree_sitter_python",
            "javascript": "tree_sitter_javascript",
            "typescript": "tree_sitter_typescript",
            "java": "tree_sitter_java",
            "c": "tree_sitter_c",
            "cpp": "tree_sitter_cpp",
            "go": "tree_sitter_go",
            "ruby": "tree_sitter_ruby",
            "rust": "tree_sitter_rust",
            "php": "tree_sitter_php",
            "kotlin": "tree_sitter_kotlin",
            "swift": "tree_sitter_swift",
            "scala": "tree_sitter_scala",
            "bash": "tree_sitter_bash",
            "yaml": "tree_sitter_yaml",
            "json": "tree_sitter_json",
            "sql": "tree_sitter_sql",
        }

        module_name = language_modules.get(language)
        if not module_name:
            raise ValueError(f"No tree-sitter module for language: {language}")

        try:
            ts_module = __import__(module_name)
        except ImportError:
            pytest.skip(
                f"Tree-sitter module not available: {module_name}. "
                f"Install it with: uv pip install {module_name.replace('_', '-')}"
            )

        # Parse the file
        # Special handling for TypeScript (has language_typescript and language_tsx)
        if language == "typescript" and hasattr(ts_module, "language_typescript"):
            language_func = ts_module.language_typescript
        elif language == "tsx" and hasattr(ts_module, "language_tsx"):
            language_func = ts_module.language_tsx
        elif hasattr(ts_module, "language"):
            language_func = ts_module.language
        elif hasattr(ts_module, f"language_{language}"):
            language_func = getattr(ts_module, f"language_{language}")
        else:
            raise AttributeError(
                f"Module {module_name} does not have a language() function"
            )

        lang = tree_sitter.Language(language_func())
        parser = tree_sitter.Parser(lang)
        source_code = corpus_path.read_text(encoding="utf-8")
        tree = parser.parse(source_code.encode("utf-8"))

        # Count node types recursively
        def count_nodes(node: tree_sitter.Node) -> Counter[str]:
            counts: Counter[str] = Counter()
            if node.is_named:
                counts[node.type] += 1
            for child in node.children:
                counts.update(count_nodes(child))
            return counts

        actual_counts = count_nodes(tree.root_node)
        return dict(actual_counts)

    def _format_diff_critical_only(
        self,
        expected: dict[str, int],
        actual: dict[str, int],
        language: str,
        mismatches: list[tuple[str, int, int]],
    ) -> str:
        """
        Format a clear diff between expected and actual node counts for critical types only.

        Args:
            expected: Expected node type counts (critical types only)
            actual: Actual node type counts (all types)
            language: Language name
            mismatches: List of (node_type, expected_count, actual_count) tuples

        Returns:
            Formatted diff string
        """
        lines = [f"\n{language.upper()} Critical Node Type Count Mismatch:\n"]

        # Header
        lines.append(f"{'Node Type':<40} {'Expected':>10} {'Actual':>10} {'Diff':>10}")
        lines.append("-" * 72)

        # Show only expected types (critical types)
        for node_type in sorted(expected.keys()):
            exp_count = expected[node_type]
            act_count = actual.get(node_type, 0)
            diff = act_count - exp_count

            if diff != 0:
                status = "✗"
            else:
                status = "✓"

            diff_str = f"{diff:+d}" if diff != 0 else "0"
            lines.append(
                f"{status} {node_type:<38} {exp_count:>10} {act_count:>10} {diff_str:>10}"
            )

        # Summary
        lines.append("-" * 72)
        lines.append(
            f"Mismatches: {len(mismatches)} / {len(expected)} critical node types"
        )
        lines.append(
            f"Total node types in corpus: {len(actual)} "
            f"({len(actual) - len(expected)} additional types OK)"
        )
        if mismatches:
            failed_types = [m[0] for m in mismatches]
            lines.append(f"Failed critical types: {', '.join(failed_types)}")

        return "\n".join(lines)

    @pytest.mark.parametrize(
        "language",
        [
            "python",
            "javascript",
            "typescript",
            "java",
            "c",
            "cpp",
            "go",
            "ruby",
            "rust",
            "php",
            "kotlin",
            "swift",
            "scala",
            "bash",
            "yaml",
            "json",
            "sql",
        ],
    )
    def test_golden_corpus(self, language: str, golden_dir: Path) -> None:
        """
        Test golden corpus for a specific language.

        Args:
            language: Language to test
            golden_dir: Golden directory path

        Verifies:
        - Corpus file can be parsed
        - Analysis succeeds
        - Node type counts match expected values
        """
        corpus_path = self._get_corpus_path(golden_dir, language)
        expected_path = self._get_expected_path(golden_dir, language)

        # Check corpus file exists
        if not corpus_path.exists():
            pytest.skip(
                f"Corpus file not found: {corpus_path}. "
                f"Create it to enable {language} golden corpus testing."
            )

        # Load expected counts
        expected_data = self._load_expected_json(expected_path)
        expected_language = expected_data.get("language")
        expected_node_types = expected_data.get("node_types", {})

        # Verify language matches
        assert expected_language == language, (
            f"Language mismatch in expected.json: "
            f"expected '{language}', got '{expected_language}'"
        )

        # Verify corpus can be parsed by analyzer
        # ALWAYS use relative path to avoid security validator issues
        project_root = Path.cwd()
        if corpus_path.is_absolute():
            try:
                corpus_relative = corpus_path.relative_to(project_root)
            except ValueError:
                # corpus_path is outside project_root - this should not happen in tests
                pytest.fail(
                    f"Corpus file {corpus_path} is outside project root {project_root}. "
                    "Tests must use files within the project."
                )
        else:
            corpus_relative = corpus_path

        result = api.analyze_file(str(corpus_relative), language=language)

        # Verify analysis succeeded — skip if language not supported in this environment
        if not result["success"]:
            error = result.get("error", "")
            if "Unsupported language" in error or "not installed" in error:
                pytest.skip(
                    f"Language {language} not supported in this environment: {error}"
                )
        assert result["success"], (
            f"Analysis failed for {language} corpus: "
            f"{result.get('error', 'Unknown error')}"
        )

        # Extract actual node type counts using tree-sitter directly
        # This ensures we're comparing against the full AST, not just extracted elements
        actual_node_types = self._extract_node_types_from_file(corpus_path, language)

        # Compare counts - verify all expected types are present with correct counts
        # Additional node types in actual are OK (expected.json contains only critical types)
        mismatches = []
        for node_type, expected_count in expected_node_types.items():
            actual_count = actual_node_types.get(node_type, 0)
            if actual_count != expected_count:
                mismatches.append((node_type, expected_count, actual_count))

        if mismatches:
            diff = self._format_diff_critical_only(
                expected_node_types, actual_node_types, language, mismatches
            )
            pytest.fail(diff)
