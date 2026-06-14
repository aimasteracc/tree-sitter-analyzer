"""Unit tests for symbol_lineage_tool."""

import asyncio

import pytest

from tree_sitter_analyzer.mcp.tools.symbol_lineage_tool import (
    SymbolLineageTool,
    _assess_risk,
    _is_test_file,
)


@pytest.fixture
def tool(tmp_path):
    t = SymbolLineageTool(project_root=str(tmp_path))
    t.set_project_path(str(tmp_path))
    return t


def _write_py(tmp_path, name, content):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


class TestRiskAssessment:
    def test_unknown_when_no_definitions(self):
        result = _assess_risk(0, 5, 3)
        assert result["level"] == "unknown"
        assert "Symbol not found" in result["reasons"]

    def test_low_risk(self):
        result = _assess_risk(1, 2, 1)
        assert result["level"] == "low"

    def test_medium_risk(self):
        result = _assess_risk(1, 10, 5)
        assert result["level"] == "medium"

    def test_high_risk(self):
        result = _assess_risk(2, 25, 15)
        assert result["level"] == "high"
        assert result["score"] >= 6


class TestIsTestFile:
    # DF-19: _is_test_file now delegates to utils.test_detection.is_test_file
    # (the canonical implementation).  Assertions are re-pinned to match
    # canonical semantics: test_*.py under a production directory is NOT a test
    # file; FooTest.java / foo_test.js are not in the canonical suffix set.
    @pytest.mark.parametrize(
        "path",
        [
            "tests/test_foo.py",  # test dir prefix → True
            "tests/unit/test_bar.py",  # test dir segment → True
            "foo_test.py",  # _test.py suffix → True
            "foo_test.go",  # _test.go suffix → True
        ],
    )
    def test_detects_test_files(self, path):
        assert _is_test_file(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "src/main.py",
            "tree_sitter_analyzer/mcp/server.py",
            "README.md",
            "setup.py",
            # DF-19 production-file false positives now correctly False:
            "src/test_widget.py",  # test_ prefix but no test-dir evidence
            "tree_sitter_analyzer/mcp/tools/test_gap_tool.py",  # production tool
            "FooTest.java",  # not in canonical suffix set
            "foo_test.js",  # _test.js not in canonical suffix set
        ],
    )
    def test_rejects_non_test_files(self, path):
        assert _is_test_file(path) is False


class TestValidation:
    def test_requires_symbol(self, tool):
        with pytest.raises(ValueError, match="symbol is required"):
            tool.validate_arguments({})

    def test_rejects_empty_symbol(self, tool):
        with pytest.raises(ValueError):
            tool.validate_arguments({"symbol": "  "})

    def test_rejects_bad_depth(self, tool):
        with pytest.raises(ValueError, match="max_depth"):
            tool.validate_arguments({"symbol": "foo", "max_depth": 0})
        with pytest.raises(ValueError, match="max_depth"):
            tool.validate_arguments({"symbol": "foo", "max_depth": 6})

    def test_valid_args_pass(self, tool):
        assert tool.validate_arguments({"symbol": "foo"}) is True
        assert tool.validate_arguments({"symbol": "bar", "max_depth": 2}) is True


class TestToolDefinition:
    def test_definition_has_name(self, tool):
        defn = tool.get_tool_definition()
        assert defn["name"] == "symbol_lineage"
        assert "lineage" in defn["description"].lower()
        assert "inputSchema" in defn

    def test_schema_requires_symbol(self, tool):
        schema = tool.get_tool_schema()
        assert "symbol" in schema["properties"]
        assert "symbol" in schema["required"]


