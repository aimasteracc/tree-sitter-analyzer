---
name: tsa-constraints
version: 1.0.0
description: |
  Architectural constraint enforcement. Detect forbidden cross-module calls
  ("MCP must not depend on CLI") at index time and gate edits on them. Rules
  live in YAML at repo root; violations bubble up through safe_to_edit and
  change_impact as UNSAFE verdicts.

  Use when:
  - User asks "does this PR break architecture?"
  - Pre-merge gate: "any forbidden edges?"
  - User wants to ADD a new architectural rule
  - You see a verdict=UNSAFE and want to understand why
  - Onboarding: "what are the architectural rules of this repo?"

  Replaces: tribal-knowledge architecture reviews + manual import audits
  (~5-15k tokens) with 1 MCP call (~200 tokens) + a YAML file (the rules).
allowed-tools:
  - mcp__tree-sitter-analyzer__check_constraints
  - mcp__tree-sitter-analyzer__safe_to_edit
  - Bash
  - Read
  - Edit
  - Write
---

# tsa-constraints — Inhibitory edges as code

> Bio-analogy: **inhibitory synapses** — declared "X must NOT call Y" rules
> that fire UNSAFE verdicts when violated. Rules live in
> `architectural-constraints.yml` at repo root, are evaluated against the
> persisted call graph, and persist violations in SQLite for fast re-reads.

## When to use

| Goal                                       | Action                                |
|--------------------------------------------|---------------------------------------|
| List current rules                         | Read `architectural-constraints.yml`  |
| Check repo against rules                   | `check_constraints` (no args)         |
| Pre-edit gate (includes rule check)        | `safe_to_edit` (auto)                 |
| Add a new rule                             | Edit YAML + re-run `check_constraints`|
| Filter violations by severity              | `check_constraints(severity_min="error")` |
| Filter by path                             | `check_constraints(path_filter="mcp/**")` |

## Procedure

### One-shot audit

```
check_constraints()
```

Returns:
```yaml
success: true
verdict: SAFE | CAUTION | UNSAFE
violations: [
  {rule_id, caller_file, caller_line, callee_name, callee_file, severity, reason}
]
rule_count: <int>
evaluated_edge_count: <int>
```

Verdict cascade:
- `UNSAFE` → any error-severity violation
- `CAUTION` → any warn-severity violation
- `SAFE` → none

### Adding a new rule

1. Open `architectural-constraints.yml` at repo root
2. Append:
   ```yaml
   - id: <slug, kebab-case>
     severity: error | warn | info
     rule: forbid
     from: "path/glob/**"
     to:   "path/glob/**"
     reason: "<why this is forbidden>"
     exceptions: ["specific/file.py"]   # optional
   ```
3. Run `check_constraints` to see if existing code violates the new rule
4. Either: fix the violations OR add them to `exceptions`

### Reading violations

For each violation row:
- `rule_id` — which rule fired (look it up in the YAML for `reason`)
- `caller_file:caller_line` — the offending call site
- `callee_file` — what it's calling (may be empty if callee unresolved)
- `severity` — `error` = block, `warn` = surface only, `info` = noise

## DSL semantics

- `rule: forbid` — currently the only supported rule type (MVP)
- `from` / `to` — fnmatch-style globs (`**` for recursive)
- `exceptions` — caller-side globs that bypass the rule
- Unknown top-level keys → fatal parse error
- Unknown per-rule keys → warn + skip (forward-compat)

## Default rules in THIS repo

Inspect:
```bash
cat architectural-constraints.yml
```

Current 3 rules (as of last commit):
1. `mcp-must-not-depend-on-cli` — MCP tools are runtime adapters; CLI imports MCP, never reverse
2. `language-plugins-isolated` — language plugins can't know about MCP
3. `core-must-not-import-mcp` — core analysis primitives precede MCP layer

## CLI equivalents

```bash
uv run tree-sitter-analyzer --check-constraints --output-format toon
uv run tree-sitter-analyzer --check-constraints --severity-min error
uv run tree-sitter-analyzer --check-constraints --constraint-path-filter "mcp/**"
uv run tree-sitter-analyzer --check-constraints --constraint-file path/to/alt-rules.yml
```

Exit codes mirror `--change-impact`:
- 0 → SAFE
- 2 → CAUTION (warn-only)
- 1 → UNSAFE (error severity)

CI gating example:
```bash
uv run tree-sitter-analyzer --check-constraints || exit 1   # block PR on UNSAFE
```

## Anti-patterns

- Don't write a rule per file — use globs (`tree_sitter_analyzer/mcp/**`)
- Don't set severity=info on rules you actually want enforced (info = visible only)
- Don't forget `reason:` — agents reading violations need it to suggest fixes
- Don't disable via `--no-constraints` in CI — that defeats the gate's purpose

## Decision surface

```yaml
verdict: SAFE | CAUTION | UNSAFE
violations: [...]   # empty when SAFE
rule_count: <int>
evaluated_edge_count: <int>
```
