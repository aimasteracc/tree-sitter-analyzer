# tree-sitter-analyzer — Claude Code 项目规范

> 此文件由 Claude Code 自动加载，记录项目规范、架构知识和踩坑经验。
> 换电脑后 `git pull` 即可恢复所有上下文。

---

## 项目强制规范（每次必须遵守）

1. **Spec/文档**：使用汉语（代码格式/技术术语用英文）
2. **代码**：英文书写；注释用汉语；log 用英文
3. **代码质量**：遵守编码基准（immutable、小函数、小文件、错误处理）
4. **测试**：遵守测试框架分层（unit/integration），无重复无效测试，≥90% 覆盖率
5. **提交前**：必须保证 CI/CD 通过（`uv run pytest -q` + `uv run ruff check` 全绿）

---

## 项目概况

- 企业级代码分析工具，v1.10.4，17 个语言插件
- Python、MCP 协议、CLI、Python API
- ~8000+ 测试，目标覆盖率 80%+

---

## 测试架构

### 目录结构

```
tests/
  unit/
    languages/       # 仅 Mock 节点 — 禁止真实解析器、tempfile、asyncio
    core/            # Mock-based 核心服务测试
    formatters/      # Formatter 单元测试
  integration/
    languages/       # 真实 tree-sitter + tempfile + asyncio.analyze_file
  property/          # Hypothesis 属性测试
```

### Unit vs Integration 边界

| 类型 | 规则 |
|------|------|
| **unit** | 只用 `MagicMock` 节点，禁止 `import tree_sitter_xxx`、`tempfile`、`asyncio.run(plugin.analyze_file(...))` |
| **integration** | 真实 tree-sitter 解析，真实 tempfile，真实 `asyncio.run(plugin.analyze_file(...))` |

---

## CI/CD 前置检查（提交前必须执行）

```bash
# 1. Ruff lint（新建文件必须先跑）
uv run ruff check <文件路径> --fix

# 2. 完整测试
uv run pytest tests/unit/ tests/integration/ -q --override-ini="addopts="
```

### 常见 Ruff 错误（已踩坑）

| 错误码 | 原因 | 预防方法 |
|--------|------|---------|
| `F401` | `import pytest` 未使用（纯 class-based 测试不需要显式 import） | 写完后检查所有 import 是否真正被用到 |
| `I001` | import 排序不规范 | 运行 `ruff check --fix` 自动修复 |

### 正确的测试文件 import 顺序

```python
# 1. stdlib
import inspect

# 2. third-party（按字母排序，pytest 只在真正用到时才 import）
import tree_sitter
import tree_sitter_cpp

# 3. local
from tree_sitter_analyzer.languages.cpp_plugin import CppPlugin
```

---

## 语言插件架构

### 正确模式（参考 Go/Rust/Java）

```python
# extract_elements() 正确写法：
extractor = self.create_extractor()          # 每次新建，保证隔离
# 1. 先提取"前置状态"（命名空间/包名/注解）
annotations = extractor.extract_annotations(tree, source_code)
packages    = extractor.extract_packages(tree, source_code)
# 2. 再提取依赖前置状态的元素
functions   = extractor.extract_functions(tree, source_code)
classes     = extractor.extract_classes(tree, source_code)
# 3. 同步语言特有状态回 self.extractor（对外 API 一致）
self.extractor.annotations    = extractor.annotations
self.extractor.current_package = extractor.current_package
```

### `_reset_caches()` 职责边界

**只能清性能缓存，不能碰业务状态：**

```python
def _reset_caches(self) -> None:
    """清除性能缓存，不触碰业务状态。"""
    self._node_text_cache.clear()       # ✅ 性能缓存
    self._processed_nodes.clear()      # ✅ 性能缓存
    # self.current_namespace = ""      # ❌ 业务状态，不能在这里清
    # self.annotations.clear()         # ❌ 业务状态，不能在这里清
```

### 各插件风险矩阵（2026-03-11 更新）

| Plugin | `_reset_caches` 状态 | 修复状态 |
|--------|---------------------|---------|
| java_plugin | ✅ 已修复 | PR #99 |
| cpp_plugin | ✅ 已修复（添加 `_pre_extract_namespace`） | PR #99 |
| kotlin_plugin | ✅ 已修复（删除 source_code 条件） | PR #99 |
| php_plugin | ✅ 已修复（`extract_functions` 独立扫命名空间） | PR #99 |
| csharp_plugin | 🔴 `current_namespace` 仍在 `_reset_caches` 中清除 | 待修复 |
| ruby_plugin | 🟡 `current_module` 仍在 `_reset_caches` 中清除 | 待修复 |
| go_plugin | ✅ 参考实现 | — |
| rust_plugin | ✅ 参考实现 | — |
| c/css/html/sql/yaml/python/typescript | ✅ 无问题 | — |

---

## Mock 节点常用模板

```python
from unittest.mock import MagicMock

# 构造 tree-sitter 节点
node = MagicMock()
node.start_point = (line_idx, col)
node.start_byte = 0
node.end_byte = len("text")
node.type = "function_declaration"
node.children = []

# 预填充文本缓存（避免真实字节提取）
extractor._node_text_cache[(0, len("text"))] = "text"
```

---

## 测试命令速查

```bash
uv run pytest tests/unit/ -q                              # 仅单元测试
uv run pytest tests/integration/ -q                      # 仅集成测试
uv run pytest tests/unit/languages/test_java_plugin.py -v # 单个文件
uv run ruff check tree_sitter_analyzer/ tests/ --fix      # lint + 自动修复
uv run python scripts/audit_test_governance.py            # 治理审计
```

---

## 预存失败（不用修复）

以下测试在所有环境均失败，是已知问题，不影响开发：

- `tests/unit/mcp/test_utils/test_file_output_manager.py::test_set_output_path_not_exists`
- `tests/unit/mcp/test_utils/test_gitignore_detector.py::test_nonexistent_project_root`
- `tests/unit/test_boundary_manager.py::TestBoundaryManagerInitialization::test_nonexistent_project_root`
- `tests/unit/test_boundary_manager.py::TestAddAllowedDirectory::test_add_nonexistent_directory`
- `tests/integration/mcp/test_mcp_performance.py::test_list_files_performance`（xdist 负载下偶发）

---

## Locale 敏感模式

`output_format_validator.py._get_error_message()` 根据 `_detect_language()` 返回日文或英文。
测试断言应匹配参数名（`total_only`、`group_by_file`），而非英文语句。
