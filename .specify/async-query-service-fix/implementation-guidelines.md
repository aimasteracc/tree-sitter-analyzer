# Implementation Guidelines: Async Query Service Fix

**Feature**: Async Query Service Fix  
**Date**: 2025-10-14  
**Target**: Development Team  

## 実装ガイドライン概要

### 目的
- 15個の詳細タスクの具体的な実装手順を提供
- コード変更箇所の正確な特定と修正方法
- テスト実行方法と品質チェック項目の明確化
- 一貫性のある実装品質の確保

### 適用範囲
- Phase 1: 緊急修正（T001-T005）
- Phase 2: 包括的テスト（T006-T010）
- Phase 3: 品質保証（T011-T015）

## Phase 1: Emergency Fix Implementation

### T001: QueryService.execute_query()の非同期化

**対象ファイル**: [`tree_sitter_analyzer/core/query_service.py`](tree_sitter_analyzer/core/query_service.py:33)

**実装手順**:
1. **行33の修正**:
   ```python
   # Before
   def execute_query(
   
   # After
   async def execute_query(
   ```

2. **検証方法**:
   ```python
   import inspect
   from tree_sitter_analyzer.core.query_service import QueryService
   
   service = QueryService()
   assert inspect.iscoroutinefunction(service.execute_query)
   print("✅ execute_query is now async")
   ```

**注意事項**:
- メソッドシグネチャのみ変更、パラメータは変更しない
- 戻り値の型注釈は維持する
- docstringは後で更新（T013で対応）

### T002: 非同期ファイル読み込みの実装

**対象ファイル**: [`tree_sitter_analyzer/core/query_service.py`](tree_sitter_analyzer/core/query_service.py:67)

**実装手順**:
1. **行67の修正**:
   ```python
   # Before
   content, encoding = read_file_safe(file_path)
   
   # After
   content, encoding = await self._read_file_async(file_path)
   ```

2. **新規メソッドの追加** (クラス末尾に追加):
   ```python
   async def _read_file_async(self, file_path: str) -> tuple[str, str]:
       """
       非同期ファイル読み込み
       
       Args:
           file_path: ファイルパス
           
       Returns:
           tuple[str, str]: (content, encoding)
       """
       import asyncio
       from ..encoding_utils import read_file_safe
       
       # CPU集約的でない単純なファイル読み込みなので、
       # run_in_executorを使用して非同期化
       loop = asyncio.get_event_loop()
       return await loop.run_in_executor(None, read_file_safe, file_path)
   ```

**検証方法**:
```python
import asyncio
from tree_sitter_analyzer.core.query_service import QueryService

async def test_async_file_read():
    service = QueryService()
    content, encoding = await service._read_file_async("examples/sample.py")
    assert isinstance(content, str)
    assert isinstance(encoding, str)
    print("✅ Async file reading works")

asyncio.run(test_async_file_read())
```

### T003: asyncioインポートの追加

**対象ファイル**: [`tree_sitter_analyzer/core/query_service.py`](tree_sitter_analyzer/core/query_service.py:9)

**実装手順**:
1. **インポートセクションの修正**:
   ```python
   #!/usr/bin/env python3
   """
   Query Service
   ...
   """
   
   import asyncio  # 追加
   import logging
   from typing import Any
   ```

**検証方法**:
```bash
python -c "from tree_sitter_analyzer.core.query_service import QueryService; import asyncio; print('✅ asyncio imported successfully')"
```

### T004: MCP QueryToolの非同期呼び出し修正

**対象ファイル**: [`tree_sitter_analyzer/mcp/tools/query_tool.py`](tree_sitter_analyzer/mcp/tools/query_tool.py:159)

**実装手順**:
1. **行159の修正**:
   ```python
   # Before
   results = self.query_service.execute_query(
       resolved_file_path, language, query_key, query_string, filter_expression
   )
   
   # After
   results = await self.query_service.execute_query(
       resolved_file_path, language, query_key, query_string, filter_expression
   )
   ```

