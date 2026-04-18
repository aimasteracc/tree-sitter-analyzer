# Pull Request Summary Generator

## Goal
从代码变更自动生成有意义的 Pull Request 描述。

## One-Sentence Definition
"从 git diff 和代码分析自动生成结构化的 PR 描述"

## MVP Scope
- 解析 git diff 获取变更文件列表
- 分析代码变更类型（feature, bugfix, refactor, docs, test, chore）
- 生成变更摘要（文件数量、增删行数、影响范围）
- 检测破坏性变更（breaking changes）
- 输出格式：Markdown (GitHub/GitLab PR body)

## Test Standards
- 单元测试：≥5 个 per sprint
- 集成测试：真实 git repo 变更分析
- 覆盖率：≥80%

## Technical Approach

### Sprint 1: Core Analysis Engine
**目标**: 实现基础的 diff 解析和变更分类

**文件**:
- `tree_sitter_analyzer/pr_summary/diff_parser.py` - Git diff 解析
- `tree_sitter_analyzer/pr_summary/change_classifier.py` - 变更类型分类
- `tests/unit/pr_summary/test_diff_parser.py` - 单元测试

**功能**:
- 解析 `git diff` 输出
- 提取文件变更（added, modified, deleted）
- 计算增删行数
- 分类变更类型（基于文件路径和内容）
  - `src/` → feature/refactor
  - `tests/` → test
  - `docs/` → docs
  - `*.md` → docs
  - `fix/` or `bug/` → bugfix

### Sprint 2: Multi-Language Support
**目标**: 实现语义级代码变更分析

**文件**:
- `tree_sitter_analyzer/pr_summary/semantic_analyzer.py` - 语义分析
- `tests/unit/pr_summary/test_semantic_analyzer.py` - 单元测试

**功能**:
- 检测函数签名变更（breaking change）
- 检测类/接口变更（public API）
- 检测依赖变更（import/require）
- 支持语言: Python, JavaScript, TypeScript, Java, Go

### Sprint 3: CLI + MCP Integration
**目标**: 提供 CLI 和 MCP 工具接口

**文件**:
- `cli/commands/pr_summary_command.py` - CLI 命令
- `mcp/tools/pr_summary_tool.py` - MCP 工具
- `tests/integration/cli/test_pr_summary_cli.py` - 集成测试

**功能**:
- CLI: `tree-sitter pr-summary [--format markdown|json]`
- MCP: `pr_summary` 工具（在 git toolset）
- 输出格式:
  - Markdown: 标准 PR body 格式
  - JSON: 程序化处理
  - TOON: 结构化数据

## Dependencies
- 现有模块: `analyzer/git_analyzer.py`, `mcp/tools/code_diff_tool.py`
- 外部依赖: git (系统命令)

## Success Criteria
- ✅ 生成可读的 PR 摘要
- ✅ 检测破坏性变更准确率 >80%
- ✅ 支持至少 5 种编程语言
- ✅ CLI 和 MCP 工具正常工作
- ✅ 测试覆盖率 ≥80%

## Completion Status ✅

**Sprint 1: Core Analysis Engine** ✅ 完成
- ✅ tree_sitter_analyzer/pr_summary/diff_parser.py (291 lines)
- ✅ tree_sitter_analyzer/pr_summary/change_classifier.py (370 lines)
- ✅ tests/unit/pr_summary/test_diff_parser.py
- ✅ tests/unit/pr_summary/test_change_classifier.py

**Sprint 2: Multi-Language Support** ✅ 完成
- ✅ tree_sitter_analyzer/pr_summary/semantic_analyzer.py (531 lines)
- ✅ tests/unit/pr_summary/test_semantic_analyzer.py
- ✅ 支持语言: Python, JavaScript, TypeScript, Java, Go

**Sprint 3: CLI + MCP Integration** ✅ 完成
- ✅ tree_sitter_analyzer/mcp/tools/pr_summary_tool.py (459 lines)
- ✅ tree_sitter_analyzer/cli/commands/pr_summary_command.py (461 lines)
- ✅ tests/integration/mcp/test_pr_summary_tool.py
- ✅ CLI: `tree-sitter pr-summary [--format markdown|json]`
- ✅ MCP: `pr_summary` 工具 (git toolset)

**总计**: 2154 lines of code, 90+ tests passing, tool registered in git toolset
**Commits**: ba507d85, 84418e28
**Date**: 2026-04-18
