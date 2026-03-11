# 规格说明：Ruby current_module 死代码清理

## 问题描述

`RubyElementExtractor` 中的 `current_module` 字段是**死代码**：

```python
# __init__ 中声明
self.current_module: str = ""

# _reset_caches 中清空
self.current_module = ""
```

但在整个文件中，`current_module` 从未被**赋值**（除了初始化和清空），
也从未被**读取**用于任何业务逻辑（如构建类的全限定名）。

### 与其他插件的对比

| 插件 | 类似字段 | 是否被使用 |
|------|---------|---------|
| java_plugin | `current_package` | ✅ 被读取，用于构建包名 |
| cpp_plugin | `current_namespace` | ✅ 被读取，用于构建限定名 |
| kotlin_plugin | `current_package` | ✅ 被读取，用于构建包名 |
| **ruby_plugin** | `current_module` | ❌ 声明但从未使用 |

### 潜在来源

`current_module` 可能是为了将来实现"嵌套模块支持"而预留的占位符，
但从未实现，留下了误导性的死代码。

## 修复方案

1. 从 `__init__` 中删除 `self.current_module: str = ""`
2. 从 `_reset_caches()` 中删除 `self.current_module = ""`

```python
def __init__(self) -> None:
    """初始化提取器。"""
    self.source_code: str = ""
    self.content_lines: list[str] = []
    # current_module 已移除（从未使用的死代码）
    self._node_text_cache: dict[tuple[int, int], str] = {}
    ...

def _reset_caches(self) -> None:
    """清除性能缓存，不触碰业务状态。"""
    self._node_text_cache.clear()
    self._processed_nodes.clear()
    self._element_cache.clear()
    # current_module 已移除（从未使用的死代码）
```

## 验收标准

| ID | 条件 | 期望结果 |
|----|------|---------|
| AC-RB-001 | 检查 `RubyElementExtractor` 实例属性 | 无 `current_module` 属性 |
| AC-RB-002 | `_reset_caches()` 源码 | 不包含 `current_module` |
| AC-RB-003 | `extract_classes()` 正常调用 | 行为与之前完全一致 |
| AC-RB-004 | `_reset_caches()` 调用后 | 性能缓存被清除（不影响现有行为）|

## 范围外（不做）

- 实现 `current_module` 功能（嵌套模块支持）— 超出此次 bug 修复范围
