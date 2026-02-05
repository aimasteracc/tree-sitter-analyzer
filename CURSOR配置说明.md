# Tree-Sitter Analyzer V2 - Cursor 配置说明

## 📍 项目路径

```
C:/git-private/tree-sitter-analyzer-workspace/tree-sitter-analyzer-v2
```

## ⚙️ Cursor MCP 配置

### 配置文件位置

在 Cursor 中配置 MCP 服务器，通常在以下位置之一：

1. **Cursor 设置界面**
   - 打开 Cursor 设置 (Ctrl+,)
   - 搜索 "MCP" 或 "Model Context Protocol"
   - 添加新的 MCP 服务器配置

2. **配置文件** (如果 Cursor 支持)
   - Windows: `%APPDATA%\Cursor\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json`

### 配置内容

将以下配置添加到 Cursor 的 MCP 服务器设置中：

```json
{
  "mcpServers": {
    "tree-sitter-analyzer-v2": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "C:/git-private/tree-sitter-analyzer-workspace/tree-sitter-analyzer-v2",
        "python",
        "-m",
        "tree_sitter_analyzer_v2.mcp"
      ],
      "env": {
        "TREE_SITTER_PROJECT_ROOT": "C:/git-private/tree-sitter-analyzer-workspace/tree-sitter-analyzer-v2"
      },
      "timeout": 3600,
      "disabled": false
    }
  }
}
```

### 配置说明

- **command**: `uv` - 使用 uv 包管理器运行
- **args**: 指定运行 MCP 服务器的参数
  - `--directory`: 指定项目目录
  - `python -m tree_sitter_analyzer_v2.mcp.server`: 运行 MCP 服务器模块
- **env**: 环境变量
  - `TREE_SITTER_PROJECT_ROOT`: 要分析的项目根目录
- **timeout**: 3600 秒 (1 小时)
- **disabled**: false (启用服务器)

### 自定义项目路径

如果你想分析其他项目，只需修改 `TREE_SITTER_PROJECT_ROOT` 环境变量：

```json
"env": {
  "TREE_SITTER_PROJECT_ROOT": "C:/你的项目路径"
}
```

## 🚀 使用步骤

### 1. 确认依赖已安装

```bash
cd C:/git-private/tree-sitter-analyzer-workspace/tree-sitter-analyzer-v2
uv pip install -e ".[mcp]"
```

### 2. 验证安装

```bash
cd C:/git-private/tree-sitter-analyzer-workspace
uv run --directory tree-sitter-analyzer-v2 python test_mcp_server.py
```

应该看到：
```
[SUCCESS] All tests passed!
```

### 3. 配置 Cursor

按照上面的配置内容添加到 Cursor 中。

### 4. 重启 Cursor

配置完成后重启 Cursor 使配置生效。

### 5. 开始使用

在 Cursor 的 AI 对话中使用：

```
请分析 tree_sitter_analyzer_v2/mcp/server.py 文件
```

```
帮我找出项目中所有的 Python 文件
```

```
搜索代码中的 TODO 注释
```

## 🛠️ 可用工具 (11 个)

### 核心分析
1. **analyze_code_structure** - 分析代码结构
2. **query_code** - 查询代码元素
3. **check_code_scale** - 检查代码规模
4. **extract_code_section** - 提取代码片段

### 搜索功能
5. **find_files** - 快速查找文件 (使用 fd)
6. **search_content** - 快速搜索内容 (使用 ripgrep)
7. **find_and_grep** - 组合搜索

### 代码图谱
8. **analyze_code_graph** - 分析代码依赖关系
9. **find_function_callers** - 查找函数调用者
10. **query_call_chain** - 查询调用链
11. **visualize_code_graph** - 可视化代码结构

## 🐛 故障排查

### 问题 1: MCP 服务器无法启动

**检查**:
```bash
cd C:/git-private/tree-sitter-analyzer-workspace/tree-sitter-analyzer-v2
uv run python -c "from tree_sitter_analyzer_v2.mcp.server import TreeSitterAnalyzerMCPServer; print('OK')"
```

**解决**:
```bash
uv pip install -e ".[mcp]"
```

### 问题 2: Cursor 找不到 uv 命令

**解决**: 确保 uv 在系统 PATH 中，或使用完整路径：
```json
"command": "C:/Users/你的用户名/.cargo/bin/uv"
```

### 问题 3: 路径错误

**检查**: 确保所有路径使用正斜杠 `/` 而不是反斜杠 `\`

### 问题 4: 权限问题

**解决**: 以管理员身份运行 Cursor

## 📊 使用示例

### 示例 1: 分析当前项目

```
User: 分析 tree_sitter_analyzer_v2/mcp/server.py

AI: [使用 analyze_code_structure 工具]
找到:
- 2 个类: MCPServer, TreeSitterAnalyzerMCPServer
- 2 个函数: main, main_sync
- 多个方法...
```

### 示例 2: 查找文件

```
User: 找出所有 Python 测试文件

AI: [使用 find_files 工具，pattern: "**/test_*.py"]
找到 38 个测试文件...
```

### 示例 3: 搜索代码

```
User: 搜索项目中所有的 TODO

AI: [使用 search_content 工具]
找到 15 处 TODO 注释...
```

## 📝 环境变量详解

| 变量 | 说明 | 示例 | 必需 |
|------|------|------|------|
| `TREE_SITTER_PROJECT_ROOT` | 要分析的项目根目录 | `C:/git-private/my-project` | ✅ |
| `TREE_SITTER_OUTPUT_PATH` | 分析结果输出路径 | `C:/output/.analysis` | ❌ |
| `TREE_SITTER_ANALYZER_ENABLE_FILE_LOG` | 启用文件日志 | `true` | ❌ |
| `TREE_SITTER_ANALYZER_LOG_DIR` | 日志目录 | `C:/logs` | ❌ |
| `TREE_SITTER_ANALYZER_LOG_LEVEL` | 日志级别 | `DEBUG` | ❌ |

## 🎯 最佳实践

1. **明确项目路径**: 始终使用绝对路径
2. **合理超时设置**: 大项目需要更长超时
3. **启用日志**: 调试时启用 DEBUG 日志
4. **定期更新**: 保持 MCP SDK 和工具最新

## 📚 相关文档

- [完整集成指南](../README_CURSOR_INTEGRATION.md)
- [详细设置文档](../CURSOR_SETUP.md)
- [快速开始](../如何在Cursor中使用.md)
- [项目 README](./README.md)

## ✅ 检查清单

配置前请确认：

- [ ] 已安装 Python 3.10+
- [ ] 已安装 uv 包管理器
- [ ] 已安装 MCP 依赖 (`uv pip install -e ".[mcp]"`)
- [ ] 测试脚本通过 (`test_mcp_server.py`)
- [ ] 路径配置正确
- [ ] Cursor 已重启

---

**项目路径**: `C:/git-private/tree-sitter-analyzer-workspace/tree-sitter-analyzer-v2`
**状态**: ✅ 可用
**版本**: v2.0.0-alpha.1
**测试**: 全部通过
