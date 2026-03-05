# Token优化设计文档

**日期:** 2026-03-05
**版本:** 1.0
**状态:** 待审批

---

## 1. 概述

### 1.1 背景

tree-sitter-analyzer 的 MCP 工具在处理大文件或大量结果时，可能产生Token爆炸问题，导致：
- LLM上下文窗口溢出
- 响应延迟增加
- API成本上升

### 1.2 问题分析

通过代码分析发现以下Token冗余问题：

| 问题 | 位置 | 影响 |
|------|------|------|
| TOON响应双重数据 | `format_helper.py:attach_toon_content_to_response()` | 数据量翻倍 |
| 输出字段重叠 | `analyze_scale_tool.py` | summary与structural_overview重复 |
| 空结构占位符 | `analyze_scale_tool.py:454-455` | 无效Token消耗 |

### 1.3 解决方案目标

- 消除TOON输出中的冗余字段
- 统一TOON格式处理行为
- 防止Token爆炸

---

## 2. 详细设计

### 2.1 问题1: TOON响应双重数据

**当前代码** (`format_helper.py:208-223`):
```python
def attach_toon_content_to_response(result: dict[str, Any]) -> dict[str, Any]:
    """Attach TOON formatted content to a response *without removing* any existing fields."""
    toon_content = format_as_toon(result)
    enriched = result.copy()  # 保留所有原始数据
    enriched["format"] = "toon"
    enriched["toon_content"] = toon_content  # 再添加TOON格式
    return enriched
```

**问题**: 原始JSON数据 + TOON格式 = 数据量约2倍

**修复方案**:
```python
def attach_toon_content_to_response(result: dict[str, Any]) -> dict[str, Any]:
    """Attach TOON formatted content, removing redundant data fields."""
    toon_content = format_as_toon(result)

    # 移除冗余字段（已在toon_content中编码）
    redundant_fields = {
        "results", "matches", "content", "partial_content_result",
        "analysis_result", "data", "items", "files", "lines",
        "table_output", "detailed_analysis", "structural_overview",
    }

    toon_response = {
        "format": "toon",
        "toon_content": toon_content,
    }

    # 只保留元数据字段
    for key, value in result.items():
        if key not in redundant_fields:
            toon_response[key] = value

    return toon_response
```

### 2.2 问题2: 输出字段重叠

**当前结构** (`analyze_scale_tool.py:465-520`):
```python
result = {
    "file_metrics": {...},
    "summary": {  # 包含 classes, methods, fields, imports 计数
        "classes": 5,
        "methods": 25,
        ...
    },
    "structural_overview": {  # 包含相同信息的详细版本
        "classes": [...],  # 每个class都有name, line_span等
        "methods": [...],  # 每个method都有详细信息
        ...
    },
}
```

**问题**: `summary` 的计数信息可以从 `structural_overview` 数组长度推断

**修复方案**: 在TOON格式下，移除 `summary` 字段

```python
# 在 apply_toon_format_to_response 中添加
if "structural_overview" in result:
    # summary信息可从structural_overview推断
    redundant_fields.add("summary")
```

### 2.3 问题3: 空结构占位符

**当前代码** (`analyze_scale_tool.py:454-455`):
```python
analysis_result = None  # Placeholder
structural_overview = {}  # Placeholder
```

**问题**: 非Java文件返回空字典，浪费Token

**修复方案**: 完全省略空字段

```python
# 只在非空时添加
if structural_overview:
    result["structural_overview"] = structural_overview
```

---

## 3. 统一TOON处理策略

### 3.1 冗余字段清单

```python
TOON_REDUNDANT_FIELDS = frozenset({
    # 数据字段（已在toon_content中编码）
    "results",
    "matches",
    "content",
    "partial_content_result",
    "analysis_result",
    "data",
    "items",
    "files",
    "lines",
    "table_output",

    # 详细分析字段
    "detailed_analysis",
    "structural_overview",

    # 可从其他字段推断的摘要
    "summary",  # 可从structural_overview数组长度推断
})
```

### 3.2 元数据字段（保留）

```python
TOON_METADATA_FIELDS = frozenset({
    "success",
    "file_path",
    "language",
    "format",
    "toon_content",
    "warnings",
    "error",
    "total_count",
    "truncated",
    "execution_time",
})
```

### 3.3 处理流程

```
原始响应 dict
      │
      ▼
┌─────────────────────┐
│ format_as_toon()    │ ← 完整数据转换为TOON
└─────────────────────┘
      │
      ▼
┌─────────────────────┐
│ 移除冗余字段        │ ← 删除已在TOON中编码的数据
└─────────────────────┘
      │
      ▼
┌─────────────────────┐
│ 保留元数据字段      │ ← success, warnings, format等
└─────────────────────┘
      │
      ▼
  TOON响应 dict
  {
    "format": "toon",
    "toon_content": "...",
    "success": true,
    "warnings": [...],
    ...
  }
```

---

## 4. Token节省估算

| 优化项 | 预估节省 |
|--------|----------|
| 移除重复数据字段 | ~50% |
| 移除summary（有structural_overview时）| ~5% |
| 移除空占位符 | ~2% |
| **总计** | **~55-60%** |

---

## 5. 测试策略

### 5.1 单元测试

1. **测试TOON响应不包含冗余字段**
2. **测试空字段被正确省略**
3. **测试元数据字段被保留**
4. **测试向后兼容性**

### 5.2 集成测试

1. **对比优化前后的Token数量**
2. **验证TOON输出完整性**
3. **验证MCP工具链正常工作**

---

## 6. 风险评估

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 依赖原始字段的代码中断 | 中 | 高 | 检查所有调用点 |
| TOON格式解析失败 | 低 | 中 | 保留fallback到JSON |
| 元数据字段遗漏 | 低 | 中 | 完整的测试覆盖 |

---

## 7. 实施计划

### Phase 1: 核心优化 (优先级: HIGH)
- 统一 `attach_toon_content_to_response()` 行为
- 更新冗余字段列表

### Phase 2: 工具层优化 (优先级: MEDIUM)
- 优化 `analyze_scale_tool.py` 输出结构
- 移除空占位符

### Phase 3: 测试与验证 (优先级: HIGH)
- 添加单元测试
- 添加集成测试
- Token对比基准测试

---

## 8. 验收标准

- [ ] TOON响应不包含冗余数据字段
- [ ] 空字段被省略而非返回空字典
- [ ] 元数据字段（success, warnings等）被正确保留
- [ ] 所有现有测试通过
- [ ] 新增测试覆盖Token优化逻辑
- [ ] Token使用量减少 >= 50%
