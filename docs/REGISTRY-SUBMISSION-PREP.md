# Registry Submission Prep — [HUMAN] steps 14-16

This document contains the submission texts and materials for Steps 14, 15, and 16
of the visibility campaign plan.  The AI has prepared these materials; a human
operator must perform the actual submissions.

**Do not submit any of these without reviewing for accuracy first.**

---

## Step 14: Official MCP Registry (registry.modelcontextprotocol.io)

**Method:** `mcp-publisher` CLI with GitHub OAuth.

**Prerequisites:**
- `server.json` at repo root (already created).
- GitHub account `aimasteracc` with OAuth access to `mcp-publisher`.
- **PyPI ownership marker**: the published PyPI package README must contain the line
  `mcp-name: io.github.aimasteracc/tree-sitter-analyzer`
  before `mcp-publisher publish` will pass ownership verification
  (see https://modelcontextprotocol.io/registry/package-types#pypi-packages).
  Add this line to `README.md` under a dedicated `## MCP Registry` section and
  publish a new PyPI release first.

**Command (human executes after OAuth login):**

```bash
# Install mcp-publisher (Homebrew or direct download — see registry quickstart)
brew install modelcontextprotocol/tap/mcp-publisher
# or: download binary from https://github.com/modelcontextprotocol/registry/releases

# Authenticate with GitHub OAuth:
mcp-publisher login github

# From the tree-sitter-analyzer repo root:
mcp-publisher publish
```

**Verify after submission:**
- Visit https://registry.modelcontextprotocol.io/servers/io.github.aimasteracc%2Ftree-sitter-analyzer
- Confirm `name`, `description`, `version`, and `packages` fields match `server.json`.

**Key fields to double-check before submitting:**
- `name`: `io.github.aimasteracc/tree-sitter-analyzer`
- `version`: matches current PyPI release (currently `1.29.0`)
- `description`: no unattributable statistics; ratio language uses both 124x and 390x
  with methodology labels (per `docs/CONTENT_GUIDELINES.md`).

---

## Step 15: mcpservers.org/submit

**Method:** Web form at https://mcpservers.org/submit

**Submission text (copy-paste ready):**

```
Name: tree-sitter-analyzer

Short description (1-2 sentences):
Cross-language-safe code-intelligence MCP for AI agents. Provides a
family-gated call graph that produces zero cross-language mis-wires on
four polyglot repos (Rust+Python+JS, Go, etc.), compared to hundreds
from name-only indexes.

Full description:
tree-sitter-analyzer is a local, no-external-service MCP server that
gives AI agents accurate, language-aware code intelligence across 13
programming languages. Its key differentiator is the family-gated call
graph: every edge is checked for language compatibility before binding,
so a Python caller is never wired to a Swift definition just because
they share a name.

Key facts:
- 8 facade MCP tools covering search, navigation, structure, health,
  editing, project management, indexing, and visualization
- 13 curated skills for common code-intelligence patterns
- 0 cross-language mis-wires measured on 3 external polyglot open-source repos
  (huggingface/tokenizers, astral-sh/ruff, pola-rs/polars — see GAUNTLET.md)
- TOON-compressed output to keep agent context usage low
- 100% local — no external API, no internet required after install
- MIT license

Install:
  uvx --from tree-sitter-analyzer tree-sitter-analyzer-mcp

Repository: https://github.com/aimasteracc/tree-sitter-analyzer
PyPI: https://pypi.org/project/tree-sitter-analyzer/
License: MIT
```

**URL field:** `https://github.com/aimasteracc/tree-sitter-analyzer`

---

## Step 16: Claude Skills marketplace

**Method:** Manual submission to agentskill.club or equivalent Claude Skills
marketplace directory.

**13 curated skills (GitHub URL format):**

The skills are located in `.claude/skills/tsa-*/SKILL.md` in the repository.
Submit the following list with GitHub URLs:

| Skill name | URL |
|---|---|
| tsa-landing | https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/.claude/skills/tsa-landing/SKILL.md |
| tsa-find | https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/.claude/skills/tsa-find/SKILL.md |
| tsa-graph | https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/.claude/skills/tsa-graph/SKILL.md |
| tsa-structure | https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/.claude/skills/tsa-structure/SKILL.md |
| tsa-deps | https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/.claude/skills/tsa-deps/SKILL.md |
| tsa-health-watch | https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/.claude/skills/tsa-health-watch/SKILL.md |
| tsa-index | https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/.claude/skills/tsa-index/SKILL.md |
| tsa-edit-safety | https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/.claude/skills/tsa-edit-safety/SKILL.md |
| tsa-edit-then-verify | https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/.claude/skills/tsa-edit-then-verify/SKILL.md |
| tsa-temporal | https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/.claude/skills/tsa-temporal/SKILL.md |
| tsa-refactor-queue | https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/.claude/skills/tsa-refactor-queue/SKILL.md |
| tsa-pr-review | https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/.claude/skills/tsa-pr-review/SKILL.md |
| tsa-constraints | https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/.claude/skills/tsa-constraints/SKILL.md |

**Submission text for marketplace listing:**

```
tree-sitter-analyzer Claude Skills

13 curated skills for code-intelligence workflows with AI agents.
Each skill provides a step-by-step protocol for a common task:
finding callers/callees, understanding module structure, analyzing
call graphs, monitoring health scores, planning edits safely, and
reviewing PRs with AST-grounded context.

All skills are designed for tree-sitter-analyzer's 8-facade MCP surface.
They are language-agnostic and work on any of the 13 supported languages.

Repository: https://github.com/aimasteracc/tree-sitter-analyzer
License: MIT
```

---

*Prepared by: AI (general-builder) as part of the visibility-credibility-hygiene
campaign.  Human operator must review and execute all submissions.*
