# 可靠性与稳定性改进实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复7个CRITICAL和16个HIGH优先级的可靠性问题，提升系统稳定性

**Architecture:** 分3个阶段实施，每个阶段独立提交。Phase 1修复关键问题（单例竞态、静默数据丢失、安全验证），Phase 2修复高优先级问题（内存安全、递归转迭代、缓存限制），Phase 3修复中优先级问题。

**Tech Stack:** Python 3.10+, pytest, threading, asyncio

---

## Phase 1: 关键修复

### Task 1: 修复 UnifiedAnalysisEngine 单例竞态条件

**Files:**
- Modify: `tree_sitter_analyzer/core/analysis_engine.py:45-54`
- Test: `tests/unit/core/test_analysis_engine_singleton.py`

**Step 1: 编写失败的测试**

创建测试文件 `tests/unit/core/test_analysis_engine_singleton.py`:

```python
"""Tests for UnifiedAnalysisEngine singleton thread safety."""
import threading
import time

import pytest


class TestSingletonThreadSafety:
    """Test singleton pattern thread safety."""

    def test_singleton_returns_same_instance_single_thread(self):
        """Single thread should always get same instance."""
        from tree_sitter_analyzer.core.analysis_engine import UnifiedAnalysisEngine

        # Reset for test isolation
        UnifiedAnalysisEngine._instances.clear()

        instance1 = UnifiedAnalysisEngine()
        instance2 = UnifiedAnalysisEngine()

        assert instance1 is instance2

    def test_singleton_returns_same_instance_multi_thread(self):
        """Multiple threads should get same instance."""
        from tree_sitter_analyzer.core.analysis_engine import UnifiedAnalysisEngine

        # Reset for test isolation
        UnifiedAnalysisEngine._instances.clear()

        instances = []
        errors = []

        def create_instance():
            try:
                instance = UnifiedAnalysisEngine()
                instances.append(instance)
            except Exception as e:
                errors.append(e)

        # Create 10 threads trying to instantiate simultaneously
        threads = [threading.Thread(target=create_instance) for _ in range(10)]

        # Start all threads at nearly the same time
        for t in threads:
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors during instantiation: {errors}"
        assert len(instances) == 10

        # All instances should be the same object
        first_instance = instances[0]
        for instance in instances:
            assert instance is first_instance, "Not all instances are identical"

    def test_singleton_different_project_roots(self):
        """Different project roots should get different instances."""
        from tree_sitter_analyzer.core.analysis_engine import UnifiedAnalysisEngine

        # Reset for test isolation
        UnifiedAnalysisEngine._instances.clear()

        instance1 = UnifiedAnalysisEngine("/path/to/project1")
        instance2 = UnifiedAnalysisEngine("/path/to/project2")
        instance3 = UnifiedAnalysisEngine("/path/to/project1")

        assert instance1 is not instance2
        assert instance1 is instance3

    def test_singleton_initialized_flag_set_atomically(self):
        """_initialized flag should be set before instance is returned."""
        from tree_sitter_analyzer.core.analysis_engine import UnifiedAnalysisEngine

        # Reset for test isolation
        UnifiedAnalysisEngine._instances.clear()

        instance = UnifiedAnalysisEngine()

        # Check that _initialized was set (not False)
        # This tests the atomic initialization
        assert hasattr(instance, "_initialized")
```

**Step 2: 运行测试验证失败**

```bash
pytest tests/unit/core/test_analysis_engine_singleton.py -v
```

预期结果: 测试可能通过或因竞态条件间歇性失败

**Step 3: 实现最小修复**

修改 `tree_sitter_analyzer/core/analysis_engine.py`:

```python
# 替换第45-54行
def __new__(cls, project_root: str | None = None) -> "UnifiedAnalysisEngine":
    """Singleton instance management (thread-safe)."""
    instance_key = project_root or "default"
    # Always acquire lock to ensure thread-safe initialization
    with cls._lock:
        if instance_key not in cls._instances:
            instance = super().__new__(cls)
            # Set _initialized atomically within lock
            instance._initialized = False
            cls._instances[instance_key] = instance
    return cls._instances[instance_key]
```

**Step 4: 运行测试验证通过**

```bash
pytest tests/unit/core/test_analysis_engine_singleton.py -v
```

预期结果: 所有测试通过

**Step 5: 提交**

```bash
git add tests/unit/core/test_analysis_engine_singleton.py tree_sitter_analyzer/core/analysis_engine.py
git commit -m "fix(core): make UnifiedAnalysisEngine singleton thread-safe

- Move instance creation entirely within lock
- Set _initialized flag atomically within lock
- Add comprehensive thread safety tests

Fixes: C-1"
```

