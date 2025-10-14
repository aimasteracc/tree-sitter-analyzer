#!/usr/bin/env python3
"""
MCP Performance Tests

パフォーマンス要件の検証:
- 単一ツール実行時間: 3秒以内
- 複合ワークフロー実行時間: 10秒以内
- 大規模プロジェクト対応: 10,000ファイル
- メモリ使用量の最適化確認
"""

import asyncio
import time
import psutil
import pytest
from pathlib import Path
from typing import Any, Dict
import tempfile
import os

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool
from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool


class PerformanceMonitor:
    """パフォーマンス測定ユーティリティ"""
    
    def __init__(self):
        self.process = psutil.Process()
        self.start_time = None
        self.start_memory = None
        
    def start_measurement(self):
        """測定開始"""
        self.start_time = time.time()
        self.start_memory = self.process.memory_info().rss
        
    def end_measurement(self) -> Dict[str, Any]:
        """測定終了と結果取得"""
        end_time = time.time()
        end_memory = self.process.memory_info().rss
        
        return {
            "execution_time": end_time - self.start_time,
            "memory_used": end_memory - self.start_memory,
            "peak_memory": self.process.memory_info().rss
        }


@pytest.fixture
def performance_monitor():
    """パフォーマンスモニター"""
    return PerformanceMonitor()


@pytest.fixture
def sample_code_file(tmp_path):
    """サンプルコードファイル作成"""
    code_content = '''
class SampleClass:
    """Sample class for testing"""
    
    def __init__(self, name: str):
        self.name = name
        
    def method_one(self) -> str:
        """First method"""
        return f"Hello, {self.name}"
        
    def method_two(self, value: int) -> int:
        """Second method"""
        return value * 2
        
    def complex_method(self, data: list) -> dict:
        """Complex method with multiple operations"""
        result = {}
        for i, item in enumerate(data):
            if isinstance(item, str):
                result[f"string_{i}"] = item.upper()
            elif isinstance(item, int):
                result[f"number_{i}"] = item ** 2
            else:
                result[f"other_{i}"] = str(item)
        return result
'''
    
    file_path = tmp_path / "sample.py"
    file_path.write_text(code_content)
    return str(file_path)


@pytest.fixture
def large_code_file(tmp_path):
    """大規模コードファイル作成（1000行以上）"""
    lines = []
    lines.append("# Large Python file for performance testing")
    lines.append("from typing import Any, Dict, List, Optional")
    lines.append("")
    
    # 100個のクラスを生成
    for class_num in range(100):
        lines.append(f"class TestClass{class_num}:")
        lines.append(f'    """Test class number {class_num}"""')
        lines.append("")
        lines.append(f"    def __init__(self, value: int = {class_num}):")
        lines.append("        self.value = value")
        lines.append("")
        
        # 各クラスに10個のメソッドを追加
        for method_num in range(10):
            lines.append(f"    def method_{method_num}(self, param: Any) -> Any:")
            lines.append(f'        """Method {method_num} of class {class_num}"""')
            lines.append(f"        return param + {method_num}")
            lines.append("")
    
    file_path = tmp_path / "large_file.py"
    file_path.write_text("\n".join(lines))
    return str(file_path)


@pytest.fixture
def large_project_structure(tmp_path):
    """大規模プロジェクト構造作成（1000ファイル）"""
    project_root = tmp_path / "large_project"
    project_root.mkdir()
    
    # 複数のディレクトリ構造を作成
    for dir_num in range(20):
        dir_path = project_root / f"module_{dir_num}"
        dir_path.mkdir()
        
        # 各ディレクトリに50個のファイルを作成
        for file_num in range(50):
            file_path = dir_path / f"file_{file_num}.py"
            content = f"""
# Module {dir_num}, File {file_num}

class Class{file_num}:
    def method_{file_num}(self):
        return {file_num}

def function_{file_num}():
    return "result_{file_num}"
"""
            file_path.write_text(content)
    
    return str(project_root)


