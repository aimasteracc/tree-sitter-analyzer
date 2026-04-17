# Code Complexity Heatmap — 代码复杂度热力图输出

## 背景

当前 tree-sitter-analyzer 的 `health_score` 工具提供文件级健康评分（A-F），但无法直观显示文件**内部**的复杂度分布。

AI 助手和开发者在处理大文件时需要：
- 快速识别复杂度集中的区域（函数/类级别）
- 优先关注可能存在 bug 的复杂代码
- 在代码审查时快速定位需要重点检查的部分

## 目标

为现有工具添加**复杂度热力图**输出模式，提供行级复杂度可视化。

### 一句话定义
"Find complex code before it breaks" — 在代码出问题前找到复杂代码

## 实现计划

### Sprint 1: Cyclomatic Complexity 分析器 ✅
- [x] 创建 `analysis/complexity.py` 模块
- [x] 实现圈复杂度计算（基于分支节点数）
- [x] 实现函数级复杂度聚合
- [x] 添加单元测试 (23 tests)

### Sprint 2: Heatmap Formatter ✅
- [x] 创建 `ComplexityHeatmapFormatter` in `analysis/complexity.py`
- [x] 实现 ASCII 热力图输出（低→高：░▒▓█）
- [x] 实现行级复杂度映射
- [x] 添加颜色编码选项（ANSI）
- [x] 添加单元测试

### Sprint 3: MCP 工具集成 ✅
- [x] 创建 `complexity_heatmap` MCP 工具
- [x] 注册到 ToolRegistry (analysis toolset)
- [x] 添加集成测试 (13 tests)
- [x] 更新 tool count (25 → 26)

### Sprint 4: 文档更新 ⏳
- [ ] 更新 CHANGELOG.md
- [ ] 更新 README.md
- [ ] 更新 ARCHITECTURE.md

## 验收标准

- [ ] `complexity_heatmap` 工具可以生成文件的热力图
- [ ] 热力图正确标注高复杂度区域
- [ ] 支持 ASCII 和 ANSI 两种输出格式
- [ ] 测试覆盖率 >80%
- [ ] mypy --strict 通过
- [ ] ruff check 通过

## 技术细节

### 圈复杂度计算
- 基础复杂度 = 1
- 每个分支节点 (+1): if, elif, for, while, try, except, case, catch, &&, ||, ?
- 函数复杂度 = 所有分支节点数 + 1

### 热力图等级
```
低复杂度 (1-5):    ░  绿色 (安全)
中等复杂度 (6-10): ▒  黄色 (注意)
高复杂度 (11-20):  ▓  橙色 (警告)
极高复杂度 (20+):  █  红色 (危险)
```

### 输出示例
```
example.py (125 lines, complexity: LOW)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   1   def simple_function(x):                    ░░░░░░░░░░░  [1]
   2       return x + 1                          ░░░░░░░░░░░  [1]
   3                                              ░░░░░░░░░░░
   4   def complex_logic(data):                  ████████████  [15]
   5       result = []                           ████████████
   6       for item in data:                      ████████████
   7           if item.is_valid():                ████████████
   8               for sub in item.items:         ████████████
   9                   if sub.condition:          ████████████
  10                      result.append(sub)      ████████████
 11           elif item.alternative():             ████████████
 12               try:                             ████████████
 13                   result.extend(item.data)     ████████████
 14               except:                          ████████████
 15                   pass                          ████████████
 16       return result                            ████████████
```

## 参考资料

- `/Users/aisheng.yu/wiki/raw/ai-tech/tree-sitter-analyzer/` - 圈复杂度计算
- `/Users/aisheng.yu/wiki/wiki/ai-tech/codeflow-overview.md` - CodeFlow 可视化启发
