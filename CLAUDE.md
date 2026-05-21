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

## Deliberate design decisions — do NOT "fix" these

These look like inconsistencies in a dogfood pass, but they are intentional and reflect the project's design priorities. Reverting them costs real value. **If a dogfood agent proposes any of the items below as a "finding", REJECT the finding and link the agent back to this section.**

### 1. MCP defaults to TOON; CLI defaults to JSON

- **Why**: TOON is 50-70% more token-efficient than JSON. MCP callers are LLM agents — token cost is real money. CLI callers are humans / shells — JSON is human-readable and pipes into `jq`.
- **Symptom that looks like a bug**: `MCP execute()` returns `{format: "toon", toon_content: "..."}` while CLI returns a parsed dict.
- **Correct action**: leave the defaults alone. If TOON-vs-JSON divergence causes a real bug, fix the divergence (e.g. make TOON carry the same scalar fields, per F7/N8), don't flip the default.
- **Past incident**: r36 attempted "R3: flip MCP output_format default to json" — rolled back. The token savings outweigh the parity argument.

### 2. project_root canonicalisation is a foundational change

- **Why**: macOS `/var/folders/...` symlinks to `/private/var/folders/...`. Naive `os.path.abspath()` doesn't resolve the symlink but `realpath()` does. The SecurityValidator and test fixtures use different resolutions, so any change to `BaseMCPTool.__init__` propagates through 164+ tests.
- **Symptom that looks like a bug**: MCP `safe_to_edit(project_root='.')` returns SAFE while CLI returns UNSAFE (different downstream counts because `DependencyGraph('.')` walks a different tree than `DependencyGraph('/abs/path')`).
- **Correct action**: if you fix this, study the macOS symlink behavior and the test fixture conventions FIRST. Use `os.path.abspath` only after confirming SecurityValidator / PathResolver / test fixtures all use the same resolution. Test on macOS specifically. Land it in a dedicated commit, never bundled with other fixes.
- **Past incident**: r36 attempted "R1: canonicalise project_root in BaseMCPTool" — broke 164 tests on macOS, rolled back.

### 3. CLI INFO/diagnostic output → stderr; JSON/TOON payload → stdout

- **Why**: This was correctly fixed in r34 (Q2). DO NOT revert it. `print(message)` calls in CLI code MUST go to `sys.stderr` unless they emit machine-readable data to stdout.

### 4. Markdown smell-detection is intentionally OFF in `project_health`

- **Why**: r34 Q4 narrowed `PROJECT_HEALTH_SOURCE_EXTS` to code-only. `.md` files no longer count for code-quality grading. Re-adding markdown would re-inflate the C-grade bucket with golden_master fixtures.
- **Correct action**: if you want to score markdown structure, build a separate `markdown_health` tool. Don't merge it back into `project_health`.

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
