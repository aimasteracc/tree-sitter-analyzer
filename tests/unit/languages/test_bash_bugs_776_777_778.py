"""Tests for Bash extraction bugs #776, #777, #778.

#776 — extract_variables() must be wired into the extraction pipeline so
       variable assignments are actually returned.
#777 — shebang lines (#!) must not appear as 'comment' expressions; bare
       top-level commands must not appear as phantom 'function' entries.
#778 — compact_table_header must not emit '# Unknown' when classes is
       empty; it must fall back to the filename stem.
"""

from __future__ import annotations

import tree_sitter

import tree_sitter_analyzer.formatters  # noqa: F401
from tree_sitter_analyzer.languages.bash_plugin import BashPlugin


def _parse(code: str) -> tuple[tree_sitter.Tree, BashPlugin]:
    plugin = BashPlugin()
    language = plugin.get_tree_sitter_language()
    assert language is not None, "tree-sitter-bash must be available"
    parser = tree_sitter.Parser(language)
    return parser.parse(code.encode("utf-8")), plugin


# ── Bug #776 ─────────────────────────────────────────────────────────────────


class TestVariableExtractionWired:
    """Bug #776: extract_variables() must be called by the pipeline."""

    def test_variables_key_present_in_extract_elements(self) -> None:
        """extract_elements() must return a 'variables' key."""
        code = 'FOO="bar"\n'
        tree, plugin = _parse(code)
        elements = plugin.create_extractor().extract_elements(tree, code)
        assert "variables" in elements

    def test_simple_assignment_is_extracted(self) -> None:
        """A plain variable assignment must yield at least one variable entry."""
        code = 'NAME="Alice"\nCOUNT=42\n'
        tree, plugin = _parse(code)
        elements = plugin.create_extractor().extract_elements(tree, code)
        # extract_variables() must now return real entries, not []
        assert len(elements["variables"]) == 2

    def test_variable_has_name_attribute(self) -> None:
        """Each extracted variable must carry the variable name."""
        code = 'GREETING="hello"\n'
        tree, plugin = _parse(code)
        elements = plugin.create_extractor().extract_elements(tree, code)
        assert len(elements["variables"]) == 1
        assert elements["variables"][0].name == "GREETING"


# ── Bug #777 ─────────────────────────────────────────────────────────────────


class TestNoPhantomElements:
    """Bug #777: shebang must not be a 'comment'; bare commands must not be
    misclassified as functions."""

    def test_shebang_not_in_expressions(self) -> None:
        """#!/usr/bin/env bash shebang must not appear as a comment expression."""
        code = "#!/usr/bin/env bash\necho hello\n"
        tree, plugin = _parse(code)
        expressions = plugin.create_extractor().extract_expressions(tree, code)
        raw_texts = [e.raw_text for e in expressions]
        assert not any(t.startswith("#!") for t in raw_texts), (
            f"Shebang appeared in expressions: {raw_texts}"
        )

    def test_bare_exit_not_a_function(self) -> None:
        """A bare 'exit 0' at top-level must not be classified as a function."""
        code = "#!/usr/bin/env bash\nexit 0\n"
        tree, plugin = _parse(code)
        elements = plugin.create_extractor().extract_elements(tree, code)
        function_names = [f.name for f in elements["functions"]]
        assert "exit" not in function_names, (
            f"'exit' appeared as a function name: {function_names}"
        )

    def test_real_functions_still_extracted(self) -> None:
        """Real function definitions must still be extracted after the fix."""
        code = "#!/usr/bin/env bash\ndeploy() {\n  echo ready\n}\nexit 0\n"
        tree, plugin = _parse(code)
        elements = plugin.create_extractor().extract_elements(tree, code)
        assert [f.name for f in elements["functions"]] == ["deploy"]