class TestExecute:
    def test_symbol_not_found_returns_unknown_risk(self, tool, tmp_path):
        _write_py(tmp_path, "pkg/__init__.py", "")
        result = asyncio.run(
            tool.execute({"symbol": "NonExistent", "output_format": "json"})
        )
        assert result["success"] is True
        assert result["risk"]["level"] == "unknown"
        assert result["definition_count"] == 0
        # pain #3: missing symbol must surface NOT_FOUND, NOT None.
        # Agents that branch on verdict were treating None as INFO and
        # then "safely" deleting symbols that didn't exist anywhere.
        assert result["verdict"] == "NOT_FOUND"

    def test_verdict_present_when_symbol_found(self, tool, tmp_path):
        """Found symbols must emit a canonical verdict (not None)."""
        _write_py(
            tmp_path,
            "pkg/core.py",
            "def my_func():\n    return 42\n",
        )
        result = asyncio.run(
            tool.execute({"symbol": "my_func", "output_format": "json"})
        )
        assert result["verdict"] in ("INFO", "REVIEW", "CAUTION")

    def test_finds_symbol_returns_success(self, tool, tmp_path):
        _write_py(
            tmp_path,
            "pkg/core.py",
            "def my_func():\n    return 42\n",
        )
        _write_py(
            tmp_path,
            "tests/test_core.py",
            "from pkg.core import my_func\ndef test_my_func():\n    my_func()\n",
        )
        result = asyncio.run(
            tool.execute({"symbol": "my_func", "output_format": "json"})
        )
        assert result["success"] is True
        assert result["definition_count"] + result["reference_count"] >= 0
        assert result["risk"]["level"] in ("low", "medium", "high", "unknown")
        assert "smart_workflow_hint" in result

    def test_toon_format_includes_content(self, tool, tmp_path):
        _write_py(tmp_path, "pkg/__init__.py", "x = 1\n")
        result = asyncio.run(tool.execute({"symbol": "x", "output_format": "toon"}))
        assert result["success"] is True
        assert "toon_content" in result

    def test_no_project_root_raises(self, tmp_path):
        t = SymbolLineageTool(project_root=None)
        with pytest.raises(ValueError, match="Project root"):
            asyncio.run(t.execute({"symbol": "foo"}))


