#!/usr/bin/env python3
"""
Semantic Golden Master Tests for MCP Tools

这些测试确保 MCP 工具的输出在功能上保持一致，
即使具体的内部实现发生变化。

不同于 CLI 的 golden master 测试（精确字符串匹配），
MCP 工具测试使用语义比较——验证结构、字段、计数是否匹配，
而不是精确的字符串比较。

这解决了用户关注的问题：
"如何能保证别人用我们的项目能够真正实现我们的价值？"

Semantic golden master tests 确保:
1. 工具返回的数据结构保持一致
2. 字段名称、类型不会意外变化
3. 语义等价的输出被认为是相同的（例如，结果顺序可以不同）
4. **Intent Aliases 和原始工具名返回完全相同的结果**（不变性测试）

注意：传统的 golden master baseline 测试（保存响应并逐次比较）
不适用于 MCP 工具，因为响应中包含临时文件路径、时间戳等不稳定字段。
我们使用 **Invariance Testing** 来替代——确保同一个工具的不同调用方式
（原始名称 vs alias）返回语义相同的结果。这种方法更可靠地检测不完整的修改。
"""

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer


class SemanticComparator:
    """
    语义比较器 - 理解工具响应的结构和意义

    不进行精确字符串匹配，而是验证：
    - 必需字段是否存在
    - 数据类型是否正确
    - 计数是否匹配
    - 结果集合是否等价（忽略顺序）
    """

    @staticmethod
    def compare_tool_responses(
        actual: dict[str, Any] | list[Any],
        expected: dict[str, Any] | list[Any],
        ignore_fields: set[str] | None = None
    ) -> tuple[bool, str]:
        """
        比较两个工具响应是否语义等价

        Args:
            actual: 实际响应（dict 或 list）
            expected: 期望响应（dict 或 list）
            ignore_fields: 要忽略的字段集合（如时间戳、版本号）

        Returns:
            (是否匹配, 差异描述)
        """
        if ignore_fields is None:
            ignore_fields = {
                'timestamp', 'analysis_time', 'version',
                'elapsed_ms', 'cache_hit'  # 忽略时间和缓存字段（每次调用都不同）
            }

        # 0. 如果响应是列表（如 get_code_outline 返回 [{"type": "text", "text": "..."}]）
        if isinstance(actual, list) and isinstance(expected, list):
            if len(actual) != len(expected):
                return False, f"列表长度不匹配: actual={len(actual)}, expected={len(expected)}"

            # 逐个比较列表元素
            for i, (a, e) in enumerate(zip(actual, expected, strict=False)):
                if isinstance(a, dict) and isinstance(e, dict):
                    matches, diff = SemanticComparator.compare_tool_responses(a, e, ignore_fields)
                    if not matches:
                        return False, f"列表索引 {i} 不匹配: {diff}"
                elif a != e:
                    return False, f"列表索引 {i} 不匹配: actual={a}, expected={e}"

            return True, "列表语义匹配"

        # 如果一个是列表一个是字典，类型不匹配
        if isinstance(actual, list) != isinstance(expected, list):
            return False, f"响应类型不匹配: actual={type(actual).__name__}, expected={type(expected).__name__}"

        # 1. 检查 success 字段
        if actual.get('success') != expected.get('success'):
            return False, f"success 字段不匹配: actual={actual.get('success')}, expected={expected.get('success')}"

        # 2. 检查 count 字段（如果存在）
        if 'count' in expected:
            if actual.get('count') != expected.get('count'):
                return False, f"count 字段不匹配: actual={actual.get('count')}, expected={expected.get('count')}"

        # 3. 检查 results 字段（如果存在）
        if 'results' in expected:
            actual_results = actual.get('results', [])
            expected_results = expected.get('results', [])

            if len(actual_results) != len(expected_results):
                return False, f"results 长度不匹配: actual={len(actual_results)}, expected={len(expected_results)}"

            # 对于结果列表，我们检查集合等价性（顺序可以不同）
            # 但首先需要将结果标准化为可比较的形式
            matches, diff = SemanticComparator._compare_result_sets(
                actual_results, expected_results, ignore_fields
            )
            if not matches:
                return False, f"results 内容不匹配: {diff}"

        # 4. 检查其他顶层字段（排除忽略字段）
        expected_keys = set(expected.keys()) - ignore_fields
        actual_keys = set(actual.keys()) - ignore_fields

        missing_keys = expected_keys - actual_keys
        if missing_keys:
            return False, f"缺少字段: {missing_keys}"

        extra_keys = actual_keys - expected_keys
        if extra_keys:
            return False, f"多余字段: {extra_keys}"

        # 5. 递归比较其他字段（除了 success, count, results 已经比较过）
        for key in expected_keys - {'success', 'count', 'results'}:
            actual_val = actual[key]
            expected_val = expected[key]

            if isinstance(expected_val, dict) and isinstance(actual_val, dict):
                matches, diff = SemanticComparator.compare_tool_responses(
                    actual_val, expected_val, ignore_fields
                )
                if not matches:
                    return False, f"字段 {key} 不匹配: {diff}"
            elif actual_val != expected_val:
                return False, f"字段 {key} 不匹配: actual={actual_val}, expected={expected_val}"

        return True, "语义匹配"

    @staticmethod
    def _compare_result_sets(
        actual: list[Any],
        expected: list[Any],
        ignore_fields: set[str]
    ) -> tuple[bool, str]:
        """
        比较结果集合（集合语义，忽略顺序）

        对于文件路径结果，只要集合相同即可
        对于结构化结果，递归比较每个元素
        """
        # 如果都是字符串列表（如文件路径），使用集合比较
        if all(isinstance(r, str) for r in actual + expected):
            actual_set = set(actual)
            expected_set = set(expected)

            if actual_set != expected_set:
                missing = expected_set - actual_set
                extra = actual_set - expected_set
                return False, f"集合不匹配: missing={missing}, extra={extra}"
            return True, "集合匹配"

        # 如果是字典列表，需要更复杂的比较
        # 这里简化为逐个元素比较（假设顺序一致）
        # 实际应用中可能需要更智能的匹配算法
        for i, (act, exp) in enumerate(zip(actual, expected, strict=False)):
            if isinstance(exp, dict) and isinstance(act, dict):
                matches, diff = SemanticComparator.compare_tool_responses(
                    act, exp, ignore_fields
                )
                if not matches:
                    return False, f"第 {i} 个元素不匹配: {diff}"
            elif act != exp:
                return False, f"第 {i} 个元素不匹配: actual={act}, expected={exp}"

        return True, "列表匹配"


