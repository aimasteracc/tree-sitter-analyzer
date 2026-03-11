# 规格说明：Kotlin _reset_caches 条件语句清理

## 问题描述

`KotlinElementExtractor._reset_caches()` 包含一个令人困惑的条件语句：

```python
def _reset_caches(self) -> None:
    self._node_text_cache.clear()
    # Keep current_package if already extracted?   ← 注释本身就表达了不确定
    if not self.source_code:       # ← 靠外部状态来决定是否清业务数据
        self.current_package = ""
```

### 为什么这样写是代码坏味道

1. 注释中带问号，表示原作者自己也不确定
2. 条件 `if not self.source_code` 依赖调用方顺序（source_code 必须先被设置）
3. 若将来有人传入空字符串 `""` 作为 source_code，条件反转，触发意外清空
4. `_reset_caches` 语义应该只清缓存，不应带业务逻辑判断

### 为什么直接删除条件是安全的

`extract_classes()` 在 `_reset_caches()` 之后**立即**调用 `_extract_package(tree.root_node)`，
无条件地重新填充 `current_package`。所以 `_reset_caches()` 是否清 `current_package` 完全不影响结果。

## 修复方案

删除 `_reset_caches()` 中的 `if not self.source_code: self.current_package = ""` 整段，
方法只清性能缓存：

```python
def _reset_caches(self) -> None:
    """清除性能缓存，不触碰业务状态。"""
    self._node_text_cache.clear()
```

## 验收标准

| ID | 条件 | 期望结果 |
|----|------|---------|
| AC-KT-001 | 调用 `_reset_caches()`，`source_code` 为空 | `current_package` 不被清除 |
| AC-KT-002 | 调用 `_reset_caches()`，`source_code` 有值 | `current_package` 不被清除 |
| AC-KT-003 | 调用 `extract_classes()` | 类的 `package_name` 正确 |
| AC-KT-004 | 调用 `_reset_caches()` | `_node_text_cache` 被清除 |