class TestInheritanceLineage:
    """#568: lineage of a class returns the advertised inheritance/override
    content (subclasses/superclasses via extends edges), not only an impact
    profile. Non-class symbols carry no hierarchy section."""

    def test_class_symbol_returns_inheritance_hierarchy(self, tool, tmp_path):
        from tree_sitter_analyzer.ast_cache import ASTCache

        _write_py(
            tmp_path, "base.py", "class Base:\n    def run(self):\n        pass\n"
        )
        _write_py(
            tmp_path,
            "sub.py",
            "from base import Base\n\nclass Sub1(Base):\n    pass\n\n"
            "class Sub2(Base):\n    pass\n",
        )
        ASTCache(str(tmp_path)).index_project(max_files=50)
        result = asyncio.run(tool.execute({"symbol": "Base", "output_format": "json"}))
        hier = result["hierarchy"]
        assert hier["subclass_count"] == 2
        assert sorted(s["name"] for s in hier["subclasses"]) == ["Sub1", "Sub2"]
        # Second call with the index unchanged: result is stable (the cache is
        # not spuriously invalidated when the AST index mtime is the same).
        again = asyncio.run(tool.execute({"symbol": "Base", "output_format": "json"}))
        assert again["hierarchy"]["subclass_count"] == 2

    def test_function_symbol_has_no_hierarchy(self, tool, tmp_path):
        from tree_sitter_analyzer.ast_cache import ASTCache

        _write_py(tmp_path, "m.py", "def standalone():\n    return 1\n")
        ASTCache(str(tmp_path)).index_project(max_files=50)
        result = asyncio.run(
            tool.execute({"symbol": "standalone", "output_format": "json"})
        )
        assert "hierarchy" not in result

    def test_qualified_symbol_name_resolves_hierarchy(self, tool, tmp_path):
        # Codex P2: a qualified symbol (pkg.Base) must resolve via its bare name
        # — ClassHierarchy stores classes by bare name from the AST cache.
        from tree_sitter_analyzer.ast_cache import ASTCache

        _write_py(tmp_path, "base.py", "class Base:\n    pass\n")
        _write_py(
            tmp_path, "sub.py", "from base import Base\n\nclass Sub(Base):\n    pass\n"
        )
        ASTCache(str(tmp_path)).index_project(max_files=50)
        result = asyncio.run(
            tool.execute({"symbol": "base.Base", "output_format": "json"})
        )
        assert result["hierarchy"]["subclass_count"] == 1

    def test_cache_invalidates_when_index_built_after_first_call(self, tool, tmp_path):
        # Codex P2: a lineage call BEFORE the index is built caches a no-
        # hierarchy response; once the index is built the cache must refresh
        # (the index.db mtime invalidates the per-symbol cache).
        from tree_sitter_analyzer.ast_cache import ASTCache

        _write_py(tmp_path, "base.py", "class Base:\n    pass\n")
        _write_py(
            tmp_path, "sub.py", "from base import Base\n\nclass Sub(Base):\n    pass\n"
        )
        # First call: no index yet → no hierarchy (cached).
        first = asyncio.run(tool.execute({"symbol": "Base", "output_format": "json"}))
        assert "hierarchy" not in first
        # Build the index, then re-query: the stale miss must NOT be served.
        ASTCache(str(tmp_path)).index_project(max_files=50)
        second = asyncio.run(tool.execute({"symbol": "Base", "output_format": "json"}))
        assert second["hierarchy"]["subclass_count"] == 1

    def test_hierarchy_degrades_to_none_on_error(self, tool, tmp_path, monkeypatch):
        # A ClassHierarchy failure (e.g. corrupt cache) must degrade to no
        # hierarchy, never crash the lineage call.
        import tree_sitter_analyzer.class_hierarchy as ch_mod
        from tree_sitter_analyzer.ast_cache import ASTCache

        _write_py(tmp_path, "base.py", "class Base:\n    pass\n")
        ASTCache(str(tmp_path)).index_project(max_files=50)

        def _boom(self):
            raise RuntimeError("corrupt cache")

        monkeypatch.setattr(ch_mod.ClassHierarchy, "build", _boom)
        result = asyncio.run(tool.execute({"symbol": "Base", "output_format": "json"}))
        assert result["success"] is True
        assert "hierarchy" not in result

    def test_hierarchy_flags_stale_after_source_edit_without_reindex(
        self, tool, tmp_path
    ):
        """#692: index_stale=True when source is newer than the AST index."""
        import os
        import time

        from tree_sitter_analyzer.ast_cache import ASTCache

        _write_py(
            tmp_path, "base.py", "class Base:\n    def run(self):\n        pass\n"
        )
        sub_path = tmp_path / "sub.py"
        _write_py(
            tmp_path,
            "sub.py",
            "from base import Base\nclass Sub(Base):\n    pass\n",
        )
        # Build the index so hierarchy is populated.
        ASTCache(str(tmp_path)).index_project(max_files=50)

        # Bump sub.py's mtime to AFTER the index was written, WITHOUT re-indexing.
        # Use a deterministic future timestamp to avoid timing races.
        future_ns = int(time.time() * 1e9) + 10_000_000_000  # 10 seconds ahead
        future_s = future_ns / 1e9
        os.utime(str(sub_path), (future_s, future_s))

        # The tool must re-build the dep graph (source mtime changed) so
        # _dep_graph_fingerprint.max_mtime_ns reflects the bumped mtime.
        # Force cache invalidation by resetting the tool state.
        tool._dep_graph = None
        tool._dep_graph_fingerprint = None
        tool._symbol_cache = {}

        result = asyncio.run(tool.execute({"symbol": "Base", "output_format": "json"}))
        hier = result["hierarchy"]
        # Stale row still reported (the index still has Sub).
        assert hier["subclass_count"] == 1
        # Freshness flag must be present and True.
        assert hier["index_stale"] is True
        assert "index_hint" in hier

    def test_hierarchy_not_stale_when_index_fresh(self, tool, tmp_path):
        """#692: index_stale=False immediately after indexing (no source edits)."""
        import os
        import time

        from tree_sitter_analyzer.ast_cache import ASTCache

        _write_py(
            tmp_path, "base.py", "class Base:\n    def run(self):\n        pass\n"
        )
        _write_py(
            tmp_path,
            "sub.py",
            "from base import Base\nclass Sub(Base):\n    pass\n",
        )
        # Set source mtimes to a point in the past so index is guaranteed newer.
        past_s = time.time() - 60
        for name in ("base.py", "sub.py"):
            p = str(tmp_path / name)
            os.utime(p, (past_s, past_s))

        # Build the index AFTER setting source mtimes to the past.
        ASTCache(str(tmp_path)).index_project(max_files=50)

        result = asyncio.run(tool.execute({"symbol": "Base", "output_format": "json"}))
        hier = result["hierarchy"]
        assert hier["subclass_count"] == 1
        # Index is fresh: stale flag must be False, hint must be absent.
        assert hier["index_stale"] is False
        assert "index_hint" not in hier

    def test_hierarchy_stale_uses_fingerprint_fallback_when_graph_missing(
        self, tool, tmp_path
    ):
        """#692: when the dep-graph fingerprint is absent (graph build failed) the
        freshness check falls back to compute_graph_fingerprint directly."""
        import os
        import time

        from tree_sitter_analyzer.ast_cache import ASTCache

        _write_py(tmp_path, "base.py", "class Base:\n    pass\n")
        _write_py(
            tmp_path, "sub.py", "from base import Base\nclass Sub(Base):\n    pass\n"
        )
        past_s = time.time() - 60
        for name in ("base.py", "sub.py"):
            os.utime(str(tmp_path / name), (past_s, past_s))
        ASTCache(str(tmp_path)).index_project(max_files=50)

        # Force the fallback: no cached dep-graph fingerprint available.
        tool._dep_graph_fingerprint = None
        hier = tool._hierarchy_for("Base")
        assert hier is not None
        assert hier["subclass_count"] == 1
        # Source mtimes are in the past, index is newer → fresh via the fallback.
        assert hier["index_stale"] is False
        assert "index_hint" not in hier