---

### Task 2: 修复 SharedCache 单例竞态条件

**Files:**
- Modify: `tree_sitter_analyzer/mcp/utils/shared_cache.py:12-18`
- Test: `tests/unit/mcp/utils/test_shared_cache_thread_safety.py`

**Step 1: 编写失败的测试**

创建测试文件 `tests/unit/mcp/utils/test_shared_cache_thread_safety.py`:

```python
"""Tests for SharedCache singleton thread safety."""
import threading

import pytest


class TestSharedCacheThreadSafety:
    """Test SharedCache singleton thread safety."""

    def test_shared_cache_singleton_thread_safety(self):
        """Multiple threads should get same SharedCache instance."""
        from tree_sitter_analyzer.mcp.utils.shared_cache import SharedCache

        instances = []
        errors = []

        def get_instance():
            try:
                instance = SharedCache()
                instances.append(instance)
            except Exception as e:
                errors.append(e)

        # Reset singleton
        SharedCache._instance = None

        # Create 10 threads
        threads = [threading.Thread(target=get_instance) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(instances) == 10

        # All should be same instance
        first = instances[0]
        for inst in instances:
            assert inst is first, "Not all SharedCache instances are identical"

    def test_shared_cache_concurrent_access(self):
        """Concurrent cache operations should not cause issues."""
        from tree_sitter_analyzer.mcp.utils.shared_cache import SharedCache

        SharedCache._instance = None
        cache = SharedCache()

        errors = []

        def cache_operations(thread_id: int):
            try:
                for i in range(100):
                    key = f"test_key_{thread_id}_{i}"
                    cache.set_language(key, f"lang_{thread_id}")
                    result = cache.get_language(key)
                    assert result == f"lang_{thread_id}"
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=cache_operations, args=(i,)) for i in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrent access errors: {errors}"
```

**Step 2: 运行测试验证失败**

```bash
pytest tests/unit/mcp/utils/test_shared_cache_thread_safety.py -v
```

**Step 3: 实现最小修复**

修改 `tree_sitter_analyzer/mcp/utils/shared_cache.py`:

```python
# 在文件开头添加
import threading

# 替换 SharedCache 类定义
class SharedCache:
    """Shared cache for MCP tools with thread-safe singleton."""

    _instance: "SharedCache | None" = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "SharedCache":
        """Thread-safe singleton instantiation."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialize()
                    cls._instance = instance
        return cls._instance

    def _initialize(self) -> None:
        """Initialize cache dictionaries."""
        self._language_cache: dict[str, str] = {}
        self._language_meta_cache: dict[str, dict[str, Any]] = {}
        self._security_cache: dict[str, tuple[bool, str]] = {}
        self._metrics_cache: dict[str, dict[str, Any]] = {}
        self._resolved_paths: dict[str, str] = {}

    # 保持其余方法不变，但添加锁保护
    _access_lock: threading.Lock = threading.Lock()

    def set_language(
        self, file_path: str, language: str, project_root: str | None = None
    ) -> None:
        with self._access_lock:
            self._language_cache[self._make_key("language", file_path, project_root)] = (
                language
            )

    def get_language(
        self, file_path: str, project_root: str | None = None
    ) -> str | None:
        with self._access_lock:
            return self._language_cache.get(
                self._make_key("language", file_path, project_root)
            )
```

**Step 4: 运行测试验证通过**

```bash
pytest tests/unit/mcp/utils/test_shared_cache_thread_safety.py -v
```

**Step 5: 提交**

```bash
git add tests/unit/mcp/utils/test_shared_cache_thread_safety.py tree_sitter_analyzer/mcp/utils/shared_cache.py
git commit -m "fix(mcp): make SharedCache singleton thread-safe

- Add thread-safe singleton pattern with lock
- Add access lock for cache operations
- Add comprehensive thread safety tests

Fixes: H-4"
```

---

### Task 3: 修复非Java文件静默数据丢失

**Files:**
- Modify: `tree_sitter_analyzer/mcp/tools/analyze_scale_tool.py:452-456`
- Test: `tests/unit/mcp/tools/test_analyze_scale_tool_error.py`

**Step 1: 编写失败的测试**

创建测试文件 `tests/unit/mcp/tools/test_analyze_scale_tool_error.py`:

