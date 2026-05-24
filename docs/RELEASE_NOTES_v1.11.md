# Release Notes — v1.11

**Theme:** the AI-agent code-understanding MCP server gets faster,
sharper, and harder to misuse.

> If you're new here: Tree-sitter Analyzer is the MCP server built for
> AI agents — 23 tools, 17 languages, **TOON output cuts response
> tokens by ~73%**, and you install it with one `uvx`. See the
> [README](../README.md) for the elevator pitch.

## ⚡ Performance

| Operation | Before | After | Delta |
|---|---:|---:|---:|
| **Route detection, warm pass** (1 280-file project) | 2.23 s | **13 ms** | **~140×** |
| **Same-file repeated parse via `Parser._cache`** | 4.44 ms | **0.003 ms** | **~1334×** |
| **Project AST indexing** (1 293 files, multi-core) | 2.30 s | **1.22 s** | 1.9× now, ~4× scaling on 10k-file repos |
| **MCP server cold import** | 316 ms | **222 ms** | 1.4× |
| **TOON-encoded `--table=full` payload** vs JSON | 12 233 B | **1 812 B** | **–85 %** |

The headline 140× is the demo to show your team: open a Django-sized
project, run `--detect-routes` twice — the second run is effectively
instant, because we now content-hash cache per-file route extraction.

## 🚀 New features

- **`--detect-routes`** — URL → handler mapping across Flask, Django,
  FastAPI, Express, and Spring Boot. Five modes (`summary`, `all`,
  `lookup`, `prefix`, `file`), framework filtering, full CLI/MCP
  parity. CodeGraph's route-map equivalent without the graph DB.
- **Autonomous development pipeline** — daily cron filed a "sprint
  plan" GitHub issue using the analyzer's own MCP tools. Optional
  Level-2 mode hands the brief to a Claude Code agent that opens a
  PR (a human still merges). See
  [docs/AUTONOMOUS_DEV.md](AUTONOMOUS_DEV.md) for the 4-layer
  architecture and operator playbook.
- **`ToolResponse` typed envelope** — every MCP tool's response now
  honours a documented `success: bool, error: str-when-failure`
  contract. Validator runs on the full 23-tool registry at test time
  so the envelope can't drift.

## 🛡 Hardening

- **Path-traversal write protection** on `output_file` — agent-supplied
  paths that resolve outside the configured output directory are
  refused before any `mkdir` or `write`.
- **`RouteDetector.file` mode** routes user-supplied paths through
  `BaseMCPTool.resolve_and_validate_file_path` before parsing.
- **Symlink boundary enforcement** in `RouteDetector._walk_source_files`
  — rejects symlinks whose target resolves outside the project root.
- **Error sanitisation** — new `mcp/utils/error_sanitizer.py` strips
  absolute paths from exception strings before they reach the MCP
  caller. In-project paths become `./<rel>`; external paths become
  `<external-path>`. Applied at the five known leakage sites.

## 🔧 Developer experience

- **mypy clean across 438 source files.** Targeted overrides for the
  tree-sitter-Node propagation noise codes mean real type bugs still
  fail builds, and `git commit` no longer needs `--no-verify` for
  normal work.
- **18-plugin regression net** — `tests/regression/test_plugin_golden_masters.py`
  snapshots every language plugin's stable output summary. Catches
  cross-cutting plugin refactors that would otherwise silently drift.
- **20 contract tests** in `tests/unit/test_agent_contracts.py` pin
  the invariants this release locked in (CLI-MCP parity, no
  `set_project_path` overrides, no `mcp/tools/` reaching into `cli/`,
  MCP server doesn't eagerly import tools, etc.).
- **Orphan-module guard rail** — `scripts/check_orphan_modules.py`
  fails CI if a new source file lands without a name-matched test.
  Baseline locked at the current state; the line only moves down.
- **Hypothesis xdist DB contention** killed — text-generative
  property tests no longer flake under parallel suite runs.
- **IO/timing tests** relocated from `tests/unit/` to
  `tests/integration/` so the unit suite matches its "fast isolated"
  contract.

## 🏗 Architecture

- **`services/` boundary layer** — shared builders (`parser_readiness`,
  `agent_workflow`, `agent_skills`) are reachable from both `cli/`
  and `mcp/`. The previous bidirectional `cli ↔ mcp` import cycle
  is broken. Contract test prevents regression.
- **Single-init `BaseMCPTool`** — `__init__` and `set_project_path`
  funnel through one `_apply_project_root` helper. Subclasses
  override the new `_on_project_root_changed` hook instead of
  reimplementing the wiring. 12 tools migrated; AST-walking
  contract test ensures no future tool re-introduces the dual track.
- **`ElementExtractor.set_file_encoding` hook** — promoted to a
  documented method on the plugin base class. The C/Java byte-level
  slicing path now reads its encoding from a public surface, not from
  an ad-hoc `setattr` in `analyze_file`. PHP/Ruby's unused
  `_file_encoding` placeholders removed.
- **Lazy MCP tool import** — the 23 individual tool modules no
  longer load at `import mcp.server`. The per-tool import cost is
  paid only when a registry is actually built.

## 📚 Documentation

- **README hero** — TOON's 73% token reduction, the 23-tool roster,
  and the 17 languages are now on the first screen (they used to be
  buried under feature tables).
- **`docs/AUTONOMOUS_DEV.md`** — the four-level architecture of the
  self-driving sprint pipeline. Operator quick reference + safety
  contract.

## 🙏 Acknowledgements

This release was developed end-to-end through the autonomous-dev
pipeline it ships. Every PR went through the same `--change-impact`,
`--project-health`, golden-master, and mypy gates the project asks
its users to use. The pipeline is open-source and documented; we'd
love to hear what it finds in your repo.

## 🛠 Upgrade notes

- **Public API:** no breaking changes. MCP tool response envelopes
  are stricter but only on the existing `success` / `error` keys —
  any tool already returning a well-formed response keeps working.
- **CLI:** no flag removals. New flags: `--detect-routes` family,
  `--ast-cache-mode sync|changes`.
- **Dependencies:** no new runtime deps. `tomli` (already transitive)
  is now used as fallback for the 3.10 build of one CLI helper.

Try it:

```bash
uvx tree-sitter-analyzer --detect-routes --project-root <your-project>
uvx tree-sitter-analyzer <a-file.py> --table=full --output-format=toon
```

Found a bug or want a feature? Open an issue —
the autonomous-sprint pipeline will see it on its next pass.
