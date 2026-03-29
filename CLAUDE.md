## gstack Skills

Use `/browse` from gstack for all web browsing. Never use `mcp__claude-in-chrome__*` tools.

Available skills:
- `/office-hours` — YC-style product/design discussion
- `/plan-ceo-review` — CEO-mode plan review
- `/plan-eng-review` — Engineering architecture review
- `/plan-design-review` — Design review
- `/design-consultation` — Full design system from scratch
- `/review` — Staff engineer code review
- `/ship` — Automated pre-merge pipeline (test → review → version bump → PR)
- `/land-and-deploy` — Merge PR + verify production
- `/canary` — Post-deploy SRE monitoring
- `/benchmark` — Page load / Core Web Vitals baseline
- `/browse` — Persistent headless Chromium browser
- `/qa` — QA Lead: real browser testing + bug fixes
- `/qa-only` — QA report only, no code changes
- `/design-review` — Design audit + fix loop
- `/setup-browser-cookies` — Import browser cookies for authenticated testing
- `/setup-deploy` — One-time deploy configuration
- `/retro` — Engineering retrospective
- `/investigate` — Systematic root-cause debugger
- `/document-release` — Update docs to match shipped code
- `/codex` — Second opinion from OpenAI Codex
- `/cso` — Chief Security Officer audit
- `/autoplan` — CEO + design + eng review in one command
- `/careful` — Safety guardrails for destructive operations
- `/freeze` — Lock file edits to one directory
- `/guard` — `/careful` + `/freeze` combined
- `/unfreeze` — Remove edit lock
- `/gstack-upgrade` — Self-updater

## CI 质量检查规则

**CRITICAL**: 所有代码必须在推送前通过 CI 检查。遵守以下规则避免 CI 失败：

### 编码前必读
详细规则见 [docs/ai-coding-rules.md](docs/ai-coding-rules.md)

### 快速检查清单

每次编写代码后，立即检查：

1. **Import 排序** (Ruff I001)
   - 顺序：stdlib → third-party → local
   - 同组内字母排序
   - 运行：`uv run ruff check <file> --fix`

2. **类型注解** (MyPy)
   - 所有变量、参数、返回值都要有明确类型
   - 字典必须注解：`hashes: dict[str, str | None] = {}`
   - 可选类型显式声明：`self.value: str | None`
   - 仅检查 `tree_sitter_analyzer/` 目录

3. **异常处理** (Ruff B904)
   - 重抛异常使用 `from None` 或 `from err`
   - `raise ValueError("msg") from None`

4. **现代语法** (Ruff UP006)
   - 使用 `dict` 而非 `Dict`
   - 使用 `list` 而非 `List`

5. **zip() 参数** (Ruff B905)
   - `zip(a, b, strict=True)`

### 本地 CI 检查（推送前必跑）

```bash
# 完整检查（推荐）
.github/scripts/local-ci-check.sh

# 快速检查（跳过测试）
SKIP_TESTS=1 .github/scripts/local-ci-check.sh

# 单个文件
uv run ruff check <file> --fix && uv run mypy <file> --strict
```

### 自动检查（推荐设置）

```bash
# 设置 pre-commit hook，每次提交自动检查
ln -sf ../../.github/scripts/pre-commit-check.sh .git/hooks/pre-commit
```

### AI 编码工作流

```
1. 写代码
   ↓
2. ruff check --fix  ← 立即修复格式问题
   ↓
3. mypy --strict     ← 修复类型错误
   ↓
4. git commit        ← 触发 pre-commit hook (可选)
   ↓
5. 本地 CI 检查      ← 推送前最后确认
   ↓
6. git push          ← GitHub Actions CI
```

### 禁止行为

- ❌ 不要写未使用的 import
- ❌ 不要使用没有占位符的 f-string
- ❌ 不要遗漏类型注解
- ❌ 不要使用已弃用的 `typing.Dict/List`
- ❌ 不要在推送前跳过 CI 检查
