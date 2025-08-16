## 07 故障排查（Troubleshooting）

### 1. CLI 无输出或报错

排查：
- 使用 `--quiet` 去除噪声日志，仅看结果是否产生
- 加 `| cat` 防止分页卡住
- 确认 `file_path` 在项目根边界内（或传入 `--project-root`）

### 2. MCP 工具不可见

排查：
- 确认客户端配置 `uv run --with tree-sitter-analyzer[mcp]`
- 重启客户端（Claude/Cursor）
- 查看 `pyproject.toml` 工具/脚本配置是否存在

### 3. 新语言插件不生效

排查：
- 是否在 `pyproject.toml` 正确注册 entry point
- 是否安装对应 tree-sitter 语言包
- `extensions` 列表是否覆盖目标文件扩展名

### 4. mypy/ruff 失败

排查：
- 逐个修复而非全局忽略；必要时使用精准 `# type: ignore[code]`
- 遵循 `CODE_STYLE_GUIDE.md` 与 `LLM_CODING_GUIDELINES.md`

### 5. 测试失败

排查：
- 定位具体测试模块（`tests/` 路径与命名）
- 优先修复公共 API 行为变更导致的断言失败
- 覆盖率下滑时，补足关键路径测试




