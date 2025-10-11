# ROO规则

## 🎯 核心原则

### 1. 基本规则
- **禁止**: 使用标准`read_file`读取代码文件
- **必须**: 使用tree-sitter-analyzer MCP工具
- **智能**: 遵循`check_code_scale`的推荐

### 2. 推荐工作流
```
1. search_content (定位相关文件)
2. check_code_scale (智能评估)
3. 遵循工具推荐策略
4. 必要时使用extract_code_section
```

### 3. Token节约策略
- 大量结果: `suppress_output=true + output_file`
- 搜索优化: `total_only → summary_only → 详细`
- 日语搜索: 避免汎用語，使用分阶段搜索

### 4. 危险警告
⚠️ **Token爆发风险**: 汎用語搜索（「項目名」「データ」「処理」）
⚠️ **解决方案**: 使用`total_only=true`先检查数量


## 📋 快速参考

| 场景 | 推荐工具链 | 关键参数 |
|------|-----------|---------|
| 小文件探索 | search_content → read_file | - |
| 大文件分析 | search_content → check_code_scale → analyze_code_structure | suppress_output=true |
| 代码搜索 | search_content | total_only=true (先检查) |
| 结构分析 | analyze_code_structure | format_type=full |
| 精确提取 | extract_code_section | 基于结构分析结果 |
