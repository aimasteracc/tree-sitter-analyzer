<!-- Generated: 2026-05-22 -->
# Security Codemap

Security boundary enforcement for both CLI and MCP. Located in `tree_sitter_analyzer/security/`.

## Components

| File | Responsibility |
|---|---|
| `security/validator.py` | `SecurityValidator` — path validation, **god class — high-risk to touch** |
| `security/boundary_manager.py` | `BoundaryManager` — root resolution & boundary checks |
| `security/path_resolver.py` | Canonicalize paths consistently across macOS/Windows |
| `security/regex_checker.py` | Block regex DoS (ReDoS) patterns in user-supplied regex |

## Boundary Contract

> **Every tool — MCP and CLI — must operate strictly within `TREE_SITTER_PROJECT_ROOT`.**

`BoundaryManager.is_within_project_root(path)`:
- Resolves `path` to absolute form
- Compares against `project_root` using `os.path.abspath` (NOT `realpath`)
- Returns `False` for anything outside; tools then return `status=error` with `reason`

**Why `abspath` not `realpath`**: on macOS, `/var/folders/...` symlinks to
`/private/var/folders/...`. `realpath()` resolves the symlink and breaks 164+ test fixtures.
This is a **locked design decision** — see `CLAUDE.md` § "project_root canonicalisation".

## Threat Model

The server is intended to be run by **trusted users on their own machines**, but:

| Threat | Mitigation |
|---|---|
| Path traversal via crafted file_path | `BoundaryManager.is_within_project_root` |
| ReDoS via crafted regex | `RegexChecker` rejects exponential-blowup patterns |
| Arbitrary command execution | No `shell=True`, all subprocess invocations use list form |
| Reading sensitive files (`.env`, `.ssh`) | Boundary check + `.gitignore` aware |
| SQL injection in `_route_cache.py` | Parameterised queries (validated in r37d3) |
| Large file DoS | Streaming reads + `MAX_FILE_SIZE` cap |

## Input Validation Points

All boundary checks happen at MCP/CLI entry:

1. `mcp/tools/base_tool.py:BaseMCPTool.__init__` — receives `project_root`, builds
   `BoundaryManager` lazily.
2. `cli/commands/base_command.py` — same project_root resolution.
3. Per-tool `execute()` validates `file_path` against the boundary before any IO.

Adding a new tool that touches files? **Always call `self._security.is_within_project_root(path)`
before `open()`.** Tests in `tests/unit/security/test_security_boundary_properties.py` are
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
