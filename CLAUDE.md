# Ruflo — Claude Code Configuration

## Rules

- Do what has been asked; nothing more, nothing less
- NEVER create files unless absolutely necessary — prefer editing existing files
- NEVER create documentation files unless explicitly requested
- NEVER save working files or tests to root — use `/src`, `/tests`, `/docs`, `/config`, `/scripts`
- ALWAYS read a file before editing it
- NEVER commit secrets, credentials, or .env files
- Keep files under 500 lines
- Validate input at system boundaries

### Exact assertions only — no `>=` / approximate test assertions

**🔒 LOCKED BY USER (2026-06-10):** 「测试拒绝大于等于这样的约等不严谨的测试」。
Count/measurement assertions in tests MUST pin the **exact** expected value
(`== 11`), never a loose bound (`>= 10`, `> 0`, `<= 100`) that lets drift pass
silently. If an upstream change (e.g. a grammar-version bump) shifts the
number, the test SHOULD go red and force a conscious re-pin with the new
measured value — an approximate green is a false green. Reviewer suggestions
to "relax to a lower bound for resilience" are REJECTED under this rule.
Legitimate exceptions are rare and only where the value is genuinely
nondeterministic (timing, memory) — and then the test should assert a
documented invariant, not a hand-waved bound on a deterministic count.

## Deliberate design decisions — do NOT "fix" these

These look like inconsistencies in a dogfood pass, but they are intentional and reflect the project's design priorities. Reverting them costs real value. **If a dogfood agent proposes any of the items below as a "finding", REJECT the finding and link the agent back to this section.**

### 1. MCP defaults to TOON; CLI defaults to JSON — LOCKED

- **Why**: TOON is 50-70% more token-efficient than JSON. MCP callers are LLM agents — token cost is real money. CLI callers are humans / shells — JSON is human-readable and pipes into `jq`.
- **Symptom that looks like a bug**: `MCP execute()` returns `{format: "toon", toon_content: "..."}` while CLI returns a parsed dict.
- **Correct action**: leave the defaults alone. If TOON-vs-JSON divergence causes a real bug, fix the divergence (e.g. make TOON carry the same scalar fields, per F7/N8), don't flip the default.
- **Past incident**: r36 attempted "R3: flip MCP output_format default to json" — rolled back. The token savings outweigh the parity argument.
- **🔒 LOCKED BY USER (r37b)**: 用户明确指示「默认使用 toon，不用使用 json，不让 ai agent 修改这个」. Any AI agent that proposes flipping MCP defaults from `toon` → `json`, or removes the `"toon"` default literal in `arguments.get("output_format", "toon")` for any MCP tool, is **violating a user-locked design decision**. The cost analysis is settled: token savings win over parity. **REJECT such proposals at the brief stage. Do not even read the dogfood agent's reasoning beyond seeing the words "flip default" or "toon to json".**

### 2. project_root canonicalisation is a foundational change

- **Why**: macOS `/var/folders/...` symlinks to `/private/var/folders/...`. Naive `os.path.abspath()` doesn't resolve the symlink but `realpath()` does. The SecurityValidator and test fixtures use different resolutions, so any change to `BaseMCPTool.__init__` propagates through 164+ tests.
- **Symptom that looks like a bug**: MCP `edit action=safe` (formerly `safe_to_edit`) with `project_root='.'` returns SAFE while CLI returns UNSAFE (different downstream counts because `DependencyGraph('.')` walks a different tree than `DependencyGraph('/abs/path')`).
- **Correct action**: if you fix this, study the macOS symlink behavior and the test fixture conventions FIRST. Use `os.path.abspath` only after confirming SecurityValidator / PathResolver / test fixtures all use the same resolution. Test on macOS specifically. Land it in a dedicated commit, never bundled with other fixes.
- **Past incident**: r36 attempted "R1: canonicalise project_root in BaseMCPTool" — broke 164 tests on macOS, rolled back.

### 3. CLI INFO/diagnostic output → stderr; JSON/TOON payload → stdout