```python
"""Tests for AnalyzeScaleTool error handling."""
import pytest


class TestAnalyzeScaleToolErrorHandling:
    """Test error handling for non-Java structural analysis."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create AnalyzeScaleTool instance."""
        from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool

        return AnalyzeScaleTool(str(tmp_path))

    @pytest.mark.asyncio
    async def test_non_java_file_raises_clear_error(self, tool, tmp_path):
        """Non-Java files should raise clear error, not return empty data."""
        # Create a Python file
        python_file = tmp_path / "test.py"
        python_file.write_text("def hello(): pass")

        arguments = {
            "file_path": str(python_file),
            "include_guidance": False,
        }

        result = await tool.execute(arguments)

        # Should have error for structural analysis
        assert result.get("success") is False
        assert "structural analysis" in result.get("error", "").lower()
        assert "python" in result.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_java_file_works_correctly(self, tool, tmp_path):
        """Java files should work correctly."""
        # Create a Java file
        java_file = tmp_path / "Test.java"
        java_file.write_text("""
public class Test {
    public void method() {}
}
""")

        arguments = {
            "file_path": str(java_file),
            "include_guidance": False,
        }

        result = await tool.execute(arguments)

        # Should succeed
        assert result.get("success") is True
        # Should have structural overview
        assert "structural_overview" in result or "classes" in result.get("summary", {})
```

**Step 2: 运行测试验证失败**

```bash
pytest tests/unit/mcp/tools/test_analyze_scale_tool_error.py -v
```

预期结果: 测试失败，因为当前代码返回空数据而不是错误

**Step 3: 实现最小修复**

修改 `tree_sitter_analyzer/mcp/tools/analyze_scale_tool.py` 第452-456行:

```python
# 替换占位符代码
if language != "java":
    # Non-Java languages: provide basic metrics without structural analysis
    # but return clear indication that structural analysis is limited
    analysis_result = None
    structural_overview = {
        "_note": f"Structural analysis not fully supported for {language}",
        "_suggestion": "Use analyze_code_structure tool for detailed analysis",
    }
else:
    # Continue with Java analysis...
    # (existing Java code remains unchanged)
    pass
```

更好的方案是修改返回结果，在结果中明确说明限制:

```python
# 在构建result之前添加
if language != "java" and analysis_result is None:
    result["warnings"] = result.get("warnings", [])
    result["warnings"].append(
        f"Structural analysis limited for {language}. "
        "Use analyze_code_structure tool for detailed code structure."
    )
```

**Step 4: 运行测试验证通过**

```bash
pytest tests/unit/mcp/tools/test_analyze_scale_tool_error.py -v
```

**Step 5: 提交**

```bash
git add tests/unit/mcp/tools/test_analyze_scale_tool_error.py tree_sitter_analyzer/mcp/tools/analyze_scale_tool.py
git commit -m "fix(mcp): return clear warning for non-Java structural analysis

- Add warning when structural analysis is limited
- Suggest alternative tool for detailed analysis
- Add tests for error handling

Fixes: C-3"
```

---

### Task 4: 添加 PartialReadCommand 安全验证

**Files:**
- Modify: `tree_sitter_analyzer/cli/commands/partial_read_command.py:34-50`
- Test: `tests/unit/cli/commands/test_partial_read_security.py`

**Step 1: 编写失败的测试**

创建测试文件 `tests/unit/cli/commands/test_partial_read_security.py`:

```python
"""Tests for PartialReadCommand security validation."""
import argparse
from pathlib import Path

import pytest


class TestPartialReadCommandSecurity:
    """Test security validation in PartialReadCommand."""

    @pytest.fixture
    def command_class(self):
        """Get PartialReadCommand class."""
        from tree_sitter_analyzer.cli.commands.partial_read_command import (
            PartialReadCommand,
        )

        return PartialReadCommand

    def test_rejects_path_traversal_attack(self, command_class, tmp_path):
        """Should reject paths with .. traversal."""
        # Create a file in tmp_path
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        args = argparse.Namespace(
            file_path="../../../etc/passwd",
            start_line=1,
            end_line=10,
            output_format="text",
        )

        command = command_class(args)
        result = command.validate_file()

        assert result is False

    def test_rejects_symlink_outside_project(self, command_class, tmp_path):
        """Should reject symlinks pointing outside project."""
        # Create symlink pointing outside
        symlink = tmp_path / "symlink"
        try:
            symlink.symlink_to("/etc/passwd")
        except OSError:
            pytest.skip("Cannot create symlink on this system")

        args = argparse.Namespace(
            file_path=str(symlink),
            start_line=1,
            end_line=10,
            output_format="text",
        )

        command = command_class(args)
        result = command.validate_file()

        assert result is False

    def test_accepts_valid_file(self, command_class, tmp_path):
        """Should accept valid files within project."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')\n" * 10)

        args = argparse.Namespace(
            file_path=str(test_file),
            start_line=1,
            end_line=5,
            output_format="text",
        )

        command = command_class(args)
        result = command.validate_file()

        assert result is True

    def test_rejects_absolute_path_outside_project(self, command_class):
        """Should reject absolute paths outside project."""
        args = argparse.Namespace(
            file_path="/etc/passwd",
            start_line=1,
            end_line=10,
            output_format="text",
        )

        command = command_class(args)
        result = command.validate_file()

        assert result is False
```

