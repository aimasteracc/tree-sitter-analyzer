<!-- Generated: 2026-05-30; doc-code re-sync: 2026-06-17 -->
# Formatters Codemap

JSON response formatting and explicit terminal views. Located in
`tree_sitter_analyzer/formatters/`; a language formatter name describes its input
language, not an additional MCP or CLI wire encoding.

## Format Registry

| Format | Module | Default for | Use case |
|---|---|---|---|
| `json` | Standard JSON serialization; `mcp/server_utils/tool_registration.py` serializes MCP results | **MCP + CLI** | Canonical structured response format; `jq`-friendly programmatic ingestion |
| `full` table | `formatters/table_formatter.py` (canonical, re-exports `LegacyTableFormatter`) + `tree_sitter_analyzer/default_table_formatter.py` + `legacy_table_formatter.py` | `--table full` | Terminal structure view |
| `signatures` | `formatters/_java_formatter_signatures_mixin.py` (Java); `formatters/_python_formatter_signatures_table.py` (Python); `formatters/_typescript_formatter_signatures_table.py` (TypeScript); `default_table_formatter.py` (fallback) | `--table signatures` | Method directory; use `--partial-read` for bodies |

The generic `FormatterRegistry` registers exactly `json` and `full`; these
`CodeElement` formatters are separate from the language-specific table registry.
The main CLI accepts only `--format json` and `--table {full,signatures}`.
Command-specific `--output-format` also permits `text`; CSV, YAML, and compact
are not CLI format choices.
`formatters/json_formatter.py` and `formatters/yaml_formatter.py` format analysis
of JSON and YAML source files respectively; the latter does not provide a
`--format yaml` response encoding.

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
| `IFormatter` | `HtmlFormatter`, `JsonFormatter`, `FullFormatter`, … | `format(elements)` → str |
| `IStructureFormatter` | legacy adapters | `format_structure(dict)` → str |

`formatters/formatter_registry.py` re-exports both for backward compat.
Generic `CodeElement` implementations (`JsonFormatter` and `FullFormatter`) live in
`formatters/_builtin_formatters.py`; the registry remains their stable import
facade. `formatters/_language_formatter_registration.py` owns bundled-language
registration and defers only the legacy default formatter during circular
imports, so importing `default_table_formatter` first cannot silently disable
the language-specific registry.
`formatters/html_formatter.py` imports directly from `formatters/_formatter_interface.py` to avoid the
`formatter_registry ↔ html_formatter` import cycle (fixed 2026-05-30).

## Formatter Architecture

Language formatters use `formatters/base_formatter.py`:

```python
class BaseFormatter(ABC):
    def format(self, data: Any) -> str: ...
    def format_summary(self, analysis_result: dict) -> str: ...
    def format_structure(self, analysis_result: dict) -> str: ...
    def format_advanced(self, ...) -> str: ...
    def format_table(self, ...) -> str: ...

class BaseTableFormatter(BaseFormatter):
    # 表格辅助方法位于此处；紧凑摘要方法仅为子类兼容保留。
    def _format_full_table(self, ...) -> str: ...
    def _format_compact_table(self, ...) -> str: ...
```

Per-language formatter mixins live alongside (`_java_formatter_*_mixin.py`,
`_cpp_formatter_*_mixin.py`, etc.) and are composed into the concrete formatter
classes via Python's MRO.

Standalone per-language formatters (self-contained, no mixin composition):
- `formatters/go_formatter.py` — `GoTableFormatter`; full-table and JSON rendering;
  retains an internal compact summary method. The full table renders
  `| Func | Signature | Vis | Lines | Cx | Doc |` (functions) and
  `| Receiver | Func | Signature | Vis | Lines | Cx | Doc |` (methods)
- `formatters/bash_formatter.py` — `BashTableFormatter`; registered for "bash" / "sh";
  renders `| Name | Signature | Vis | Lines | Cx | Doc |` in the full table;
  also retains an internal compact summary method. These summary methods do
  not restore a public `--table compact` choice.

Key mixins for the Java formatter:
- `formatters/_java_formatter_full_mixin.py` — `_format_full_table`
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

## JSON Format

JSON emits a standard structured object with stable field names and nested response data.

JSON example:

```json
{
  "file": "src/foo.py",
  "language": "python",
  "classes": [{"name": "Foo", "line": 12, "end_line": 80}]
}
```

The JSON serializer is the sole wire-format implementation. Language-specific
formatters remain available for explicit terminal table views.

## Format Stability Contract

Format changes are tracked by:

- `docs/format_specifications.md` — canonical schema
- `tests/regression/` — Golden Master tests

Breaking a format requires updating golden masters and tagging it in the changelog as a
major version bump (semver).

## Cache & File Output

- `mcp/utils/file_output_factory.py` — atomic write for large payloads
- `TREE_SITTER_OUTPUT_PATH` env var sets the default output directory

## Legacy Subpackage

`formatters/legacy/` contains the split-out legacy table formatter modules,
extracted from the monolithic `legacy_table_formatter.py`:

| Module | Role |
|---|---|
| `formatters/legacy/__init__.py` | Re-exports the public `LegacyTableFormatter` surface |
| `formatters/legacy/common.py` | Shared constants and helper types used across legacy modules |
| `formatters/legacy/detail.py` | Detail-row rendering helpers |
| `formatters/legacy/full.py` | `_format_full_table` implementation for the legacy formatter |
| `formatters/legacy/helpers.py` | General rendering helpers (column widths, header lines, etc.) |
| `formatters/legacy/members.py` | Member (field/method) row formatting helpers |

## See Also

- [`docs/format_specifications.md`](../format_specifications.md)
- [`docs/format-testing-guide.md`](../format-testing-guide.md)
- [`CLAUDE.md` § "Deliberate design decisions"](../../CLAUDE.md) — JSON contract rationale
- [`scripts/codemap-sync-check.sh`](../../scripts/codemap-sync-check.sh) — pre-commit gate that blocks new `formatters/*.py` without a `formatters.md` update
