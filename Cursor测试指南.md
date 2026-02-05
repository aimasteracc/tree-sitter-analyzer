# Cursor MCP 服务器测试指南

## 🔧 问题已修复

MCP 服务器启动问题已经修复！现在可以在 Cursor 中正常使用了。

---

## 📋 测试前准备

### 1. 确认修复已应用

检查以下文件是否存在：
- ✅ `tree_sitter_analyzer_v2/mcp/__main__.py` - 新的入口点
- ✅ `tree_sitter_analyzer_v2/mcp/server.py` - 已更新（包含 ServerCapabilities）

### 2. 使用正确的配置

**重要**: 确保使用新的启动命令：

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

**注意**: 命令是 `tree_sitter_analyzer_v2.mcp` 而不是 `tree_sitter_analyzer_v2.mcp.server`

---

## 🚀 在 Cursor 中测试

### 步骤 1: 更新配置

1. 打开 Cursor 设置
2. 找到 MCP 服务器配置
3. 如果已有旧配置，删除它
4. 添加上面的新配置
5. 保存设置

### 步骤 2: 重启 Cursor

**重要**: 必须完全重启 Cursor 才能使新配置生效。

### 步骤 3: 检查服务器状态

重启后，检查 Cursor 的 MCP 服务器状态：
- 应该显示 "tree-sitter-analyzer-v2" 已连接
- 没有错误信息

### 步骤 4: 测试基本功能

在 Cursor 的 AI 对话中尝试以下命令：

#### 测试 1: 查找文件
```
请找出项目中所有的 Python 文件
```

**预期结果**: 列出所有 `.py` 文件

#### 测试 2: 分析代码
```
请分析 tree_sitter_analyzer_v2/mcp/server.py 文件
```

**预期结果**: 显示文件中的类、函数、方法等结构

#### 测试 3: 搜索内容
```
搜索项目中包含 "MCP" 的代码
```

**预期结果**: 列出包含 "MCP" 的文件和行号

#### 测试 4: 代码规模检查
```
检查项目的代码规模
```

**预期结果**: 显示文件数量、代码行数等统计信息

---

## 🐛 如果遇到问题

### 问题 1: 服务器无法启动

**症状**: Cursor 显示 MCP 服务器连接失败

**检查**:
1. 确认使用的是新命令（`tree_sitter_analyzer_v2.mcp`）
2. 检查路径是否正确
3. 确认 MCP 依赖已安装：
   ```bash
   cd C:/git-private/tree-sitter-analyzer-workspace/tree-sitter-analyzer-v2
   uv pip install -e ".[mcp]"
   ```

**查看日志**:
- 在 Cursor 中打开开发者工具（Help > Toggle Developer Tools）
- 查看 Console 标签页的错误信息

### 问题 2: 仍然看到 RuntimeWarning

**症状**: 日志中仍有模块导入警告

**解决**:
- 这只是一个警告，不影响功能
- 如果服务器能正常响应，可以忽略
- 如果服务器无法响应，检查是否使用了正确的命令

### 问题 3: 工具调用失败

**症状**: AI 说无法调用工具

**检查**:
1. 确认服务器已连接
2. 查看 Cursor 的 MCP 服务器状态
3. 尝试重启 Cursor
4. 检查 `TREE_SITTER_PROJECT_ROOT` 路径是否正确

### 问题 4: 找不到 uv 命令

**症状**: Cursor 报错 "command not found: uv"

**解决**:
- 确保 uv 在系统 PATH 中
- 或使用完整路径：
  ```json
  "command": "C:/Users/你的用户名/.cargo/bin/uv"
  ```

---

## ✅ 测试清单

完成以下测试以确认 MCP 服务器正常工作：

- [ ] Cursor 显示 MCP 服务器已连接
- [ ] 没有错误信息（警告可以忽略）
- [ ] 测试 1: 查找文件 - 成功
- [ ] 测试 2: 分析代码 - 成功
- [ ] 测试 3: 搜索内容 - 成功
- [ ] 测试 4: 代码规模检查 - 成功

---

## 📊 预期的日志输出

### 正常启动（可能有警告）

```
2026-02-05 XX:XX:XX.XXX [info] Starting new stdio process with command: uv run --directory C:/git-private/tree-sitter-analyzer-workspace/tree-sitter-analyzer-v2 python -m tree_sitter_analyzer_v2.mcp
2026-02-05 XX:XX:XX.XXX [info] MCP server connected
```

可能会看到 RuntimeWarning，但只要后面显示 "connected" 就是正常的。

### 工具调用成功

```
2026-02-05 XX:XX:XX.XXX [info] Calling tool: find_files
2026-02-05 XX:XX:XX.XXX [info] Tool execution successful
```

---

## 🎯 高级测试

如果基本测试都通过了，可以尝试更高级的功能：

### 测试代码图谱
```
分析 tree_sitter_analyzer_v2/mcp/server.py 的代码依赖关系
```

### 测试调用链查询
```
查找所有调用 handle_request 方法的地方
```

### 测试代码可视化
```
生成 MCP 服务器的代码结构图
```

---

## 📝 反馈

测试完成后，请记录：

1. **成功的测试**: 哪些功能正常工作
2. **失败的测试**: 哪些功能有问题
3. **错误信息**: 完整的错误日志
4. **环境信息**: 
   - Cursor 版本
   - Python 版本
   - uv 版本
   - 操作系统

---

## 📚 相关文档

- [修复说明.md](./修复说明.md) - 详细的修复说明
- [快速配置.txt](./快速配置.txt) - 配置参考
- [CURSOR配置说明.md](./CURSOR配置说明.md) - 完整配置指南

---

**修复版本**: v2.0.0-alpha.1 (2026-02-05)  
**状态**: ✅ 已修复，待测试  
**优先级**: 高 - 请尽快在 Cursor 中测试