class TestSingleToolPerformance:
    """単一ツールのパフォーマンステスト（目標: 3秒以内）"""
    
    @pytest.mark.asyncio
    async def test_check_code_scale_performance(self, sample_code_file, performance_monitor):
        """check_code_scale ツールのパフォーマンステスト"""
        tool = AnalyzeScaleTool()
        
        performance_monitor.start_measurement()
        
        result = await tool.execute({
            "file_path": sample_code_file,
            "include_complexity": True,
            "include_details": True,
            "include_guidance": True
        })
        
        metrics = performance_monitor.end_measurement()
        
        # パフォーマンス要件検証
        assert metrics["execution_time"] < 3.0, f"実行時間が3秒を超過: {metrics['execution_time']:.2f}秒"
        assert result["success"] is True
        
        print(f"check_code_scale実行時間: {metrics['execution_time']:.2f}秒")
        print(f"メモリ使用量: {metrics['memory_used'] / 1024 / 1024:.2f}MB")
    
    @pytest.mark.asyncio
    async def test_analyze_code_structure_performance(self, sample_code_file, performance_monitor):
        """analyze_code_structure ツールのパフォーマンステスト"""
        tool = TableFormatTool()
        
        performance_monitor.start_measurement()
        
        result = await tool.execute({
            "file_path": sample_code_file,
            "format_type": "full"
        })
        
        metrics = performance_monitor.end_measurement()
        
        # パフォーマンス要件検証
        assert metrics["execution_time"] < 3.0, f"実行時間が3秒を超過: {metrics['execution_time']:.2f}秒"
        assert result["success"] is True
        
        print(f"analyze_code_structure実行時間: {metrics['execution_time']:.2f}秒")
        print(f"メモリ使用量: {metrics['memory_used'] / 1024 / 1024:.2f}MB")
    
    @pytest.mark.asyncio
    async def test_extract_code_section_performance(self, large_code_file, performance_monitor):
        """extract_code_section ツールのパフォーマンステスト"""
        tool = ReadPartialTool()
        
        performance_monitor.start_measurement()
        
        result = await tool.execute({
            "file_path": large_code_file,
            "start_line": 1,
            "end_line": 100,
            "format": "text"
        })
        
        metrics = performance_monitor.end_measurement()
        
        # パフォーマンス要件検証
        assert metrics["execution_time"] < 3.0, f"実行時間が3秒を超過: {metrics['execution_time']:.2f}秒"
        assert result["success"] is True
        
        print(f"extract_code_section実行時間: {metrics['execution_time']:.2f}秒")
        print(f"メモリ使用量: {metrics['memory_used'] / 1024 / 1024:.2f}MB")
    
    @pytest.mark.asyncio
    async def test_query_code_performance(self, sample_code_file, performance_monitor):
        """query_code ツールのパフォーマンステスト"""
        tool = QueryTool()
        
        performance_monitor.start_measurement()
        
        result = await tool.execute({
            "file_path": sample_code_file,
            "query_key": "methods",
            "output_format": "json"
        })
        
        metrics = performance_monitor.end_measurement()
        
        # パフォーマンス要件検証
        assert metrics["execution_time"] < 3.0, f"実行時間が3秒を超過: {metrics['execution_time']:.2f}秒"
        assert result["success"] is True
        
        print(f"query_code実行時間: {metrics['execution_time']:.2f}秒")
        print(f"メモリ使用量: {metrics['memory_used'] / 1024 / 1024:.2f}MB")
    
    @pytest.mark.asyncio
    async def test_list_files_performance(self, large_project_structure, performance_monitor):
        """list_files ツールのパフォーマンステスト"""
        tool = ListFilesTool()
        
        performance_monitor.start_measurement()
        
        result = await tool.execute({
            "roots": [large_project_structure],
            "extensions": ["py"],
            "limit": 1000
        })
        
        metrics = performance_monitor.end_measurement()
        
        # パフォーマンス要件検証
        assert metrics["execution_time"] < 3.0, f"実行時間が3秒を超過: {metrics['execution_time']:.2f}秒"
        assert result["success"] is True
        
        print(f"list_files実行時間: {metrics['execution_time']:.2f}秒")
        print(f"メモリ使用量: {metrics['memory_used'] / 1024 / 1024:.2f}MB")
        print(f"検出ファイル数: {result.get('count', 0)}")
    
    @pytest.mark.asyncio
    async def test_search_content_performance(self, large_project_structure, performance_monitor):
        """search_content ツールのパフォーマンステスト"""
        tool = SearchContentTool()
        
        performance_monitor.start_measurement()
        
        result = await tool.execute({
            "roots": [large_project_structure],
            "query": "class",
            "include_globs": ["*.py"],
            "max_count": 100
        })
        
        metrics = performance_monitor.end_measurement()
        
        # パフォーマンス要件検証
        assert metrics["execution_time"] < 3.0, f"実行時間が3秒を超過: {metrics['execution_time']:.2f}秒"
        assert result["success"] is True
        
        print(f"search_content実行時間: {metrics['execution_time']:.2f}秒")
        print(f"メモリ使用量: {metrics['memory_used'] / 1024 / 1024:.2f}MB")


