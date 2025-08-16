## 01 0到1快速上手（Onboarding）

目标：在30–60分钟内完成环境搭建、运行首个命令、得到可验证的结果，并理解基础目录结构。

### 1. 环境准备

- Python >= 3.10（建议 3.10–3.12）
- Windows: PowerShell 7（已满足）
- 包管理：uv（推荐）或 pip


#### 安装 uv：

Windows/PowerShell：
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Codespace / Linux / macOS：
```bash
curl -Ls https://astral.sh/uv/install.sh | sh
# 或使用 pip 安装（可选）
# pip install uv
```

### 2. 获取代码与依赖


Windows/PowerShell：
```powershell
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer
uv sync --extra full
```

Codespace / Linux / macOS（已在项目根目录，无需 clone/cd）：
```bash
uv sync --extra full
```


如使用 pip：

Windows/PowerShell：
```powershell
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -e ".[full]"
```

Codespace / Linux / macOS：
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[full]"
```

### 3. 第一次运行（CLI）


Windows/PowerShell：
```powershell
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full --quiet
```

Codespace / Linux / macOS：
```bash
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full --quiet
```

期望输出：一个关于类/方法/字段的结构化表格，能直观看到方法数量与行号范围。

### 4. 基础目录认知（最小必读）

- `tree_sitter_analyzer/cli_main.py`：CLI 主入口与参数解析
- `tree_sitter_analyzer/mcp/server.py`：MCP 服务入口
- `tree_sitter_analyzer/languages/*.py`：语言插件（Java/Python/JS）
- `tree_sitter_analyzer/core/*`：核心引擎（解析、查询、缓存等）
- `tree_sitter_analyzer/queries/*`：Tree-sitter 查询库
- `tests/`：完整测试套件

### 5. 产生第一个可验证结果


Windows/PowerShell：
```powershell
# 规模与复杂度（文本输出）
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text
# 按行提取片段（100–105行）
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 100 --end-line 105
```

Codespace / Linux / macOS：
```bash
# 规模与复杂度（文本输出）
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text
# 按行提取片段（100–105行）
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 100 --end-line 105
```

### 5.5 新功能演示：高级查询过滤（NEW!）

Windows/PowerShell：
```powershell
# 查找特定方法
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=main"

# 查找认证相关方法（模式匹配）
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=~auth*"

# 查找无参数的公开方法
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "params=0,public=true"

# 查看过滤语法帮助
uv run python -m tree_sitter_analyzer --filter-help
```

Codespace / Linux / macOS：
```bash
# 查找特定方法
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=main"

# 查找认证相关方法（模式匹配）
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=~auth*"

# 查找无参数的公开方法
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "params=0,public=true"

# 查看过滤语法帮助
uv run python -m tree_sitter_analyzer --filter-help
```

### 6. 质量检查（本地）


Windows/PowerShell：
```powershell
uv run python check_quality.py --new-code-only
uv run python llm_code_checker.py --check-all
uv run pytest -q
```

Codespace / Linux / macOS：
```bash
uv run python check_quality.py --new-code-only
uv run python llm_code_checker.py --check-all
uv run pytest -q
```

### 7. 下一步

继续阅读：`03_cli_cheatsheet.md`（常用命令）、`02_architecture_map.md`（架构认知）。
