# V2 Development Guide - 完整开发指南

## Quick Start

```bash
# 1. 进入 v2 目录
cd D:/git/tree-sitter-analyzer-v2

# 2. 安装依赖
uv sync

# 3. 运行测试
uv run pytest v2/tests/ -v

# 4. 开始开发
#    使用 TDD 工作流
python scripts/v2_tdd_workflow.py --help
```

## Project Structure

```
v2/
├── tree_sitter_analyzer_v2/     # 核心代码
│   ├── api/                      # API 接口
│   ├── cli/                      # CLI 命令
│   ├── core/                     # 核心模块
│   │   ├── detector.py          # 项目检测
│   │   ├── parser.py            # 解析器
│   │   ├── types.py             # 类型定义
│   │   └── exceptions.py        # 异常类
│   ├── formatters/              # 格式化器
│   ├── languages/               # 语言支持
│   ├── mcp/                     # MCP 协议
│   ├── graph/                   # 图分析
│   ├── search.py                # 搜索功能
│   └── security/                # 安全模块
├── tests/                       # 测试
│   ├── unit/                    # 单元测试
│   ├── integration/             # 集成测试
│   └── fixtures/                # 测试数据
├── scripts/                     # 工具脚本
└── pyproject.toml              # 项目配置
```

## TDD Development Workflow

### 方法 1：使用脚本

```bash
# 运行完整 TDD 循环
python scripts/v2_tdd_workflow.py --module core --tdd

# Critic 模式
python scripts/v2_tdd_workflow.py --role critic --task "review token optimizer"

# Worker 模式
python scripts/v2_tdd_workflow.py --role worker --task "implement token optimizer"
```

### 方法 2：手动 TDD 循环

```bash
# 1. 写测试（Red）
uv run pytest v2/tests/unit/test_new_feature.py -v  # 失败

# 2. 实现代码（Green）
#    编辑 tree_sitter_analyzer_v2/core/new_feature.py

# 3. 测试通过（Green）
uv run pytest v2/tests/unit/test_new_feature.py -v  # 通过

# 4. 重构（Refactor）
uv run mypy v2/tree_sitter_analyzer_v2/core/new_feature.py
uv run ruff check v2/tree_sitter_analyzer_v2/core/new_feature.py
uv run ruff format v2/tree_sitter_analyzer_v2/core/new_feature.py

# 5. 完整测试
uv run pytest v2/tests/ -v
```

## Coding Standards

### 必须遵循的标准

1. **类型注解** - 所有函数必须有类型注解
2. **文档字符串** - 所有公共方法必须有文档
3. **异常类** - 每个模块必须有 3 个异常类
4. **性能监控** - 每个模块必须有性能统计
5. **测试覆盖** - 核心模块 > 80% 覆盖

### 代码模板

```python
"""Brief description.

Detailed description.

Features:
    - Feature 1
    - Feature 2

Architecture:
    - Component 1: Purpose

Usage:
    Example code

Performance Characteristics:
    - Time: O(n)
    - Space: O(1)

Thread Safety:
    - Thread-safe: Yes/No

Dependencies:
    - External: list
    - Internal: list

Error Handling:
    - 3 custom exceptions

Note:
    Important notes

Example:
    ```python
    example()
    ```
"""


class FeatureBaseException(Exception):
    """Base exception."""
    pass


class InvalidInputError(FeatureBaseException):
    """Invalid input error."""
    pass


class ProcessingError(FeatureBaseException):
    """Processing error."""
    pass


class Feature:
    """Feature class.
    
    Attributes:
        attr: Description
    """
    
    __all__ = [
        'Feature',
        'FeatureBaseException',
        'InvalidInputError',
        'ProcessingError'
    ]
    
    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize.
        
        Args:
            config: Configuration dict
        """
        self._config = config
        self._stats = {
            'total_calls': 0,
            'total_time': 0.0,
            'errors': 0
        }
    
    def process(self, input_data: str) -> dict[str, Any]:
        """Process input data.
        
        Args:
            input_data: Input string
            
        Returns:
            dict[str, Any]: Processing result
        """
        start = perf_counter()
        try:
            self._stats['total_calls'] += 1
            # Implementation
            result = {'status': 'success', 'data': input_data}
            return result
        except Exception as e:
            self._stats['errors'] += 1
            raise InvalidInputError(f"Processing failed: {e}") from e
        finally:
            self._stats['total_time'] += perf_counter() - start
    
    def get_statistics(self) -> dict[str, Any]:
        """Get statistics.
        
        Args:
            None (instance method with no parameters)
            
        Returns:
            dict[str, Any]: Statistics with derived metrics
        """
        total = max(1, self._stats['total_calls'])
        return {
            **self._stats,
            'avg_time': self._stats['total_time'] / total
        }
```

## Testing

### 测试命名

```python
# 文件命名
tests/unit/test_<module>.py
tests/integration/test_<feature>.py

# 测试函数命名
test_<feature>_<scenario>_<expected_result>

# 示例
def test_token_optimizer_remove_python_comments_success():
    ...

def test_token_optimizer_empty_file_returns_empty():
    ...

def test_token_optimizer_large_file_performance():
    ...
```

### 测试示例