**検証方法**:
```python
# MCP tool execution test
import asyncio
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool

async def test_mcp_async():
    tool = QueryTool()
    result = await tool.execute({
        "file_path": "examples/sample.py",
        "query_key": "function"
    })
    assert result["success"] is True
    print("✅ MCP async execution works")

asyncio.run(test_mcp_async())
```

### T005: 基本動作確認テストの実行

**実装手順**:
1. **テストスクリプトの作成** (`test_emergency_fix.py`):
   ```python
   #!/usr/bin/env python3
   """Emergency fix verification script"""
   
   import asyncio
   import sys
   import tempfile
   from pathlib import Path
   
   # Add project root to path
   sys.path.insert(0, str(Path(__file__).parent))
   
   from tree_sitter_analyzer.core.query_service import QueryService
   
   async def test_basic_async_query():
       """Basic async query test"""
       service = QueryService()
       
       # Create test file
       test_file = "test_sample.py"
       with open(test_file, "w") as f:
           f.write("""
   def hello_world():
       print("Hello, World!")
   
   class TestClass:
       def test_method(self):
           pass
   """)
       
       try:
           # Test async execution
           results = await service.execute_query(
               file_path=test_file,
               language="python",
               query_key="function"
           )
           
           print(f"✅ Query executed successfully. Results: {len(results) if results else 0}")
           return True
           
       except Exception as e:
           print(f"❌ Query execution failed: {e}")
           return False
       finally:
           Path(test_file).unlink(missing_ok=True)
   
   async def test_cli_integration():
       """CLI integration test"""
       import subprocess
       
       try:
           result = subprocess.run([
               sys.executable, "-m", "tree_sitter_analyzer", 
               "query", "--file-path", "examples/sample.py", "--query-key", "function"
           ], capture_output=True, text=True, timeout=30)
           
           if result.returncode == 0:
               print("✅ CLI integration test passed")
               return True
           else:
               print(f"❌ CLI integration test failed: {result.stderr}")
               return False
       except Exception as e:
           print(f"❌ CLI integration test error: {e}")
           return False
   
   async def main():
       print("🔧 Testing async QueryService emergency fix...")
       
       # Test 1: Basic async functionality
       test1_success = await test_basic_async_query()
       
       # Test 2: CLI integration
       test2_success = await test_cli_integration()
       
       if test1_success and test2_success:
           print("🎉 All emergency fix tests passed!")
           return 0
       else:
           print("💥 Some tests failed!")
           return 1
   
   if __name__ == "__main__":
       exit_code = asyncio.run(main())
       sys.exit(exit_code)
   ```

2. **実行方法**:
   ```bash
   python test_emergency_fix.py
   ```

3. **期待される出力**:
   ```
   🔧 Testing async QueryService emergency fix...
   ✅ Query executed successfully. Results: 1
   ✅ CLI integration test passed
   🎉 All emergency fix tests passed!
   ```

## Phase 2: Comprehensive Testing Implementation

### T006: 非同期テストスイートの実装

**対象ファイル**: `tests/test_async_query_service.py` (新規作成)