- **Why**: This was correctly fixed in r34 (Q2). DO NOT revert it. `print(message)` calls in CLI code MUST go to `sys.stderr` unless they emit machine-readable data to stdout.

### 4. Markdown smell-detection is intentionally OFF in `project_health`

- **Why**: r34 Q4 narrowed `PROJECT_HEALTH_SOURCE_EXTS` to code-only. `.md` files no longer count for code-quality grading. Re-adding markdown would re-inflate the C-grade bucket with golden_master fixtures.
- **Correct action**: if you want to score markdown structure, build a separate `markdown_health` tool. Don't merge it back into `project_health`.

## Code intelligence analysis — lessons learned (2026-05-30)

Rules distilled from a full mycelium + call-graph analysis sprint. Violations here cost hours of rework.

### 5. Static call graph ≠ test coverage — do NOT use it as a coverage proxy

**Why**: `conftest.py` has a `reset_global_singletons()` with `autouse=True` that imports ~50 modules and calls methods on them before/after every test. This pollutes the static call graph: every test file appears to call every singleton method, producing meaningless caller counts (e.g., `HealthHistory.append` shows 183 test-file callers; actual direct callers: ~3). `execute()` on any `BaseMCPTool` subclass shows 1511 callers because dynamic dispatch is unresolvable statically.

**Correct action**: Use `pytest-cov` for real coverage data. Use static call graphs only for "zero-coverage detection" (methods with 0 callers are definitely untested) — the false positives only go high, never low.

**Symptom that looks real but isn't**: `test_go_plugin.py` appears to test `PythonPlugin` methods — this is conftest fixture contamination, not actual coverage.

### 6. `--callers "ClassName.method"` requires AST cache to have receiver field populated

**Why**: Three code layers historically dropped the `class` field: `_build_function_entry`, `CachedCallGraph._build_from_cache`, and `CodeGraphCallersTool` used the SQL fast-path which stores bare callee names. Fixed in commit 3ced467a.

