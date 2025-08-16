## 项目接管与训练索引（training/）

本目录面向“零基础快速接管”与“新成员上手”。按顺序阅读与动手，可在1–3天内完成初步接管，1–2周内达到高效开发与扩展。

- 01_onboarding.md — 0到1快速上手（环境、运行、首个结果）
- 02_architecture_map.md — 架构与代码地图（控制流/数据流/关键模块）
- 03_cli_cheatsheet.md — CLI 速查与常用组合
- 04_mcp_cheatsheet.md — MCP 集成速查（Claude/Cursor 等）
- 05_plugin_tutorial.md — 新增语言插件的最小闭环教程
- 06_quality_workflow.md — 质量门禁与本地开发工作流
- 07_troubleshooting.md — 常见问题与排障指引
- 08_prompt_library.md — 针对本项目的高质量 LLM 提示词库
- 09_tasks.md — 实操任务清单（含验收标准）
- 10_glossary.md — 术语与核心概念

阅读建议：先 01 → 03 → 02 → 04 → 05（如需扩展语言）→ 06 → 09，遇到问题查 07/10。

快速开始（Windows / PowerShell）：

```powershell
# 安装 uv（推荐）
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 克隆与依赖
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer
uv sync --extra popular --extra mcp

# 首次体验（推荐示例）
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full --quiet

# 运行测试
uv run pytest -q
```

完成后，请继续阅读 `01_onboarding.md`。



