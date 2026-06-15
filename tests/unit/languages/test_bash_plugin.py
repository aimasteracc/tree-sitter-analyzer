"""Unit tests for the Bash language plugin."""

from __future__ import annotations

import tree_sitter

from tree_sitter_analyzer.languages.bash_plugin import BashPlugin


def _parse(code: str) -> tuple[tree_sitter.Tree, BashPlugin]:
    plugin = BashPlugin()
    language = plugin.get_tree_sitter_language()
    assert language is not None
    parser = tree_sitter.Parser()
    parser.language = language
    return parser.parse(code.encode("utf-8")), plugin


class TestBashExtraction:
    def test_extracts_function_definition(self) -> None:
        code = "deploy() {\n  echo ready\n}\n"
        tree, plugin = _parse(code)
        elements = plugin.create_extractor().extract_elements(tree, code)

        functions = elements["functions"]
        assert [function.name for function in functions] == ["deploy"]
        assert functions[0].language == "bash"

    def test_extracts_control_flow_expression(self) -> None:
        code = 'for file in *.py; do\n  echo "$file"\ndone\n'
        tree, plugin = _parse(code)
        expressions = plugin.create_extractor().extract_expressions(tree, code)

        kinds = {expr.expression_kind for expr in expressions}
        assert "for_loop" in kinds


class TestBashPluginMetadata:
    def test_language_name(self) -> None:
        assert BashPlugin().get_language_name() == "bash"

    def test_file_extensions(self) -> None:
        assert BashPlugin().get_file_extensions() == [".sh", ".bash", ".zsh"]

    def test_is_applicable(self) -> None:
        plugin = BashPlugin()
        assert plugin.is_applicable("deploy.sh") is True
        assert plugin.is_applicable("deploy.py") is False