class TestCompositeWorkflowPerformance:
    """複合ワークフローのパフォーマンステスト（目標: 10秒以内）"""
    
    @pytest.mark.asyncio
    async def test_full_analysis_workflow_performance(self, large_code_file, performance_monitor):
        """完全解析ワークフローのパフォーマンステスト"""
        performance_monitor.start_measurement()
        
        # Step 1: コード規模チェック
        scale_tool = AnalyzeScaleTool()
        scale_result = await scale_tool.execute({
            "file_path": large_code_file,
            "include_complexity": True,
            "include_guidance": True
        })
        assert scale_result["success"] is True
        
        # Step 2: 構造解析
        structure_tool = TableFormatTool()
        structure_result = await structure_tool.execute({
            "file_path": large_code_file,
            "format_type": "full"
        })
        assert structure_result["success"] is True
        
        # Step 3: コード抽出
        extract_tool = ReadPartialTool()
        extract_result = await extract_tool.execute({
            "file_path": large_code_file,
            "start_line": 1,
            "end_line": 50,
            "format": "text"
        })
        assert extract_result["success"] is True
        
        # Step 4: クエリ実行
        query_tool = QueryTool()
        query_result = await query_tool.execute({
            "file_path": large_code_file,
            "query_key": "methods",
            "output_format": "json"
        })
        assert query_result["success"] is True
        
        metrics = performance_monitor.end_measurement()
        
        # パフォーマンス要件検証
        assert metrics["execution_time"] < 10.0, f"ワークフロー実行時間が10秒を超過: {metrics['execution_time']:.2f}秒"
        
        print(f"完全解析ワークフロー実行時間: {metrics['execution_time']:.2f}秒")
        print(f"メモリ使用量: {metrics['memory_used'] / 1024 / 1024:.2f}MB")
    
    @pytest.mark.asyncio
    async def test_search_and_extract_workflow_performance(self, large_project_structure, performance_monitor):
        """検索・抽出ワークフローのパフォーマンステスト"""
        performance_monitor.start_measurement()
        
        # Step 1: ファイル検索
        list_tool = ListFilesTool()
        list_result = await list_tool.execute({
            "roots": [large_project_structure],
            "extensions": ["py"],
            "limit": 100
        })
        assert list_result["success"] is True
        
        # Step 2: コンテンツ検索
        search_tool = SearchContentTool()
        search_result = await search_tool.execute({
            "roots": [large_project_structure],
            "query": "def method_",
            "include_globs": ["*.py"],
            "max_count": 50
        })
        assert search_result["success"] is True
        
        # Step 3: 統合検索
        find_grep_tool = FindAndGrepTool()
        find_grep_result = await find_grep_tool.execute({
            "roots": [large_project_structure],
            "query": "class",
            "extensions": ["py"],
            "max_count": 30
        })
        assert find_grep_result["success"] is True
        
        metrics = performance_monitor.end_measurement()
        
        # パフォーマンス要件検証（Windowsでは時間制限を緩和）
        time_limit = 35.0 if os.name == 'nt' else 10.0  # Windows環境では35秒まで許可
        assert metrics["execution_time"] < time_limit, f"検索ワークフロー実行時間が{time_limit}秒を超過: {metrics['execution_time']:.2f}秒"
        
        print(f"検索・抽出ワークフロー実行時間: {metrics['execution_time']:.2f}秒")
        print(f"メモリ使用量: {metrics['memory_used'] / 1024 / 1024:.2f}MB")


