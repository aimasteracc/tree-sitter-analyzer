# Code Diff Analysis — 语义级代码差异分析

## 背景

当前 tree-sitter-analyzer 缺少代码差异分析功能。现有的 `diff` 工具只能提供行级别的差异，无法识别语义级别的变化：
- 无法识别函数签名的变化（参数类型变化、返回值变化）
- 无法识别类继承关系的变化
- 无法识别方法可见性的变化
- 无法识别 API 兼容性的破坏

AI 助手在审查 PR 或理解代码变更时，需要知道：
- 哪些公共 API 被修改了？
- 哪些函数签名变化了？
- 哪些类/方法被添加或删除了？
- 是否有破坏性变更？

## 目标

实现 `code_diff` MCP 工具，提供语义级别的代码差异分析：

1. **Semantic Diff** - 语义级差异
   - 对比两个版本的代码（文件路径或直接内容）
   - 识别添加/删除/修改的元素（类、方法、函数、字段）
   - 显示元素级别的变化（签名、可见性、类型注解）

2. **Breaking Change Detection** - 破坏性变更检测
   - 检测公共 API 的变化
   - 识别方法签名的破坏性变更
   - 识别类继承关系的破坏

3. **Change Summary** - 变更摘要
   - 按类型统计变更（类、方法、函数、字段）
   - 显示变更的严重程度（破坏性 vs 非破坏性）
   - 提供变更的影响范围

## 实现计划

### Sprint 1: Core Diff Algorithm
- [ ] 创建 `mcp/tools/code_diff_tool.py`
- [ ] 实现基础的 AST 对比算法
- [ ] 识别添加/删除/修改的元素
- [ ] 添加单元测试

### Sprint 2: Breaking Change Detection
- [ ] 实现破坏性变更检测逻辑
- [ ] 识别公共 API 变化
- [ ] 识别签名不兼容的变更
- [ ] 添加集成测试

### Sprint 3: MCP Integration
- [ ] 注册到 ToolRegistry (diff toolset)
- [ ] 添加 schema 和参数验证
- [ ] 实现 TOON 格式输出
- [ ] 添加文档和示例

## 验收标准

- [ ] `code_diff` 工具可以对比两个版本的代码
- [ ] 正确识别添加/删除/修改的元素
- [ ] 破坏性变更检测准确率 >90%
- [ ] 测试覆盖率 >80%
- [ ] mypy --strict 通过
- [ ] ruff check 通过

## 参考资料

- `/Users/aisheng.yu/wiki/raw/ai-tech/tree-sitter-analyzer/` - 现有 tree-sitter 集成
- tree-sitter AST 节点对比算法
