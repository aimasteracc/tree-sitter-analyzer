"""Unit tests for call_graph_tool.py — CodeGraphCallTool MCP tool."""

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.call_graph_tool import CodeGraphCallTool

# See tests/unit/test_call_graph.py — root cause was iteration-order
# in CallGraph.build(), now fixed with a two-pass build. Marker kept
# as no-op for backwards compat with @decorators below.
_WINDOWS_SKIP_PY_FIXTURE = pytest.mark.skipif(
    False, reason="resolved by two-pass build in call_graph.py"
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "call_graph"
PY_PROJECT = str(FIXTURES_DIR / "python_project")


@pytest.fixture
def tool():
    t = CodeGraphCallTool(PY_PROJECT)
    return t


# ============================================================
# Initialization and configuration
# ============================================================


class TestCodeGraphCallToolInit:
    def test_init_with_project_root(self):
        t = CodeGraphCallTool(PY_PROJECT)
        assert t.project_root == PY_PROJECT
        assert not t.call_graph_initialized

    def test_init_without_project_root(self):
        t = CodeGraphCallTool()
        assert t.project_root is None
        assert not t.call_graph_initialized

    def test_set_project_path_resets_graph(self, tool):
        tool.get_call_graph()
        assert tool.call_graph_initialized
        tool.set_project_path(PY_PROJECT)
        assert not tool.call_graph_initialized

    def test_get_call_graph_creates_instance(self, tool):
        cg = tool.get_call_graph()
        assert cg is not None
        assert cg.project_root == Path(PY_PROJECT).resolve()

    def test_get_call_graph_caches(self, tool):
        cg1 = tool.get_call_graph()
        cg2 = tool.get_call_graph()
        assert cg1 is cg2

    def test_get_call_graph_raises_without_root(self):
        t = CodeGraphCallTool()
        with pytest.raises(ValueError, match="Project root not set"):
            t.get_call_graph()


# ============================================================
# Tool definition and schema
# ============================================================


class TestCodeGraphCallToolDefinition:
    def test_get_tool_definition(self, tool):
        defn = tool.get_tool_definition()
        assert defn["name"] == "codegraph_call_graph"
        assert "inputSchema" in defn
        assert "description" in defn

    def test_get_tool_schema_modes(self, tool):
        schema = tool.get_tool_schema()
        modes = schema["properties"]["mode"]["enum"]
        assert "callers" in modes
        assert "callees" in modes
        assert "chain" in modes
        assert "summary" in modes
        assert "all_functions" in modes

    def test_get_tool_schema_defaults(self, tool):
        schema = tool.get_tool_schema()
        assert schema["properties"]["mode"]["default"] == "summary"
        assert schema["properties"]["output_format"]["default"] == "toon"
        assert schema["properties"]["depth"]["default"] == 5

    def test_get_tool_schema_no_additional_props(self, tool):
        schema = tool.get_tool_schema()
        assert schema["additionalProperties"] is False


# ============================================================
# Validation
# ============================================================


class TestCodeGraphCallToolValidation:
    def test_validate_summary_no_func_name(self, tool):
        assert tool.validate_arguments({"mode": "summary"})

    def test_validate_all_functions_no_func_name(self, tool):
        assert tool.validate_arguments({"mode": "all_functions"})

    def test_validate_callers_requires_func_name(self, tool):
        with pytest.raises(ValueError, match="function_name is required"):
            tool.validate_arguments({"mode": "callers"})

    def test_validate_callees_requires_func_name(self, tool):
        with pytest.raises(ValueError, match="function_name is required"):
            tool.validate_arguments({"mode": "callees"})

    def test_validate_chain_requires_func_name(self, tool):
        with pytest.raises(ValueError, match="function_name is required"):
            tool.validate_arguments({"mode": "chain"})

    def test_validate_callers_with_func_name(self, tool):
        assert tool.validate_arguments({"mode": "callers", "function_name": "foo"})

    def test_validate_default_mode(self, tool):
        assert tool.validate_arguments({})

    # Regression: M8 — `mode='tree'` (a reasonable typo for 'chain')
    # used to fall through to the deep ``else: raise ValueError("Unknown mode")``
    # *after* the graph was built (2-5s on medium repos). Now it must fail
    # fast in validate_arguments with the enum spelled out.
    def test_validate_invalid_mode_lists_valid_modes(self, tool):
        with pytest.raises(ValueError) as exc_info:
            tool.validate_arguments({"mode": "tree", "function_name": "foo"})
        msg = str(exc_info.value)
        assert "tree" in msg
        # All five valid modes must appear in the error message
        for valid in ("callers", "callees", "chain", "summary", "all_functions"):
            assert valid in msg, f"Missing '{valid}' in error: {msg}"

    def test_validate_invalid_mode_without_function_name(self, tool):
        # Even without function_name, the invalid-mode check fires first.
        with pytest.raises(ValueError, match="Invalid mode 'bogus'"):
            tool.validate_arguments({"mode": "bogus"})

    @pytest.mark.asyncio
    async def test_execute_invalid_mode_fails_before_graph_build(self, tool):
        # Pre-condition: no graph built yet.
        assert not tool.call_graph_initialized
        with pytest.raises(ValueError, match="Invalid mode 'tree'"):
            await tool.execute({"mode": "tree"})
        # Post-condition: still no graph — validation rejected before build.
        assert not tool.call_graph_initialized


# ============================================================
# Execute — summary mode
# ============================================================


class TestCodeGraphCallToolSummary:
    @pytest.mark.asyncio
    async def test_summary_mode(self, tool):
        result = await tool.execute({"mode": "summary", "output_format": "json"})
        assert result["success"] is True
        assert result["mode"] == "summary"
        assert "function_count" in result
        assert "call_edge_count" in result
        assert "file_count" in result

    @pytest.mark.asyncio
    async def test_default_mode_is_summary(self, tool):
        result = await tool.execute({"output_format": "json"})
        assert result["mode"] == "summary"


# ============================================================
# Execute — all_functions mode
# ============================================================


class TestCodeGraphCallToolAllFunctions:
    @pytest.mark.asyncio
    async def test_all_functions(self, tool):
        result = await tool.execute({"mode": "all_functions", "output_format": "json"})
        assert result["success"] is True
        assert result["mode"] == "all_functions"
        assert "count" in result
        assert "functions" in result
        assert result["count"] == len(result["functions"])


# ============================================================
# Execute — callers mode
# ============================================================


class TestCodeGraphCallToolCallers:
    @pytest.mark.asyncio
    async def test_callers_of_existing_function(self, tool):
        result = await tool.execute(
            {
                "mode": "callers",
                "function_name": "load_data",
                "output_format": "json",
            }
        )
        assert result["success"] is True
        assert result["mode"] == "callers"
        assert result["function"] == "load_data"
        assert isinstance(result["callers"], list)

    @pytest.mark.asyncio
    async def test_callers_of_nonexistent(self, tool):
        result = await tool.execute(
            {
                "mode": "callers",
                "function_name": "nonexistent",
                "output_format": "json",
            }
        )
        assert result["success"] is True
        assert result["caller_count"] == 0

    @pytest.mark.asyncio
    async def test_callers_with_file_path(self, tool):
        result = await tool.execute(
            {
                "mode": "callers",
                "function_name": "load_data",
                "file_path": "main.py",
                "output_format": "json",
            }
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_callers_qualified_class_method_resolves(self, tool):
        """Qualified ``Class.method`` form should resolve, not silently return 0."""
        result = await tool.execute(
            {
                "mode": "callers",
                "function_name": "UserService._fetch",
                "output_format": "json",
            }
        )
        assert result["success"] is True
        # Same number of callers as the bare form.
        bare = await tool.execute(
            {
                "mode": "callers",
                "function_name": "_fetch",
                "output_format": "json",
            }
        )
        assert result["caller_count"] == bare["caller_count"]
        assert result["caller_count"]
        # No hint needed when qualified form matched.
        assert "hint" not in result

    @pytest.mark.asyncio
    async def test_callers_qualified_zero_hits_with_hint(self, tmp_path):
        """When a qualified ``Class.method`` lookup resolves but yields 0
        callers, and the bare name has callers via inherited/super calls,
        the response must include a ``hint`` field pointing to the bare name."""
        # Build a synthetic project where Base.method is defined but its
        # only callers reference it via super().method() (which resolves
        # only to the bare name, not to Base.method).
        project = tmp_path
        (project / "base.py").write_text(
            "class Base:\n    def method(self):\n        return 1\n"
        )
        (project / "child.py").write_text(
            "from base import Base\n"
            "class Child(Base):\n"
            "    def method(self):\n"
            "        return super().method() + 1\n"
            "    def other(self):\n"
            "        return self.method()\n"
        )
        t = CodeGraphCallTool(str(project))
        # Qualified — Base.method has 0 direct callers (super() resolves to
        # bare 'method', not 'Base.method').
        qualified = await t.execute(
            {
                "mode": "callers",
                "function_name": "Base.method",
                "output_format": "json",
            }
        )
        assert qualified["success"] is True
        assert qualified["caller_count"] == 0
        # Bare 'method' has callers.
        bare = await t.execute(
            {
                "mode": "callers",
                "function_name": "method",
                "output_format": "json",
            }
        )
        assert bare["caller_count"]
        # Hint must be present on the qualified zero-hit response.
        assert "hint" in qualified
        assert "method" in qualified["hint"]
        assert str(bare["caller_count"]) in qualified["hint"]
        # No hint when bare form already returned results.
        assert "hint" not in bare


# ============================================================
# Execute — callees mode
# ============================================================


class TestCodeGraphCallToolCallees:
    @_WINDOWS_SKIP_PY_FIXTURE
    @pytest.mark.asyncio
    async def test_callees_of_main(self, tool):
        result = await tool.execute(
            {
                "mode": "callees",
                "function_name": "main",
                "output_format": "json",
            }
        )
        assert result["success"] is True
        assert result["function"] == "main"
        assert isinstance(result["callees"], list)
        callee_names = {c["name"] for c in result["callees"]}
        assert "load_data" in callee_names

    @pytest.mark.asyncio
    async def test_callees_leaf_function(self, tool):
        result = await tool.execute(
            {
                "mode": "callees",
                "function_name": "save",
                "output_format": "json",
            }
        )
        assert result["success"] is True
        assert result["callee_count"] == 0


# ============================================================
# Execute — chain mode
# ============================================================


class TestCodeGraphCallToolChain:
    @pytest.mark.asyncio
    async def test_chain_from_main(self, tool):
        result = await tool.execute(
            {
                "mode": "chain",
                "function_name": "main",
                "output_format": "json",
            }
        )
        assert result["success"] is True
        assert result["mode"] == "chain"
        assert isinstance(result["chain"], list)
        assert result["edge_count"] == len(result["chain"])

    @pytest.mark.asyncio
    async def test_chain_custom_depth(self, tool):
        result = await tool.execute(
            {
                "mode": "chain",
                "function_name": "main",
                "depth": 1,
                "output_format": "json",
            }
        )
        assert result["success"] is True
        assert result["depth"] == 1

    @pytest.mark.asyncio
    async def test_chain_nonexistent(self, tool):
        result = await tool.execute(
            {
                "mode": "chain",
                "function_name": "nonexistent",
                "output_format": "json",
            }
        )
        assert result["success"] is True
        assert result["edge_count"] == 0


# ============================================================
# Execute — unknown mode
# ============================================================


class TestCodeGraphCallToolUnknownMode:
    @pytest.mark.asyncio
    async def test_unknown_mode_raises(self, tool):
        # Updated for round-15 M8: validate_arguments now raises early
        # with the full enum spelled out instead of the deep
        # ``Unknown mode`` fallback. We assert on the canonical
        # ``Invalid mode`` prefix that the new validator emits.
        with pytest.raises(ValueError, match="Invalid mode 'unknown'"):
            await tool.execute({"mode": "unknown", "output_format": "json"})


# ============================================================
# TOON format
# ============================================================


class TestCodeGraphCallToolToonFormat:
    @pytest.mark.asyncio
    async def test_toon_format_summary(self, tool):
        result = await tool.execute({"mode": "summary"})
        assert isinstance(result, dict)


class TestCodeGraphCallToolFileImpact:
    def test_validate_file_impact_requires_file_path(self, tool):
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({"mode": "file_impact"})

    def test_validate_file_impact_with_file_path(self, tool):
        assert tool.validate_arguments({"mode": "file_impact", "file_path": "main.py"})

    @pytest.mark.asyncio
    async def test_file_impact_mode(self, tool):
        result = await tool.execute(
            {
                "mode": "file_impact",
                "file_path": "main.py",
                "output_format": "json",
            }
        )
        assert result["success"] is True
        assert result["mode"] == "file_impact"
        assert "upstream" in result
        assert "downstream" in result
        assert "function_count" in result

    @pytest.mark.asyncio
    async def test_file_impact_nonexistent(self, tool):
        result = await tool.execute(
            {
                "mode": "file_impact",
                "file_path": "nonexistent.py",
                "output_format": "json",
            }
        )
        assert result["success"] is True
        assert result["function_count"] == 0

    def test_validate_functions_in_file_requires_file_path(self, tool):
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({"mode": "functions_in_file"})

    @pytest.mark.asyncio
    async def test_functions_in_file_mode(self, tool):
        result = await tool.execute(
            {
                "mode": "functions_in_file",
                "file_path": "main.py",
                "output_format": "json",
            }
        )
        assert result["success"] is True
        assert result["mode"] == "functions_in_file"
        assert "functions" in result
        assert result["file"] == "main.py"