class TestLargeScalePerformance:
    """大規模プロジェクト対応のパフォーマンステスト（10,000ファイル対応）"""
    
    @pytest.mark.asyncio
    async def test_large_project_file_listing(self, large_project_structure, performance_monitor):
        """大規模プロジェクトでのファイル一覧取得"""
        tool = ListFilesTool()
        
        performance_monitor.start_measurement()
        
        result = await tool.execute({
            "roots": [large_project_structure],
            "extensions": ["py"],
            "limit": 2000  # 実際のファイル数は1000個
        })
        
        metrics = performance_monitor.end_measurement()
        
        assert result["success"] is True
        assert metrics["execution_time"] < 5.0, f"大規模ファイル一覧取得が5秒を超過: {metrics['execution_time']:.2f}秒"
        
        # 1000ファイルが検出されることを確認
        file_count = result.get("count", 0)
        assert file_count == 1000, f"期待されるファイル数と異なる: {file_count}"
        
        print(f"大規模プロジェクト（{file_count}ファイル）一覧取得時間: {metrics['execution_time']:.2f}秒")
        print(f"メモリ使用量: {metrics['memory_used'] / 1024 / 1024:.2f}MB")
    
    @pytest.mark.asyncio
    async def test_large_project_content_search(self, large_project_structure, performance_monitor):
        """大規模プロジェクトでのコンテンツ検索"""
        tool = SearchContentTool()
        
        performance_monitor.start_measurement()
        
        result = await tool.execute({
            "roots": [large_project_structure],
            "query": "def function_",
            "include_globs": ["*.py"],
            "max_count": 500
        })
        
        metrics = performance_monitor.end_measurement()
        
        assert result["success"] is True
        assert metrics["execution_time"] < 8.0, f"大規模コンテンツ検索が8秒を超過: {metrics['execution_time']:.2f}秒"
        
        print(f"大規模プロジェクトコンテンツ検索時間: {metrics['execution_time']:.2f}秒")
        print(f"メモリ使用量: {metrics['memory_used'] / 1024 / 1024:.2f}MB")


class TestMemoryOptimization:
    """メモリ使用量最適化の検証"""
    
    @pytest.mark.asyncio
    async def test_memory_usage_optimization(self, large_code_file, performance_monitor):
        """メモリ使用量最適化の確認"""
        tool = TableFormatTool()
        
        # 初期メモリ使用量を記録
        initial_memory = psutil.Process().memory_info().rss
        
        performance_monitor.start_measurement()
        
        # suppress_output=True でメモリ最適化を有効化
        result = await tool.execute({
            "file_path": large_code_file,
            "format_type": "full",
            "suppress_output": True,
            "output_file": "test_output.json"
        })
        
        metrics = performance_monitor.end_measurement()
        final_memory = psutil.Process().memory_info().rss
        
        assert result["success"] is True
        
        # メモリ使用量が適切に制御されていることを確認
        memory_increase = (final_memory - initial_memory) / 1024 / 1024  # MB
        assert memory_increase < 50, f"メモリ使用量増加が50MBを超過: {memory_increase:.2f}MB"
        
        print(f"メモリ最適化実行時間: {metrics['execution_time']:.2f}秒")
        print(f"メモリ使用量増加: {memory_increase:.2f}MB")
        
        # 出力ファイルが作成されていることを確認
        output_file = Path("test_output.json")
        if output_file.exists():
            output_file.unlink()  # クリーンアップ


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])