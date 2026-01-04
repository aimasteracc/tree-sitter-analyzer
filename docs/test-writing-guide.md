# 测试编写指南

本文档为tree-sitter-analyzer项目提供全面的测试编写指南，帮助开发者编写高质量、可维护的测试用例。

## 📋 目录

- [测试结构](#测试结构)
- [测试最佳实践](#测试最佳实践)
- [测试示例](#测试示例)
- [常见问题解答](#常见问题解答)
- [工具和资源](#工具和资源)

---

## 测试结构

### 基本测试结构

所有测试应遵循 **Arrange-Act-Assert (AAA)** 模式：

```python
def test_example():
    """测试示例功能的描述。"""
    # Arrange (准备): 设置测试数据和依赖
    input_data = create_test_data()
    expected_result = calculate_expected(input_data)

    # Act (执行): 调用被测试的函数
    actual_result = function_under_test(input_data)

    # Assert (断言): 验证结果
    assert actual_result == expected_result
```

### 测试文件组织

```
tests/
├── unit/              # 单元测试
│   ├── core/         # 核心模块测试
│   ├── mcp/          # MCP工具测试
│   ├── cli/          # CLI命令测试
│   └── languages/     # 语言插件测试
├── integration/        # 集成测试
├── regression/         # 回归测试
├── compatibility/      # 兼容性测试
├── property/          # 属性测试
├── benchmarks/        # 性能基准测试
└── fixtures/          # 测试数据和辅助工具
```

### 测试命名约定

- **文件名**: `test_<module_name>.py`
- **测试类**: `Test<ClassName>`
- **测试函数**: `test_<function_name>_<scenario>`

示例：
```python
# 文件: tests/unit/core/test_performance.py

class TestPerformanceMonitor:
    def test_start_monitoring(self):
        """测试开始监控功能。"""
        pass

    def test_stop_monitoring_with_active_session(self):
        """测试在活动会话时停止监控。"""
        pass
```

---

## 测试最佳实践

### 1. 使用清晰的docstring

所有测试函数必须有Google格式的docstring：

```python
def test_analyze_python_file_success():
    """测试成功分析Python文件。

    应该正确识别所有类、方法和函数。

    Args:
        None

    Returns:
        None

    Raises:
        AssertionError: 如果分析结果不符合预期
    """
    # 测试代码
```

### 2. 适当的测试隔离

每个测试应该是独立的，不依赖于其他测试的执行顺序：

```python
@pytest.fixture
def fresh_test_file(tmp_path):
    """创建一个新的测试文件。"""
    test_file = tmp_path / "test.py"
    test_file.write_text("def foo(): pass")
    return test_file

def test_isolated_test_1(fresh_test_file):
    """第一个独立测试。"""
    # 使用fresh_test_file，不依赖其他测试
    pass

def test_isolated_test_2(fresh_test_file):
    """第二个独立测试。"""
    # 使用新的fresh_test_file实例
    pass
```

### 3. 使用fixtures

使用pytest fixtures来管理测试数据和设置：

```python
# conftest.py
@pytest.fixture
def sample_python_code():
    """提供示例Python代码。"""
    return """
def hello():
    print("Hello, World!")

class MyClass:
    def method(self):
        return 42
"""

@pytest.fixture
def temp_test_file(tmp_path, sample_python_code):
    """创建临时测试文件。"""
    test_file = tmp_path / "sample.py"
    test_file.write_text(sample_python_code)
    return test_file

# 测试文件
def test_with_fixtures(temp_test_file):
    """使用fixtures的测试。"""
    result = analyze_file(temp_test_file)
    assert result is not None
```

### 4. 使用参数化测试

使用`@pytest.mark.parametrize`来测试多个场景：

```python
@pytest.mark.parametrize("language,extension", [
    ("python", ".py"),
    ("java", ".java"),
    ("javascript", ".js"),
    ("typescript", ".ts"),
])
def test_language_detection(language, extension):
    """测试不同语言的文件扩展名检测。"""
    file_path = Path(f"test{extension}")
    detected = detect_language(file_path)
    assert detected == language
```

### 5. 异常测试

使用`pytest.raises`来测试异常情况：

```python
def test_file_not_found_error():
    """测试文件不存在时的错误处理。"""
    non_existent_file = Path("/non/existent/path.py")

    with pytest.raises(FileNotFoundError):
        analyze_file(non_existent_file)

def test_unsupported_language_error():
    """测试不支持的语言错误。"""
    with pytest.raises(LanguageNotSupportedError) as exc_info:
        analyze_file(Path("test.xyz"))

    assert "xyz" in str(exc_info.value)
```

### 6. 异步测试

对于异步函数，使用`@pytest.mark.asyncio`：

```python
@pytest.mark.asyncio
async def test_async_analysis():
    """测试异步分析功能。"""
    result = await analyze_file_async(Path("test.py"))
    assert result is not None
```

### 7. Mock和Patch

使用`unittest.mock`来模拟外部依赖：

```python
from unittest.mock import patch, AsyncMock

def test_with_mock():
    """使用mock的测试。"""
    with patch('tree_sitter_analyzer.core.load_parser') as mock_load:
        mock_load.return_value = mock_parser

        result = analyze_file(Path("test.py"))

        mock_load.assert_called_once()
        assert result is not None

@pytest.mark.asyncio
async def test_with_async_mock():
    """使用async mock的测试。"""
    with patch('tree_sitter_analyzer.core.async_load_parser') as mock_load:
        mock_load.return_value = AsyncMock()

        result = await analyze_file_async(Path("test.py"))

        mock_load.assert_awaited_once()
```

### 8. 使用测试工厂

使用`tests/fixtures/factories.py`中的工厂函数创建测试数据：

```python
from tests.fixtures.factories import (
    CodeElementFactory,
    AnalysisResultFactory,
    QueryResultFactory,
)

def test_with_factory():
    """使用测试工厂的测试。"""
    # 创建测试元素
    test_class = CodeElementFactory.create_class(name="TestClass")
    test_method = CodeElementFactory.create_method(name="testMethod")

    # 创建测试结果
    result = AnalysisResultFactory.create(
        elements=[test_class, test_method],
        metadata={"language": "python"}
    )

    assert len(result["elements"]) == 2
    assert result["metadata"]["language"] == "python"
```

---

## 测试示例

### 单元测试示例

```python
"""测试性能监控模块。"""

import pytest
from tree_sitter_analyzer.core.performance import PerformanceMonitor

class TestPerformanceMonitor:
    """PerformanceMonitor类的测试套件。"""

    def test_initialization(self):
        """测试PerformanceMonitor初始化。"""
        monitor = PerformanceMonitor()
        assert monitor is not None
        assert len(monitor.metrics) == 0

    def test_start_and_stop_monitoring(self):
        """测试开始和停止监控。"""
        monitor = PerformanceMonitor()

        # 开始监控
        monitor.start_monitoring("test_operation")
        assert "test_operation" in monitor.metrics

        # 停止监控
        monitor.stop_monitoring("test_operation")
        assert monitor.metrics["test_operation"]["duration"] > 0

    @pytest.mark.parametrize("iterations", [1, 10, 100])
    def test_multiple_operations(self, iterations):
        """测试多次操作的性能监控。"""
        monitor = PerformanceMonitor()

        for i in range(iterations):
            monitor.start_monitoring(f"operation_{i}")
            monitor.stop_monitoring(f"operation_{i}")

        assert len(monitor.metrics) == iterations
```

### 集成测试示例

```python
"""测试MCP工具集成。"""

import pytest
from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool,
)

class TestAnalyzeCodeStructureIntegration:
    """AnalyzeCodeStructureTool集成测试。"""

    @pytest.mark.asyncio
    async def test_full_analysis_workflow(self, temp_test_file):
        """测试完整的分析工作流。"""
        tool = AnalyzeCodeStructureTool()

        # 执行分析
        result = await tool.execute({
            "file_path": str(temp_test_file),
            "format_type": "full",
        })

        # 验证结果
        assert result["success"] is True
        assert "elements" in result
        assert len(result["elements"]) > 0
```

### 回归测试示例

```python
"""测试格式输出回归。"""

import pytest
from pathlib import Path

class TestFormatRegression:
    """格式输出回归测试。"""

    @pytest.mark.regression
    def test_python_format_stability(self, sample_python_file):
        """测试Python格式输出的稳定性。"""
        # 执行分析
        result = analyze_code_structure(
            sample_python_file,
            format_type="full"
        )

        # 加载Golden Master
        golden_master_path = Path(
            "tests/golden_masters/python_sample_full.txt"
        )
        with open(golden_master_path, 'r') as f:
            expected_output = f.read()

        # 验证一致性
        assert result == expected_output, (
            f"Format output changed. "
            f"Run: uv run pytest tests/regression/test_format_regression.py "
            f"--update-golden-masters"
        )
```

### 属性测试示例

```python
"""测试语言检测属性。"""

import pytest
from hypothesis import given, strategies as st
from tree_sitter_analyzer.core.language_detection import detect_language

class TestLanguageDetectionProperties:
    """语言检测属性测试。"""

    @given(st.text(min_size=1, max_size=100))
    def test_language_detection_never_fails(self, code):
        """语言检测永远不会失败。"""
        file_path = Path("test.py")
        result = detect_language(file_path, code)
        assert result is not None

    @given(st.lists(st.sampled_from(["python", "java", "javascript"]), min_size=1))
    def test_language_detection_consistency(self, languages):
        """语言检测在多次调用中保持一致。"""
        file_path = Path("test.py")
        code = "def foo(): pass"

        results = [detect_language(file_path, code) for _ in range(10)]
        assert all(r == results[0] for r in results)
```

### 性能基准测试示例

```python
"""测试分析性能基准。"""

import pytest

class TestPythonAnalysisBenchmarks:
    """Python分析性能基准测试。"""

    def test_small_file_analysis(self, benchmark, small_python_file):
        """测试小文件分析性能。"""
        result = benchmark(analyze_file, small_python_file)
        assert result is not None

    def test_large_file_analysis(self, benchmark, large_python_file):
        """测试大文件分析性能。"""
        result = benchmark(analyze_file, large_python_file)
        assert result is not None

    @pytest.mark.parametrize("file_size", [100, 1000, 10000])
    def test_scaling_performance(self, benchmark, file_size):
        """测试不同文件大小的性能扩展。"""
        code = "def foo(): pass\n" * file_size
        test_file = Path("test.py")
        test_file.write_text(code)

        result = benchmark(analyze_file, test_file)
        assert result is not None
```

---

## 常见问题解答

### Q1: 如何测试私有方法？

**A:** 通常不建议直接测试私有方法（以`_`开头）。应该通过公共API测试它们的行为。如果必须测试，可以使用`patch`：

```python
def test_private_method_via_public_api():
    """通过公共API测试私有方法。"""
    with patch('module._private_method') as mock_private:
        mock_private.return_value = expected_value

        result = module.public_method()

        mock_private.assert_called_once()
        assert result == expected_value
```

### Q2: 如何处理外部依赖？

**A:** 使用mock来隔离外部依赖：

```python
from unittest.mock import patch

def test_with_external_dependency():
    """测试外部依赖隔离。"""
    with patch('module.external_service.call') as mock_call:
        mock_call.return_value = {"status": "success"}

        result = module.function_using_external_service()

        mock_call.assert_called_once()
        assert result["status"] == "success"
```

### Q3: 如何测试文件系统操作？

**A:** 使用`tmp_path` fixture进行临时文件操作：

```python
def test_file_operations(tmp_path):
    """测试文件系统操作。"""
    test_file = tmp_path / "test.txt"
    test_file.write_text("content")

    result = process_file(test_file)

    assert test_file.exists()
    assert result == "processed"
```

### Q4: 如何测试异步代码？

**A:** 使用`@pytest.mark.asyncio`标记和`async def`：

```python
@pytest.mark.asyncio
async def test_async_function():
    """测试异步函数。"""
    result = await async_function()
    assert result is not None
```

### Q5: 如何处理测试数据？

**A:** 使用fixtures和测试工厂：

```python
# 使用fixture
@pytest.fixture
def test_data():
    return {"key": "value"}

# 使用工厂
from tests.fixtures.factories import CodeElementFactory

test_element = CodeElementFactory.create_class(name="TestClass")
```

---

## 工具和资源

### pytest插件

- **pytest-asyncio**: 异步测试支持
- **pytest-benchmark**: 性能基准测试
- **pytest-cov**: 代码覆盖率
- **pytest-timeout**: 测试超时控制
- **pytest-mock**: Mock和patch支持

### 测试库

- **hypothesis**: 基于属性的测试
- **unittest.mock**: Mock和patch
- **pytest fixtures**: 测试数据管理

### 命令

```bash
# 运行所有测试
uv run pytest tests/

# 运行特定测试文件
uv run pytest tests/unit/core/test_performance.py

# 运行特定测试
uv run pytest tests/unit/core/test_performance.py::TestPerformanceMonitor::test_initialization

# 运行带覆盖率的测试
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=term-missing

# 运行回归测试
uv run pytest tests/ -m regression

# 运行基准测试
uv run pytest tests/benchmarks/ --benchmark-only

# 运行属性测试
uv run pytest tests/property/

# 查看测试覆盖率
uv run pytest --cov=tree_sitter_analyzer --cov-report=html
open htmlcov/index.html
```

### 质量检查

```bash
# 运行代码格式化
uv run black tests/

# 运行linter
uv run ruff check tests/

# 运行类型检查
uv run mypy tests/

# 运行安全检查
uv run bandit -r tests/
```

---

## 测试覆盖率目标

- **单元测试**: > 80%
- **集成测试**: > 70%
- **回归测试**: 100% (所有关键路径)
- **总体覆盖率**: > 75%

---

## 贡献指南

1. **编写测试**: 遵循本指南编写新测试
2. **运行测试**: 确保所有测试通过
3. **检查覆盖率**: 确保覆盖率不下降
4. **代码审查**: 提交PR进行代码审查
5. **持续改进**: 根据反馈改进测试

---

## 参考资料

- [pytest文档](https://docs.pytest.org/)
- [hypothesis文档](https://hypothesis.readthedocs.io/)
- [unittest.mock文档](https://docs.python.org/3/library/unittest.mock.html)
- [项目测试规范](../TESTING.md)
- [回归测试指南](./regression-testing-guide.md)
