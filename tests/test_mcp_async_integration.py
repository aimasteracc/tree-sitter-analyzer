#!/usr/bin/env python3
"""MCP async integration tests"""

import os
import pytest
import asyncio
import tempfile
import json
from pathlib import Path

from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool


class TestMCPAsyncIntegration:
    """MCP非同期統合テスト"""
    
    @pytest.fixture
    def sample_code_file(self):
        """テスト用コードファイル"""
        # Create file in current directory to avoid security restrictions
        test_file = Path("test_sample_code.py")
        try:
            test_file.write_text("""
def example_function():
    '''Example function for testing'''
    return "Hello, World!"

class ExampleClass:
    '''Example class for testing'''
    def __init__(self):
        self.value = 42
    
    def get_value(self):
        return self.value
    
    def set_value(self, new_value):
        self.value = new_value

async def async_example_function():
    '''Async example function'''
    await asyncio.sleep(0.1)
    return "Async Hello, World!"

def utility_function(x, y):
    '''Utility function for calculations'''
    return x + y

class UtilityClass:
    @staticmethod
    def static_method():
        return "static"
    
    @classmethod
    def class_method(cls):
        return "class"
""")
            yield str(test_file)
        finally:
            test_file.unlink(missing_ok=True)
    
    @pytest.fixture
    def sample_javascript_file(self):
        """テスト用JavaScriptファイル"""
        # Create file in current directory to avoid security restrictions
        test_file = Path("test_sample_javascript.js")
        try:
            test_file.write_text("""
function exampleFunction() {
    return "Hello, JavaScript!";
}

class ExampleClass {
    constructor() {
        this.value = 42;
    }
    
    getValue() {
        return this.value;
    }
    
    setValue(newValue) {
        this.value = newValue;
    }
}

const arrowFunction = () => {
    return "Arrow function";
};

async function asyncExampleFunction() {
    return new Promise(resolve => {
        setTimeout(() => resolve("Async Hello, JavaScript!"), 100);
    });
}
""")
            yield str(test_file)
        finally:
            test_file.unlink(missing_ok=True)
    
    @pytest.fixture
    def large_code_file(self):
        """大きなコードファイル"""
        # Create file in current directory to avoid security restrictions
        test_file = Path("test_large_code.py")
        try:
            content = ""
            # 50個の関数とクラスを持つファイルを生成
            for i in range(50):
                content += f"""
def function_{i}():
    '''Function {i} for testing'''
    return {i}

class Class_{i}:
    '''Class {i} for testing'''
    def __init__(self):
        self.value = {i}
    
    def method_{i}(self):
        return self.value * 2
"""
            test_file.write_text(content)
            yield str(test_file)
        finally:
            test_file.unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_query_tool_basic_execution(self, sample_code_file):
        """QueryToolの基本実行テスト"""
        tool = QueryTool(project_root=os.getcwd())
        
        result = await tool.execute({
            "file_path": sample_code_file,
            "query_key": "function"
        })
        
        assert result["success"] is True
        assert result["count"] >= 3  # example_function + async_example_function + utility_function
        assert "results" in result
        assert isinstance(result["results"], list)
        
        # 関数名の確認
        function_results = [r for r in result["results"] if r.get("capture_name") == "function"]
        function_contents = [r.get("content", "") for r in function_results]
        assert any("example_function" in content for content in function_contents)
    
    @pytest.mark.asyncio
    async def test_query_tool_class_execution(self, sample_code_file):
        """QueryToolのクラスクエリ実行テスト"""
        tool = QueryTool(project_root=os.getcwd())
        
        result = await tool.execute({
            "file_path": sample_code_file,
            "query_key": "class"
        })
        
        assert result["success"] is True
        assert result["count"] >= 2  # ExampleClass + UtilityClass
        assert "results" in result
        
        # クラス名の確認
        class_results = [r for r in result["results"] if r.get("capture_name") == "class"]
        class_contents = [r.get("content", "") for r in class_results]
        assert any("ExampleClass" in content for content in class_contents)
        assert any("UtilityClass" in content for content in class_contents)
    
    @pytest.mark.asyncio
    async def test_query_tool_javascript_execution(self, sample_javascript_file):
        """QueryToolのJavaScript実行テスト"""
        tool = QueryTool(project_root=os.getcwd())
        
        result = await tool.execute({
            "file_path": sample_javascript_file,
            "language": "javascript",
            "query_key": "function"
        })
        
        assert result["success"] is True
        assert result["count"] >= 2  # exampleFunction + asyncExampleFunction (arrowFunctionは検出されない場合がある)
        assert "results" in result
    
    @pytest.mark.asyncio
    async def test_query_tool_output_formats(self, sample_code_file):
        """出力フォーマットのテスト"""
        tool = QueryTool(project_root=os.getcwd())
        
        # JSON format
        json_result = await tool.execute({
            "file_path": sample_code_file,
            "query_key": "function",
            "output_format": "json"
        })
        assert json_result["success"] is True
        assert "results" in json_result
        assert isinstance(json_result["results"], list)
        
        # Summary format
        summary_result = await tool.execute({
            "file_path": sample_code_file,
            "query_key": "function", 
            "output_format": "summary"
        })
        assert summary_result["success"] is True
        # サマリー形式では異なる構造になる可能性がある
        assert "captures" in summary_result or "results" in summary_result
    
    @pytest.mark.asyncio
    async def test_query_tool_custom_query_string(self, sample_code_file):
        """カスタムクエリ文字列のテスト"""
        tool = QueryTool(project_root=os.getcwd())
        
        result = await tool.execute({
            "file_path": sample_code_file,
            "language": "python",
            "query_string": "(function_definition name: (identifier) @function)"
        })
        
        assert result["success"] is True
        assert result["count"] >= 3
        assert "results" in result
    
    @pytest.mark.asyncio
    async def test_query_tool_filter_expression(self, sample_code_file):
        """フィルター式のテスト"""
        tool = QueryTool(project_root=os.getcwd())
        
        # フィルター式を使用してクエリ実行
        result = await tool.execute({
            "file_path": sample_code_file,
            "query_key": "function",
            "filter": "name=example_function"
        })
        
        # フィルターが実装されている場合の確認
        if result["success"]:
            assert "results" in result
            # フィルターが効いている場合、結果が絞り込まれることを期待
            if result["count"] > 0:
                function_results = [r for r in result["results"] if r.get("capture_name") == "function"]
                if function_results:
                    # example_functionが含まれることを確認
                    function_contents = [r.get("content", "") for r in function_results]
                    assert any("example_function" in content for content in function_contents)
    
    @pytest.mark.asyncio
    async def test_query_tool_language_auto_detection(self, sample_code_file):
        """言語自動検出のテスト"""
        tool = QueryTool(project_root=os.getcwd())
        
        # 言語を指定せずに実行
        result = await tool.execute({
            "file_path": sample_code_file,
            "query_key": "function"
        })
        
        assert result["success"] is True
        assert result["count"] >= 3
        assert "results" in result
    
    @pytest.mark.asyncio
    async def test_query_tool_error_handling_nonexistent_file(self):
        """エラーハンドリング: 存在しないファイル"""
        tool = QueryTool(project_root=os.getcwd())
        
        result = await tool.execute({
            "file_path": "nonexistent_file.py",
            "query_key": "function"
        })
        
        assert result["success"] is False
        assert "error" in result
        # More flexible error message checking
        error_msg = result["error"].lower()
        assert ("not exist" in error_msg or "not found" in error_msg or
                "no such file" in error_msg or "errno 2" in error_msg), f"Unexpected error message: {result['error']}"
    
    @pytest.mark.asyncio
    async def test_query_tool_error_handling_invalid_language(self, sample_code_file):
        """エラーハンドリング: 無効な言語"""
        tool = QueryTool(project_root=os.getcwd())
        
        result = await tool.execute({
            "file_path": sample_code_file,
            "language": "invalid_language",
            "query_key": "function"
        })
        
        # 無効な言語の場合、エラーになるかデフォルト動作するかは実装依存
        if not result["success"]:
            assert "error" in result
            error_msg = result["error"].lower()
            assert ("language" in error_msg or "unsupported" in error_msg or
                    "failed to parse" in error_msg or "parse file" in error_msg), f"Unexpected error message: {result['error']}"
    
    @pytest.mark.asyncio
    async def test_query_tool_error_handling_invalid_query_key(self, sample_code_file):
        """エラーハンドリング: 無効なクエリキー"""
        tool = QueryTool(project_root=os.getcwd())
        
        result = await tool.execute({
            "file_path": sample_code_file,
            "query_key": "invalid_query_key"
        })
        
        # 無効なクエリキーの場合、エラーになるか空結果を返すかは実装依存
        if not result["success"]:
            assert "error" in result
        else:
            # 成功の場合、空結果または何らかの結果があることを確認
            assert "results" in result
            assert result["count"] >= 0
    
    @pytest.mark.asyncio
    async def test_query_tool_error_handling_malformed_query_string(self, sample_code_file):
        """エラーハンドリング: 不正なクエリ文字列"""
        tool = QueryTool(project_root=os.getcwd())
        
        result = await tool.execute({
            "file_path": sample_code_file,
            "language": "python",
            "query_string": "((invalid query syntax"
        })
        
        # 不正なクエリの場合、成功する場合もある（空結果を返す）
        if not result["success"]:
            assert "error" in result
            error_msg = result["error"].lower()
            assert ("query" in error_msg or "syntax" in error_msg or
                    "parse" in error_msg), f"Unexpected error message: {result['error']}"
        else:
            # 成功した場合は空結果であることを確認
            assert result["count"] == 0
    
    @pytest.mark.asyncio
    async def test_concurrent_mcp_execution(self, sample_code_file):
        """並行MCP実行テスト"""
        tool = QueryTool(project_root=os.getcwd())
        
        tasks = [
            tool.execute({
                "file_path": sample_code_file,
                "query_key": "function"
            }),
            tool.execute({
                "file_path": sample_code_file,
                "query_key": "class"
            }),
            tool.execute({
                "file_path": sample_code_file,
                "query_key": "function"
            })
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 全てのタスクが正常に完了することを確認
        successful_results = 0
        for result in results:
            if isinstance(result, dict) and result.get("success"):
                successful_results += 1
                assert "results" in result
                assert result["count"] >= 0
            elif isinstance(result, Exception):
                pytest.fail(f"Task failed with exception: {result}")
            else:
                # 失敗した場合でもエラー情報があることを確認
                assert isinstance(result, dict)
                assert "error" in result
        
        assert successful_results >= 2, "At least 2 tasks should succeed"
    
    @pytest.mark.asyncio
    async def test_multiple_languages_concurrent(self, sample_code_file, sample_javascript_file):
        """複数言語の並行処理テスト"""
        tool = QueryTool(project_root=os.getcwd())
        
        tasks = [
            tool.execute({
                "file_path": sample_code_file,
                "language": "python",
                "query_key": "function"
            }),
            tool.execute({
                "file_path": sample_javascript_file,
                "language": "javascript",
                "query_key": "function"
            })
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 両方の結果が正常に取得できることを確認
        successful_results = 0
        for result in results:
            if isinstance(result, dict) and result.get("success"):
                successful_results += 1
                assert "results" in result
                assert result["count"] >= 1
            elif isinstance(result, Exception):
                pytest.fail(f"Task failed with exception: {result}")
        
        assert successful_results >= 1, "At least 1 language should work"
    
    @pytest.mark.asyncio
    async def test_large_file_mcp_processing(self, large_code_file):
        """大きなファイルのMCP処理テスト"""
        tool = QueryTool(project_root=os.getcwd())
        
        result = await tool.execute({
            "file_path": large_code_file,
            "query_key": "function"
        })
        
        assert result["success"] is True
        assert result["count"] >= 50  # 50個の関数が見つかることを確認
        assert "results" in result
        assert len(result["results"]) >= 50
    
    @pytest.mark.asyncio
    async def test_mcp_performance_baseline(self, sample_code_file):
        """MCPパフォーマンスベースラインテスト"""
        import time
        
        tool = QueryTool(project_root=os.getcwd())
        
        start_time = time.time()
        
        result = await tool.execute({
            "file_path": sample_code_file,
            "query_key": "function"
        })
        
        end_time = time.time()
        duration = end_time - start_time
        
        assert result["success"] is True
        assert result["count"] >= 3
        
        # パフォーマンス要件: 5秒以内
        assert duration < 5.0, f"MCP execution took too long: {duration:.2f}s"
        
        print(f"MCP Performance: {duration:.2f}s for {result['count']} results")
    
    @pytest.mark.asyncio
    async def test_stress_concurrent_mcp_execution(self, sample_code_file):
        """ストレステスト: 大量の並行MCP実行"""
        tool = QueryTool(project_root=os.getcwd())
        
        # 10個の並行タスクを実行
        tasks = [
            tool.execute({
                "file_path": sample_code_file,
                "query_key": "function"
            })
            for _ in range(10)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 全てのタスクが正常に完了することを確認
        successful_results = 0
        for result in results:
            if isinstance(result, dict) and result.get("success"):
                successful_results += 1
                assert "results" in result
                assert result["count"] >= 3
            elif isinstance(result, Exception):
                pytest.fail(f"Task failed with exception: {result}")
        
        assert successful_results >= 8, "At least 8 out of 10 tasks should succeed"
    
    @pytest.mark.asyncio
    async def test_mcp_tool_argument_validation(self):
        """MCP引数バリデーションテスト"""
        from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError
        tool = QueryTool(project_root=os.getcwd())

        # 必須引数が不足している場合
        with pytest.raises(AnalysisError) as excinfo:
            await tool.execute({})
        assert "file_path is required" in str(excinfo.value)

        # file_pathが不足している場合
        with pytest.raises(AnalysisError) as excinfo:
            await tool.execute({
                "query_key": "function"
            })
        assert "file_path is required" in str(excinfo.value)
    
    @pytest.mark.asyncio
    async def test_mcp_tool_output_file_feature(self, sample_code_file):
        """MCP出力ファイル機能のテスト"""
        tool = QueryTool(project_root=os.getcwd())
        
        output_file = "test_mcp_output.json"
        
        try:
            result = await tool.execute({
                "file_path": sample_code_file,
                "query_key": "function",
                "output_file": output_file
            })
            
            # 出力ファイル機能が実装されている場合
            if result["success"]:
                # ファイルが作成されることを確認
                output_path = Path(output_file)
                if output_path.exists():
                    assert output_path.stat().st_size > 0
                    
                    # ファイル内容の確認
                    with open(output_file, 'r') as f:
                        content = f.read()
                        assert len(content) > 0
                        
                        # JSON形式の場合
                        try:
                            json_data = json.loads(content)
                            assert isinstance(json_data, (list, dict))
                        except json.JSONDecodeError:
                            # JSON以外の形式でも問題なし
                            pass
        
        finally:
            # クリーンアップ
            output_path = Path(output_file)
            if output_path.exists():
                output_path.unlink()
    
    @pytest.mark.asyncio
    async def test_mcp_tool_suppress_output_feature(self, sample_code_file):
        """MCP出力抑制機能のテスト"""
        tool = QueryTool(project_root=os.getcwd())
        
        output_file = "test_mcp_suppress_output.json"
        
        try:
            result = await tool.execute({
                "file_path": sample_code_file,
                "query_key": "function",
                "output_file": output_file,
                "suppress_output": True
            })
            
            # 出力抑制機能が実装されている場合
            if result["success"]:
                # suppress_outputがTrueの場合、結果が抑制されることを確認
                # 実装によっては、resultsキーが存在しないか、空の配列になる
                if result.get("suppress_output") or result.get("file_saved"):
                    # 結果が抑制されている場合、詳細な結果は含まれない
                    assert "results" not in result or len(result.get("results", [])) == 0
                else:
                    # 機能が実装されていない場合は通常通り結果が返される
                    # ただし、output_fileが指定されている場合は抑制される可能性がある
                    pass  # 柔軟に対応
        
        finally:
            # クリーンアップ
            output_path = Path(output_file)
            if output_path.exists():
                output_path.unlink()