**Debug protocol when `--callers "ClassName.method"` returns NOT_FOUND**:
1. Verify the class is known: `--class-hierarchy mode=subclasses --class-hierarchy-class BaseClass`
2. Check if the method exists under the qualified receiver in the AST cache
3. If it returns NOT_FOUND but bare name works: the SQL path is being used (qualified name should now bypass it — verify you're on commit ≥ 3ced467a)

### 7. After changing the LanguagePlugin interface, always test cli/info_commands

**Why**: `cli/info_commands.py` (15 methods: `--show-supported-languages`, `--show-supported-extensions`, etc.) has **zero tests** and reads directly from the plugin registry. Any change to `REQUIRED_PLUGIN_METHODS`, plugin removal, or extractor interface changes can silently break these commands. The call graph won't catch this because the commands are never called by tests.

**Mandatory check**: After any plugin interface change, run:
```bash
uv run python -m tree_sitter_analyzer --show-supported-languages
uv run python -m tree_sitter_analyzer --show-supported-extensions
```
and verify the output is sane before committing.

### ⚠️ 规则 8/9 事实核查（2026-06-02 — 命令语法已过时，开用前必读）

下方规则 8/9 引用的 `mycelium subclasses-tree` / `get-descendants` / `get-all-symbols --prefix` 命令，在 2026-06-02 实测的 **Rhizome v0.11.6**（github.com/basidiocarp/rhizome，Mycelium 生态当前的 standalone code-intel MCP）中**不存在** —— Rhizome v0.11.6 没有任何专门的继承/层级遍历子命令（recon 实锤，见 memory `tsa-vs-mycelium-rhizome` + `.recon/recon-mycelium.md`）。这两条规则可能引用了已停用/改名的早期 mycelium 工具，或一个不同的工具。

- **不要照抄下方命令语法** —— 先确认你当前使用的工具是否真有这些子命令。
- 底层*教训*仍可能适用于任意继承查询工具：(8) 用裸类名而非 `file>Class` 路径做反向继承查询；(9) "explicit override" 视图通常不含继承成员，需 cross-check ABC 提供的默认方法。
- **首选**改用 TSA 自己的工具（见规则 10）：`--class-hierarchy mode=subclasses --class-hierarchy-class LanguagePlugin`。

### 8. mycelium: use bare class name for inheritance queries, not file>Class path

**Why**: After the Extends-edge fix (mycelium PR #263/#264), extends edges store the unresolved base name `"LanguagePlugin"`, not the full path. Reverse lookup by full path only finds same-file subclasses.

**Correct**:   `mycelium subclasses-tree "LanguagePlugin"` → finds all 21 plugins  
**Wrong**:     `mycelium subclasses-tree "plugins/base.py>LanguagePlugin"` → finds only DefaultLanguagePlugin

### 9. mycelium `get-descendants` shows ONLY explicitly-defined methods, NOT inherited ones

**Why**: `--include-inherited` depends on resolved Extends edges pointing to the full-path base class symbol. Cross-file resolution is not yet complete (mycelium issue #261 partially fixed). Using `get-descendants` alone to compare plugin interface compliance will falsely conclude that 16/21 plugins are "missing" methods that are actually inherited from the ABC.

**Correct approach**: Compare explicit-override sets via `get-descendants` then cross-check against the ABC using `mycelium get-all-symbols --prefix "plugins/base.py"` to identify what the base provides by default.

### 10. Before writing custom Python AST scripts, try TSA's own tools first

In order: `--class-hierarchy`, `--callers`, `--callees`, `--call-graph`, `--class-hierarchy mode=tree`. These exist and work. Writing a 50-line Python script to answer "what subclasses does LanguagePlugin have" is wasted effort — `--class-hierarchy mode=subclasses --class-hierarchy-class LanguagePlugin` gives the same answer in one command.

### 11. A non-functional claim (cost / size / latency) is a BELIEF until it is an executable invariant

**Why (incident, 2026-06-08):** The MCP TOON response was ~**1.96× the size of plain JSON** for metadata-heavy decision tools — the "token-efficient" format was nearly twice as expensive as the one it replaced. ~18,000 tests were green throughout. A **human using the tool** found it; the suite never could. Root cause: the suite is a *conformance* net (does the code match its spec?), and it **cannot discover that the spec itself is wasteful**. The premise — CLAUDE.md §1's "TOON is 50-70% more token-efficient" — lived only as prose, so it was never falsifiable. (Worse: the bug was *self-protecting* — 62 test files asserted the duplicated shape as "correct", so the fix broke them.)

**Rules:**
1. **Any claim about cost/size/latency/token-count in a design doc MUST have a matching executable invariant** in `tests/unit/mcp/test_output_cost_invariants.py` (or a perf-budget test). If it isn't measured in CI, it is a belief, not a fact — and beliefs rot silently.
2. **Assert "is it good?", not only "does it match?".** Conformance tests (`assert field == X`, `set(keys) <= SURFACE`) verify intent; they cannot question intent. Add at least one test that measures the *value* (bytes, ratio, count) and asserts a **documented relationship** (`toon ≤ json`, `compact < default`) or an exact pin — NEVER a hand-waved numeric ceiling (`ratio <= 2.5` passed for months while the bug sat at 1.96×; see the exact-assertion rule above).
3. **Locked/"settled" design claims carry their evidence.** A LOCKED decision (e.g. §1) must cite a **measurement command + last-measured date**; "the cost analysis is settled" without a number is the exact framing that shielded this bug. Re-measure on a cadence.
4. **Dogfood means USE + MEASURE, not run-the-suite.** A dogfood round must actually invoke tools and look at the bytes/tokens. Green tests prove self-consistency, not quality — discovering a wrong belief needs input from *outside* the loop (real use, or an outside reviewer; cf. Codex catching the `deprecation`-dropping test that was itself protecting a bug).
5. **Prefer differential/ratchet invariants.** Assert *relationships* (`toon ≤ json`, `compact < default`) and use `strict` xfail to track a known-bad invariant so that *fixing it forces un-xfailing it* — the cost can never silently regress back.

## Dogfood-finding triage rules (when you receive a list of bugs from a dogfood agent)

Before dispatching a fix agent for any finding, ask:

1. **Is this a deliberate design decision?** Cross-check against the section above. If yes → REJECT, document, move on.
2. **Does the proposed fix flip a default that exists for performance reasons?** (token cost, runtime, etc.) → REJECT unless the user explicitly approves.
3. **Does the fix touch BaseMCPTool, PathResolver, SecurityValidator, or the plugin registry?** → SOLO commit with macOS gate-check; never bundle with cosmetic fixes.
4. **Did the dogfood agent assume a non-existent flag exists?** (e.g. `--smart-context --query` when `--smart-context` is a bare flag) → REJECT as agent-error, not a bug.
5. **Is the divergence cross-tool (e.g. CLI vs MCP)?** → check whether the asymmetry is intentional (see section above) before unifying.

If a finding survives all five checks, dispatch a fix agent. Otherwise log the rejection rationale and skip it. **A dogfood round that fixes the wrong things is worse than one that finds nothing.**

## Agent Comms — Reality-Based Coordination

**Tool-availability asymmetry:** `SendMessage` works **lead↔subagent** and lead↔lead, but **NOT subagent↔subagent**. Subagents spawned via the `Agent` tool are stateless one-shot workers — they have no inbox, cannot wait for events, and `SendMessage`/`TaskUpdate` are typically not in their tool allowlists. The `hive-mind_*` MCP tools provide coordination **metadata** (registry, consensus state) but do NOT grant subagents communication channels. Patterns that assume peer messaging will silently fail — agents either abort cleanly or run open-loop with stale assumptions. (See ruvnet/ruflo#2028 for the diagnosis.)

### Canonical pattern: memory-as-bus, lead-orchestrated phases

```
Lead (the orchestrator)
  │
  ├─ spawns agent → agent reads inputs from memory keys → writes outputs to memory keys → completes
  │
  ├─ verifies outputs in memory
  │
  └─ spawns next agent with explicit input-key list in its brief
```

All inter-agent state lives in a shared memory namespace (`memory_store` / `memory_search`). Lead-to-subagent `SendMessage` is fine when needed; subagent-to-subagent `SendMessage` is not.

### Spawning rules

- **Parallelize ONLY when work is genuinely independent** (no upstream dependency between siblings).
- **Spawn dependent agents only after the lead confirms upstream outputs are in memory.** Do NOT tell a downstream agent to "WAIT for SendMessage from X" — it has no mechanism to wait; it will abort.
- **Every subagent brief MUST include a degraded-mode paragraph** at the top: *"If your expected coordination tools (SendMessage, TaskUpdate, hive-mind_*) are missing, do NOT abort. Read these specific source files directly, write outputs to these specific memory keys, and complete your phase."*
- **Name agents** — `name: "role"` makes them addressable by the lead even though they cannot address each other.
- **After spawning**: STOP, tell user what's running, wait for completion notifications. No polling.

### Subagent engineering principles (dev/research briefs)

Every **dev / research / fix** subagent brief MUST also carry these four principles
(adapted from Karpathy's LLM-coding-pitfalls list). The key adaptation for this
project: the audience for "ask / surface" is the **lead**, never the end user —
and an uncertain agent picks a reasonable default, flags it, and **keeps going**
(a subagent has no inbox; pausing = wasted run). Do NOT send these to **review**
subagents — they must stay adversarial truth-seekers, not style-followers.

1. **Think before coding (report to the lead, never block).** In your final
   return, state your assumptions explicitly; if multiple interpretations exist,
   list them and pick one *with a reason* (don't pick silently); surface any
   inconsistency or simpler approach you notice. If something is unclear, assume
   the most reasonable default, finish the task, and note *"assumed X — lead,
   correct if wrong."* Never stop the pipeline waiting for a human.
2. **Simplicity first.** Minimum code that solves the task, nothing speculative —
   no features/abstractions/config/impossible-case error handling that weren't
   asked for. If 200 lines could be 50, rewrite it.
3. **Surgical changes.** Touch only what the task needs; every changed line
   traces to the task. Don't "improve" adjacent code/comments/formatting, don't
   refactor what isn't broken, match existing style. Clean up only the orphans
   *your* change created; pre-existing dead code you only *mention*, never delete
   (unless asked). Reinforces the focused-PR rule.
4. **Goal-driven execution.** Turn the task into a verifiable goal: write the
   failing test first (RED), then implement to green; for multi-step work, state
   a brief `step → verify` plan. Strong success criteria let you loop
   independently; weak ones ("make it work") force round-trips.

The lead also honors 2–4; for principle 1 the lead's "report" audience is the
investor's node-level Chinese briefing — but the lead likewise never pauses for
permission.

### Spawning example (memory-as-bus)

```javascript
// Phase 1 — independent parallel work
Agent({
  prompt: "Read docs at <paths>. Write inventory JSON to memory key phase1/researcher/inventory in namespace <ns>. Degraded mode: if memory tools missing, return inventory in your final message.",
  subagent_type: "researcher", name: "researcher", run_in_background: true
})
Agent({
  prompt: "Walk the source tree. Write capability matrix to memory key phase1/coder/capability-matrix. Degraded mode: ...",
  subagent_type: "coder", name: "source-reader", run_in_background: true
})

// AFTER both Phase 1 agents complete (lead verifies via memory_search), THEN spawn Phase 2.
// Each Phase 2 agent's brief explicitly lists the Phase 1 memory keys it should read.
```

### Patterns

| Pattern | Flow | Use When |
|---------|------|----------|
| **Sequential pipeline** | Lead → A → (verify in memory) → B → (verify) → C | Phase dependencies (audit, complex refactor) |
| **Fan-out** | Lead → A, B, C (parallel) → Lead aggregates from memory | Independent parallel work (research, multi-lens critique) |
| **Lead-as-bus** | Subagents → Lead → reroute by spawning next | Workaround when supervisor↔workers coordination needed |

### Anti-patterns (will silently fail)

- "WAIT for SendMessage from X" in a subagent prompt — no mechanism to wait
- "SendMessage findings to architect" in a subagent prompt — architect can't receive
- Spawning N dependent agents in one batch expecting them to chain via messages — they won't
- Relying on `hive-mind_consensus` to gather subagent votes — subagents aren't registered hive workers

### Lead-only SendMessage (still works)

`SendMessage` is still useful for **lead → subagent** redirects and priority changes:

```javascript
// Lead → subagent: redirect or update priority mid-flight
SendMessage({ to: "developer", summary: "Prioritize auth", message: "Auth is blocking tester, do that first." })
// Lead → subagent: graceful shutdown
SendMessage({ to: "developer", message: { type: "shutdown_request" } })
```

## Swarm & Routing

### Config
- **Topology**: hierarchical-mesh (anti-drift)
- **Max Agents**: 15
- **Memory**: hybrid
- **HNSW**: Enabled
- **Neural**: Enabled

```bash
npx @claude-flow/cli@latest swarm init --topology hierarchical --max-agents 8 --strategy specialized
```

### Agent Routing

| Task | Agents | Topology |
|------|--------|----------|
| Bug Fix | researcher, coder, tester | hierarchical |
| Feature | architect, coder, tester, reviewer | hierarchical |
| Refactor | architect, coder, reviewer | hierarchical |
| Performance | perf-engineer, coder | hierarchical |
| Security | security-architect, auditor | hierarchical |

### When to Swarm
- **YES**: 3+ files, new features, cross-module refactoring, API changes, security, performance
- **NO**: single file edits, 1-2 line fixes, docs updates, config changes, questions

### 3-Tier Model Routing

| Tier | Handler | Use Cases |
|------|---------|-----------|
| 1 | Agent Booster (WASM) | Simple transforms — skip LLM, use Edit directly |
| 2 | Haiku | Simple tasks, low complexity |
| 3 | Sonnet/Opus | Architecture, security, complex reasoning |

## Memory & Learning

### Before Any Task
```bash
npx @claude-flow/cli@latest memory search --query "[task keywords]" --namespace patterns
npx @claude-flow/cli@latest hooks route --task "[task description]"
```

### After Success
```bash
npx @claude-flow/cli@latest memory store --namespace patterns --key "[name]" --value "[what worked]"
npx @claude-flow/cli@latest hooks post-task --task-id "[id]" --success true --store-results true
```

### MCP Tools (use `ToolSearch("keyword")` to discover)

| Category | Key Tools |
|----------|-----------|
| **Memory** | `memory_store`, `memory_search`, `memory_search_unified` |
| **Bridge** | `memory_import_claude`, `memory_bridge_status` |
| **Swarm** | `swarm_init`, `swarm_status`, `swarm_health` |
| **Agents** | `agent_spawn`, `agent_list`, `agent_status` |
| **Hooks** | `hooks_route`, `hooks_post-task`, `hooks_worker-dispatch` |
| **Security** | `aidefence_scan`, `aidefence_is_safe`, `aidefence_has_pii` |
| **Hive-Mind** | `hive-mind_init`, `hive-mind_consensus`, `hive-mind_spawn` |

### Background Workers

| Worker | When |
|--------|------|
| `audit` | After security changes |
| `optimize` | After performance work |
| `testgaps` | After adding features |
| `map` | Every 5+ file changes |
| `document` | After API changes |

```bash
npx @claude-flow/cli@latest hooks worker dispatch --trigger audit
```

## Agents

**Core**: `coder`, `reviewer`, `tester`, `planner`, `researcher`
**Architecture**: `system-architect`, `backend-dev`, `mobile-dev`
**Security**: `security-architect`, `security-auditor`
**Performance**: `performance-engineer`, `perf-analyzer`
**Coordination**: `hierarchical-coordinator`, `mesh-coordinator`, `adaptive-coordinator`
**GitHub**: `pr-manager`, `code-review-swarm`, `issue-tracker`, `release-manager`

Any string works as a custom agent type.

## Build & Test

- ALWAYS run tests after code changes
- ALWAYS verify build succeeds before committing
- After edits, run `uv run python -m tree_sitter_analyzer --change-impact --format json` and follow its `verification_command`
- If `pytest_required` is `false`, do not run tests just to look busy

```bash
npm run build && npm test
```

## CLI Quick Reference

```bash
npx @claude-flow/cli@latest init --wizard           # Setup
npx @claude-flow/cli@latest swarm init --v3-mode     # Start swarm
npx @claude-flow/cli@latest memory search --query "" # Vector search
npx @claude-flow/cli@latest hooks route --task ""    # Route to agent
npx @claude-flow/cli@latest doctor --fix             # Diagnostics
npx @claude-flow/cli@latest security scan            # Security scan
npx @claude-flow/cli@latest performance benchmark    # Benchmarks
```

26 commands, 140+ subcommands. Use `--help` on any command for details.

## Setup

```bash
claude mcp add claude-flow -- npx -y @claude-flow/cli@latest
npx @claude-flow/cli@latest daemon start
npx @claude-flow/cli@latest doctor --fix
```

**Agent tool** handles execution (agents, files, code, git). **MCP tools** handle coordination (swarm, memory, hooks). **CLI** is the same via Bash.

## gstack (recommended)

This project uses [gstack](https://github.com/garrytan/gstack) for AI-assisted workflows.
Install it for the best experience:

```bash
git clone --depth 1 https://github.com/garrytan/gstack.git ~/.claude/skills/gstack
cd ~/.claude/skills/gstack && ./setup --team
```

Skills like /qa, /ship, /review, /investigate, and /browse become available after install.
Use /browse for all web browsing. Use ~/.claude/skills/gstack/... for gstack file paths.

## PR Hygiene — no kitchen-sink, no half-baked PRs

**🔒 LOCKED BY USER (2026-06-04):** 「以後不要出這麼多半成品或者垃圾」. Every PR must be **focused** and **finished**. This applies to autonomous-agent output too — same bar.

- **One PR = one feature.** The title must match the actual diff. A PR titled `include_body` must NOT also carry `code_patterns`, `symbol_lineage`, `find_references`, test splits, and 33 skill files. If a branch accumulated unrelated commits, split them into separate `feature/*` → develop PRs, one per feature.
- **Finished, not half-baked.** Before opening a PR: tests green, `ruff`/`mypy` clean, and the change actually works end-to-end (re-index / dogfood verified where relevant). No "Sprint N" dumps of WIP.
- **GitFlow, every time.** Base = `develop` (never `main`); branch = `feature/*` (never `feat/*` — the GitFlow check rejects it). Verify both before opening.
- **A kitchen-sink PR is closed, not merged.** If you receive (or an agent produces) a PR with >1 feature, a misleading title, or a 100-file diff, **close it** and re-open focused PRs. Keep the branch so commits can be cherry-picked. Codex can only meaningfully review a focused diff.
- **Past incident (2026-06-04):** PR #276 ("include_body") bundled 10+ unrelated commits + 33 `.agents/skills` files (100 files). Closed; the rule above is the response.

## RFC Process — substantial changes start as an RFC (not a loose docs/*.md)

**🔒 LOCKED BY USER (2026-06-03):** 「我們出一個 docs 太隨便了，沒有 mycelium 體系化」。Substantial changes go through the RFC process in [`rfcs/`](rfcs/), modeled on the sibling mycelium project. Do NOT drop a one-off `docs/designs/*.md` for a feature design — that is too ad-hoc.

- **What needs an RFC**: public API / MCP facade-or-tool additions & changes, ast_cache schema changes, cross-surface (CLI↔MCP) parity changes, performance/SLA changes, and any change to a locked design decision. See [`rfcs/README.md`](rfcs/README.md) for the full table. Bug fixes and internal refactors do not.
- **How**: copy `rfcs/0000-template.md` → `rfcs/NNNN-title.md`, PR to develop. The RFC carries a **Status** line (`draft`→`accepted`→`implemented`), checkbox **Acceptance criteria** that flip as the implementation lands, a **Three-Surface (CLI↔MCP) parity** section, and a **RED-first test plan**.
- **Spec-first pays off**: RFC-0001's Codex review caught an architecture-level dead-end (session inaccessible from `Server.run()`) *before any code* — exactly what a loose docs file would have missed.
- After merge, RFCs are immutable except status/clarification; to change an accepted RFC, write a superseding one.

## PR Review Rules — NEVER ignore Codex review

**🔒 LOCKED BY USER (2026-06-03):** 「每次 PR 之後不可以無視 codex 的 review」。After creating OR updating any PR, you MUST fetch and triage the Codex (`chatgpt-codex-connector[bot]`) review. Ignoring it — even when CI is green or the PR already merged — is a violation of this rule.

### Mandatory workflow after every PR

1. **Fetch the review** (the PR-body summary is just a template — the real findings are inline comments):
   ```bash
   gh api repos/aimasteracc/tree-sitter-analyzer/pulls/<N>/comments \
     | python3 -c "import json,sys; [print(c['path'],c.get('line'),'\n',c['body'][:1500],'\n---') for c in json.load(sys.stdin)]"
   ```
   Codex review is triggered on open / ready-for-review / `@codex review` comment. If it hasn't posted yet, wait for it (CI-monitor pattern) before merging.

2. **Triage EVERY comment** — do not skip any. For each, render an explicit verdict:
   - **Real problem** → fix it (own PR or follow-up PR). Codex P-badges (P1/P2/P3) set priority; P1/P2 must be fixed before or right after merge.
   - **Already fixed** → Codex often reviews an older commit; verify on the current HEAD and record "already fixed by #X".
   - **False positive / won't-fix** → state the concrete reason (cross-ref a CLAUDE.md design decision if applicable). Never dismiss silently.

3. **Report the triage to the user** — a table of (comment → verdict → action), so nothing is swept under the rug.

4. **If the PR already merged when the review lands**, still triage; open a follow-up PR for any real finding. A merged PR does NOT exempt its review.

### Why (past incident, 2026-06-03)
Codex flagged 3 real P2 correctness bugs across #269/#270 (Hyphae file-identity false positives, `:subclasses` wrong endpoint → empty results, `:implements` missing the `implements` edge kind). All three were genuine; ignoring them would have shipped a query DSL that returns wrong graph results to agents. The 4th finding (`.class` empty) was a stale-commit review already fixed by a later PR — which is exactly why each comment needs an explicit verdict, not a blanket dismiss. Fixed via #271.

## Release Gate Rules

**NEVER merge release branch → main until ALL of these are confirmed:**

1. **All CI axes green** — every platform (ubuntu/macos/windows) × every Python version must pass. Check with `gh run list --branch release/vX.Y.Z`.
2. **PyPI published** — `Deploy to PyPI` job in Release Branch Automation shows ✓.
3. **Release Automation completes** — the full `Release Branch Automation` workflow must reach the `Finalize Release` step. If that step fails (e.g. Actions permission error), fix the root cause or create the PR manually — but still wait for PyPI deploy to finish first.
4. **README numbers verified against actuals** — CLI flag count, MCP tool count, and test count must be re-measured from the release CI logs, not assumed.

**Merge order:**
```
feature/* → develop → release/vX.Y.Z → main (only after all gates above)
```

**Develop freeze while a release is in flight (🔒 LOCKED BY USER, 2026-06-10):**
while a `release/* → main` PR is open, feature PRs QUEUE — do NOT merge them
into develop, even with green CI. Exception: hotfixes for the in-flight
release go to the release branch (never straight to develop). The freeze
lifts only when release finalization (below) completes.
*Past incident (2026-06-10):* 6 feature PRs were merged into develop while
the v1.22.0 release PR was open. No material damage (the release diff was
untouched), but the "release state" and "next-version content" interleaved —
review/rollback baselines get muddy. User called it out; rule locked.

**Release finalization — mandatory steps AFTER release → main merges**
(none of these are automated; v1.20 and v1.21 both required them manually):

1. `gh release create vX.Y.Z --target main --notes-file <changelog section>` — the git tag and GitHub Release are NOT auto-created.
2. **Back-merge main → develop.** Conflict conventions: take main's authoritative test-count (measured from release CI), keep develop's newer feature surface (e.g. flag counts for develop-only params). Verify with the registry commands below, not by trusting either side.
3. Re-verify PyPI version / main README badge / `__version__` agree.
4. Finalization complete = release closed = develop unfreezes.

**Past incident (2026-05-31):** merged release/v1.17.0 → main immediately after the Release Automation `Finalize Release` step failed — before confirming PyPI had published and before README numbers were verified. The correct order is: wait for PyPI ✓, fix README, then merge.

### How to get authoritative counts for README numbers

**CLI flag count** — do NOT use grep on `--help` output (double-counts flags in multiple sections):
```bash
# WRONG
uv run python -m tree_sitter_analyzer --help | grep -E "^\s+--" | wc -l

# RIGHT — matches what test_readme_counts_match_registry uses
uv run python -c "
from tree_sitter_analyzer.cli_main import create_argument_parser
p = create_argument_parser()
flags = {s for a in p._actions for s in a.option_strings if s.startswith('--')}
print(len(flags))
"
```

**MCP tool count** — use the registry directly (matches `test_readme_counts_match_registry`):
```bash
uv run python -c "
from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry
tools, _ = create_tool_registry('.')
print(len(tools))
"
```

**Test count** — read from the release CI log (`ubuntu-latest` axis), not from local `uv run pytest` (local skips differ from CI).