**実装手順**:
1. **テストファイルの作成**:
   ```python
   #!/usr/bin/env python3
   """Comprehensive async QueryService tests"""
   
   import pytest
   import asyncio
   import tempfile
   from pathlib import Path
   
   from tree_sitter_analyzer.core.query_service import QueryService
   
   class TestAsyncQueryService:
       """非同期QueryServiceのテスト"""
       
       @pytest.fixture
       def sample_python_file(self):
           """テスト用Pythonファイル"""
           with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
               f.write("""
   def test_function():
       return 42
   
   class TestClass:
       def method(self):
           pass
   
   async def async_function():
       await asyncio.sleep(0.1)
       return "async result"
   """)
               yield f.name
           Path(f.name).unlink(missing_ok=True)
       
       @pytest.mark.asyncio
       async def test_execute_query_is_async(self):
           """execute_queryが非同期メソッドであることを確認"""
           service = QueryService()
           
           with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
               f.write("def test(): pass")
               f.flush()
               
               result_coro = service.execute_query(
                   file_path=f.name,
                   language="python",
                   query_key="function"
               )
               
               # コルーチンオブジェクトが返されることを確認
               assert asyncio.iscoroutine(result_coro)
               
               # 実際に実行
               result = await result_coro
               assert isinstance(result, list)
       
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
           assert len(results) >= 2  # test_function + async_function
           assert any(r["capture_name"] == "function" for r in results)
       
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
               )
               for _ in range(3)
           ]
           
           results = await asyncio.gather(*tasks)
           
           # 全ての結果が正常に取得できることを確認
           for result in results:
               assert result is not None
               assert len(result) >= 2
       
       @pytest.mark.asyncio
       async def test_error_handling(self):
           """エラーハンドリングテスト"""
           service = QueryService()
           
           # 存在しないファイル
           with pytest.raises(Exception):
               await service.execute_query(
                   file_path="nonexistent.py",
                   language="python",
                   query_key="function"
               )
       
       @pytest.mark.asyncio
       async def test_timeout_behavior(self, sample_python_file):
           """タイムアウト動作テスト"""
           service = QueryService()
           
           # タイムアウト付き実行
           try:
               async with asyncio.timeout(5.0):
                   results = await service.execute_query(
                       file_path=sample_python_file,
                       language="python",
                       query_key="function"
                   )
                   assert results is not None
           except asyncio.TimeoutError:
               pytest.fail("Query execution timed out")
   ```

2. **実行方法**:
   ```bash
   pip install pytest-asyncio
   pytest tests/test_async_query_service.py -v
   ```

### T007: CLI統合テストの実装

**対象ファイル**: `tests/test_cli_async_integration.py` (新規作成)

**実装手順**:
1. **テストファイルの作成**:
   ```python
   #!/usr/bin/env python3
   """CLI async integration tests"""
   
   import pytest
   import asyncio
   import subprocess
   import sys
   import tempfile
   from pathlib import Path
   
   class TestCLIAsyncIntegration:
       """CLI非同期統合テスト"""
       
       @pytest.fixture
       def sample_files(self):
           """複数のテストファイル"""
           files = []
           for i, content in enumerate([
               "def function_a(): pass",
               "class ClassB: pass", 
               "def function_c(): return 42"
           ]):
               with tempfile.NamedTemporaryFile(mode='w', suffix=f'_{i}.py', delete=False) as f:
                   f.write(content)
                   files.append(f.name)
           
           yield files
           
           for file_path in files:
               Path(file_path).unlink(missing_ok=True)
       
       def test_basic_cli_execution(self, sample_files):
           """基本的なCLI実行テスト"""
           result = subprocess.run([
               sys.executable, "-m", "tree_sitter_analyzer",
               "query", "--file-path", sample_files[0], "--query-key", "function"
           ], capture_output=True, text=True, timeout=30)
           
           assert result.returncode == 0
           assert "function_a" in result.stdout or len(result.stdout) > 0
       
       def test_multiple_file_processing(self, sample_files):
           """複数ファイルの処理テスト"""
           for file_path in sample_files:
               result = subprocess.run([
                   sys.executable, "-m", "tree_sitter_analyzer",
                   "query", "--file-path", file_path, "--query-key", "function"
               ], capture_output=True, text=True, timeout=30)
               
               assert result.returncode == 0
       
       def test_error_cases(self):
           """エラーケースのテスト"""
           # 存在しないファイル
           result = subprocess.run([
               sys.executable, "-m", "tree_sitter_analyzer",
               "query", "--file-path", "nonexistent.py", "--query-key", "function"
           ], capture_output=True, text=True, timeout=30)
           
           assert result.returncode != 0
           assert "not exist" in result.stderr or "not found" in result.stderr
   ```

