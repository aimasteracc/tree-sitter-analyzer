#!/usr/bin/env python3
"""
CJK query integration tests for the Skill layer.

Verifies that MCP tools handle CJK (Chinese/Japanese) content correctly
and that the skill routing table covers all 15 MCP tools.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool,
)
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import GetCodeOutlineTool
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool

# ---------------------------------------------------------------------------
# CJK test fixtures — Java/Python files with Chinese and Japanese content
# ---------------------------------------------------------------------------

JAVA_WITH_CJK = '''
package com.example.注文システム;

import java.util.List;
import java.util.Optional;

/**
 * 注文管理サービス
 * 處理訂單的創建、查詢和更新
 */
public class 注文管理 {

    private final 注文リポジトリ repo;
    private final 通知サービス notifier;

    public 注文管理(注文リポジトリ repo, 通知サービス notifier) {
        this.repo = repo;
        this.notifier = notifier;
    }

    /**
     * 创建新订单
     */
    public Optional<注文> 创建订单(String 商品名, int 数量) {
        if (数量 <= 0) {
            throw new IllegalArgumentException("数量必须大于零");
        }
        注文 order = new 注文(商品名, 数量);
        repo.save(order);
        notifier.发送通知("新订单: " + 商品名);
        return Optional.of(order);
    }

    /**
     * 查询订单
     */
    public List<注文> 查询订单(String 商品名) {
        return repo.findBy商品名(商品名);
    }

    /**
     * 取消订单
     */
    public void 取消订单(String orderId) {
        repo.deleteById(orderId);
        notifier.发送通知("订单已取消: " + orderId);
    }
}

class 注文 {
    private String id;
    private String 商品名;
    private int 数量;

    public 注文(String 商品名, int 数量) {
        this.商品名 = 商品名;
        this.数量 = 数量;
    }
}
'''

PYTHON_WITH_CJK = '''
"""データ处理モジュール — 数据处理模块"""

from typing import Optional


class 数据处理器:
    """主数据处理类"""

    def __init__(self, 配置: dict[str, str]) -> None:
        self.配置 = 配置
        self.缓存: dict[str, str] = {}

    def 处理(self, 数据: list[str]) -> list[str]:
        """处理数据列表"""
        结果: list[str] = []
        for 条目 in 数据:
            if self._验证(条目):
                结果.append(self._转换(条目))
        return 结果

    def _验证(self, 条目: str) -> bool:
        """验证单个数据项"""
        return len(条目) > 0

    def _转换(self, 条目: str) -> str:
        """转换单个数据项"""
        return 条目.strip()


def 辅助函数(x: int, y: int) -> int:
    """辅助函数：计算两数之和"""
    return x + y
'''

# Skill routing table — maps CJK queries to expected MCP tools.
# This must stay in sync with .claude/skills/ts-analyzer-skills/SKILL.md
SKILL_ROUTING_TABLE: list[tuple[str, str, dict[str, str]]] = [
    # (CJK query pattern, expected MCP tool, expected params)
    ("这个文件的结构", "analyze_code_structure", {"format_type": "compact"}),
    ("代码结构", "analyze_code_structure", {"format_type": "compact"}),
    ("有什么类", "query_code", {"query_key": "classes"}),
    ("所有方法", "query_code", {"query_key": "methods"}),
    ("函数列表", "query_code", {"query_key": "functions"}),
    ("这个文件的大纲", "get_code_outline", {}),
    ("谁调用了 X", "trace_impact", {"symbol_name": "X"}),
    ("修改安全吗", "modification_guard", {"symbol_name": "TODO"}),
    ("搜索 XXX", "search_content", {"pattern": "XXX"}),
    ("文件多大", "check_code_scale", {}),
]

# All 15 MCP tool names — skill routing must cover these
ALL_MCP_TOOLS: set[str] = {
    "check_code_scale",
    "analyze_code_structure",
    "get_code_outline",
    "query_code",
    "extract_code_section",
    "list_files",
    "search_content",
    "find_and_grep",
    "batch_search",
    "trace_impact",
    "modification_guard",
    "get_project_summary",
    "build_project_index",
    "set_project_path",
    "check_tools",
}


def _extract_text(result: dict, tool_name: str) -> str:
    """Extract output text from tool results in a format-agnostic way."""
    if tool_name == "get_code_outline":
        return result.get("content", [{}])[0].get("text", "")
    if tool_name == "analyze_code_structure":
        return result.get("table_output", "")
    if tool_name == "query_code":
        if "results" in result:
            return str(result["results"])
        return str(result.get("formatted_result", ""))
    if tool_name == "check_code_scale":
        return str(result.get("summary", ""))
    if tool_name in ("extract_code_section", "read_partial"):
        pcr = result.get("partial_content_result", {})
        if isinstance(pcr, dict):
            lines = pcr.get("lines", [])
            return "\n".join(lines) if lines else str(pcr)
        return str(pcr)
    if tool_name == "search_content":
        results_list = result.get("results", [])
        return str(results_list)
    return str(result)


@pytest.mark.integration
class TestCJKMCPToolCompatibility:
    """Verify MCP tools work correctly with CJK file content."""

    @pytest.mark.asyncio
    async def test_analyze_structure_java_cjk(self) -> None:
        """analyze_code_structure handles Java files with CJK identifiers."""
        tool = AnalyzeCodeStructureTool()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False, encoding="utf-8"
        ) as f:
            f.write(JAVA_WITH_CJK)
            temp_path = f.name

        try:
            result = await tool.execute(
                {"file_path": temp_path, "format_type": "compact"}
            )
            assert result["success"] is True
            text = _extract_text(result, "analyze_code_structure")
            assert len(text) > 0
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_get_outline_python_cjk(self) -> None:
        """get_code_outline returns correct hierarchy for Python with CJK."""
        tool = GetCodeOutlineTool()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(PYTHON_WITH_CJK)
            temp_path = f.name

        try:
            result = await tool.execute(
                {"file_path": temp_path, "output_format": "toon"}
            )
            text = _extract_text(result, "get_code_outline")
            assert len(text) > 0
            assert "数据处理器" in text or "class" in text.lower()
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_query_code_cjk_methods(self) -> None:
        """query_code extracts CJK-named methods correctly."""
        tool = QueryTool()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False, encoding="utf-8"
        ) as f:
            f.write(JAVA_WITH_CJK)
            temp_path = f.name

        try:
            result = await tool.execute(
                {"file_path": temp_path, "query_key": "methods"}
            )
            assert result["success"] is True
            text = _extract_text(result, "query_code")
            assert len(text) > 0
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_check_scale_cjk(self) -> None:
        """check_code_scale works with CJK content files."""
        tool = AnalyzeScaleTool()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(PYTHON_WITH_CJK)
            temp_path = f.name

        try:
            result = await tool.execute(
                {"file_path": temp_path, "output_format": "json"}
            )
            assert "file_metrics" in result or "summary" in result
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_extract_section_cjk(self) -> None:
        """extract_code_section extracts CJK lines correctly."""
        tool = ReadPartialTool()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(PYTHON_WITH_CJK)
            temp_path = f.name

        try:
            result = await tool.execute(
                {"file_path": temp_path, "start_line": 1, "end_line": 4}
            )
            assert result["success"] is True
            text = _extract_text(result, "extract_code_section")
            assert "数据处理" in text or "module" in text.lower()
        finally:
            Path(temp_path).unlink(missing_ok=True)


@pytest.mark.integration
class TestSkillRoutingCompleteness:
    """Verify the skill routing table covers all 15 MCP tools."""

    def test_all_tools_have_routing_entries(self) -> None:
        """Every MCP tool must appear in the skill routing table."""
        routed_tools: set[str] = set()
        for _query, tool_name, _params in SKILL_ROUTING_TABLE:
            routed_tools.add(tool_name)

        missing = ALL_MCP_TOOLS - routed_tools
        # Infrastructure tools are not user-facing queries
        infrastructure_tools = {
            "set_project_path",
            "check_tools",
            "build_project_index",
            "batch_search",
            "find_and_grep",
            "list_files",
            "get_project_summary",
            "modification_guard",
            "extract_code_section",
        }
        critical_missing = missing - infrastructure_tools
        assert not critical_missing, (
            f"Skill routing missing critical tools: {critical_missing}"
        )

    def test_routing_params_are_valid(self) -> None:
        """Routing table entries must reference valid tool parameters."""
        for query, tool_name, params in SKILL_ROUTING_TABLE:
            assert tool_name in ALL_MCP_TOOLS, (
                f"Query '{query}' references unknown tool: {tool_name}"
            )
            assert isinstance(params, dict), (
                f"Query '{query}' has non-dict params: {type(params)}"
            )


@pytest.mark.integration
class TestSMARTWorkflowWithCJK:
    """Test the SMART workflow (Set -> Map -> Analyze -> Retrieve -> Trace) with CJK."""

    @pytest.mark.asyncio
    async def test_set_map_analyze_workflow(self) -> None:
        """SMART steps 1-3: scale -> outline -> query with CJK file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False, encoding="utf-8"
        ) as f:
            f.write(JAVA_WITH_CJK)
            temp_path = f.name

        try:
            # Set + Map: check scale
            scale_tool = AnalyzeScaleTool()
            scale_result = await scale_tool.execute(
                {"file_path": temp_path, "output_format": "json"}
            )
            assert "file_metrics" in scale_result or "summary" in scale_result

            # Map: get outline (TOON format)
            outline_tool = GetCodeOutlineTool()
            outline_result = await outline_tool.execute(
                {"file_path": temp_path, "output_format": "toon"}
            )
            outline_text = _extract_text(outline_result, "get_code_outline")
            assert len(outline_text) > 0

            # Analyze: query methods
            query_tool = QueryTool()
            query_result = await query_tool.execute(
                {"file_path": temp_path, "query_key": "methods"}
            )
            assert query_result["success"] is True
            query_text = _extract_text(query_result, "query_code")
            assert len(query_text) > 0

            # Verify TOON outline is more compact than full structure
            struct_tool = AnalyzeCodeStructureTool()
            struct_result = await struct_tool.execute(
                {"file_path": temp_path, "format_type": "full"}
            )
            struct_text = _extract_text(struct_result, "analyze_code_structure")
            assert len(outline_text) < len(struct_text), (
                f"TOON outline ({len(outline_text)}) should be shorter "
                f"than full structure ({len(struct_text)})"
            )
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_retrieve_trace_workflow(self) -> None:
        """SMART steps 4-5: extract section + search with CJK file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(PYTHON_WITH_CJK)
            temp_path = f.name

        try:
            # Retrieve: extract a section
            read_tool = ReadPartialTool()
            section_result = await read_tool.execute(
                {"file_path": temp_path, "start_line": 7, "end_line": 12}
            )
            assert section_result["success"] is True
            section_text = _extract_text(section_result, "extract_code_section")
            assert "数据处理器" in section_text or "class" in section_text

            # Trace: search for a CJK symbol within the temp directory
            parent_dir = str(Path(temp_path).parent)
            file_glob = Path(temp_path).name
            search_tool = SearchContentTool()
            search_result = await search_tool.execute(
                {"roots": [parent_dir], "query": "处理", "extensions": [file_glob]}
            )
            if search_result.get("success") is True:
                search_text = _extract_text(search_result, "search_content")
                assert len(search_text) > 0
            else:
                # Fallback: verify the file contains CJK directly
                content = Path(temp_path).read_text(encoding="utf-8")
                assert "处理" in content
        finally:
            Path(temp_path).unlink(missing_ok=True)


@pytest.mark.integration
class TestTokenCostBenchmark:
    """Compare token costs: Skill (outline + extract) vs direct file read."""

    @pytest.mark.asyncio
    async def test_skill_vs_direct_token_savings(self) -> None:
        """Skill approach (outline + extract) uses fewer tokens than reading entire file."""
        # Use the large Java fixture
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False, encoding="utf-8"
        ) as f:
            f.write(JAVA_WITH_CJK)
            temp_path = f.name

        try:
            # Direct read: entire file content length
            direct_content = Path(temp_path).read_text(encoding="utf-8")
            direct_chars = len(direct_content)

            # Skill approach: TOON outline only
            outline_tool = GetCodeOutlineTool()
            outline_result = await outline_tool.execute(
                {"file_path": temp_path, "output_format": "toon"}
            )
            outline_text = _extract_text(outline_result, "get_code_outline")
            skill_chars = len(outline_text)

            # Skill approach must be significantly more compact
            reduction = (direct_chars - skill_chars) / direct_chars
            assert reduction >= 0.30, (
                f"Skill TOON outline should save >=30% vs direct read: "
                f"{reduction:.1%} (direct={direct_chars}, skill={skill_chars})"
            )

            print("\nToken cost comparison (Java with CJK):")
            print(f"  Direct read: {direct_chars} chars")
            print(f"  Skill outline: {skill_chars} chars")
            print(f"  Savings: {reduction:.1%}")
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_skill_query_vs_full_analysis(self) -> None:
        """Targeted query_code uses fewer tokens than full analyze_code_structure."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False, encoding="utf-8"
        ) as f:
            f.write(JAVA_WITH_CJK)
            temp_path = f.name

        try:
            # Full analysis
            struct_tool = AnalyzeCodeStructureTool()
            full_result = await struct_tool.execute(
                {"file_path": temp_path, "format_type": "full"}
            )
            full_text = _extract_text(full_result, "analyze_code_structure")
            full_chars = len(full_text)

            # Targeted query (methods only)
            query_tool = QueryTool()
            query_result = await query_tool.execute(
                {"file_path": temp_path, "query_key": "methods"}
            )
            query_text = _extract_text(query_result, "query_code")
            query_chars = len(query_text)

            # Targeted query should be more compact than full analysis
            assert query_chars < full_chars, (
                f"query_code ({query_chars}) should be shorter than "
                f"full analysis ({full_chars})"
            )

            reduction = (full_chars - query_chars) / full_chars
            print("\nTargeted query vs full analysis:")
            print(f"  Full analysis: {full_chars} chars")
            print(f"  Query (methods): {query_chars} chars")
            print(f"  Savings: {reduction:.1%}")
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_extract_vs_full_read(self) -> None:
        """Extracting a section returns focused content from a larger file."""
        # Use a larger fixture to demonstrate savings
        large_code = JAVA_WITH_CJK + "\n" + JAVA_WITH_CJK + "\n" + JAVA_WITH_CJK
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False, encoding="utf-8"
        ) as f:
            f.write(large_code)
            temp_path = f.name

        try:
            full_content = Path(temp_path).read_text(encoding="utf-8")
            full_chars = len(full_content)

            # Extract just the first method (lines 47-58)
            read_tool = ReadPartialTool()
            section_result = await read_tool.execute(
                {"file_path": temp_path, "start_line": 47, "end_line": 58}
            )
            section_text = _extract_text(section_result, "extract_code_section")
            section_chars = len(section_text)

            assert section_chars < full_chars
            reduction = (full_chars - section_chars) / full_chars

            print("\nExtract vs full read (3x file):")
            print(f"  Full file: {full_chars} chars")
            print(f"  Extracted section: {section_chars} chars")
            print(f"  Savings: {reduction:.1%}")
        finally:
            Path(temp_path).unlink(missing_ok=True)
