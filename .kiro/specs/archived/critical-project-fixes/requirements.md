# 要件ドキュメント：项目致命问题修复

## 执行者视角

扮演**全球顶级 GitHub 开发者**，以最高标准审视项目，识别并修复致命问题。

## 问题分析（Critical Issues Identified）

### 现状诊断

通过深度代码审查，发现以下**10个致命问题**：

| # | 问题 | 严重性 | 影响范围 | 当前状态 |
|---|------|--------|---------|---------|
| 1 | **版本号不一致** | 🔴 CRITICAL | 发布流程 | `pyproject.toml`: 1.10.4 vs `__init__.py`: 1.10.3 |
| 2 | **临时文件污染仓库** | 🔴 CRITICAL | 代码质量 | 6个 `tmpclaude-*` 文件未被 .gitignore |
| 3 | **.gitignore 不完整** | 🟠 HIGH | 版本控制 | 缺少 Claude/AI 工具临时文件模式 |
| 4 | **未提交的关键文件** | 🟠 HIGH | Git 状态 | CLAUDE.md 等已暂存未提交 |
| 5 | **__pycache__ 泄漏** | 🟠 HIGH | 代码质量 | 源代码目录中有 .pyc 文件 |
| 6 | **planning-with-files 临时目录** | 🟡 MEDIUM | 仓库清洁 | `planning-with-files/` 未被跟踪 |
| 7 | **测试数量不一致** | 🟡 MEDIUM | 文档准确性 | README 声称 8409，实际 8405 |
| 8 | **.claude/ 配置策略** | 🟡 MEDIUM | IDE 集成 | 需区分项目配置(提交)和本地配置(忽略) |
| 9 | **分支策略混乱** | 🟡 MEDIUM | Git 管理 | 多个过时的远程分支未清理 |
| 10 | **缺少自动化版本同步检查** | 🟡 MEDIUM | CI/CD | 没有 pre-commit 钩子验证版本一致性 |

## 问题详情

### 问题 1: 版本号不一致 🔴

**现状:**
```
pyproject.toml: version = "1.10.4"
__init__.py: __version__ = "1.10.3"
```

**影响:**
- PyPI 发布会混乱
- 用户无法确定实际版本
- 违反单一真实来源原则

**根本原因:**
- 手动维护两处版本号
- 缺少自动同步机制验证

**目标:**
- 立即同步为 1.10.4
- 确保 `scripts/sync_version_minimal.py` 正常工作

### 问题 2: 临时文件污染 🔴

**现状:**
```
tmpclaude-6dc4-cwd
tmpclaude-c8c2-cwd
tmpclaude-27be-cwd
tmpclaude-690b-cwd
tmpclaude-3e01-cwd
tmpclaude-90a2-cwd
```

**影响:**
- 污染工作区
- 可能被意外提交
- 违反代码清洁原则

**根本原因:**
- Claude Code 产生的临时工作目录
- .gitignore 未覆盖此模式

### 问题 3: .gitignore 不完整 🟠

**缺失模式:**
```
tmpclaude-*       # Claude Code 临时目录
.claude/          # Claude IDE 设置
planning-with-files/  # Planning skill 临时文件
.kiro/specs/*/progress.md  # 会话日志（应该 gitignore）
```

### 问题 4: Git 状态混乱 🟠

**未提交文件:**
```
Changes to be committed:
  new file:   .claude/settings.json
  new file:   .claude/settings.local.json
  new file:   CLAUDE.md
```

**问题:**
- 关键文档 CLAUDE.md 已暂存但未提交
- .claude/ 设置文件不应提交

### 问题 5: __pycache__ 泄漏 🟠

**统计:**
- 源代码中有 1339 个 .pyc 文件
- 主要在 tree_sitter_analyzer/ 目录

**根本原因:**
- .gitignore 有 `__pycache__/` 但某些 IDE 可能已跟踪
- 需要清理并确保未被跟踪

### 问题 6-10: 中优先级问题

详见设计文档。

## 成功标准

修复完成后必须满足：

1. ✅ 版本号在所有位置一致（1.10.4 或更新）
2. ✅ 工作区完全清洁（`git status` 无未跟踪文件）
3. ✅ .gitignore 覆盖所有已知临时文件模式
4. ✅ 所有测试通过（8405+）
5. ✅ 类型检查零错误（mypy）
6. ✅ Linting 零错误（ruff）
7. ✅ Git 历史清晰（一次性提交所有修复）
8. ✅ README 文档数据准确
9. ✅ 按照 GITFLOW_zh.md 成功发布
10. ✅ GitHub Release 创建成功

## 风险评估

| 风险 | 缓解措施 |
|------|---------|
| 版本冲突 | 先确认当前 develop 分支状态 |
| 破坏性更改 | 所有修改前创建测试 |
| 发布失败 | 验证 PyPI 凭证和 CI/CD 流程 |
| 测试失败 | 修复后完整回归测试 |

## 预期时间

- 问题分析: 30分钟 ✅
- 设计方案: 30分钟（进行中）
- 实施修复: 1小时
- 测试验证: 30分钟
- 发布流程: 30分钟
- **总计**: 约3小时

## 依赖工具

- ✅ uv（包管理）
- ✅ pytest（测试）
- ✅ mypy（类型检查）
- ✅ ruff（代码检查）
- ✅ gh（GitHub CLI）
- ✅ git（版本控制）