class GoldenMasterMCPTester:
    """
    MCP 工具的 Golden Master 测试器

    管理基线响应的存储和比较
    """

    def __init__(self, golden_dir: Path | None = None):
        if golden_dir is None:
            golden_dir = Path(__file__).parent.parent.parent / "golden_masters" / "mcp"
        self.golden_dir = golden_dir
        self.golden_dir.mkdir(parents=True, exist_ok=True)

    def save_golden_master(self, tool_name: str, test_case: str, response: dict[str, Any]) -> Path:
        """保存 golden master 基线"""
        filename = f"{tool_name}_{test_case}.json"
        filepath = self.golden_dir / filename

        with filepath.open('w', encoding='utf-8') as f:
            json.dump(response, f, indent=2, ensure_ascii=False)

        return filepath

    def load_golden_master(self, tool_name: str, test_case: str) -> dict[str, Any] | None:
        """加载 golden master 基线"""
        filename = f"{tool_name}_{test_case}.json"
        filepath = self.golden_dir / filename

        if not filepath.exists():
            return None

        with filepath.open('r', encoding='utf-8') as f:
            return json.load(f)

    def assert_matches_golden_master(
        self,
        tool_name: str,
        test_case: str,
        actual_response: dict[str, Any],
        update_golden: bool = False
    ) -> None:
        """
        断言响应与 golden master 匹配

        Args:
            tool_name: 工具名称
            test_case: 测试用例名称
            actual_response: 实际响应
            update_golden: 是否更新 golden master（用于初始化或有意更改后）
        """
        if update_golden:
            self.save_golden_master(tool_name, test_case, actual_response)
            return

        expected_response = self.load_golden_master(tool_name, test_case)

        if expected_response is None:
            # 首次运行，保存为 golden master
            self.save_golden_master(tool_name, test_case, actual_response)
            pytest.skip(f"Created golden master for {tool_name}:{test_case}")

        # 语义比较
        matches, diff = SemanticComparator.compare_tool_responses(
            actual_response, expected_response
        )

        if not matches:
            pytest.fail(
                f"Golden master 不匹配 ({tool_name}:{test_case}):\n"
                f"{diff}\n\n"
                f"Expected:\n{json.dumps(expected_response, indent=2, ensure_ascii=False)}\n\n"
                f"Actual:\n{json.dumps(actual_response, indent=2, ensure_ascii=False)}"
            )


