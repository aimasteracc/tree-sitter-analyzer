## 03 CLI 速查

最常用到的命令与组合，默认基于 uv 运行。

### 基础

```powershell
# 查看帮助
uv run python -m tree_sitter_analyzer -h | cat

# 列出支持的查询键
uv run python -m tree_sitter_analyzer --list-queries

# 显示支持语言/扩展名
uv run python -m tree_sitter_analyzer --show-supported-languages
uv run python -m tree_sitter_analyzer --show-supported-extensions
```

### 单文件分析

```powershell
# 文本模式（统计/结构）
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text

# 表格模式
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full
uv run python -m tree_sitter_analyzer examples/BigService.java --table=compact
uv run python -m tree_sitter_analyzer examples/BigService.java --table=csv

# 结构 JSON（适合二次处理）
uv run python -m tree_sitter_analyzer examples/BigService.java --structure --quiet
```

### 精确代码片段提取

```powershell
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 100 --end-line 120
```

### 查询驱动

```powershell
# 使用预置查询键
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods

# 直接传入 Tree-sitter 查询
uv run python -m tree_sitter_analyzer examples/BigService.java --query-string "(method_declaration name: (identifier) @name)"
```

### 常见选项

- `--language`: 显式指定语言
- `--project-root`: 设置项目根（安全边界）
- `--quiet`: 仅输出结果




