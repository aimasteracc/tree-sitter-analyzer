# Plugin Architecture Known Issues

Last updated: 2026-05-20

## Medium

### KI-3: Helper file sprawl (C: 9, C++: 11, Go: 7, Java: 5)

Single-file plugins have their helper functions split across many `_*_helpers.py` files in the
`languages/` root directory. This makes the directory hard to navigate and breaks IDE navigation.

**Counts:**
- C: 9 helpers (8 private `_c_*_helpers.py` + 1 public `c_helpers.py`)
- C++: 11 helpers (10 private `_cpp_*_helpers.py` + 1 public `cpp_helpers.py`)
- Go: 7 helpers (6 private `_go_*_helpers.py` + 1 public `go_helpers.py`)
- Java: 5 helpers (4 private `_java_*_helpers.py` + 1 public `java_helpers.py`)

**Fix:** Migrate to package structure (`languages/<lang>_plugin/`), move helpers into the package.
Blocked by KI-4 (single-file to package migration).

### KI-4: 13 single-file vs 5 package plugins

13 plugins are single-file (`languages/<lang>_plugin.py`) while 5 are packages
(`languages/<lang>_plugin/plugin.py`). Gate test `test_no_new_single_file_plugins_in_languages_root`
prevents new single-file plugins but doesn't require migration.

**Affected:** c, cpp, csharp, css, go, html, java, kotlin, php, ruby, rust, swift, yaml

**Fix:** Migrate each plugin to package structure. This is a large refactor — each migration
requires moving the main plugin class, all helpers, and updating all imports.

## Low

### KI-5: YAML analyze_file is a thin wrapper

YAML's `analyze_file()` delegates entirely to `_analyze_yaml_file_standalone()` — a module-level
function. All other plugins implement the logic directly in the method. Functionally correct but
inconsistent with the pattern.

### KI-6: SQL create_extractor has extra coupling

SQL's `create_extractor()` must propagate `diagnostic_mode`, `platform_info`, and `adapter`
from the plugin instance. Other plugins' `create_extractor()` takes no arguments. This is correct
for SQL's platform-compatibility feature but adds coupling.

## Resolved

### KI-R1: `self.extractor` in `analyze_file` (resolved: d42322a)

All 18 plugins now use `create_extractor()` in `analyze_file()`. Go/Rust use `isinstance`
guards to read side-effect attributes (goroutines/channels/defers/modules/impl_blocks) from
the local extractor instance.

### KI-R2: `extract_elements` return type inconsistency (resolved: e1a024c)

All 18 plugins' `extract_elements` returns `dict[str, list[Any]]`.

### KI-R3: LegacyTableFormatter naming (resolved: e1a024c)

Renamed to `DefaultTableFormatter` with backward-compatible alias.

### KI-R4: C# `_file_encoding` dead code (resolved: d42322a)

Removed unused `_file_encoding` declaration and assignment. C# extractor uses `self.source_code`
string slicing, not byte-level operations.

### KI-R5: C/Java `_file_encoding` never propagated to extractors (resolved: 2026-05-20)

`analyze_file()` in `c_plugin.py` and `java_plugin.py` now sets
`extractor._file_encoding = detected_encoding` immediately after `create_extractor()` and
before any `extract_*` call. Non-UTF-8 files (GBK, Shift-JIS, Latin-1) now produce correct
byte-level node text. Regression coverage:
`tests/unit/languages/test_plugin_encoding_propagation.py::TestCPluginEncodingPropagation`
and `TestJavaPluginEncodingPropagation`.

### KI-R6: PHP/Ruby `_file_encoding` dead code (resolved: 2026-05-20)

Removed the unused `self._file_encoding: str | None = None` declaration from
`PHPElementExtractor.__init__` and `RubyElementExtractor.__init__`. These extractors do
not perform byte-level slicing; the attribute was copy-paste residue. Regression coverage:
`tests/unit/languages/test_plugin_encoding_propagation.py::TestPhpRubyNoDeadEncodingAttr`.

### KI-R7: `RouteDetectorTool` registered in MCP but unreachable (resolved: 2026-05-20)

The new `RouteDetectorTool` was wired into `mcp/server.py` but had two
architecture defects that made it useless in practice:

1. **CLI-MCP parity gap** — no CLI flag existed, violating the project's hard
   CLI-MCP parity rule (see `MEMORY.md`). Added `--detect-routes`, `--detect-routes-mode`,
   `--detect-routes-url`, `--detect-routes-file`, `--detect-routes-framework`, plus a
   `detect-routes` subcommand alias.

2. **Runtime bug** — `RouteDetector.detect_file()` called
   `_language_from_ext(ext)` but that helper expects a full path (it strips the
   suffix internally). It therefore always returned `None`, and `detect_all()`
   always returned `[]`. Fixed to pass the file path.

3. **500-line cap violation** — `route_detector.py` was 623 lines. Pure
   `@staticmethod` helpers were extracted into `_route_detector_helpers.py`,
   bringing the main module to 496 lines.

Regression coverage: `tests/unit/test_route_detector.py` (36 tests covering
Flask/FastAPI/Express/Spring detection, summary/lookup/prefix/file/all modes,
language dispatch, excluded directories, and MCP tool execute()).
