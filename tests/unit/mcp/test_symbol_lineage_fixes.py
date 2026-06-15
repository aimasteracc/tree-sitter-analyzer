"""Regression tests for issues #756 and #757 in symbol_lineage_tool.

#756: file_paths scope parameter is silently ignored — response must carry a
      scope_note when file_paths is provided, and the CLI spec must pass it.
#757: ref_count counts only import references, not actual call-site callers —
      the call graph must be queried for real callers.
"""

import asyncio
from pathlib import Path

from tree_sitter_analyzer.mcp.tools.symbol_lineage_tool import SymbolLineageTool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_py(tmp_path: Path, name: str, content: str) -> None:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def _make_tool(tmp_path: Path) -> SymbolLineageTool:
    t = SymbolLineageTool(project_root=str(tmp_path))
    t.set_project_path(str(tmp_path))
    return t


# ---------------------------------------------------------------------------
# #756: scope_note emitted when file_paths provided
# ---------------------------------------------------------------------------


class TestFilepathsScopeNote:
    """#756: when file_paths is passed, lineage must emit a scope_note
    telling the caller that results are project-wide and file_paths is
    not a scope filter for this tool.
    """

    def test_scope_note_absent_when_no_file_paths(self, tmp_path):
        """No file_paths → no scope_note (clean envelope)."""
        _write_py(tmp_path, "a.py", "def foo():\n    pass\n")
        tool = _make_tool(tmp_path)
        result = asyncio.run(tool.execute({"symbol": "foo", "output_format": "json"}))
        assert result["success"] is True
        assert "scope_note" not in result

    def test_scope_note_present_when_file_paths_provided(self, tmp_path):
        """file_paths is given → scope_note must be present in the response."""
        _write_py(tmp_path, "a.py", "def foo():\n    pass\n")
        tool = _make_tool(tmp_path)
        result = asyncio.run(
            tool.execute(
                {
                    "symbol": "foo",
                    "file_paths": ["a.py"],
                    "output_format": "json",
                }
            )
        )
        assert result["success"] is True
        assert "scope_note" in result

    def test_scope_note_mentions_project_wide(self, tmp_path):
        """scope_note must state that lineage is project-wide."""
        _write_py(tmp_path, "a.py", "def foo():\n    pass\n")
        tool = _make_tool(tmp_path)
        result = asyncio.run(
            tool.execute(
                {
                    "symbol": "foo",
                    "file_paths": ["x/empty.py", "y/other.py"],
                    "output_format": "json",
                }
            )
        )
        assert "scope_note" in result
        note = result["scope_note"].lower()
        assert "project" in note

    def test_file_paths_in_tool_schema(self, tmp_path):
        """file_paths must be declared in the tool schema so MCP callers can pass it."""
        tool = _make_tool(tmp_path)
        schema = tool.get_tool_schema()
        assert "file_paths" in schema["properties"]

    def test_file_paths_not_required(self, tmp_path):
        """file_paths must be optional (not in required list)."""
        tool = _make_tool(tmp_path)
        schema = tool.get_tool_schema()
        assert "file_paths" not in schema.get("required", [])

    def test_validate_arguments_accepts_file_paths(self, tmp_path):
        """validate_arguments must not raise when file_paths is present."""
        tool = _make_tool(tmp_path)
        assert (
            tool.validate_arguments({"symbol": "foo", "file_paths": ["a.py"]}) is True
        )

    def test_cli_spec_passes_file_paths(self, tmp_path):
        """CLI spec build_tool_args must include file_paths when present."""
        from tree_sitter_analyzer.cli.commands.mcp_commands._specs_core import (
            _CORE_SPECS,
        )

        spec = next(s for s in _CORE_SPECS if s.flag_name == "symbol_lineage")

        class _FakeArgs:
            symbol_lineage = "foo"
            max_depth = 3
            file_path = None
            file_paths = ["a.py", "b.py"]

        args = _FakeArgs()
        tool_args = spec.build_tool_args(args, "json")
        assert "file_paths" in tool_args
        assert tool_args["file_paths"] == ["a.py", "b.py"]

    def test_cli_spec_file_paths_none_not_included(self, tmp_path):
        """When CLI --file-paths is not set (None), file_paths must not appear
        in the tool args (clean envelope, no spurious scope_note)."""
        from tree_sitter_analyzer.cli.commands.mcp_commands._specs_core import (
            _CORE_SPECS,
        )

        spec = next(s for s in _CORE_SPECS if s.flag_name == "symbol_lineage")

        class _FakeArgs:
            symbol_lineage = "foo"
            max_depth = 3
            file_path = None
            file_paths = None

        args = _FakeArgs()
        tool_args = spec.build_tool_args(args, "json")
        # file_paths absent OR None — either is fine, but scope_note must not
        # fire (tested in test_scope_note_absent_when_no_file_paths above).
        assert tool_args.get("file_paths") is None or "file_paths" not in tool_args