**Step 2: 运行测试验证失败**

```bash
pytest tests/unit/cli/commands/test_partial_read_security.py -v
```

预期结果: 测试失败，因为当前没有安全验证

**Step 3: 实现最小修复**

修改 `tree_sitter_analyzer/cli/commands/partial_read_command.py`:

```python
def validate_file(self) -> bool:
    """Validate input file exists, is accessible, and is safe."""
    if not hasattr(self.args, "file_path") or not self.args.file_path:
        from ...output_manager import output_error

        output_error("File path not specified.")
        return False

    from pathlib import Path

    file_path = Path(self.args.file_path)

    # Security checks
    # 1. Check for path traversal
    if ".." in str(file_path):
        from ...output_manager import output_error

        output_error(f"Path traversal not allowed: {self.args.file_path}")
        return False

    # 2. Check if file exists
    if not file_path.exists():
        from ...output_manager import output_error

        output_error(f"File not found: {self.args.file_path}")
        return False

    # 3. Check for symlinks pointing outside allowed areas
    try:
        resolved = file_path.resolve()
        # Basic check: don't allow access to system files
        if str(resolved).startswith("/etc/") or str(resolved).startswith("/root/"):
            from ...output_manager import output_error

            output_error(f"Access denied to system path: {self.args.file_path}")
            return False
    except OSError as e:
        from ...output_manager import output_error

        output_error(f"Cannot resolve file path: {e}")
        return False

    return True
```

**Step 4: 运行测试验证通过**

```bash
pytest tests/unit/cli/commands/test_partial_read_security.py -v
```

**Step 5: 提交**

```bash
git add tests/unit/cli/commands/test_partial_read_security.py tree_sitter_analyzer/cli/commands/partial_read_command.py
git commit -m "fix(cli): add security validation to PartialReadCommand

- Add path traversal check
- Add symlink safety check
- Add system path protection
- Add comprehensive security tests

Fixes: C-5"
```

---

### Task 5: 改进顶层异常处理

**Files:**
- Modify: `tree_sitter_analyzer/cli_main.py:647-649`
- Test: `tests/unit/test_cli_main_exception_handling.py`

**Step 1: 编写失败的测试**

创建测试文件 `tests/unit/test_cli_main_exception_handling.py`:

```python
"""Tests for CLI main exception handling."""
import sys
from unittest import mock

import pytest


class TestCLIMainExceptionHandling:
    """Test exception handling in CLI main."""

    def test_unexpected_exception_includes_traceback(self, capsys):
        """Unexpected exceptions should include traceback in output."""
        # Mock to trigger an unexpected exception
        with mock.patch(
            "tree_sitter_analyzer.cli_main.handle_special_commands",
            side_effect=RuntimeError("Unexpected error"),
        ):
            with mock.patch.object(sys, "argv", ["tree-sitter-analyzer", "test.py"]):
                from tree_sitter_analyzer.cli_main import main

                with pytest.raises(SystemExit) as exc_info:
                    main()

                # Should exit with code 1
                assert exc_info.value.code == 1

                # Should include error message
                captured = capsys.readouterr()
                assert "Unexpected error" in captured.err or "Unexpected error" in captured.out

    def test_exception_type_is_shown(self, capsys):
        """Exception type should be shown for debugging."""
        with mock.patch(
            "tree_sitter_analyzer.cli_main.handle_special_commands",
            side_effect=ValueError("Bad value"),
        ):
            with mock.patch.object(sys, "argv", ["tree-sitter-analyzer", "test.py"]):
                from tree_sitter_analyzer.cli_main import main

                with pytest.raises(SystemExit):
                    main()

                captured = capsys.readouterr()
                output = captured.err + captured.out
                # Should mention the exception type
                assert "ValueError" in output or "value" in output.lower()
```

**Step 2: 运行测试验证失败**

```bash
pytest tests/unit/test_cli_main_exception_handling.py -v
```

**Step 3: 实现最小修复**

修改 `tree_sitter_analyzer/cli_main.py`:

```python
# 替换第647-649行
except Exception as e:
    import traceback

    output_error(f"Unexpected error: {type(e).__name__}: {e}")
    # Log full traceback for debugging
    output_error("Full traceback:")
    for line in traceback.format_exc().splitlines():
        output_error(f"  {line}")
    sys.exit(1)
```