### T008: MCP統合テストの実装

**対象ファイル**: `tests/test_mcp_async_integration.py` (新規作成)

**実装手順**:
1. **テストファイルの作成**:
   ```python
   #!/usr/bin/env python3
   """MCP async integration tests"""
   
   import pytest
   import asyncio
   import tempfile
   from pathlib import Path
   
   from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
   
   class TestMCPAsyncIntegration:
       """MCP非同期統合テスト"""
       
       @pytest.fixture
       def sample_code_file(self):
           """テスト用コードファイル"""
           with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
               f.write("""
   def example_function():
       '''Example function for testing'''
       return "Hello, World!"
   
   class ExampleClass:
       def __init__(self):
           self.value = 42
       
       def get_value(self):
           return self.value
   """)
               yield f.name
           Path(f.name).unlink(missing_ok=True)
       
       @pytest.mark.asyncio
       async def test_query_tool_basic_execution(self, sample_code_file):
           """QueryToolの基本実行テスト"""
           tool = QueryTool()
           
           result = await tool.execute({
               "file_path": sample_code_file,
               "query_key": "function"
           })
           
           assert result["success"] is True
           assert result["count"] >= 1
           assert "results" in result
       
       @pytest.mark.asyncio
       async def test_query_tool_output_formats(self, sample_code_file):
           """出力フォーマットのテスト"""
           tool = QueryTool()
           
           # JSON format
           json_result = await tool.execute({
               "file_path": sample_code_file,
               "query_key": "function",
               "output_format": "json"
           })
           assert json_result["success"] is True
           assert "results" in json_result
           
           # Summary format
           summary_result = await tool.execute({
               "file_path": sample_code_file,
               "query_key": "function", 
               "output_format": "summary"
           })
           assert summary_result["success"] is True
           assert "captures" in summary_result
       
       @pytest.mark.asyncio
       async def test_query_tool_error_handling(self):
           """エラーハンドリングテスト"""
           tool = QueryTool()
           
           # 存在しないファイル
           result = await tool.execute({
               "file_path": "nonexistent.py",
               "query_key": "function"
           })
           assert result["success"] is False
           assert "error" in result
       
       @pytest.mark.asyncio
       async def test_concurrent_mcp_execution(self, sample_code_file):
           """並行MCP実行テスト"""
           tool = QueryTool()
           
           tasks = [
               tool.execute({
                   "file_path": sample_code_file,
                   "query_key": "function"
               }),
               tool.execute({
                   "file_path": sample_code_file,
                   "query_key": "class"
               })
           ]
           
           results = await asyncio.gather(*tasks, return_exceptions=True)
           
           for result in results:
               if isinstance(result, dict):
                   assert result["success"] is True
               else:
                   pytest.fail(f"Unexpected exception: {result}")
   ```

### T009: パフォーマンステストの実装

**対象ファイル**: `tests/test_async_performance.py` (新規作成)

