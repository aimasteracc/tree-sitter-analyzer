<!-- Generated: 2026-05-30; doc-code re-sync: 2026-06-17 -->
# Formatters Codemap

Output formats supported by both CLI and MCP. Located in `tree_sitter_analyzer/formatters/`.

## Format Registry

| Format | Module | Default for | Use case |
|---|---|---|---|
| `json` | `formatters/json_formatter.py` | **MCP + CLI** | Canonical structured response format; `jq`-friendly programmatic ingestion |
| `table` | `formatters/table_formatter.py` (canonical, re-exports `LegacyTableFormatter`) + `tree_sitter_analyzer/default_table_formatter.py` + `legacy_table_formatter.py` | `--table` flag | Terminal viewing with box-drawing chars |
| `csv` | via `tree_sitter_analyzer/_legacy_table_formatter_csv.py` | `--table csv` | Spreadsheet ingestion |
| `signatures` | `formatters/_java_formatter_signatures_mixin.py` (Java); `formatters/_python_formatter_signatures_table.py` (Python); `formatters/_typescript_formatter_signatures_table.py` (TypeScript); `default_table_formatter.py` (fallback) | `--table signatures` | Lightweight method-directory for large files — ~25-80% of full tokens; agent-first, then `--partial-read` for bodies |
| `yaml` | `formatters/yaml_formatter.py` | explicit `--format yaml` | Human-readable structured |

## Why JSON for MCP and CLI?

**Locked design decision** (see `CLAUDE.md`):

| | JSON |
|---|---|
| Interoperability | standard |
| Loss | none |
| `jq` friendliness | yes |
| Human readability | high |

→ MCP and CLI callers share one canonical, machine-readable JSON contract.

## Formatter Interfaces

Interfaces live in `formatters/_formatter_interface.py` (no upward imports — breaks cycle):

| Interface | Implementors | Purpose |
|---|---|---|
| `IFormatter` | `HtmlFormatter`, `JsonFormatter`, `CsvFormatter`, … | `format(elements)` → str |
| `IStructureFormatter` | legacy adapters | `format_structure(dict)` → str |

`formatters/formatter_registry.py` re-exports both for backward compat.
Generic `CodeElement` implementations (`JsonFormatter`, `CsvFormatter`,
`FullFormatter`, and `CompactFormatter`) live in
`formatters/_builtin_formatters.py`; the registry remains their stable import
facade. `formatters/_language_formatter_registration.py` owns bundled-language
registration and defers only the legacy default formatter during circular
imports, so importing `default_table_formatter` first cannot silently disable
the language-specific registry.
`formatters/html_formatter.py` imports directly from `formatters/_formatter_interface.py` to avoid the
`formatter_registry ↔ html_formatter` import cycle (fixed 2026-05-30).

## Formatter Architecture

Each formatter inherits from `formatters/base_formatter.py`:

```python
class BaseFormatter(ABC):
    def format(self, data: Any) -> str: ...
    def format_summary(self, analysis_result: dict) -> str: ...
    def format_structure(self, analysis_result: dict) -> str: ...
    def format_advanced(self, ...) -> str: ...
    def format_table(self, ...) -> str: ...

class BaseTableFormatter(BaseFormatter):
    # table-flavour helpers live here, not on BaseFormatter
    def _format_full_table(self, ...) -> str: ...
    def _format_compact_table(self, ...) -> str: ...
    def _format_csv(self, ...) -> str: ...
```

Per-language formatter mixins live alongside (`_java_formatter_*_mixin.py`,
`_cpp_formatter_*_mixin.py`, etc.) and are composed into the concrete formatter
classes via Python's MRO.

Standalone per-language formatters (self-contained, no mixin composition):
- `formatters/go_formatter.py` — `GoTableFormatter`; full/compact/csv/json; renders
  `| Func | Signature | Vis | Lines | Cx | Doc |` (functions) and
  `| Receiver | Func | Signature | Vis | Lines | Cx | Doc |` (methods)
- `formatters/bash_formatter.py` — `BashTableFormatter`; registered for "bash" / "sh";
  renders `| Name | Signature | Vis | Lines | Cx | Doc |` (full) and
  `| Name | Sig | V | L | Cx | Doc |` (compact)

