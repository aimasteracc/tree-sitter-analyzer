# Code Map Intelligence - Progress

## Session 1: Initial Implementation (Previous)
- Created design.md + requirements.md
- Implemented all 3 phases with TDD: trace_call_flow, impact_analysis, gather_context
- 19/20 tests passed; 1 failure: `test_trace_finds_downstream_callees`
- Root cause identified: `_build_call_index` uses `func.get("body")` but PythonParser doesn't provide body

## Session 2: Fix + QA + Closing (Current)

### Issues Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| `_build_call_index` fails — no `body` field | 1 | Read actual source file using `line_start`/`line_end`, regex word-boundary scan |
| Ruff I001 unsorted imports | 1 | `ruff --fix` auto-sorted |
| Ruff C420 dict comprehension | 1 | `ruff --fix` auto-replaced with `dict.fromkeys` |
| Ruff SIM102 nested if | 1 | Manually collapsed into single `if` with `and` |
| Mypy no-any-return in `_resolve_import` | 1 | Added explicit `str` type annotation for `module_name` |

### Results
- **32/32 intelligence tests pass** (20 core + 12 QA edge cases)
- **37/37 code_map + intelligence tests pass** combined
- Ruff: 0 errors
- Mypy: 0 errors
- Full suite: pending DevOps verification

### Key Design Decision
**Why read source files instead of AST?**
- PythonParser returns `{name, parameters, return_type, line_start, line_end}` — no body text
- Reading 10-20 lines per function via `line_start:line_end` is lightweight (~1ms per file)
- Regex word-boundary check (`\btarget_name\s*\(`) prevents false positives
- This approach is language-agnostic: works for Python, Java, TypeScript equally

## Session 3: Decorator Awareness + 7-Role Autonomous Loop

### Workflow
Full 7-role closed loop: PO → Architect → Worker(TDD) → Critic → QA → Writer → DevOps

### Issues Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| `test_decorator_factory_not_dead` — `route` in dead code | 1 | Added decorator-usage tracking: functions USED AS decorators are also alive |
| `test_fqn_unique_across_symbols` — duplicate `wrapper` FQN | 1 | Renamed wrapper closures in fixture to unique names |
| Critic: recursive AST walk could overflow | 1 | Added `_max_depth=50` limit to `_scan_ast_for_decorators` |

### Results
- **61/61 intelligence tests pass** (32 core + 10 decorator + 4 QA edge + 2 ranking + 13 FQN)
- Ruff: 0 errors
- Mypy: 0 errors
- Decorator detection: @route, @command, @fixture, @property, @staticmethod all exempt
- Truly dead code (orphan_function) still correctly detected
- Decorator factories (route, command) tracked as alive via usage analysis

### Key Design Decisions
1. **Two-strategy decorator detection**: Parser metadata first, AST fallback second
2. **Decorator-usage tracking**: Functions used AS decorators are also marked alive
3. **Pattern-based matching**: `_FRAMEWORK_DECORATORS` is configurable, not hardcoded
4. **Depth-limited AST recursion**: Prevents stack overflow on deeply nested code

## Session 4: MCP Tool Exposure + 8-Role Autonomous Loop

### Workflow
Full 8-role closed loop with Elite Critic:
PO → Architect → Worker(TDD#1) → Elite Critic → Worker(TDD#2) → QA → Writer → DevOps

### PO Discovery
**Critical gap**: trace_call_flow, impact_analysis, gather_context had 61 passing tests
but ZERO exposure via MCP/API/CLI. Users couldn't use the features at all.

### Architecture Decision
Single `code_intelligence` MCP tool with action-based routing:
- `scan` → build code map (cached per project)
- `trace_calls` → bidirectional call flow
- `impact` → modification impact analysis
- `gather_context` → LLM context capture
- `dead_code` → dead code listing
- `hot_spots` → most-referenced symbols

### Issues Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| TOON prefix mismatch (`PROJECT:` vs `PROJECT_MAP`) | 1 | Fixed test assertion |
| Critic: scan called twice for "scan" action | 1 | Restructured execute() dispatch logic |
| Critic: no path validation on project_path | 1 | Added Path.is_dir() check with ValueError |
| Tool count regression (11 → 12) | 1 | Updated assertions in 2 test files |

### Results
- **18/18 MCP tool integration tests pass**
- **61/61 intelligence unit tests pass** (unchanged)
- Tool coverage: 91% on intelligence.py
- Ruff: 0 errors, Mypy: 0 errors
- Full suite: pending DevOps verification