class TestR37uTopLevelVerdictMirror:
    """r37u dogfood: ``--symbol-lineage`` envelope used to omit top-level
    ``verdict`` even though ``agent_summary.verdict`` was populated.
    Matches the N4 pattern other tools already follow — agents branching
    on ``result["verdict"]`` should see the same value as
    ``result["agent_summary"]["verdict"]``.
    """

    def test_top_level_verdict_mirrors_agent_summary_when_found(self, tool, tmp_path):
        _write_py(
            tmp_path,
            "pkg/core.py",
            "def my_func():\n    return 42\n",
        )
        result = asyncio.run(
            tool.execute({"symbol": "my_func", "output_format": "json"})
        )
        assert result["success"] is True
        # Top-level verdict must be present (not None) AND match agent_summary.
        assert result["verdict"] is not None, (
            "r37u: top-level 'verdict' must be populated for envelope contract parity"
        )
        assert result["verdict"] == result["agent_summary"]["verdict"]

    def test_top_level_verdict_mirrors_when_not_found(self, tool, tmp_path):
        """Even when no definition is found, top-level verdict must mirror."""
        _write_py(tmp_path, "pkg/__init__.py", "")
        result = asyncio.run(
            tool.execute({"symbol": "NonExistent", "output_format": "json"})
        )
        assert result["success"] is True
        assert result["verdict"] is not None
        assert result["verdict"] == result["agent_summary"]["verdict"]
        # 'unknown' risk maps to 'NOT_FOUND' verdict per the canonical
        # vocabulary (CLAUDE.md). The historical "n/a" placeholder was
        # non-canonical and caused agents to treat missing symbols as INFO.
        assert result["verdict"] == "NOT_FOUND"