Key mixins for the Java formatter:
- `formatters/_java_formatter_full_mixin.py` — `_format_full_table`
- `formatters/_java_formatter_compact_mixin.py` — `_format_compact_table`
- `formatters/_java_formatter_signatures_mixin.py` — `_format_signatures_table` (lightweight
  method-directory; lists methods as `name →returnType(Np) L-L`, no bodies)

Python formatter signatures module:
- `formatters/_python_formatter_signatures_table.py` — `format_python_signatures_table`
  (same lightweight directory shape as Java; groups methods by class + emits
  `<module functions>` block for top-level functions; used by
  `PythonTableFormatter._format_signatures_table` via `structure action=signatures`)

TypeScript formatter signatures module:
- `formatters/_typescript_formatter_signatures_table.py` — `format_typescript_signatures_table`
  (lightweight directory for .ts/.tsx/.d.ts files; interfaces count as grouping
  containers; overloads each appear as separate lines; used by
  `TypeScriptTableFormatter._format_signatures_table` via `structure action=signatures`)

TS/JS full-table module-level functions:
- `formatters/_typescript_formatter_full.py` and
  `formatters/_javascript_formatter_full_mixin.py` render top-level (non-class)
  functions in a `## Global Functions` section (same `Cx` column as class
  methods). JS reads both `methods` (class methods) and `functions` (top-level)
  since the JS plugin stores them in disjoint lists.

## CSV Control-Char Safety

`formatters/_csv_safety.py` (`csv_safe_row` / `csv_safe_cell`) strips
C0/DEL control characters (NULL etc.) from CSV cells before they reach
`csv.writer`. Python 3.10's `csv.writer` raises `_csv.Error: need to escape,
but no escapechar set` on a NULL byte; setting `escapechar` would silence it
but double literal backslashes in ordinary fields (a format regression). Tab
and newline are preserved (the writer quotes them on every version); a bare
carriage return is **stripped** because Python 3.10 emits it unquoted, yielding
an unreadable CSV. Used by `CsvFormatter`, `format_html_csv`, and
`format_csv_output`.

## JSON Format

JSON emits a standard structured object with stable field names and nested response data.

<!-- Legacy compact-format implementation removed; historical references belong in changelog/postmortems only. -->

JSON example:

```json
{
  "file": "src/foo.py",
  "language": "python",
  "classes": [{"name": "Foo", "line": 12, "end_line": 80}]
}
```

The JSON serializer is the sole wire-format implementation. Language-specific
formatters remain available for explicit terminal table/CSV views.

## Format Stability Contract

Format changes are tracked by:

- `docs/format_specifications.md` — canonical schema
- `tests/regression/` — Golden Master tests

Breaking a format requires updating golden masters and tagging it in the changelog as a
major version bump (semver).

## Cache & File Output

- `mcp/utils/search_cache.py` — LRU for fd/ripgrep results (in-process)
- `mcp/utils/file_output_factory.py` — atomic write for large payloads
- `TREE_SITTER_OUTPUT_PATH` env var sets the default output directory

## Legacy Subpackage

`formatters/legacy/` contains the split-out legacy table formatter modules,
extracted from the monolithic `legacy_table_formatter.py`:

| Module | Role |
|---|---|
| `formatters/legacy/__init__.py` | Re-exports the public `LegacyTableFormatter` surface |
| `formatters/legacy/common.py` | Shared constants and helper types used across legacy modules |
| `formatters/legacy/compact.py` | `_format_compact_table` implementation for the legacy formatter |
| `formatters/legacy/csv.py` | `_format_csv` implementation for the legacy formatter |
| `formatters/legacy/detail.py` | Detail-row rendering helpers |
| `formatters/legacy/full.py` | `_format_full_table` implementation for the legacy formatter |
| `formatters/legacy/helpers.py` | General rendering helpers (column widths, header lines, etc.) |
| `formatters/legacy/members.py` | Member (field/method) row formatting helpers |

## See Also

- [`docs/format_specifications.md`](../format_specifications.md)
- [`docs/format-testing-guide.md`](../format-testing-guide.md)
- [`CLAUDE.md` § "Deliberate design decisions"](../../CLAUDE.md) — JSON contract rationale
- [`scripts/codemap-sync-check.sh`](../../scripts/codemap-sync-check.sh) — pre-commit gate that blocks new `formatters/*.py` without a `formatters.md` update
