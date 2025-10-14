# Quick Start: Async Query Service Fix

**Feature**: Async Query Service Fix  
**Date**: 2025-10-14  
**Estimated Time**: 4-8 hours  

## Overview

tree-sitter-analyzer v1.8.0の重大な非同期処理不整合を修正するためのクイックスタートガイドです。QueryService.execute_query()メソッドの非同期化により、QueryCommandとMCPツールでのTypeErrorを解決します。

## Prerequisites

### Environment Setup

```bash
# Python version check
python --version  # Should be 3.10+

# Virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -e .[dev]
pip install pytest-asyncio
```

### Project Structure Verification

```bash
# Verify key files exist
ls tree_sitter_analyzer/core/query_service.py
ls tree_sitter_analyzer/cli/commands/query_command.py
ls tree_sitter_analyzer/mcp/tools/query_tool.py
```

## Problem Verification

### Reproduce the Issue

```bash
# This should fail with TypeError
python -m tree_sitter_analyzer query --file-path examples/sample.py --query-key function
```

**Expected Error**:
```
TypeError: object NoneType can't be used in 'await' expression
```

### Verify Current State

```python
# Check current method signature
import inspect
from tree_sitter_analyzer.core.query_service import QueryService

service = QueryService()
sig = inspect.signature(service.execute_query)
print(f"Is async: {inspect.iscoroutinefunction(service.execute_query)}")
print(f"Signature: {sig}")
```

**Expected Output**:
```
Is async: False
Signature: (file_path: str, language: str, query_key: str | None = None, ...)
```

## Phase 1: Emergency Fix (1-2 hours)

### Step 1: Backup Current State

```bash
# Create backup
git checkout -b hotfix/async-query-service-fix
git log --oneline -5 > backup_commit_hashes.txt
cp tree_sitter_analyzer/core/query_service.py tree_sitter_analyzer/core/query_service.py.backup
```

### Step 2: Modify QueryService

**File**: `tree_sitter_analyzer/core/query_service.py`

**Change 1: Method Signature (Line 33)**
```python
# Before
def execute_query(
    self,
    file_path: str,
    language: str,
    query_key: str | None = None,
    query_string: str | None = None,
    filter_expression: str | None = None,
) -> list[dict[str, Any]] | None:

# After
async def execute_query(
    self,
    file_path: str,
    language: str,
    query_key: str | None = None,
    query_string: str | None = None,
    filter_expression: str | None = None,
) -> list[dict[str, Any]] | None:
```

**Change 2: File Reading (Line 67)**
```python
# Before
content, encoding = read_file_safe(file_path)

# After
content, encoding = await self._read_file_async(file_path)
```

**Change 3: Add Async File Reader (Add at end of class)**
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

**Change 4: Update Imports (Add at top if needed)**
```python
import asyncio
```

### Step 3: Fix MCP Tool

**File**: `tree_sitter_analyzer/mcp/tools/query_tool.py`

**Change: Line 159**
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

### Step 4: Basic Verification

**Create Test Script**: `test_async_fix.py`
```python
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from tree_sitter_analyzer.core.query_service import QueryService

async def test_basic_query():
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

async def main():
    print("🔧 Testing async QueryService fix...")
    success = await test_basic_query()
    return 0 if success else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
```

**Run Test**:
```bash
python test_async_fix.py
```

**Expected Output**:
```
🔧 Testing async QueryService fix...
✅ Query executed successfully. Results: 1
```

### Step 5: CLI Verification

```bash
# Test CLI command
python -m tree_sitter_analyzer query --file-path examples/sample.py --query-key function
```

**Expected**: No TypeError, normal query results displayed.

## Phase 2: Comprehensive Testing (2-4 hours)

### Step 1: Create Async Test Suite

**File**: `tests/test_async_query_service.py`
```python
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
        assert len(results) >= 1
        assert results[0]["capture_name"] == "function"
    
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
            assert len(result) >= 1
```

### Step 2: Run Test Suite

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run async tests
pytest tests/test_async_query_service.py -v

# Run all tests to check for regressions
pytest tests/ -x
```

### Step 3: Performance Testing

**File**: `tests/test_async_performance.py`
```python
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
```

**Run Performance Tests**:
```bash
pytest tests/test_async_performance.py -v -s
```

## Phase 3: Quality Assurance (1-2 hours)

### Step 1: Type Checking

```bash
# Install mypy if not already installed
pip install mypy

# Run type checking
python -m mypy tree_sitter_analyzer/core/query_service.py
```

**Expected**: No type errors

### Step 2: Code Quality

```bash
# Run linting
python -m ruff check tree_sitter_analyzer/core/query_service.py

# Format code
python -m ruff format tree_sitter_analyzer/core/query_service.py
```

### Step 3: Integration Testing

```bash
# Test CLI commands
python -m tree_sitter_analyzer query --file-path examples/sample.py --query-key function
python -m tree_sitter_analyzer query --file-path examples/sample.py --query-string "(function_definition) @func"

# Test MCP server (if running)
# This requires MCP server to be running
python start_mcp_server.py
```

### Step 4: Documentation Update

**Update CHANGELOG.md**:
```markdown
## [1.8.1] - 2025-10-14
### Fixed
- Fixed async/await inconsistency in QueryService.execute_query()
- Improved error handling for async operations
- Added comprehensive async tests

### Added
- Async file reading with run_in_executor
- Performance monitoring for async operations
- Concurrent query execution support
```

## Verification Checklist

### Functional Verification
- [ ] QueryCommand executes without TypeError
- [ ] MCP query tool works correctly
- [ ] All existing tests pass
- [ ] New async tests pass
- [ ] CLI commands work normally

### Performance Verification
- [ ] Processing time increase < 5%
- [ ] Memory usage increase < 10%
- [ ] Concurrent execution works
- [ ] No memory leaks detected

### Quality Verification
- [ ] Type checking passes (mypy)
- [ ] Code style consistent (ruff)
- [ ] Test coverage > 90%
- [ ] Documentation updated

## Troubleshooting

### Common Issues

**Issue**: `TypeError: object NoneType can't be used in 'await' expression`
**Solution**: Ensure all calls to `execute_query()` use `await`

**Issue**: `ImportError: cannot import name 'asyncio'`
**Solution**: Add `import asyncio` to the top of query_service.py

**Issue**: Tests fail with timeout
**Solution**: Increase timeout in test configuration or check for infinite loops

**Issue**: Performance degradation
**Solution**: Check if file I/O is properly async, consider caching

### Rollback Procedure

```bash
# If issues occur, rollback to previous version
git checkout HEAD~1 -- tree_sitter_analyzer/core/query_service.py
git checkout HEAD~1 -- tree_sitter_analyzer/mcp/tools/query_tool.py

# Or restore from backup
cp tree_sitter_analyzer/core/query_service.py.backup tree_sitter_analyzer/core/query_service.py
```

## Next Steps

1. **Monitor Production**: Watch for any performance issues
2. **Gather Feedback**: Collect user feedback on stability
3. **Optimize Further**: Consider additional async optimizations
4. **Document Lessons**: Update development guidelines

## Success Criteria

✅ **Critical**: QueryCommand TypeError resolved  
✅ **Critical**: All existing functionality preserved  
✅ **Important**: Performance requirements met  
✅ **Important**: Test coverage maintained  
✅ **Nice-to-have**: Concurrent execution improved  

---

**Created**: 2025-10-14  
**Estimated Completion**: 4-8 hours  
**Risk Level**: Low (minimal changes)  
**Impact**: High (fixes critical bug)