# ---------------------------------------------------------------------------
# #757: reference_count must include call-site callers, not only imports
# ---------------------------------------------------------------------------


class TestRefCountIncludesCallers:
    """#757: when the call graph has actual call-site callers, they must
    appear in references[] and reference_count must reflect them.
    """

    def test_callers_included_in_references(self, tmp_path):
        """Call-site callers appear in references list."""
        from tree_sitter_analyzer.ast_cache import ASTCache

        _write_py(
            tmp_path,
            "lib.py",
            "def my_func():\n    return 42\n",
        )
        _write_py(
            tmp_path,
            "main.py",
            "from lib import my_func\n\ndef caller():\n    return my_func()\n",
        )
        # Build the call-graph index so query_callers has edges.
        cache = ASTCache(str(tmp_path))
        cache.index_project(max_files=50)
        cache.close()

        tool = _make_tool(tmp_path)
        result = asyncio.run(
            tool.execute({"symbol": "my_func", "output_format": "json"})
        )
        assert result["success"] is True
        # Exactly one call-site caller (caller() in main.py) must appear.
        non_import_refs = [
            r
            for r in result["references"]
            if r.get("type")
            not in ("import_statement", "import_from_statement", "import")
        ]
        assert len(non_import_refs) == 1, (
            f"Expected exactly 1 call-site reference; got refs: {result['references']}"
        )

    def test_reference_count_matches_caller_count(self, tmp_path):
        """reference_count must equal len(references) — no hidden inflation."""
        from tree_sitter_analyzer.ast_cache import ASTCache

        _write_py(tmp_path, "lib.py", "def bar():\n    return 1\n")
        _write_py(
            tmp_path,
            "a.py",
            "from lib import bar\n\ndef use_a():\n    return bar()\n",
        )
        _write_py(
            tmp_path,
            "b.py",
            "from lib import bar\n\ndef use_b():\n    return bar()\n",
        )
        cache = ASTCache(str(tmp_path))
        cache.index_project(max_files=50)
        cache.close()

        tool = _make_tool(tmp_path)
        result = asyncio.run(tool.execute({"symbol": "bar", "output_format": "json"}))
        assert result["success"] is True
        # reference_count must exactly equal len(references) (no off-by-one)
        assert result["reference_count"] == len(result["references"])

    def test_caller_files_appear_in_references(self, tmp_path):
        """Files that contain call sites must appear in references."""
        from tree_sitter_analyzer.ast_cache import ASTCache

        _write_py(tmp_path, "utils.py", "def helper():\n    return 0\n")
        _write_py(
            tmp_path,
            "consumer.py",
            "from utils import helper\n\ndef main():\n    helper()\n",
        )
        cache = ASTCache(str(tmp_path))
        cache.index_project(max_files=50)
        cache.close()

        tool = _make_tool(tmp_path)
        result = asyncio.run(
            tool.execute({"symbol": "helper", "output_format": "json"})
        )
        ref_files = {r.get("file") for r in result["references"]}
        assert "consumer.py" in ref_files, (
            f"consumer.py should be in reference files; got {ref_files}"
        )

    def test_no_duplicate_references_from_call_graph(self, tmp_path):
        """Call-graph callers must not create duplicate reference entries."""
        from tree_sitter_analyzer.ast_cache import ASTCache

        _write_py(tmp_path, "lib.py", "def target():\n    pass\n")
        _write_py(
            tmp_path,
            "caller.py",
            "from lib import target\n\ndef f():\n    target()\n",
        )
        cache = ASTCache(str(tmp_path))
        cache.index_project(max_files=50)
        cache.close()

        tool = _make_tool(tmp_path)
        result = asyncio.run(
            tool.execute({"symbol": "target", "output_format": "json"})
        )
        # No duplicate (file, start_line) pairs in references
        ref_keys = [(r.get("file"), r.get("start_line")) for r in result["references"]]
        assert len(ref_keys) == len(set(ref_keys)), (
            f"Duplicate references found: {ref_keys}"
        )
