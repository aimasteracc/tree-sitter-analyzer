# 规格说明：PHP 函数命名空间提取顺序依赖修复

## 问题描述

`PhpElementExtractor.extract_functions()` 单独调用时，提取的函数不带命名空间前缀，
因为函数提取依赖 `extract_classes()` 已被提前调用来设置 `current_namespace`。

### 根本原因

```
analyze_file()
  ├── extractor = create_extractor()          # current_namespace = ""
  ├── extract_classes(tree, content)          # _reset_caches() → _extract_namespace() → current_namespace = "App"
  └── extract_functions(tree, content)        # 直接用 current_namespace（侥幸有值）
      ↑ 没有调用 _reset_caches()，也没有调用 _extract_namespace()
      ↑ 若单独调用，current_namespace = "" → 函数名缺失命名空间
```

函数提取隐式依赖类提取先运行，是**脆弱的顺序耦合**——调换顺序即出 bug。

### 具体示例

```php
<?php
namespace App\Controllers;
function handleRequest() {}
```

修复前（`extract_functions()` 单独调用）：
- `function.name == "handleRequest"`              ← 错误（缺命名空间）

修复后：
- `function.name == "App\\Controllers\\handleRequest"` ← 正确

## 修复方案

在 `PhpElementExtractor.extract_functions()` 设置 `source_code` 之后，
调用 `self._extract_namespace(tree.root_node)`，使其与 `extract_classes()` 一致，
不依赖调用顺序。

```python
def extract_functions(self, tree, source_code):
    self.source_code = source_code
    self.content_lines = source_code.splitlines()
    self._extract_namespace(tree.root_node)  # ← 新增：独立扫描命名空间
    # ... 其余不变
```

## 验收标准

| ID | 条件 | 期望结果 |
|----|------|---------|
| AC-PHP-001 | `extract_functions()` 单独调用，函数在命名空间内 | 函数名含命名空间前缀 |
| AC-PHP-002 | `extract_functions()` 在 `extract_classes()` 之后调用 | 函数名含命名空间前缀（行为不变）|
| AC-PHP-003 | 函数不在命名空间内 | 函数名无多余 `\\` 前缀 |
| AC-PHP-004 | `extract_classes()` 行为 | 完全不变 |

## 范围外（不做）

- 嵌套命名空间 —— 保持现有行为
