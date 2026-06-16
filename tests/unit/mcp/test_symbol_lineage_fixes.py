"""Regression tests for symbol_lineage_tool scope and caller enrichment.

#757: ref_count counts only import references, not actual call-site callers —
      the call graph must be queried for real callers.
"""

import asyncio
from pathlib import Path

from tree_sitter_analyzer.mcp.tools.symbol_lineage_tool import (
    SymbolLineageTool,
    _filter_references_to_scope,
    _normalize_scope_file_paths,
)

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
# file_paths scope filtering
# ---------------------------------------------------------------------------


class TestFilepathsScopeFilter:
    """file_paths filters reference/call-site rows while keeping definitions."""

    def test_scope_note_absent_when_no_file_paths(self, tmp_path):
        """No file_paths → no scope_note (clean envelope)."""
        _write_py(tmp_path, "a.py", "def foo():\n    pass\n")
        tool = _make_tool(tmp_path)
        result = asyncio.run(tool.execute({"symbol": "foo", "output_format": "json"}))
        assert result["success"] is True
        assert "scope_note" not in result
        assert result["scope_filtered"] is False

    def test_file_paths_filter_references(self, tmp_path):
        from tree_sitter_analyzer.ast_cache import ASTCache

        _write_py(tmp_path, "lib.py", "def foo():\n    return 1\n")
        _write_py(
            tmp_path,
            "a.py",
            "from lib import foo\n\ndef use_a():\n    return foo()\n",
        )
        _write_py(
            tmp_path,
            "b.py",
            "from lib import foo\n\ndef use_b():\n    return foo()\n",
        )
        cache = ASTCache(str(tmp_path))
        cache.index_project(max_files=50)
        cache.close()

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
        assert result["scope_filtered"] is True
        assert result["scope_filter"] == ["a.py"]
        assert {r["file"] for r in result["references"]} == {"a.py"}
        assert result["definition_count"] == 1

    def test_scope_note_mentions_filtered_references(self, tmp_path):
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
        assert "scope_note" in result
        note = result["scope_note"].lower()
        assert "filters references" in note

    def test_scope_cache_key_does_not_cross_pollute(self, tmp_path):
        from tree_sitter_analyzer.ast_cache import ASTCache

        _write_py(tmp_path, "lib.py", "def foo():\n    return 1\n")
        _write_py(
            tmp_path,
            "a.py",
            "from lib import foo\n\ndef use_a():\n    return foo()\n",
        )
        _write_py(
            tmp_path,
            "b.py",
            "from lib import foo\n\ndef use_b():\n    return foo()\n",
        )
        cache = ASTCache(str(tmp_path))
        cache.index_project(max_files=50)
        cache.close()

        tool = _make_tool(tmp_path)
        scoped = asyncio.run(
            tool.execute(
                {"symbol": "foo", "file_paths": ["a.py"], "output_format": "json"}
            )
        )
        unscoped = asyncio.run(tool.execute({"symbol": "foo", "output_format": "json"}))

        assert {r["file"] for r in scoped["references"]} == {"a.py"}
        assert {"a.py", "b.py"} <= {r["file"] for r in unscoped["references"]}
        assert "scope_note" not in unscoped

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
        in the tool args (clean envelope, no spurious scope)."""
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
        # file_paths absent OR None — either is fine, but scoped filtering must
        # not fire (tested in test_scope_note_absent_when_no_file_paths above).
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

    def test_multiple_calls_use_call_site_lines(self, tmp_path):
        from tree_sitter_analyzer.ast_cache import ASTCache

        _write_py(tmp_path, "lib.py", "def target():\n    return 1\n")
        _write_py(
            tmp_path,
            "caller.py",
            (
                "from lib import target\n\n"
                "def f():\n"
                "    x = target()\n"
                "    y = target()\n"
                "    return x + y\n"
            ),
        )
        cache = ASTCache(str(tmp_path))
        cache.index_project(max_files=50)
        cache.close()

        tool = _make_tool(tmp_path)
        result = asyncio.run(
            tool.execute({"symbol": "target", "output_format": "json"})
        )
        call_lines = sorted(
            r["start_line"] for r in result["references"] if r["type"] == "call_site"
        )

        assert call_lines == [4, 5]

    def test_qualified_symbol_name_is_preserved_for_callers(self, tmp_path):
        from tree_sitter_analyzer.ast_cache import ASTCache

        _write_py(tmp_path, "lib.py", "def target():\n    return 1\n")
        _write_py(tmp_path, "other.py", "def target():\n    return 2\n")
        _write_py(
            tmp_path,
            "main.py",
            (
                "import lib\n"
                "import other\n\n"
                "def use_lib():\n"
                "    return lib.target()\n\n"
                "def use_other():\n"
                "    return other.target()\n"
            ),
        )
        cache = ASTCache(str(tmp_path))
        cache.index_project(max_files=50)
        cache.close()

        tool = _make_tool(tmp_path)
        result = asyncio.run(
            tool.execute({"symbol": "lib.target", "output_format": "json"})
        )
        call_refs = [r for r in result["references"] if r["type"] == "call_site"]

        assert [r["name"] for r in call_refs] == ["use_lib"]
        assert [r["start_line"] for r in call_refs] == [5]

    def test_stale_call_graph_does_not_enrich_refs(self, tmp_path):
        from tree_sitter_analyzer.ast_cache import ASTCache

        _write_py(tmp_path, "lib.py", "def gone():\n    return 1\n")
        _write_py(
            tmp_path,
            "caller.py",
            "from lib import gone\n\ndef f():\n    return gone()\n",
        )
        cache = ASTCache(str(tmp_path))
        cache.index_project(max_files=50)
        cache.close()
        _write_py(
            tmp_path,
            "caller.py",
            "from lib import gone\n\ndef f():\n    return 0\n",
        )

        tool = _make_tool(tmp_path)
        result = asyncio.run(tool.execute({"symbol": "gone", "output_format": "json"}))

        assert not any(r["type"] == "call_site" for r in result["references"])


# ---------------------------------------------------------------------------
# scope-path normalization edge branches (#961 split helpers)
# ---------------------------------------------------------------------------


class TestNormalizeScopeFilePaths:
    """Edge branches of the new scope-path helpers."""

    def test_falsy_entries_are_skipped(self, tmp_path):
        """Empty/None entries are dropped (the ``continue`` branch)."""
        result = _normalize_scope_file_paths(str(tmp_path), ["", None, "src/a.py"])
        assert result == {"src/a.py"}

    def test_absolute_path_outside_root_is_kept_verbatim(self, tmp_path):
        """An absolute path not under root keeps its text (ValueError branch)."""
        outside = "/some/other/root/b.py"
        result = _normalize_scope_file_paths(str(tmp_path), [outside])
        assert result == {"/some/other/root/b.py"}

    def test_absolute_path_inside_root_is_relativized(self, tmp_path):
        """An absolute path under root is made relative."""
        inside = tmp_path / "pkg" / "c.py"
        result = _normalize_scope_file_paths(str(tmp_path), [str(inside)])
        assert result == {"pkg/c.py"}

    def test_dot_slash_prefix_is_stripped(self, tmp_path):
        """A leading ``./`` is stripped from relative paths."""
        result = _normalize_scope_file_paths(str(tmp_path), ["./d.py"])
        assert result == {"d.py"}


class TestFilterReferencesToScope:
    """Edge branches of _filter_references_to_scope."""

    def test_empty_scope_returns_references_unchanged(self):
        """Empty scope set short-circuits and returns the input list."""
        refs = [{"file": "a.py"}, {"file": "b.py"}]
        result = _filter_references_to_scope(refs, set())
        assert result is refs

    def test_only_in_scope_references_are_kept(self):
        """Backslash paths normalize before matching the scope set."""
        refs = [{"file": "src\\a.py"}, {"file": "src/b.py"}]
        result = _filter_references_to_scope(refs, {"src/a.py"})
        assert result == [{"file": "src\\a.py"}]
