"""Regression tests for Go parameter name/type swap bug.

Two defects (confirmed by reproduce command):
1. process_parameters("go") routes through _process_type_prefix_parameter
   which assumes type-before-name (Java style). Go is name-before-type,
   so "n int64" produces name="int64", type="n" (SWAPPED).
2. GoTableFormatter._create_go_signature does str(p) on each param dict,
   leaking {'name': 'int64', 'type': 'n'} into the rendered signature.

Reproduce:
  uv run python -m tree_sitter_analyzer /tmp/oss-go/Go/math/eulertotient.go
      --advanced --table full
  Source: func Phi(n int64) int64
  Bad:    | Phi | ({'name': 'int64', 'type': 'n'}) int64 | ...
  Good:   | Phi | (n int64) int64 | ...
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.cli.commands.table_command_helpers import process_parameters
from tree_sitter_analyzer.formatters.go_formatter import GoTableFormatter

# ---------------------------------------------------------------------------
# Defect 1: process_parameters for Go language
# ---------------------------------------------------------------------------


class TestProcessParametersGo:
    """Go params are name-before-type: 'n int64' → name='n', type='int64'."""

    def test_single_param_name_before_type(self):
        """'n int64' must parse as name='n', type='int64', not swapped."""
        result = process_parameters(["n int64"], "go")
        assert len(result) == 1
        assert result[0]["name"] == "n"
        assert result[0]["type"] == "int64"

    def test_single_param_plain_int(self):
        """'n int' must parse as name='n', type='int'."""
        result = process_parameters(["n int"], "go")
        assert len(result) == 1
        assert result[0]["name"] == "n"
        assert result[0]["type"] == "int"

    def test_two_params_same_type(self):
        """'n int, k int' — each individually parsed."""
        result = process_parameters(["n int", "k int"], "go")
        assert len(result) == 2
        assert result[0]["name"] == "n"
        assert result[0]["type"] == "int"
        assert result[1]["name"] == "k"
        assert result[1]["type"] == "int"

    def test_multi_word_type(self):
        """Pointer receiver type: 'p []byte' → name='p', type='[]byte'."""
        result = process_parameters(["p []byte"], "go")
        assert len(result) == 1
        assert result[0]["name"] == "p"
        assert result[0]["type"] == "[]byte"

    def test_pointer_param(self):
        """'config *Config' → name='config', type='*Config'."""
        result = process_parameters(["config *Config"], "go")
        assert len(result) == 1
        assert result[0]["name"] == "config"
        assert result[0]["type"] == "*Config"

    def test_variadic_param(self):
        """'numbers ...int' → name='numbers', type='...int'."""
        result = process_parameters(["numbers ...int"], "go")
        assert len(result) == 1
        assert result[0]["name"] == "numbers"
        assert result[0]["type"] == "...int"

    def test_empty_list(self):
        """Empty param list returns empty list."""
        result = process_parameters([], "go")
        assert result == []


# ---------------------------------------------------------------------------
# Defect 2: GoTableFormatter._create_go_signature renders correctly
# ---------------------------------------------------------------------------


class TestGoSignatureRendering:
    """Signature must show 'n int64', never the raw dict repr."""

    def _func_dict(self, params: list[dict], return_type: str = "") -> dict:
        return {
            "name": "Phi",
            "parameters": params,
            "return_type": return_type,
            "line_range": {"start": 1, "end": 3},
            "docstring": "",
            "is_method": False,
        }

    def test_single_param_renders_correctly(self):
        """(n int64) int64 — no raw dict repr in output."""
        formatter = GoTableFormatter("full")
        params = [{"name": "n", "type": "int64"}]
        func = self._func_dict(params, "int64")
        sig = formatter._create_go_signature(func)
        # Correct: shows "n int64"
        assert "n int64" in sig
        # Never leaks raw dict
        assert "{'name'" not in sig
        assert '{"name"' not in sig

    def test_two_params_render_correctly(self):
        """(n int, k int) — two params rendered without dict repr."""
        formatter = GoTableFormatter("full")
        params = [{"name": "n", "type": "int"}, {"name": "k", "type": "int"}]
        func = self._func_dict(params, "")
        sig = formatter._create_go_signature(func)
        assert "n int" in sig
        assert "k int" in sig
        assert "{'name'" not in sig

    def test_return_type_appended(self):
        """Return type is appended after the param list."""
        formatter = GoTableFormatter("full")
        params = [{"name": "n", "type": "int64"}]
        func = self._func_dict(params, "int64")
        sig = formatter._create_go_signature(func)
        # Should end with ) int64
        assert sig.endswith(") int64")

    def test_multi_return_type(self):
        """(int, error) return type is preserved."""
        formatter = GoTableFormatter("full")
        params = [{"name": "n", "type": "int"}, {"name": "k", "type": "int"}]
        func = self._func_dict(params, "(int, error)")
        sig = formatter._create_go_signature(func)
        assert "(int, error)" in sig
        assert "{'name'" not in sig

    def test_no_params(self):
        """() — zero-param function renders clean parens."""
        formatter = GoTableFormatter("full")
        func = self._func_dict([], "string")
        sig = formatter._create_go_signature(func)
        assert sig == "() string"


# ---------------------------------------------------------------------------
# Defect 1+2 combined: end-to-end via real Go plugin
# ---------------------------------------------------------------------------


class TestGoParamExtractionEndToEnd:
    """Parse a real Go snippet; verify the params and signature are correct."""

    @pytest.fixture
    def phi_fixture(self, tmp_path):
        """Write a minimal Go fixture with func Phi(n int64) int64."""
        go_src = tmp_path / "phi.go"
        go_src.write_text("package math\n\nfunc Phi(n int64) int64 {\n\treturn n\n}\n")
        return str(go_src)

    @pytest.fixture
    def combinations_fixture(self, tmp_path):
        """Write a minimal Go fixture with func Combinations(n int, k int) (int, error)."""
        go_src = tmp_path / "combo.go"
        go_src.write_text(
            "package math\n\n"
            "func Combinations(n int, k int) (int, error) {\n\treturn 0, nil\n}\n"
        )
        return str(go_src)

    def _extract_functions(self, file_path: str) -> list:
        """Run the Go plugin against a file and return Function elements."""
        import tree_sitter
        import tree_sitter_go

        from tree_sitter_analyzer.languages.go_plugin import GoElementExtractor

        source = open(file_path, "rb").read()
        lang = tree_sitter.Language(tree_sitter_go.language())
        parser = tree_sitter.Parser(lang)
        tree = parser.parse(source)
        extractor = GoElementExtractor()
        extractor._get_node_text = lambda node: source[
            node.start_byte : node.end_byte
        ].decode("utf-8")
        extractor._content_lines = source.decode("utf-8").splitlines()
        return extractor.extract_functions(tree, source.decode("utf-8"))

    def test_phi_param_extraction(self, phi_fixture):
        """func Phi(n int64) int64 — extracted params must have name='n', type='int64'."""
        functions = self._extract_functions(phi_fixture)
        phi = next((f for f in functions if f.name == "Phi"), None)
        assert phi is not None, "Phi function not extracted"
        # parameters is list[str] at extraction time: ["n int64"]
        assert phi.parameters == ["n int64"]

    def test_combinations_param_extraction(self, combinations_fixture):
        """func Combinations(n int, k int) — params extracted as strings."""
        functions = self._extract_functions(combinations_fixture)
        combo = next((f for f in functions if f.name == "Combinations"), None)
        assert combo is not None, "Combinations function not extracted"
        assert combo.parameters == ["n int", "k int"]

    def test_phi_signature_in_table(self, phi_fixture):
        """GoTableFormatter must render (n int64) int64, not raw dicts."""
        functions = self._extract_functions(phi_fixture)
        phi = next((f for f in functions if f.name == "Phi"), None)
        assert phi is not None

        # Simulate what TableCommand._convert_function_element does:
        from tree_sitter_analyzer.cli.commands.table_command_helpers import (
            process_parameters,
        )

        params = phi.parameters  # list[str] = ["n int64"]
        processed = process_parameters(params, "go")
        assert processed[0]["name"] == "n"
        assert processed[0]["type"] == "int64"

        # Now render via the formatter
        formatter = GoTableFormatter("full")
        func_dict = {
            "name": phi.name,
            "parameters": processed,
            "return_type": phi.return_type,
            "line_range": {"start": phi.start_line, "end": phi.end_line},
            "docstring": phi.docstring or "",
            "is_method": phi.is_method,
        }
        sig = formatter._create_go_signature(func_dict)
        assert "n int64" in sig
        assert "{'name'" not in sig
        assert '{"name"' not in sig