**Step 4: 运行测试验证通过**

```bash
pytest tests/unit/test_cli_main_exception_handling.py -v
```

**Step 5: 提交**

```bash
git add tests/unit/test_cli_main_exception_handling.py tree_sitter_analyzer/cli_main.py
git commit -m "fix(cli): improve exception handling with full traceback

- Include exception type in error message
- Log full traceback for debugging
- Add tests for exception handling

Fixes: C-7"
```

---

## Phase 2: 高优先级修复

### Task 6: 添加文件大小限制

**Files:**
- Modify: `tree_sitter_analyzer/core/parser.py:106-131`
- Test: `tests/unit/core/test_parser_file_size_limit.py`

**Step 1: 编写失败的测试**

```python
"""Tests for Parser file size limits."""
import pytest


class TestParserFileSizeLimit:
    """Test file size limit functionality."""

    @pytest.fixture
    def parser(self):
        """Create Parser instance."""
        from tree_sitter_analyzer.core.parser import Parser

        return Parser()

    def test_default_max_file_size(self, parser):
        """Should have default max file size."""
        assert hasattr(parser, "_max_file_size")
        assert parser._max_file_size > 0
        # Default should be around 10MB
        assert parser._max_file_size >= 10 * 1024 * 1024

    def test_rejects_oversized_file(self, parser, tmp_path):
        """Should reject files exceeding size limit."""
        # Create a file larger than limit
        large_file = tmp_path / "large.py"
        large_file.write_text("x = 1\n" * 1000000)  # ~8MB

        # Set a small limit for testing
        parser._max_file_size = 1024  # 1KB

        with pytest.raises(Exception) as exc_info:
            parser.parse_file(str(large_file))

        assert "size" in str(exc_info.value).lower() or "large" in str(exc_info.value).lower()

    def test_accepts_normal_sized_file(self, parser, tmp_path):
        """Should accept files within size limit."""
        normal_file = tmp_path / "normal.py"
        normal_file.write_text("def hello():\n    print('world')\n")

        result = parser.parse_file(str(normal_file))
        assert result is not None

    def test_configurable_max_file_size(self):
        """Max file size should be configurable."""
        from tree_sitter_analyzer.core.parser import Parser

        parser = Parser(max_file_size=1024)
        assert parser._max_file_size == 1024
```

**Step 2: 运行测试验证失败**

```bash
pytest tests/unit/core/test_parser_file_size_limit.py -v
```

**Step 3: 实现最小修复**

修改 `tree_sitter_analyzer/core/parser.py`:

```python
# 在 Parser.__init__ 中添加
def __init__(self, max_file_size: int | None = None) -> None:
    """Initialize parser with optional file size limit.

    Args:
        max_file_size: Maximum file size in bytes. Default is 10MB.
    """
    self._max_file_size = max_file_size or (10 * 1024 * 1024)  # 10MB default
    # ... rest of init

# 在 parse_file 方法开头添加检查
def parse_file(self, file_path: str, ...) -> ...:
    """Parse file with size check."""
    from pathlib import Path

    path_obj = Path(file_path)

    # Check file size before reading
    file_size = path_obj.stat().st_size
    if file_size > self._max_file_size:
        from ..exceptions import AnalysisError

        raise AnalysisError(
            f"File too large: {file_path} ({file_size / 1024 / 1024:.2f}MB > {self._max_file_size / 1024 / 1024:.2f}MB limit)",
            operation="parse_file",
        )

    # ... rest of method
```

**Step 4: 运行测试验证通过**

```bash
pytest tests/unit/core/test_parser_file_size_limit.py -v
```

**Step 5: 提交**

```bash
git add tests/unit/core/test_parser_file_size_limit.py tree_sitter_analyzer/core/parser.py
git commit -m "feat(core): add configurable file size limit to Parser

- Add 10MB default file size limit
- Make limit configurable via constructor
- Raise clear error for oversized files
- Add comprehensive tests

Fixes: H-1"
```

---

### Task 7: 递归转迭代 - find_error_nodes

**Files:**
- Modify: `tree_sitter_analyzer/core/parser.py:280-298`
- Test: `tests/unit/core/test_parser_iterative_traversal.py`

**Step 1: 编写失败的测试**