@pytest.fixture(scope="session")
def mcp_server():
    """Session-scoped MCP server"""
    return TreeSitterAnalyzerMCPServer()


@pytest.fixture(scope="session")
def golden_tester():
    """Session-scoped golden master tester"""
    return GoldenMasterMCPTester()


@pytest.fixture
def temp_test_file():
    """创建临时测试文件（每个测试独立目录）"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_file = tmpdir_path / "test_example.py"

        content = '''
def example_function():
    """Example function for testing"""
    return "Hello, World!"

class ExampleClass:
    def method(self):
        pass
'''
        test_file.write_text(content, encoding='utf-8')
        yield test_file


class TestIntentAliasInvariance:
    """
    Intent Alias 不变性测试

    确保 alias 和原始工具名返回完全相同的结果
    """

    @pytest.mark.asyncio
    async def test_locate_usage_search_content_invariance(
        self, mcp_server, temp_test_file
    ):
        """locate_usage 和 search_content 必须返回相同结果"""
        # 使用 alias 调用
        result_alias = await mcp_server.call_tool(
            "locate_usage",
            arguments={
                "roots": [str(temp_test_file.parent)],
                "query": "example_function",
                "output_format": "json"
            }
        )

        # 使用原始名称调用
        result_original = await mcp_server.call_tool(
            "search_content",
            arguments={
                "roots": [str(temp_test_file.parent)],
                "query": "example_function",
                "output_format": "json"
            }
        )

        # 必须完全相同（语义上）
        matches, diff = SemanticComparator.compare_tool_responses(
            result_alias, result_original
        )

        assert matches, (
            f"Intent alias 'locate_usage' 与原始工具 'search_content' 返回不同结果:\n{diff}\n\n"
            f"Alias result: {json.dumps(result_alias, indent=2, ensure_ascii=False)}\n\n"
            f"Original result: {json.dumps(result_original, indent=2, ensure_ascii=False)}"
        )

    @pytest.mark.asyncio
    async def test_map_structure_list_files_invariance(
        self, mcp_server, temp_test_file
    ):
        """map_structure 和 list_files 必须返回相同结果"""
        result_alias = await mcp_server.call_tool(
            "map_structure",
            arguments={
                "roots": [str(temp_test_file.parent)],
                "pattern": "*.py",
                "glob": True,
                "output_format": "json"
            }
        )

        result_original = await mcp_server.call_tool(
            "list_files",
            arguments={
                "roots": [str(temp_test_file.parent)],
                "pattern": "*.py",
                "glob": True,
                "output_format": "json"
            }
        )

        matches, diff = SemanticComparator.compare_tool_responses(
            result_alias, result_original
        )

        assert matches, (
            f"Intent alias 'map_structure' 与原始工具 'list_files' 返回不同结果:\n{diff}"
        )

    @pytest.mark.asyncio
    async def test_extract_structure_analyze_code_structure_invariance(
        self, mcp_server, temp_test_file
    ):
        """extract_structure 和 analyze_code_structure 必须返回相同结果"""
        result_alias = await mcp_server.call_tool(
            "extract_structure",
            arguments={
                "file_path": str(temp_test_file),
                "language": "python",
                "output_format": "json"
            }
        )

        result_original = await mcp_server.call_tool(
            "analyze_code_structure",
            arguments={
                "file_path": str(temp_test_file),
                "language": "python",
                "output_format": "json"
            }
        )

        matches, diff = SemanticComparator.compare_tool_responses(
            result_alias, result_original
        )

        assert matches, (
            f"Intent alias 'extract_structure' 与原始工具 'analyze_code_structure' 返回不同结果:\n{diff}"
        )

    @pytest.mark.asyncio
    async def test_navigate_structure_get_code_outline_invariance(
        self, mcp_server, temp_test_file
    ):
        """navigate_structure 和 get_code_outline 必须返回相同结果"""
        result_alias = await mcp_server.call_tool(
            "navigate_structure",
            arguments={
                "file_path": str(temp_test_file),
                "language": "python",
                "output_format": "toon"
            }
        )

        result_original = await mcp_server.call_tool(
            "get_code_outline",
            arguments={
                "file_path": str(temp_test_file),
                "language": "python",
                "output_format": "toon"
            }
        )

        matches, diff = SemanticComparator.compare_tool_responses(
            result_alias, result_original
        )

        assert matches, (
            f"Intent alias 'navigate_structure' 与原始工具 'get_code_outline' 返回不同结果:\n{diff}"
        )

    @pytest.mark.asyncio
    async def test_find_impacted_code_find_and_grep_invariance(
        self, mcp_server, temp_test_file
    ):
        """find_impacted_code 和 find_and_grep 必须返回相同结果"""
        result_alias = await mcp_server.call_tool(
            "find_impacted_code",
            arguments={
                "roots": [str(temp_test_file.parent)],
                "pattern": "*.py",
                "query": "example",  # find_and_grep 使用 "query" 参数，不是 "search_pattern"
                "output_format": "json"
            }
        )

        result_original = await mcp_server.call_tool(
            "find_and_grep",
            arguments={
                "roots": [str(temp_test_file.parent)],
                "pattern": "*.py",
                "query": "example",  # find_and_grep 使用 "query" 参数，不是 "search_pattern"
                "output_format": "json"
            }
        )

        matches, diff = SemanticComparator.compare_tool_responses(
            result_alias, result_original
        )

        assert matches, (
            f"Intent alias 'find_impacted_code' 与原始工具 'find_and_grep' 返回不同结果:\n{diff}"
        )

    @pytest.mark.asyncio
    async def test_multiple_aliases_same_tool_invariance(
        self, mcp_server, temp_test_file
    ):
        """测试同一工具的多个 alias 返回相同结果 (find_usage 和 locate_usage)"""
        result_alias1 = await mcp_server.call_tool(
            "locate_usage",
            arguments={
                "roots": [str(temp_test_file.parent)],
                "query": "example_function",
                "output_format": "json"
            }
        )

        result_alias2 = await mcp_server.call_tool(
            "find_usage",
            arguments={
                "roots": [str(temp_test_file.parent)],
                "query": "example_function",
                "output_format": "json"
            }
        )

        result_original = await mcp_server.call_tool(
            "search_content",
            arguments={
                "roots": [str(temp_test_file.parent)],
                "query": "example_function",
                "output_format": "json"
            }
        )

        # 两个 alias 都应该和原始工具返回相同结果
        matches1, diff1 = SemanticComparator.compare_tool_responses(
            result_alias1, result_original
        )
        matches2, diff2 = SemanticComparator.compare_tool_responses(
            result_alias2, result_original
        )

        assert matches1, f"locate_usage 与 search_content 不匹配:\n{diff1}"
        assert matches2, f"find_usage 与 search_content 不匹配:\n{diff2}"

        # 两个 alias 之间也应该完全相同
        matches_aliases, diff_aliases = SemanticComparator.compare_tool_responses(
            result_alias1, result_alias2
        )
        assert matches_aliases, f"locate_usage 与 find_usage 不匹配:\n{diff_aliases}"


class TestIncompleteModificationDetection:
    """
    不完整修改检测测试

    这些测试故意触发工具的各种边缘情况，
    确保即使修改了内部实现，工具行为仍然一致。

    如果这些测试失败，说明修改是不完整的。
    """

    @pytest.mark.asyncio
    async def test_tool_response_structure_consistency(self, mcp_server, temp_test_file):
        """所有工具必须返回一致的响应结构"""
        # 定义期望的响应结构
        required_fields = {'success'}

        tools_to_test = [
            ("search_content", {
                "roots": [str(temp_test_file.parent)],
                "query": "example",
                "output_format": "json"
            }),
            ("list_files", {
                "roots": [str(temp_test_file.parent)],
                "pattern": "*.py",
                "glob": True,
                "output_format": "json"
            }),
            ("analyze_code_structure", {
                "file_path": str(temp_test_file),
                "language": "python",
                "output_format": "json"
            })
        ]

        for tool_name, args in tools_to_test:
            result = await mcp_server.call_tool(tool_name, arguments=args)

            # 检查必需字段
            missing_fields = required_fields - set(result.keys())
            assert not missing_fields, (
                f"工具 {tool_name} 缺少必需字段: {missing_fields}\n"
                f"实际响应: {json.dumps(result, indent=2, ensure_ascii=False)}"
            )

            # 检查 success 字段类型
            assert isinstance(result['success'], bool), (
                f"工具 {tool_name} 的 success 字段类型错误: "
                f"expected=bool, actual={type(result['success'])}"
            )

            # 如果成功，检查是否有 results 或其他数据字段
            if result['success']:
                has_data = any(
                    key in result
                    for key in ['results', 'count', 'data', 'structure', 'outline',
                                'table_output', 'metadata']  # analyze_code_structure 返回这些字段
                )
                assert has_data, (
                    f"工具 {tool_name} 成功但没有返回数据字段\n"
                    f"实际响应: {json.dumps(result, indent=2, ensure_ascii=False)}"
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
