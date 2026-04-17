# Project Radar — 项目雷达

## Goal

**一句话定义:** One CLI command shows the most important files in your codebase — which are risky, who owns them, and what depends on them.

**一句话定义 (中文):** 一条命令展示项目中最关键的文件 — 哪些有风险、谁负责、什么依赖它们。

## Problem Statement

tree-sitter-analyzer has 31 MCP tools for code analysis, but developers must run multiple commands to get a complete picture of project health:
- `complexity_heatmap` for file complexity
- `semantic_impact` for blast radius
- `dependency_query` for dependencies
- Git commands for churn and ownership

**User pain:** "I just joined this project. Which files should I be careful with? Who do I ask about each file? What will break if I change something?"

## MVP Scope

**Core functionality:**
1. Git churn analysis (commit frequency per file)
2. Code ownership detection (top contributor per file via git blame)
3. Risk scoring (complexity × churn × blast radius)
4. Unified CLI output (`tree-sitter radar`)

**MVP constraints:**
- Support Python, JavaScript, TypeScript, Java, Go (top 5 languages)
- Single command invocation
- Text-based output (no interactive UI for MVP)
- Local git repository required

**Out of scope for MVP:**
- Interactive web UI (defer to v2)
- Historical trend analysis (defer to v2)
- Team-level insights (defer to v2)

## Technical Approach

### Architecture

```
Project Radar
    ↓
┌─────────────────────────────────────────┐
│  Data Collection (parallel)             │
│  ├─ Git Analyzer (churn + ownership)    │
│  ├─ Complexity Analyzer (existing)      │
│  ├─ Dependency Graph (existing)         │
│  └─ Semantic Impact (existing)          │
├─────────────────────────────────────────┤
│  Risk Scoring Engine                     │
│  └─ Normalize metrics × 3               │
├─────────────────────────────────────────┤
│  Output Formatter                        │
│  └─ TOON + Markdown tables               │
└─────────────────────────────────────────┘
```

### Components

**1. Git Analyzer (`tree_sitter_analyzer/analyzer/git_analyzer.py`)**
```python
class GitAnalyzer:
    def get_file_churn(self, repo_path: str, since: str = "6 months ago") -> dict[str, int]:
        """Return commit count per file."""

    def get_file_ownership(self, repo_path: str) -> dict[str, str]:
        """Return top contributor (email) per file via git blame."""
```

**2. Risk Scoring Engine (`tree_sitter_analyzer/analyzer/risk_scoring.py`)**
```python
@dataclass
class FileRisk:
    path: str
    complexity_score: float  # 0-1, from complexity_heatmap
    churn_score: float       # 0-1, commits normalized
    impact_score: float      # 0-1, from semantic_impact
    overall_risk: float      # weighted average

def calculate_risk(files: list[str]) -> list[FileRisk]:
    """Combine metrics into unified risk score."""
```

**3. CLI Command (`tree_sitter_analyzer/cli/commands/radar_command.py`)**
```bash
tree-sitter radar [--top N] [--since TIME] [--format FORMAT]
```

### Reuses Existing Tools

| Existing Component | Usage |
|--------------------|-------|
| `complexity_heatmap` | Get per-file complexity scores |
| `semantic_impact` | Get per-file blast radius |
| `dependency_graph` | Get dependency relationships |
| TOON formatter | Output format |

### Sprint Breakdown

**Sprint 1: Git Analyzer (2-3 days)**
- Implement `get_file_churn()` using `git log --name-only`
- Implement `get_file_ownership()` using `git blame`
- Add caching for git operations (expensive)
- 15+ tests

**Sprint 2: Risk Scoring Engine (2-3 days)**
- Implement `FileRisk` dataclass
- Create normalization functions (min-max scaling)
- Implement weighted risk calculation
- 15+ tests

**Sprint 3: CLI + MCP Integration (2-3 days)**
- Create `tree-sitter radar` CLI command
- Implement output formatters (TOON + Markdown)
- Register `project_radar` MCP tool
- 15+ tests

**Total:** 45+ tests, ~200-300 lines of new code

## Success Criteria

- [ ] Single command produces unified project health view
- [ ] Shows top 20 riskiest files with metrics
- [ ] Includes churn (commits/month) and ownership (email)
- [ ] Runs in <5 seconds for medium repo (<1000 files)
- [ ] 45+ tests passing
- [ ] CLI + MCP tool both functional

## Distribution Plan

**Installation:**
```bash
pip install tree-sitter-analyzer[radar]
```

**CI/CD:**
- Existing GitHub Actions pipeline
- Add integration test with real git repo

## Dependencies

**Required:**
- git (system tool, assumed present)
- tree-sitter-analyzer core (existing)

**Existing modules to reuse:**
- `tree_sitter_analyzer/analysis/complexity.py`
- `tree_sitter_analyzer/analysis/semantic_impact.py`
- `tree_sitter_analyzer/analysis/dependency_graph.py`

**New modules:**
- `tree_sitter_analyzer/analyzer/git_analyzer.py`
- `tree_sitter_analyzer/analyzer/risk_scoring.py`
- `tree_sitter_analyzer/cli/commands/radar_command.py`
