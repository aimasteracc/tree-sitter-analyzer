# Tool Registry System — MCP 工具注册与发现

## 背景

当前 tree-sitter-analyzer 有 15+ 个 MCP 工具，但缺乏统一的注册和组织机制：
- 工具散布在 `mcp/tools/` 目录下，没有统一的元数据
- 无法按功能分组（如：分析工具、查询工具、可视化工具）
- 缺少工具发现机制（列出所有可用工具、按类别过滤）
- 无法动态检查工具可用性（如：需要特定语言插件）

## 目标

参考 hermes-agent 的 `tools/registry.py` 设计，实现一个工具注册系统：

1. **ToolRegistry** - 中心化注册表
   - `register(name, toolset, schema, handler, check_fn, ...)`
   - `get_tool(name)` - 获取工具元数据
   - `list_tools(toolset=None)` - 列出工具
   - `get_toolsets()` - 获取所有工具集

2. **ToolEntry** - 工具元数据
   - name, toolset, schema, handler
   - check_fn (可用性检查)
   - category (分析/查询/可视化/...)
   - emoji (图标)
   - description (描述)

3. **Toolsets** - 工具分组
   - analysis: 依赖图、健康评分、爆炸半径
   - query: 符号查询、边提取、CJK 查询
   - output: TOON 输出、JSON 输出
   - advanced: AST chunking、modification guard

4. **MCP Integration** - 集成到 server.py
   - 启动时自动注册所有工具
   - 支持 `tools/list` 工具（列出所有可用工具）
   - 支持 `tools/discribe` 工具（获取工具详细信息）

## 实现计划

### Sprint 1: ToolRegistry 基础结构
- [ ] 创建 `mcp/registry.py`
- [ ] 实现 `ToolEntry` 类
- [ ] 实现 `ToolRegistry` 类
- [ ] 添加单元测试

### Sprint 2: 工具注册
- [ ] 定义工具集（toolsets）
- [ ] 注册现有 15 个 MCP 工具
- [ ] 添加工具元数据（emoji, category, description）

### Sprint 3: MCP 集成
- [ ] 修改 `mcp/server.py` 使用 registry
- [ ] 实现 `tools/list` 工具
- [ ] 实现 `tools/describe` 工具
- [ ] 集成测试

## 验收标准

- [ ] 所有现有工具通过 registry 注册
- [ ] `tools/list` 返回正确分组
- [ ] `tools/describe` 返回完整元数据
- [ ] 测试覆盖率 >80%
- [ ] mypy --strict 通过
- [ ] ruff check 通过

## 参考资料

- `/Users/aisheng.yu/wiki/raw/ai-tech/hermes-agent/tools/registry.py`
- `/Users/aisheng.yu/wiki/raw/ai-tech/hermes-agent/toolsets.py`
