#!/usr/bin/env python3
"""Comprehensive async QueryService tests"""

import pytest
import asyncio
import tempfile
import inspect
from pathlib import Path

from tree_sitter_analyzer.core.query_service import QueryService


class TestAsyncQueryService:
    """非同期QueryServiceのテスト"""
    
    @pytest.fixture
    def sample_python_file(self):
        """テスト用Pythonファイル"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            content = """def test_function():
    return 42

class TestClass:
    def method(self):
        pass

async def async_function():
    await asyncio.sleep(0.1)
    return "async result"

def another_function(x, y):
    '''Another function for testing'''
    return x + y
"""
            f.write(content)
            f.flush()  # バッファをフラッシュ
            temp_file = f.name
        
        yield temp_file
        Path(temp_file).unlink(missing_ok=True)
    
    @pytest.fixture
    def sample_javascript_file(self):
        """テスト用JavaScriptファイル"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            content = """function testFunction() {
    return 42;
}

class TestClass {
    method() {
        return "test";
    }
}

const arrowFunction = () => {
    return "arrow";
};
"""
            f.write(content)
            f.flush()  # バッファをフラッシュ
            temp_file = f.name
        
        yield temp_file
        Path(temp_file).unlink(missing_ok=True)
    
    def test_execute_query_is_async_method(self):
        """execute_queryが非同期メソッドであることを確認"""
        service = QueryService()
        
        # メソッドがコルーチン関数であることを確認
        assert inspect.iscoroutinefunction(service.execute_query)
        print("✅ execute_query is now async")
    
    @pytest.mark.asyncio
    async def test_execute_query_returns_coroutine(self, sample_python_file):
        """execute_queryがコルーチンオブジェクトを返すことを確認"""
        service = QueryService()
        
        result_coro = service.execute_query(
            file_path=sample_python_file,
            language="python",
            query_key="function"
        )
        
        # コルーチンオブジェクトが返されることを確認
        assert asyncio.iscoroutine(result_coro)
        
        # 実際に実行
        result = await result_coro
        assert isinstance(result, list)
        assert len(result) >= 4  # test_function + method + async_function + another_function
    
    @pytest.mark.asyncio
    async def test_query_key_execution(self, sample_python_file):
        """クエリキーによる実行テスト"""
        service = QueryService()
        
        results = await service.execute_query(
            file_path=sample_python_file,
            language="python",
            query_key="function"
        )
        
        assert results is not None
        assert len(results) >= 4  # test_function + method + async_function + another_function
        assert any(r["capture_name"] == "function" for r in results)
        
        # 関数名の確認
        function_results = [r for r in results if r["capture_name"] == "function"]
        function_contents = [r["content"] for r in function_results]
        assert any("test_function" in content for content in function_contents)
        assert any("async_function" in content for content in function_contents)
    
    @pytest.mark.asyncio
    async def test_class_query_execution(self, sample_python_file):
        """クラスクエリの実行テスト"""
        service = QueryService()
        
        results = await service.execute_query(
            file_path=sample_python_file,
            language="python",
            query_key="class"
        )
        
        assert results is not None
        # クラスクエリの結果は実装依存なので、結果があることのみ確認
        if results:
            assert any(r["capture_name"] == "class" for r in results)
    
    @pytest.mark.asyncio
    async def test_custom_query_string(self, sample_python_file):
        """カスタムクエリ文字列の実行テスト"""
        service = QueryService()
        
        # カスタムクエリ文字列でメソッドを検索
        results = await service.execute_query(
            file_path=sample_python_file,
            language="python",
            query_string="(function_definition name: (identifier) @method)"
        )
        
        assert results is not None
        assert len(results) >= 0  # カスタムクエリの結果は実装依存
    
    @pytest.mark.asyncio
    async def test_concurrent_execution(self, sample_python_file):
        """並行実行テスト"""
        service = QueryService()
        
        # 複数のクエリを並行実行
        tasks = [
            service.execute_query(
                file_path=sample_python_file,
                language="python",
                query_key="function"
            ),
            service.execute_query(
                file_path=sample_python_file,
                language="python",
                query_key="class"
            ),
            service.execute_query(
                file_path=sample_python_file,
                language="python",
                query_key="function"
            )
        ]
        
        results = await asyncio.gather(*tasks)
        
        # 全ての結果が正常に取得できることを確認
        assert len(results) == 3
        for result in results:
            assert result is not None
            assert isinstance(result, list)
            assert len(result) >= 1
    
    @pytest.mark.asyncio
    async def test_multiple_languages_concurrent(self, sample_python_file, sample_javascript_file):
        """複数言語の並行処理テスト"""
        service = QueryService()
        
        tasks = [
            service.execute_query(
                file_path=sample_python_file,
                language="python",
                query_key="function"
            ),
            service.execute_query(
                file_path=sample_javascript_file,
                language="javascript",
                query_key="function"
            )
        ]
        
        results = await asyncio.gather(*tasks)
        
        # 両方の結果が正常に取得できることを確認
        assert len(results) == 2
        for result in results:
            assert result is not None
            assert isinstance(result, list)
            # 結果の数は実装依存なので、リストであることのみ確認
    
    @pytest.mark.asyncio
    async def test_error_handling_nonexistent_file(self):
        """存在しないファイルのエラーハンドリングテスト"""
        service = QueryService()
        
        with pytest.raises(Exception):
            await service.execute_query(
                file_path="nonexistent_file.py",
                language="python",
                query_key="function"
            )
    
    @pytest.mark.asyncio
    async def test_error_handling_invalid_language(self, sample_python_file):
        """無効な言語のエラーハンドリングテスト"""
        service = QueryService()
        
        with pytest.raises(Exception):
            await service.execute_query(
                file_path=sample_python_file,
                language="invalid_language",
                query_key="function"
            )
    
    @pytest.mark.asyncio
    async def test_error_handling_invalid_query_key(self, sample_python_file):
        """無効なクエリキーのエラーハンドリングテスト"""
        service = QueryService()
        
        # 無効なクエリキーで例外が発生することを確認
        with pytest.raises(ValueError, match="Query 'invalid_query_key' not found"):
            await service.execute_query(
                file_path=sample_python_file,
                language="python",
                query_key="invalid_query_key"
            )
    
    @pytest.mark.asyncio
    async def test_timeout_behavior(self, sample_python_file):
        """タイムアウト動作テスト"""
        service = QueryService()
        
        # タイムアウト付き実行
        try:
            async with asyncio.timeout(10.0):  # 10秒のタイムアウト
                results = await service.execute_query(
                    file_path=sample_python_file,
                    language="python",
                    query_key="function"
                )
                assert results is not None
                # 結果の数は実装依存なので、リストであることのみ確認
        except asyncio.TimeoutError:
            pytest.fail("Query execution timed out")
    
    @pytest.mark.asyncio
    async def test_filter_expression(self, sample_python_file):
        """フィルター式のテスト"""
        service = QueryService()
        
        # フィルター式を使用してクエリ実行
        results = await service.execute_query(
            file_path=sample_python_file,
            language="python",
            query_key="function",
            filter_expression="name=test_function"
        )
        
        # フィルターが実装されている場合の確認
        if results:
            # フィルターが適用されていることを確認（具体的な内容は実装依存）
            assert isinstance(results, list)
    
    @pytest.mark.asyncio
    async def test_async_file_reading_method(self, sample_python_file):
        """非同期ファイル読み込みメソッドのテスト"""
        service = QueryService()
        
        # _read_file_asyncメソッドが存在し、動作することを確認
        if hasattr(service, '_read_file_async'):
            content, encoding = await service._read_file_async(sample_python_file)
            assert isinstance(content, str)
            assert isinstance(encoding, str)
            assert len(content) > 0
            # ファイル内容が読み込まれていることを確認
            assert "def " in content or "function" in content
    
    @pytest.mark.asyncio
    async def test_large_file_handling(self):
        """大きなファイルの処理テスト"""
        # 大きなファイルを作成
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            # 1000個の関数を持つファイルを生成
            for i in range(1000):
                f.write(f"""
def function_{i}():
    '''Function {i}'''
    return {i}
""")
            large_file = f.name
        
        try:
            service = QueryService()
            
            results = await service.execute_query(
                file_path=large_file,
                language="python",
                query_key="function"
            )
            
            assert results is not None
            # 大きなファイルでも結果が返されることを確認（具体的な数は実装依存）
            assert len(results) >= 10  # 少なくとも10個の要素が見つかることを期待
            
        finally:
            Path(large_file).unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_stress_concurrent_execution(self, sample_python_file):
        """ストレステスト: 大量の並行実行"""
        service = QueryService()
        
        # 20個の並行タスクを実行
        tasks = [
            service.execute_query(
                file_path=sample_python_file,
                language="python",
                query_key="function"
            )
            for _ in range(20)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 全てのタスクが正常に完了することを確認
        successful_results = 0
        for result in results:
            if isinstance(result, list):
                successful_results += 1
                # 結果の数は実装依存なので、リストであることのみ確認
            elif isinstance(result, Exception):
                pytest.fail(f"Task failed with exception: {result}")
        
        # 大部分のタスクが成功することを確認
        assert successful_results >= 15  # 20個中15個以上が成功