**実装手順**:
1. **テストファイルの作成**:
   ```python
   #!/usr/bin/env python3
   """Async performance tests"""
   
   import pytest
   import asyncio
   import time
   import tempfile
   from pathlib import Path
   
   from tree_sitter_analyzer.core.query_service import QueryService
   
   class TestAsyncPerformance:
       """非同期処理のパフォーマンステスト"""
       
       @pytest.fixture
       def large_python_file(self):
           """大きなPythonファイル"""
           with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
               # 100個の関数を持つファイルを生成
               for i in range(100):
                   f.write(f"""
   def function_{i}():
       '''Function {i}'''
       x = {i}
       return x * 2
   
   class Class_{i}:
       def method_{i}(self):
           return {i}
   """)
               yield f.name
           Path(f.name).unlink(missing_ok=True)
       
       @pytest.mark.asyncio
       async def test_performance_baseline(self, large_python_file):
           """パフォーマンスベースラインテスト"""
           service = QueryService()
           
           start_time = time.time()
           
           results = await service.execute_query(
               file_path=large_python_file,
               language="python",
               query_key="function"
           )
           
           end_time = time.time()
           duration = end_time - start_time
           
           # 結果の確認
           assert results is not None
           assert len(results) >= 100  # 100個の関数が見つかることを確認
           
           # パフォーマンス要件: 5秒以内
           assert duration < 5.0, f"Query took too long: {duration:.2f}s"
           
           print(f"Performance: {duration:.2f}s for {len(results)} results")
       
       @pytest.mark.asyncio
       async def test_concurrent_performance(self, large_python_file):
           """並行処理パフォーマンステスト"""
           service = QueryService()
           
           # Sequential execution
           start_time = time.time()
           for _ in range(3):
               await service.execute_query(
                   file_path=large_python_file,
                   language="python",
                   query_key="function"
               )
           sequential_time = time.time() - start_time
           
           # Concurrent execution
           start_time = time.time()
           tasks = [
               service.execute_query(
                   file_path=large_python_file,
                   language="python",
                   query_key="function"
               )
               for _ in range(3)
           ]
           await asyncio.gather(*tasks)
           concurrent_time = time.time() - start_time
           
           # 並行実行が効率的であることを確認
           efficiency = sequential_time / concurrent_time
           assert efficiency > 1.5, f"Concurrent execution not efficient: {efficiency:.2f}x"
           
           print(f"Sequential: {sequential_time:.2f}s, Concurrent: {concurrent_time:.2f}s, Efficiency: {efficiency:.2f}x")
       
       @pytest.mark.asyncio
       async def test_memory_usage(self, large_python_file):
           """メモリ使用量テスト"""
           import psutil
           import os
           
           service = QueryService()
           process = psutil.Process(os.getpid())
           
           # 初期メモリ使用量
           initial_memory = process.memory_info().rss
           
           # クエリ実行
           results = await service.execute_query(
               file_path=large_python_file,
               language="python",
               query_key="function"
           )
           
           # 実行後メモリ使用量
           final_memory = process.memory_info().rss
           memory_increase = final_memory - initial_memory
           
           # メモリ増加が10%以内であることを確認
           memory_increase_percent = (memory_increase / initial_memory) * 100
           assert memory_increase_percent < 10.0, f"Memory increase too high: {memory_increase_percent:.2f}%"
           
           print(f"Memory increase: {memory_increase_percent:.2f}%")
   ```

### T010: 回帰テストの実行

**実装手順**:
1. **回帰テストスクリプトの作成** (`run_regression_tests.py`):
   ```python
   #!/usr/bin/env python3
   """Regression test runner"""
   
   import subprocess
   import sys
   import time
   
   def run_command(cmd, description):
       """コマンド実行とログ出力"""
       print(f"\n🔧 {description}")
       print(f"Command: {' '.join(cmd)}")
       
       start_time = time.time()
       result = subprocess.run(cmd, capture_output=True, text=True)
       duration = time.time() - start_time
       
       if result.returncode == 0:
           print(f"✅ {description} passed ({duration:.2f}s)")
           return True
       else:
           print(f"❌ {description} failed ({duration:.2f}s)")
           print(f"STDOUT: {result.stdout}")
           print(f"STDERR: {result.stderr}")
           return False
   
   def main():
       """回帰テスト実行"""
       print("🚀 Running regression tests for async QueryService fix...")
       
       tests = [
           # 新規非同期テスト
           (["pytest", "tests/test_async_query_service.py", "-v"], "Async QueryService tests"),
           (["pytest", "tests/test_cli_async_integration.py", "-v"], "CLI async integration tests"),
           (["pytest", "tests/test_mcp_async_integration.py", "-v"], "MCP async integration tests"),
           (["pytest", "tests/test_async_performance.py", "-v", "-s"], "Async performance tests"),
           
           # 既存テスト（重要なもの）
           (["pytest", "tests/test_core_query_service.py", "-v"], "Core QueryService tests"),
           (["pytest", "tests/test_interfaces_cli.py", "-v"], "CLI interface tests"),
           (["pytest", "tests/test_interfaces_mcp_server.py", "-v"], "MCP server tests"),
           
           # 全テスト実行
           (["pytest", "tests/", "-x", "--tb=short"], "All tests"),
       ]
       
       passed = 0
       failed = 0
       
       for cmd, description in tests:
           if run_command(cmd, description):
               passed += 1
           else:
               failed += 1
       
       print(f"\n📊 Regression test results:")
       print(f"✅ Passed: {passed}")
       print(f"❌ Failed: {failed}")
       print(f"📈 Success rate: {(passed/(passed+failed)*100):.1f}%")
       
       if failed == 0:
           print("🎉 All regression tests passed!")
           return 0
       else:
           print("💥 Some regression tests failed!")
           return 1
   
   if __name__ == "__main__":
       sys.exit(main())
   ```