```python
import pytest
from tree_sitter_analyzer_v2.core.token_optimizer import (
    TokenOptimizer,
    TokenOptimizerBaseException,
    InvalidInputError,
    ProcessingError
)


class TestTokenOptimizer:
    """Test TokenOptimizer class."""
    
    def setup_method(self) -> None:
        """Setup test fixtures."""
        self.optimizer = TokenOptimizer()
    
    def test_remove_python_comments_success(self) -> None:
        """Test removing Python comments successfully."""
        input_code = '''
def hello():
    # 这是一个注释
    print("hello")
'''
        result = self.optimizer.remove_comments(input_code, "python")
        assert "# 这是一个注释" not in result
        assert 'print("hello")' in result
    
    def test_empty_file_returns_empty(self) -> None:
        """Test empty file returns empty string."""
        result = self.optimizer.remove_comments("", "python")
        assert result == ""
    
    def test_invalid_language_raises_error(self) -> None:
        """Test invalid language raises InvalidInputError."""
        with pytest.raises(InvalidInputError):
            self.optimizer.remove_comments("code", "invalid_lang")
```

## Quality Checks

### 运行所有检查

```bash
# Type check
uv run mypy v2/tree_sitter_analyzer_v2/

# Linter
uv run ruff check v2/tree_sitter_analyzer_v2/

# Formatter
uv run ruff format v2/tree_sitter_analyzer_v2/

# Tests
uv run pytest v2/tests/ -v --cov=v2/tree_sitter_analyzer_v2

# All checks
uv run pytest v2/tests/ -v && \
uv run mypy v2/ && \
uv run ruff check v2/
```

### Git Commit Hooks

```bash
# 安装 pre-commit hooks
uv run pre-commit install

# 手动运行
uv run pre-commit run --all-files
```

## Development Commands

### 常用命令速查

```bash
# 安装
uv sync

# 开发模式安装
uv sync --dev

# 添加依赖
uv add <package>
uv add --dev <package>

# 运行测试
uv run pytest v2/tests/ -v
uv run pytest v2/tests/unit/ -v
uv run pytest v2/tests/integration/ -v

# 运行单个测试
uv run pytest v2/tests/unit/test_core.py::TestCore::test_feature -v

# 运行并监控
uv run pytest v2/tests/ -v --cov=v2/ --cov-report=term-missing

# Type check
uv run mypy v2/

# Linter
uv run ruff check v2/

# Formatter check
uv run ruff format --check v2/

# 自动修复
uv run ruff check --fix v2/
uv run ruff format v2/

# 运行 CLI
uv run tree-sitter-analyzer-v2 --help
uv run tree-sitter-analyzer-v2 analyze <path>
```

## Adding New Module

### Step 1: 创建目录结构

```bash
mkdir -p v2/tree_sitter_analyzer_v2/new_module
mkdir -p v2/tests/unit/test_new_module
```

### Step 2: 创建模块文件

```python
# v2/tree_sitter_analyzer_v2/new_module/__init__.py
# v2/tree_sitter_analyzer_v2/new_module/new_feature.py
# v2/tree_sitter_analyzer_v2/new_module/exceptions.py
```

### Step 3: 创建测试文件

```python
# v2/tests/unit/test_new_module.py
```

### Step 4: 注册模块

```python
# 在 pyproject.toml 中添加
[tool.uv]
packages = [
    "v2/",
]
```

### Step 5: 运行 TDD 循环

```bash
python scripts/v2_tdd_workflow.py --module new_module --tdd
```

## Synchronization with V1

### 同步流程

```bash
# 1. 在 v1 目录更新
cd D:/git/tree-sitter-analyzer
git fetch origin
git pull origin main

# 2. 在 v2 目录同步
cd D:/git/tree-sitter-analyzer-v2
git fetch origin
git pull origin feature/v2-rewrite

# 3. 检查需要移植的改动
#    - Bug fixes
#    - 新功能
#    - 性能改进
```

### 移植指南

```
移植原则：

1. Bug fixes - 必须移植
2. 安全修复 - 必须移植
3. 新功能 - 选择性移植
4. 重构 - 重写，不要移植
```

## Troubleshooting

### 常见问题

1. **测试失败**
   ```bash
   # 查看详细输出
   uv run pytest v2/tests/ -v --tb=long
   
   # 查看覆盖率
   uv run pytest v2/tests/ --cov=v2/ --cov-report=html
   # 打开 htmlcov/index.html
   ```

2. **Type check 失败**
   ```bash
   # 查看详细错误
   uv run mypy v2/ --show-error-codes
   ```

3. **Import 错误**
   ```bash
   # 重新安装依赖
   uv sync --no-dev
   uv sync
   ```

4. **缓存问题**
   ```bash
   # 清除缓存
   uv run pytest --cache-clear
   rm -rf .pytest_cache
   rm -rf .mypy_cache
   ```

## Resources

- [Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [TDD](https://testdriven.io/test-driven-development/)
- [Python Type Hints](https://docs.python.org/3/library/typing.html)
- [pytest](https://docs.pytest.org/)
- [Ruff](https://docs.astral.sh/ruff/)
- [Mypy](https://mypy-lang.org/)
