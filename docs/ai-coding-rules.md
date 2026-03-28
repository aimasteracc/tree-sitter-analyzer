# AI 编码规则 - 避免 CI 失败

## 🎯 目标

确保 AI 生成的代码符合项目质量标准，避免 CI 检查失败。

## 📋 必须遵守的规则

### 1. Ruff 规则 (Linting)

#### Import 规则
```python
# ✅ 正确：分组排序 (stdlib → third-party → local)
import hashlib
import json
from pathlib import Path

import pytest
from tree_sitter import Node

from tree_sitter_analyzer.core.parser import Parser
from tree_sitter_analyzer.utils import setup_logger

# ❌ 错误：顺序混乱
from tree_sitter_analyzer.core.parser import Parser
import json
import pytest
```

#### 未使用的 Import
```python
# ❌ 错误：导入但未使用
import pytest  # F401: imported but unused

# ✅ 正确：只导入实际使用的
import pytest  # 只在使用 @pytest.mark.xxx 或 pytest.fixture 时导入
```

#### f-string 规则
```python
# ❌ 错误：f-string 没有占位符
print(f"Test results:")  # F541

# ✅ 正确：移除 f 前缀
print("Test results:")
```

#### 异常处理规则
```python
# ❌ 错误：重抛异常不带 from
try:
    do_something()
except ValueError:
    raise RuntimeError("Failed")  # B904

# ✅ 正确：显式指定异常链
try:
    do_something()
except ValueError:
    raise RuntimeError("Failed") from None  # 或 from err
```

#### zip() 规则
```python
# ❌ 错误：缺少 strict 参数
for a, b in zip(list1, list2):  # B905
    pass

# ✅ 正确：显式指定 strict
for a, b in zip(list1, list2, strict=True):
    pass
```

#### 类型注解规则
```python
# ❌ 错误：使用已弃用的 typing.Dict
from typing import Dict
data: Dict[str, int] = {}  # UP006

# ✅ 正确：使用内置 dict
data: dict[str, int] = {}
```

### 2. MyPy 规则 (Type Checking)

#### 显式类型注解
```python
# ❌ 错误：字典没有类型注解
hashes = {}  # error: Need type annotation

# ✅ 正确：显式指定类型
hashes: dict[str, str | None] = {}
```

#### 可选类型处理
```python
# ❌ 错误：类型不匹配
self.git_commit = git_commit  # str
self.git_commit = None  # error: incompatible types

# ✅ 正确：显式声明可选类型
self.git_commit: str | None
if git_commit:
    self.git_commit = git_commit
else:
    self.git_commit = None
```

#### 返回类型明确化
```python
# ❌ 错误：返回 Any 类型
def call_tool(self, name: str) -> dict[str, Any]:
    return await self.tool.execute(args)  # error: Returning Any

# ✅ 正确：显式类型注解
def call_tool(self, name: str) -> dict[str, Any]:
    result: dict[str, Any] = await self.tool.execute(args)
    return result
```

#### 缓存返回值类型
```python
# ❌ 错误：从缓存返回 Any
if key in self.cache:
    return self.cache[key]  # error: Returning Any

# ✅ 正确：显式类型注解
if key in self.cache:
    cached_value: bool = self.cache[key]
    return cached_value
```

### 3. Bandit 规则 (Security)

#### 敏感操作
```python
# ⚠️ 警告：使用 exec/eval
exec(code)  # 避免使用

# ✅ 正确：使用安全替代方案
ast.literal_eval(code)
```

#### 硬编码密钥
```python
# ❌ 错误：硬编码密钥
API_KEY = "sk-1234567890"  # B105

# ✅ 正确：使用环境变量
API_KEY = os.getenv("API_KEY")
```

## 🔧 本地检查工具

### 快速检查单个文件
```bash
# Ruff 检查 + 自动修复
uv run ruff check path/to/file.py --fix

# MyPy 检查（仅 tree_sitter_analyzer/）
uv run mypy path/to/file.py --strict
```

### 完整 CI 检查（推送前）
```bash
# 运行完整检查
.github/scripts/local-ci-check.sh

# 跳过测试（更快）
SKIP_TESTS=1 .github/scripts/local-ci-check.sh
```

### 设置 Git Pre-commit Hook
```bash
# 自动在每次提交前检查
ln -sf ../../.github/scripts/pre-commit-check.sh .git/hooks/pre-commit
```

## 📝 AI 代码编写检查清单

每次写代码后，必须检查：

- [ ] **Import 排序**: stdlib → third-party → local，同组内字母排序
- [ ] **无未使用的 Import**: 删除所有未使用的导入
- [ ] **类型注解完整**: 所有变量、参数、返回值都有明确类型
- [ ] **异常处理正确**: 重抛异常使用 `from None` 或 `from err`
- [ ] **无 f-string 浪费**: 没有占位符的字符串不使用 f-string
- [ ] **使用现代语法**: `dict` 而非 `Dict`，`list` 而非 `List`
- [ ] **zip() 有 strict**: 使用 `zip(a, b, strict=True)`

## 🚀 工作流

### 编写新代码时
1. 写完代码后立即运行 `uv run ruff check <file> --fix`
2. 如果是 `tree_sitter_analyzer/` 中的文件，运行 `uv run mypy <file> --strict`
3. 修复所有错误后再提交

### 提交前
1. 运行 `.github/scripts/local-ci-check.sh` 确保全部通过
2. 或者设置 pre-commit hook 自动检查

### 推送后
1. 检查 GitHub Actions 是否全部通过
2. 如果失败，本地复现错误并修复

## 📊 CI 检查流程

```
┌─────────────────────┐
│  编写/修改代码      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  本地 Ruff 检查     │ ← uv run ruff check . --fix
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  本地 MyPy 检查     │ ← uv run mypy tree_sitter_analyzer/
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  git commit         │ ← 触发 pre-commit hook (可选)
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  git push           │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  GitHub Actions CI  │ ← Ruff + MyPy + Bandit
└──────────┬──────────┘
           │
    ✅ 全部通过
```

## 🎓 学习资源

- **Ruff 规则**: https://docs.astral.sh/ruff/rules/
- **MyPy 文档**: https://mypy.readthedocs.io/
- **Bandit 规则**: https://bandit.readthedocs.io/en/latest/

## ⚡ 快捷命令

```bash
# 快速修复常见问题
alias ci-fix="uv run ruff check . --fix && uv run mypy tree_sitter_analyzer/"

# 完整 CI 检查
alias ci-check=".github/scripts/local-ci-check.sh"

# 检查单个文件
ci-file() { uv run ruff check "$1" --fix && uv run mypy "$1" --strict; }
```
