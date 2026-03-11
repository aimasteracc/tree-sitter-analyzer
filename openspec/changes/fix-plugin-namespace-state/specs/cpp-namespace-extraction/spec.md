# 规格说明：C++ 命名空间状态修复

## 问题描述

`CppElementExtractor.extract_classes()` 提取的类，当类定义在命名空间内时，
`full_qualified_name` 前缀永远为空，`package_name` 永远是 `""`。

### 根本原因（追踪链路）

```
extract_elements()
  ├── extract_functions()  → _reset_caches() → current_namespace = ""
  ├── extract_classes()    → _reset_caches() → current_namespace = ""
  │                          ↑ 从不调用 _pre_extract_namespace()
  │                          ↓ _extract_class_optimized() 读 current_namespace → 永远是 ""
  ├── extract_variables()
  ├── extract_imports()
  └── extract_packages()   ← 到这里才调用 _extract_namespace_info() 设置 current_namespace（太晚了）
```

`_reset_caches()` 无条件地执行 `self.current_namespace = ""`，而 `extract_classes()` 调用
`_reset_caches()` 之后**不重新扫描命名空间**，就直接开始提取类。结果所有类的限定名都缺失命名空间前缀。

### 具体示例

```cpp
namespace MyApp {
    class UserService {};
}
```

修复前：
- `class.full_qualified_name == "UserService"`     ← 错误
- `class.package_name == ""`                        ← 错误

修复后：
- `class.full_qualified_name == "MyApp::UserService"` ← 正确
- `class.package_name == "MyApp"`                     ← 正确

## 修复方案

在 `CppElementExtractor` 添加私有方法 `_pre_extract_namespace(root_node)`，
遍历根节点子节点找到 `namespace_definition`，调用已有的 `_extract_namespace_info()`
设置 `self.current_namespace`。

在 `extract_classes()` 调用 `_reset_caches()` 之后、提取循环之前，调用此方法。

```python
def extract_classes(self, tree, source_code):
    self.source_code = source_code
    self.content_lines = source_code.split("\n")
    self._reset_caches()
    self._pre_extract_namespace(tree.root_node)  # ← 新增：先扫命名空间
    # ... 其余不变
```

## 验收标准

| ID | 条件 | 期望结果 |
|----|------|---------|
| AC-CPP-001 | 类在命名空间内 | `full_qualified_name == "NS::ClassName"` |
| AC-CPP-002 | 类在命名空间内 | `package_name == "NS"` |
| AC-CPP-003 | 类不在命名空间内 | `full_qualified_name == "ClassName"`（无多余 `::` 前缀）|
| AC-CPP-004 | 调用 `_reset_caches()` | 性能缓存被清除（`_node_text_cache` 等）|
| AC-CPP-005 | 连续分析两个不同文件 | 每次使用各自文件的命名空间 |

## 范围外（不做）

- 嵌套命名空间（`namespace A::B`）—— 保持现有行为
- 匿名命名空间 —— 保持现有行为
