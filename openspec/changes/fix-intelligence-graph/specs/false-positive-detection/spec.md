# 规格说明：Intelligence Graph 误报修复

## 问题描述

Code Intelligence Graph 的架构分析（`ArchitectureMetrics`）存在两类误报，
导致分析结果不可信，健康分被错误压低。

---

## 误报 1：懒加载 import 被误判为循环依赖

### 根本原因

`project_indexer.py` 的 `_walk_for_imports()` 已能识别 `if TYPE_CHECKING:` 块，
但**无法识别函数/方法体内的懒加载 import**。这些 import 在运行时不会形成
模块级循环依赖，因为它们只在函数调用时才执行。

### 示例

```python
# tree_sitter_analyzer/core/analysis_engine.py
def _ensure_initialized(self) -> None:
    from ..language_detector import LanguageDetector   # ← 方法内 import，非循环依赖
    from ..plugins.manager import PluginManager         # ← 方法内 import，非循环依赖
```

### 修复方案

1. 在 `DependencyEdge`（`models.py`）中新增 `is_lazy_import: bool = False` 字段
2. `_walk_for_imports()` 新增 `is_inside_function: bool = False` 参数，
   进入 `function_definition` / `async_function_definition` 节点时置 `True`
3. `_add_import_edge()` 将 `is_lazy_import` 传入 `DependencyEdge`
4. `architecture_metrics.py` 的 `_detect_cycles()` 中，
   在已有 `not edge.is_type_check_only` 条件旁增加 `not edge.is_lazy_import`

---

## 误报 2：isinstance() 参数不被计为符号引用（死代码误报）

### 根本原因

`_detect_dead_symbols()` 依赖 `SymbolIndex` 的引用记录。
`isinstance(exception, MCPToolError)` 中的 `MCPToolError` 是一个标识符参数，
既不是函数调用（CallGraphBuilder 只记录被调函数名），
也不是属性访问（`_walk_for_attribute_refs` 只处理 `attribute` 节点），
因此不会被记录为引用——导致 `MCPToolError` 被误判为死代码。

### 示例

```python
# tree_sitter_analyzer/exceptions.py
class MCPToolError(Exception): ...      # 定义

# 被引用处（create_mcp_error_response 函数）
if isinstance(exception, MCPToolError):  # MCPToolError 此处未被计为引用
    ...
```

### 修复方案

在 `project_indexer.py` 中新增 `_extract_isinstance_refs()` 方法，
走读 AST 查找以下模式并注册类名引用：
- `isinstance(x, ClassName)` 中的 `ClassName`
- `issubclass(cls, ClassName)` 中的 `ClassName`
- `raise ClassName(...)` 仅作为调用已被 CallGraph 覆盖，无需额外处理

在 `_index_single_file()` 中调用此方法（与 `_extract_attribute_refs` 并列）。

---

## 验收标准

| ID | 条件 | 期望结果 |
|----|------|----------|
| AC-FP-001 | 对含方法内懒加载 import 的代码运行循环依赖检测 | 不报告循环依赖 |
| AC-FP-002 | 对顶层真实循环依赖代码运行检测 | 仍正确报告循环依赖 |
| AC-FP-003 | `isinstance(x, SomeClass)` 中的 `SomeClass` | 出现在 SymbolIndex 引用记录中 |
| AC-FP-004 | `issubclass(cls, SomeClass)` 中的 `SomeClass` | 出现在 SymbolIndex 引用记录中 |
| AC-FP-005 | 只用 isinstance 引用的类 | 不出现在 dead_symbols 列表中 |
| AC-FP-006 | 确实未被任何方式引用的符号 | 仍出现在 dead_symbols 列表中 |
| AC-FP-007 | `DependencyEdge.is_lazy_import` | 顶层 import 为 False，方法内 import 为 True |

## 范围外（不做）

- `raise SomeException` 的单独引用检测（已被 CallGraph 覆盖）
- 泛型类型参数检测（`List[SomeClass]` 等）