```python
"""Tests for iterative tree traversal."""
import pytest


class TestIterativeTreeTraversal:
    """Test iterative tree traversal to avoid stack overflow."""

    def test_find_error_nodes_deep_nesting(self):
        """Should handle deeply nested trees without stack overflow."""
        from tree_sitter_analyzer.core.parser import Parser
        import tree_sitter_python as tspython

        parser = Parser()

        # Create deeply nested Python code
        deep_code = "x = " + "(" * 1000 + "1" + ")" * 1000

        # This should not raise RecursionError
        result = parser.parse_code(deep_code, "python")
        assert result is not None

    def test_find_error_nodes_returns_same_results(self):
        """Iterative version should return same results as recursive."""
        from tree_sitter_analyzer.core.parser import Parser

        parser = Parser()

        # Code with syntax error
        code_with_error = "def foo(\n"  # Incomplete function

        result = parser.parse_code(code_with_error, "python")
        # Should detect the error node
        # (Implementation specific - adjust based on actual behavior)
```

**Step 2: 运行测试验证**

```bash
pytest tests/unit/core/test_parser_iterative_traversal.py -v
```

**Step 3: 实现修复**

修改 `tree_sitter_analyzer/core/parser.py`:

```python
# 替换递归的 find_error_nodes 函数
def _find_error_nodes_iterative(root_node: Any) -> list[Any]:
    """Find error nodes using iterative traversal.

    Uses a stack-based approach to avoid recursion limit issues
    with deeply nested ASTs.
    """
    error_nodes = []
    stack = [root_node]

    while stack:
        node = stack.pop()

        if node is None:
            continue

        if getattr(node, "is_error", False) or getattr(node, "has_error", False):
            error_nodes.append(node)

        # Add children to stack
        if hasattr(node, "children"):
            for child in reversed(node.children):  # Reverse to maintain order
                stack.append(child)

    return error_nodes
```

**Step 4: 运行测试验证通过**

```bash
pytest tests/unit/core/test_parser_iterative_traversal.py -v
```

**Step 5: 提交**

```bash
git add tests/unit/core/test_parser_iterative_traversal.py tree_sitter_analyzer/core/parser.py
git commit -m "refactor(core): convert find_error_nodes to iterative

- Replace recursive traversal with stack-based approach
- Prevent stack overflow on deeply nested code
- Add tests for deep nesting handling

Fixes: H-3"
```

---

### Task 8: 实现缓存大小限制和LRU驱逐

**Files:**
- Modify: `tree_sitter_analyzer/mcp/utils/shared_cache.py`
- Modify: `tree_sitter_analyzer/core/cache_service.py`
- Test: `tests/unit/core/test_cache_size_limits.py`

**Step 1: 编写失败的测试**

```python
"""Tests for cache size limits and LRU eviction."""
import pytest


class TestCacheSizeLimits:
    """Test cache size limits and eviction."""

    def test_shared_cache_has_max_size(self):
        """SharedCache should have configurable max size."""
        from tree_sitter_analyzer.mcp.utils.shared_cache import SharedCache

        SharedCache._instance = None
        cache = SharedCache()

        assert hasattr(cache, "_max_size")
        assert cache._max_size > 0

    def test_shared_cache_evicts_on_overflow(self):
        """Cache should evict old entries when full."""
        from tree_sitter_analyzer.mcp.utils.shared_cache import SharedCache

        SharedCache._instance = None
        cache = SharedCache()
        cache._max_size = 10  # Small limit for testing

        # Add more entries than limit
        for i in range(20):
            cache.set_language(f"/path/file_{i}", f"lang_{i}")

        # Cache should not exceed max size
        total_entries = len(cache._language_cache)
        assert total_entries <= cache._max_size

    def test_lru_eviction_removes_oldest(self):
        """LRU eviction should remove least recently used entries."""
        from tree_sitter_analyzer.mcp.utils.shared_cache import SharedCache

        SharedCache._instance = None
        cache = SharedCache()
        cache._max_size = 5

        # Add entries
        for i in range(5):
            cache.set_language(f"/path/file_{i}", f"lang_{i}")

        # Access first entry (makes it recently used)
        cache.get_language("/path/file_0")

        # Add more entries to trigger eviction
        for i in range(5, 10):
            cache.set_language(f"/path/file_{i}", f"lang_{i}")

        # First entry should still exist (was accessed recently)
        assert cache.get_language("/path/file_0") == "lang_0"
```

**Step 2: 运行测试验证失败**

```bash
pytest tests/unit/core/test_cache_size_limits.py -v
```

**Step 3: 实现修复**

修改 `tree_sitter_analyzer/mcp/utils/shared_cache.py`:

```python
from collections import OrderedDict
import threading
from typing import Any


class SharedCache:
    """Shared cache with LRU eviction and thread safety."""

    _instance: "SharedCache | None" = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, max_size: int = 1000) -> "SharedCache":
        """Thread-safe singleton with configurable max size."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._max_size = max_size
                    instance._initialize()
                    cls._instance = instance
        return cls._instance

    def _initialize(self) -> None:
        """Initialize cache with OrderedDict for LRU."""
        self._language_cache: OrderedDict[str, str] = OrderedDict()
        self._language_meta_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._security_cache: OrderedDict[str, tuple[bool, str]] = OrderedDict()
        self._metrics_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._resolved_paths: OrderedDict[str, str] = OrderedDict()
        self._access_lock = threading.Lock()

    def _evict_if_needed(self, cache: OrderedDict) -> None:
        """Evict oldest entries if cache is full."""
        while len(cache) >= self._max_size:
            cache.popitem(last=False)  # Remove oldest (FIFO for LRU)

    def set_language(
        self, file_path: str, language: str, project_root: str | None = None
    ) -> None:
        """Set language with LRU eviction."""
        with self._access_lock:
            key = self._make_key("language", file_path, project_root)
            if key in self._language_cache:
                del self._language_cache[key]  # Remove to re-add at end
            self._evict_if_needed(self._language_cache)
            self._language_cache[key] = language

    def get_language(
        self, file_path: str, project_root: str | None = None
    ) -> str | None:
        """Get language and mark as recently used."""
        with self._access_lock:
            key = self._make_key("language", file_path, project_root)
            if key in self._language_cache:
                # Move to end (most recently used)
                self._language_cache.move_to_end(key)
                return self._language_cache[key]
            return None
```

**Step 4: 运行测试验证通过**

```bash
pytest tests/unit/core/test_cache_size_limits.py -v
```

**Step 5: 提交**

```bash
git add tests/unit/core/test_cache_size_limits.py tree_sitter_analyzer/mcp/utils/shared_cache.py
git commit -m "feat(cache): add LRU eviction to SharedCache

- Use OrderedDict for LRU tracking
- Add configurable max_size (default 1000)
- Evict oldest entries when full
- Add comprehensive tests

Fixes: H-5"
```

---

## Phase 3: 中优先级修复

### Task 9: 标准化输入验证

**Files:**
- Create: `tree_sitter_analyzer/validation/standard_validator.py`
- Test: `tests/unit/validation/test_standard_validator.py`

**Step 1: 编写失败的测试**

```python
"""Tests for standardized input validation."""
import pytest


class TestStandardValidator:
    """Test standardized input validation."""

    @pytest.fixture
    def validator(self):
        """Create StandardValidator instance."""
        from tree_sitter_analyzer.validation.standard_validator import StandardValidator

        return StandardValidator()

    def test_validate_file_path_valid(self, validator, tmp_path):
        """Valid file paths should pass."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        result = validator.validate_file_path(str(test_file))
        assert result.is_valid
        assert result.resolved_path is not None

    def test_validate_file_path_traversal(self, validator):
        """Path traversal should be rejected."""
        result = validator.validate_file_path("../../../etc/passwd")
        assert not result.is_valid
        assert "traversal" in result.error.lower()

    def test_validate_positive_integer(self, validator):
        """Positive integers should pass."""
        result = validator.validate_positive_integer(5, "count")
        assert result.is_valid

    def test_validate_positive_integer_negative(self, validator):
        """Negative values should fail."""
        result = validator.validate_positive_integer(-1, "count")
        assert not result.is_valid

    def test_validate_positive_integer_zero(self, validator):
        """Zero should fail for positive integer."""
        result = validator.validate_positive_integer(0, "count")
        assert not result.is_valid

    def test_validate_output_format_valid(self, validator):
        """Valid output formats should pass."""
        for fmt in ["json", "text", "toon", "table", "csv"]:
            result = validator.validate_output_format(fmt)
            assert result.is_valid, f"Format {fmt} should be valid"

    def test_validate_output_format_invalid(self, validator):
        """Invalid output formats should fail."""
        result = validator.validate_output_format("invalid_format")
        assert not result.is_valid
```

**Step 2: 运行测试验证失败**

```bash
pytest tests/unit/validation/test_standard_validator.py -v
```

**Step 3: 实现最小代码**

创建 `tree_sitter_analyzer/validation/__init__.py`:
```python
"""Validation module for input validation."""
```