2. **実行方法**:
   ```bash
   python run_regression_tests.py
   ```

## Phase 3: Quality Assurance Implementation

### T011: 型チェックの実行

**実装手順**:
1. **型チェックスクリプトの作成** (`run_type_check.py`):
   ```python
   #!/usr/bin/env python3
   """Type checking script"""
   
   import subprocess
   import sys
   
   def run_mypy_check(file_path, description):
       """mypy型チェック実行"""
       print(f"\n🔍 {description}")
       
       cmd = ["python", "-m", "mypy", file_path, "--strict"]
       result = subprocess.run(cmd, capture_output=True, text=True)
       
       if result.returncode == 0:
           print(f"✅ {description} passed")
           return True
       else:
           print(f"❌ {description} failed")
           print(f"Errors:\n{result.stdout}")
           return False
   
   def main():
       """型チェック実行"""
       print("🔍 Running type checks for async QueryService fix...")
       
       files_to_check = [
           ("tree_sitter_analyzer/core/query_service.py", "QueryService type check"),
           ("tree_sitter_analyzer/mcp/tools/query_tool.py", "QueryTool type check"),
           ("tree_sitter_analyzer/cli/commands/query_command.py", "QueryCommand type check"),
       ]
       
       passed = 0
       failed = 0
       
       for file_path, description in files_to_check:
           if run_mypy_check(file_path, description):
               passed += 1
           else:
               failed += 1
       
       print(f"\n📊 Type check results:")
       print(f"✅ Passed: {passed}")
       print(f"❌ Failed: {failed}")
       
       return 0 if failed == 0 else 1
   
   if __name__ == "__main__":
       sys.exit(main())
   ```

2. **実行方法**:
   ```bash
   pip install mypy
   python run_type_check.py
   ```

### T012: コードスタイルチェック

**実装手順**:
1. **スタイルチェックスクリプトの作成** (`run_style_check.py`):
   ```python
   #!/usr/bin/env python3
   """Code style checking script"""
   
   import subprocess
   import sys
   
   def run_ruff_check():
       """ruffによるコードチェック"""
       print("\n🎨 Running ruff code style check...")
       
       cmd = ["python", "-m", "ruff", "check", "tree_sitter_analyzer/"]
       result = subprocess.run(cmd, capture_output=True, text=True)
       
       if result.returncode == 0:
           print("✅ Ruff check passed")
           return True
       else:
           print("❌ Ruff check failed")
           print(f"Issues:\n{result.stdout}")
           return False
   
   def run_ruff_format():
       """ruffによるコードフォーマット"""
       print("\n🎨 Running ruff code formatting...")
       
       cmd = ["python", "-m", "ruff", "format", "tree_sitter_analyzer/"]
       result = subprocess.run(cmd, capture_output=True, text=True)
       
       if result.returncode == 0:
           print("✅ Ruff format completed")
           return True
       else:
           print("❌ Ruff format failed")
           print(f"Errors:\n{result.stderr}")
           return False
   
   def main():
       """スタイルチェ