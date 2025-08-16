## 04 MCP 集成速查

目标：让 Claude Desktop / Cursor 直接调用本项目的工具链，完成“检查规模 → 结构分析 → 片段提取”的三步流。

### 配置（Claude Desktop 示例）

在配置文件添加：

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": [
        "run", "--with", "tree-sitter-analyzer[mcp]",
        "python", "-m", "tree_sitter_analyzer.mcp.server"
      ]
    }
  }
}
```

如需固定项目根：

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": [
        "run", "--with", "tree-sitter-analyzer[mcp]",
        "python", "-m", "tree_sitter_analyzer.mcp.server"
      ],
      "env": {
        "TREE_SITTER_PROJECT_ROOT": "C:/path/to/your/project"
      }
    }
  }
}
```

### 工具清单与示例提示词

- `check_code_scale`
  - 提示：
    ```
    使用MCP工具check_code_scale分析文件规模
    参数: {"file_path": "examples/BigService.java"}
    ```

- `analyze_code_structure`
  - 提示：
    ```
    使用MCP工具analyze_code_structure生成详细结构
    参数: {"file_path": "examples/BigService.java"}
    ```

- `extract_code_section`
  - 提示：
    ```
    使用MCP工具extract_code_section提取指定代码段
    参数: {"file_path": "examples/BigService.java", "start_line": 100, "end_line": 110}
    ```

### 注意事项

- 参数采用下划线命名：`file_path`、`start_line`、`end_line`
- 相对路径会被解析到项目根内（含安全边界校验）
- 建议按“规模 → 结构 → 提取”的顺序调用，便于 LLM 逐步缩小上下文




