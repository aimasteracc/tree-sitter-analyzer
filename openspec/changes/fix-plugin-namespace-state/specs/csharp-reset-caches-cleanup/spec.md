# 规格说明：C# _reset_caches 职责清理

## 问题描述

`CSharpElementExtractor._reset_caches()` 包含 `self.current_namespace = ""`，
违反了"缓存清理方法只清缓存"的原则（代码异味）。

### 当前行为（无功能 bug）

`extract_classes()` 和 `extract_functions()` 在调用 `_reset_caches()` 后，
**立即调用** `_extract_namespace(tree.root_node)` 来重新填充 `current_namespace`，
因此实际输出是正确的。

### 为什么仍需修复

1. **误导维护者**：看到 `_reset_caches()` 包含业务状态重置，会误以为这是必要的
2. **设计不一致**：与 Java（已修复）、C++（已修复）的正确模式不一致
3. **脆弱性**：若将来有人添加新的 extract_* 方法，忘记调用 `_extract_namespace()`，会引入 bug

### 与已修复插件的对比

| 插件 | `_reset_caches` 中有 `current_*`？ | `extract_classes` 补救？ | 结果 |
|------|-----------------------------------|-----------------------|------|
| Java（修复后）| ❌ 没有 | N/A | ✅ 正确 |
| C++（修复后）| ✅ 有（保留，_pre_extract_namespace 补救）| ✅ 调用 `_pre_extract_namespace` | ✅ 正确 |
| **C#（待修复）**| ✅ 有（不必要）| ✅ 调用 `_extract_namespace`（补救） | ✅ 正确但有异味 |

## 修复方案

从 `_reset_caches()` 中删除 `self.current_namespace = ""`，
方法只清性能缓存：

```python
def _reset_caches(self) -> None:
    """清除性能缓存，不触碰业务状态。"""
    self._node_text_cache.clear()
    self._processed_nodes.clear()
    self._element_cache.clear()
    self._attribute_cache.clear()
    # current_namespace 由各 extract_* 方法按需调用 _extract_namespace() 填充
```

## 验收标准

| ID | 条件 | 期望结果 |
|----|------|---------|
| AC-CS-001 | 调用 `_reset_caches()` 后，`current_namespace` 之前有值 | 不被清除（去除异味） |
| AC-CS-002 | `_reset_caches()` 源码中无 `current_namespace` | 方法不包含该赋值 |
| AC-CS-003 | `extract_classes()` 在命名空间内的类 | `full_qualified_name` 包含命名空间（行为不变）|
| AC-CS-004 | `_reset_caches()` 调用后 | 性能缓存被清除（不影响现有行为）|
