<!-- Generated: 2026-05-30; doc-code re-sync: 2026-06-17 -->
# Formatters Codemap

Output formats supported by both CLI and MCP. Located in `tree_sitter_analyzer/formatters/`.

## Format Registry

| Format | Module | Default for | Use case |
|---|---|---|---|
| `toon` | `formatters/toon_formatter.py` (+ `formatters/toon_encoder.py` engine) | **MCP** | LLM agents — 50-70% fewer tokens than JSON (see `CLAUDE.md` §1; enforced by `tests/unit/mcp/test_output_cost_invariants.py`) |
| `json` | `formatters/json_formatter.py` | **CLI** | `jq` piping, programmatic ingestion |
| `table` | `formatters/table_formatter.py` (canonical, re-exports `LegacyTableFormatter`) + `tree_sitter_analyzer/default_table_formatter.py` + `legacy_table_formatter.py` | `--table` flag | Terminal viewing with box-drawing chars |
| `csv` | via `tree_sitter_analyzer/_legacy_table_formatter_csv.py` | `--table csv` | Spreadsheet ingestion |
| `signatures` | `formatters/_java_formatter_signatures_mixin.py` (Java); `formatters/_python_formatter_signatures_table.py` (Python); `formatters/_typescript_formatter_signatures_table.py` (TypeScript); `default_table_formatter.py` (fallback) | `--table signatures` | Lightweight method-directory for large files — ~25-80% of full tokens; agent-first, then `--partial-read` for bodies |
| `yaml` | `formatters/yaml_formatter.py` | explicit `--format yaml` | Human-readable structured |

## Why TOON for MCP, JSON for CLI?

**Locked design decision** (see `CLAUDE.md`):

| | TOON | JSON |
|---|---|---|
| Token cost | -50-70% | baseline |
| Loss | none | none |
| `jq` friendliness | no | yes |
| Human readability | medium | high |

→ MCP callers are LLM agents → token cost is real money → TOON wins.
→ CLI callers are humans / shells → `jq` & readability win → JSON wins.

**Do NOT propose flipping MCP default from `toon` to `json`** — the cost analysis is settled.

## Formatter Interfaces

Interfaces live in `formatters/_formatter_interface.py` (no upward imports — breaks cycle):

| Interface | Implementors | Purpose |
|---|---|---|
| `IFormatter` | `HtmlFormatter`, `JsonFormatter`, `CsvFormatter`, … | `format(elements)` → str |

`formatters/formatter_registry.py` re-exports `IFormatter` for backward compat.
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

## TOON Format

TOON (Token-Oriented Object Notation) emits indentation-aware key:value lines without
JSON's punctuation overhead. Example:

```
file: src/foo.py
language: python
classes:
  - name: Foo
    line: 12
    end_line: 80
    methods:
      - name: bar
        line: 14
```

Same data in JSON costs noticeably more tokens for typical AST outputs (the
50-70% TOON saving cited above; the exact ratio is pinned by `tests/unit/mcp/test_output_cost_invariants.py`).

Serialization helpers: `formatters/toon_formatter.py:_emit_*` (extracted in r37dm dogfood).

### TOON Encoder/Decoder internals

| Module | Role |
|---|---|
| `formatters/toon_encoder.py` | `ToonEncoder` — iterative encoder; `encode_value` for scalars |
| `formatters/_toon_encoder_string_helpers.py` | `needs_quotes`, `escape_string` — quoting rules |
| `formatters/_toon_encoder_table_helpers.py` | Array-table encoding: `union_schema`, `encode_array_table_lines` |
| `formatters/_toon_encoder_task_helpers.py` | Stack-based task dispatch helpers |
| `formatters/toon_decoder.py` | `decode_toon(token)` — inverse of `encode_value` for scalar tokens (issue #1058); `ToonDecodeError` |

The decoder is intentionally **scalar-only** (PR1 scope): it handles `null`, `true`/`false`, numbers, quoted strings, and bare words.
Full dict/list/table parsing is deferred to RFC-0018.

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

## See Also

- [`docs/toon-format-guide.md`](../toon-format-guide.md)
- [`docs/format_specifications.md`](../format_specifications.md)
- [`docs/format-testing-guide.md`](../format-testing-guide.md)
- [`CLAUDE.md` § "Deliberate design decisions"](../../CLAUDE.md) — TOON default rationale
- [`scripts/codemap-sync-check.sh`](../../scripts/codemap-sync-check.sh) — pre-commit gate that blocks new `formatters/*.py` without a `formatters.md` update
