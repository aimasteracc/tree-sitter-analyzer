"""Unit tests for call_graph_tool.py — CodeGraphCallTool MCP tool."""

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.call_graph_tool import CodeGraphCallTool

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
        assert t._call_graph is None

    def test_init_without_project_root(self):
        t = CodeGraphCallTool()
        assert t.project_root is None
        assert t._call_graph is None

    def test_set_project_path_resets_graph(self, tool):
        tool._get_call_graph()
        assert tool._call_graph is not None
        tool.set_project_path(PY_PROJECT)
        assert tool._call_graph is None

    def test_get_call_graph_creates_instance(self, tool):
        cg = tool._get_call_graph()
        assert cg is not None
        assert cg.project_root == Path(PY_PROJECT).resolve()

    def test_get_call_graph_caches(self, tool):
        cg1 = tool._get_call_graph()
        cg2 = tool._get_call_graph()
        assert cg1 is cg2

    def test_get_call_graph_raises_without_root(self):
        t = CodeGraphCallTool()
        with pytest.raises(ValueError, match="Project root not set"):
            t._get_call_graph()


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
        result = await tool.execute({
            "mode": "callers",
            "function_name": "load_data",
            "output_format": "json",
        })
        assert result["success"] is True
        assert result["mode"] == "callers"
        assert result["function"] == "load_data"
        assert isinstance(result["callers"], list)

    @pytest.mark.asyncio
    async def test_callers_of_nonexistent(self, tool):
        result = await tool.execute({
            "mode": "callers",
            "function_name": "nonexistent",
            "output_format": "json",
        })
        assert result["success"] is True
        assert result["caller_count"] == 0

    @pytest.mark.asyncio
    async def test_callers_with_file_path(self, tool):
        result = await tool.execute({
            "mode": "callers",
            "function_name": "load_data",
            "file_path": "main.py",
            "output_format": "json",
        })
        assert result["success"] is True


# ============================================================
# Execute — callees mode
# ============================================================


class TestCodeGraphCallToolCallees:
    @pytest.mark.asyncio
    async def test_callees_of_main(self, tool):
        result = await tool.execute({
            "mode": "callees",
            "function_name": "main",
            "output_format": "json",
        })
        assert result["success"] is True
        assert result["function"] == "main"
        assert isinstance(result["callees"], list)
        callee_names = {c["name"] for c in result["callees"]}
        assert "load_data" in callee_names

    @pytest.mark.asyncio
    async def test_callees_leaf_function(self, tool):
        result = await tool.execute({
            "mode": "callees",
            "function_name": "save",
            "output_format": "json",
        })
        assert result["success"] is True
        assert result["callee_count"] == 0


# ============================================================
# Execute — chain mode
# ============================================================


class TestCodeGraphCallToolChain:
    @pytest.mark.asyncio
    async def test_chain_from_main(self, tool):
        result = await tool.execute({
            "mode": "chain",
            "function_name": "main",
            "output_format": "json",
        })
        assert result["success"] is True
        assert result["mode"] == "chain"
        assert isinstance(result["chain"], list)
        assert result["edge_count"] == len(result["chain"])

    @pytest.mark.asyncio
    async def test_chain_custom_depth(self, tool):
        result = await tool.execute({
            "mode": "chain",
            "function_name": "main",
            "depth": 1,
            "output_format": "json",
        })
        assert result["success"] is True
        assert result["depth"] == 1

    @pytest.mark.asyncio
    async def test_chain_nonexistent(self, tool):
        result = await tool.execute({
            "mode": "chain",
            "function_name": "nonexistent",
            "output_format": "json",
        })
        assert result["success"] is True
        assert result["edge_count"] == 0


# ============================================================
# Execute — unknown mode
# ============================================================


class TestCodeGraphCallToolUnknownMode:
    @pytest.mark.asyncio
    async def test_unknown_mode_raises(self, tool):
        with pytest.raises(ValueError, match="Unknown mode"):
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
        result = await tool.execute({
            "mode": "file_impact",
            "file_path": "main.py",
            "output_format": "json",
        })
        assert result["success"] is True
        assert result["mode"] == "file_impact"
        assert "upstream" in result
        assert "downstream" in result
        assert "function_count" in result

    @pytest.mark.asyncio
    async def test_file_impact_nonexistent(self, tool):
        result = await tool.execute({
            "mode": "file_impact",
            "file_path": "nonexistent.py",
            "output_format": "json",
        })
        assert result["success"] is True
        assert result["function_count"] == 0

    def test_validate_functions_in_file_requires_file_path(self, tool):
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({"mode": "functions_in_file"})

    @pytest.mark.asyncio
    async def test_functions_in_file_mode(self, tool):
        result = await tool.execute({
            "mode": "functions_in_file",
            "file_path": "main.py",
            "output_format": "json",
        })
        assert result["success"] is True
        assert result["mode"] == "functions_in_file"
        assert "functions" in result
        assert result["file"] == "main.py"
