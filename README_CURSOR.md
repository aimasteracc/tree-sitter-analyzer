# 🎉 Tree-Sitter Analyzer V2 现已支持 Cursor！

## ✅ 集成状态

**完成并测试通过！** Tree-Sitter Analyzer V2 的 MCP 服务器已经可以在 Cursor 中使用。

---

## 🚀 三步快速配置

### 步骤 1: 安装依赖

```bash
cd C:/git-private/tree-sitter-analyzer-workspace/tree-sitter-analyzer-v2
uv pip install -e ".[mcp]"
```

### 步骤 2: 验证安装

**方法 A - 运行验证脚本（推荐）:**
```powershell
.\验证安装.ps1
```

**方法 B - 手动验证:**
```bash
cd C:/git-private/tree-sitter-analyzer-workspace
uv run --directory tree-sitter-analyzer-v2 python test_mcp_server.py
```

应该看到: `[SUCCESS] All tests passed!`

### 步骤 3: 配置 Cursor

在 Cursor 的 MCP 设置中添加以下配置：

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

**重要**: 如果要分析其他项目，修改 `TREE_SITTER_PROJECT_ROOT` 的值。

### 步骤 4: 重启 Cursor 并开始使用！

---

## 🛠️ 可用功能（11 个工具）

### 核心分析
- ✅ **analyze_code_structure** - 分析代码结构（类、函数、方法、导入）
- ✅ **query_code** - Tree-sitter 查询
- ✅ **check_code_scale** - 代码规模和复杂度分析
- ✅ **extract_code_section** - 提取代码片段

### 快速搜索
- ✅ **find_files** - 文件查找（使用 fd，超快）
- ✅ **search_content** - 内容搜索（使用 ripgrep，超快）
- ✅ **find_and_grep** - 组合搜索

### 代码图谱
- ✅ **analyze_code_graph** - 分析代码依赖关系
- ✅ **find_function_callers** - 查找函数调用者
- ✅ **query_call_chain** - 查询调用链
- ✅ **visualize_code_graph** - 可视化代码结构（Mermaid）

---

## 💡 使用示例

在 Cursor 的 AI 对话中：

```
分析 tree_sitter_analyzer_v2/mcp/server.py 文件
```

```
找出所有 Python 测试文件
```

```
搜索项目中的 TODO 注释
```

```
查找调用 handle_request 方法的地方
```

```
可视化 MCP 服务器的代码结构
```

---

## 📚 详细文档

| 文档 | 说明 |
|------|------|
| [快速配置.txt](./快速配置.txt) | 快速参考卡片，可直接复制 |
| [CURSOR配置说明.md](./CURSOR配置说明.md) | 详细配置指南（中文） |
| [验证安装.ps1](./验证安装.ps1) | 自动验证脚本 |
| [../如何在Cursor中使用.md](../如何在Cursor中使用.md) | 简洁快速指南 |
| [../CURSOR集成完成.md](../CURSOR集成完成.md) | 完整总结文档 |
| [../README_CURSOR_INTEGRATION.md](../README_CURSOR_INTEGRATION.md) | 英文完整指南 |

---

## 🐛 常见问题

### Q: MCP 服务器无法启动？
**A:** 运行 `uv pip install -e ".[mcp]"` 安装依赖

### Q: Cursor 找不到 uv 命令？
**A:** 确保 uv 在系统 PATH 中，或使用完整路径

### Q: 路径配置错误？
**A:** 使用正斜杠 `/`，确保路径正确

### Q: 如何分析其他项目？
**A:** 修改配置中的 `TREE_SITTER_PROJECT_ROOT` 环境变量

---

## ✅ 验证清单

配置前请确认：

- [ ] Python 3.10+ 已安装
- [ ] uv 包管理器已安装
- [ ] MCP 依赖已安装 (`uv pip install -e ".[mcp]"`)
- [ ] 验证脚本通过 (`.\验证安装.ps1`)
- [ ] 配置已添加到 Cursor
- [ ] Cursor 已重启

---

## 🎯 项目信息

- **项目路径**: `C:/git-private/tree-sitter-analyzer-workspace/tree-sitter-analyzer-v2`
- **版本**: v2.0.0-alpha.1
- **状态**: ✅ 可用并已测试
- **工具数**: 11 个
- **测试**: 全部通过

---

## 📞 获取帮助

1. 查看 [CURSOR配置说明.md](./CURSOR配置说明.md) 的故障排查部分
2. 运行 `.\验证安装.ps1` 检查配置
3. 查看 [../CURSOR集成完成.md](../CURSOR集成完成.md) 获取完整信息

---

**开始在 Cursor 中使用 Tree-Sitter Analyzer V2 吧！** 🚀
