<!-- Generated: 2026-05-22; doc-code re-sync: 2026-06-17 -->
# Security Codemap

Security boundary enforcement for both CLI and MCP. Located in `tree_sitter_analyzer/security/`.

## Components

| File | Responsibility |
|---|---|
| `security/validator.py` | `SecurityValidator` — path validation, **god class — high-risk to touch** |
| `security/boundary_manager.py` | `ProjectBoundaryManager` — root resolution & boundary checks |
| `security/regex_checker.py` | `RegexSafetyChecker` — block regex DoS (ReDoS) patterns in user-supplied regex |
| `security/fixture_detector.py` | `is_fixture` / `fixture_to_verdict` / `list_fixtures` — cached test-fixture detection; powers the fixture-based verdict escalation in `edit action=safe` |
| `mcp/utils/path_resolver.py` | `PathResolver` — canonicalize paths consistently across macOS/Windows |

## Boundary Contract

> **Every tool — MCP and CLI — must operate strictly within `TREE_SITTER_PROJECT_ROOT`.**

`ProjectBoundaryManager.is_within_project(path)` / `validate_and_resolve_path(path)`:
- Resolves `path` via `Path.resolve()` (realpath semantics — symlinks ARE resolved)
- Compares the resolved path against the resolved `project_root`
- Returns `False` / `None` for anything outside; tools then return `status=error` with `reason`

**macOS symlink caveat (locked)**: `/var/folders/...` symlinks to `/private/var/folders/...`.
Because the boundary manager resolves via `realpath`, `project_root` and candidate paths must be
resolved the **same** way or fixtures diverge. The locked decision is therefore *do not naively
re-canonicalise `project_root` inside `BaseMCPTool.__init__`* — `SecurityValidator`, `PathResolver`,
and the test fixtures already agree on a resolution, and r36's attempt to add one broke 164 tests on
macOS. See `CLAUDE.md` § "project_root canonicalisation".

## Threat Model

The server is intended to be run by **trusted users on their own machines**, but:

| Threat | Mitigation |
|---|---|
| Path traversal via crafted file_path | `ProjectBoundaryManager.validate_and_resolve_path` |
| ReDoS via crafted regex | `RegexSafetyChecker` rejects exponential-blowup patterns |
| Arbitrary command execution | No `shell=True`, all subprocess invocations use list form |
| Reading sensitive files (`.env`, `.ssh`) | Boundary check + `.gitignore` aware |
| SQL injection in `_route_cache.py` | Parameterised queries (validated in r37d3) |
| Large file DoS | Streaming reads + `MAX_FILE_SIZE` cap |

## Input Validation Points

All boundary checks happen at MCP/CLI entry:

1. `mcp/tools/base_tool.py:BaseMCPTool.__init__` — receives `project_root`, builds
   `ProjectBoundaryManager` lazily.
2. `cli/commands/base_command.py` — same project_root resolution.
3. Per-tool `execute()` validates `file_path` against the boundary before any IO.

Adding a new tool that touches files? **Always validate via `SecurityValidator.validate_file_path(path)`
(or `ProjectBoundaryManager.validate_and_resolve_path(path)`) before `open()`.** Tests in `tests/unit/security/test_security_boundary_properties.py` are
property-based (Hypothesis) — they fuzz paths to catch missed validations.

## Critical Files — Solo Commits Only

Per `CLAUDE.md`:
- `security/validator.py` — high-risk; never bundle with cosmetic changes
- `security/boundary_manager.py` — same
- `plugins/__init__.py` — plugin registry, runtime contract
- `core/parser.py` — analysis kernel

Changes to these files require:
1. Solo commit (no other files)
2. macOS gate-check (run tests on macOS specifically — symlink behavior differs)
3. Update `tests/unit/security/test_*_properties.py` if invariant changes

## See Also

- [`docs/architecture.md`](../architecture.md) — Security in the broader stack
- [`tests/unit/security/`](../../tests/unit/security/) — Property-based boundary tests
- [`CLAUDE.md` § "Deliberate design decisions"](../../CLAUDE.md) — project_root rationale