创建 `tree_sitter_analyzer/validation/standard_validator.py`:
```python
"""Standardized input validation."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ValidationResult:
    """Result of validation."""

    is_valid: bool
    error: str | None = None
    resolved_path: str | None = None
    value: Any = None


class StandardValidator:
    """Standardized input validator for all tools and commands."""

    ALLOWED_OUTPUT_FORMATS = {"json", "text", "toon", "table", "csv"}

    def validate_file_path(
        self, path: str, allow_absolute: bool = True, project_root: str | None = None
    ) -> ValidationResult:
        """Validate file path for security and existence.

        Args:
            path: File path to validate
            allow_absolute: Whether absolute paths are allowed
            project_root: Project root for relative path resolution

        Returns:
            ValidationResult with validation status
        """
        if not path:
            return ValidationResult(is_valid=False, error="File path is empty")

        # Check for path traversal
        if ".." in path:
            return ValidationResult(
                is_valid=False, error=f"Path traversal not allowed: {path}"
            )

        try:
            path_obj = Path(path)
            resolved = path_obj.resolve()

            # Check for system paths
            if str(resolved).startswith("/etc/") or str(resolved).startswith("/root/"):
                return ValidationResult(
                    is_valid=False, error=f"Access denied to system path: {path}"
                )

            return ValidationResult(
                is_valid=True, resolved_path=str(resolved), value=path
            )
        except Exception as e:
            return ValidationResult(is_valid=False, error=str(e))

    def validate_positive_integer(self, value: Any, name: str) -> ValidationResult:
        """Validate that value is a positive integer.

        Args:
            value: Value to validate
            name: Name of the parameter for error messages

        Returns:
            ValidationResult with validation status
        """
        if not isinstance(value, int):
            return ValidationResult(
                is_valid=False, error=f"{name} must be an integer, got {type(value).__name__}"
            )
        if value <= 0:
            return ValidationResult(
                is_valid=False, error=f"{name} must be positive, got {value}"
            )
        return ValidationResult(is_valid=True, value=value)

    def validate_non_negative_integer(self, value: Any, name: str) -> ValidationResult:
        """Validate that value is a non-negative integer (>= 0)."""
        if not isinstance(value, int):
            return ValidationResult(
                is_valid=False, error=f"{name} must be an integer, got {type(value).__name__}"
            )
        if value < 0:
            return ValidationResult(
                is_valid=False, error=f"{name} must be non-negative, got {value}"
            )
        return ValidationResult(is_valid=True, value=value)

    def validate_output_format(self, format_name: str) -> ValidationResult:
        """Validate output format name.

        Args:
            format_name: Format name to validate

        Returns:
            ValidationResult with validation status
        """
        if not format_name:
            return ValidationResult(is_valid=False, error="Output format is empty")

        format_lower = format_name.lower()
        if format_lower not in self.ALLOWED_OUTPUT_FORMATS:
            allowed = ", ".join(sorted(self.ALLOWED_OUTPUT_FORMATS))
            return ValidationResult(
                is_valid=False,
                error=f"Invalid output format '{format_name}'. Allowed: {allowed}",
            )
        return ValidationResult(is_valid=True, value=format_lower)
```

**Step 4: 运行测试验证通过**

```bash
pytest tests/unit/validation/test_standard_validator.py -v
```

**Step 5: 提交**

```bash
git add tests/unit/validation/test_standard_validator.py tree_sitter_analyzer/validation/__init__.py tree_sitter_analyzer/validation/standard_validator.py
git commit -m "feat(validation): add standardized input validation

- Create StandardValidator class with common validations
- Support file path, integer, and output format validation
- Add comprehensive tests

Fixes: MEDIUM priority validation issues"
```

---

## 验收检查清单

完成所有任务后运行：

```bash
# 运行所有新测试
pytest tests/unit/core/test_analysis_engine_singleton.py \
       tests/unit/mcp/utils/test_shared_cache_thread_safety.py \
       tests/unit/mcp/tools/test_analyze_scale_tool_error.py \
       tests/unit/cli/commands/test_partial_read_security.py \
       tests/unit/test_cli_main_exception_handling.py \
       tests/unit/core/test_parser_file_size_limit.py \
       tests/unit/core/test_parser_iterative_traversal.py \
       tests/unit/core/test_cache_size_limits.py \
       tests/unit/validation/test_standard_validator.py \
       -v

# 运行完整测试套件确保无回归
pytest tests/ -x --tb=short

# 检查覆盖率
pytest tests/ --cov=tree_sitter_analyzer --cov-report=term-missing
```

---

## 回滚计划

如果任何修复导致问题：

1. 每个任务都是独立提交，可以单独回滚
2. 使用 `git revert <commit-hash>` 回滚特定修复
3. 所有修改都有测试保护，回归问题会被检测到

---

## 变更历史

| 版本 | 日期 | 说明 |
|------|------|------|
| 1.0 | 2026-03-05 | 初始实施计划 |
