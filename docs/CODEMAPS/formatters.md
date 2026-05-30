<!-- Generated: 2026-05-30 -->
# Formatters Codemap

Output formats supported by both CLI and MCP. Located in `tree_sitter_analyzer/formatters/`.

## Format Registry

| Format | Module | Default for | Use case |
|---|---|---|---|
| `toon` | `formatters/toon_formatter.py` | **MCP** | LLM agents — 73% smaller than JSON |
| `json` | `formatters/json_formatter.py` | **CLI** | `jq` piping, programmatic ingestion |
| `table` | `formatters/table_formatter.py` (canonical, re-exports `LegacyTableFormatter`) + `tree_sitter_analyzer/default_table_formatter.py` + `legacy_table_formatter.py` | `--table` flag | Terminal viewing with box-drawing chars |
| `csv` | via `tree_sitter_analyzer/_legacy_table_formatter_csv.py` | `--table csv` | Spreadsheet ingestion |
| `yaml` | `formatters/yaml_formatter.py` | explicit `--format yaml` | Human-readable structured |

## Why TOON for MCP, JSON for CLI?

**Locked design decision** (see `CLAUDE.md`):

| | TOON | JSON |
|---|---|---|
| Token cost | -73% | baseline |
| Loss | none | none |
| `jq` friendliness | no | yes |
| Human readability | medium | high |

→ MCP callers are LLM agents → token cost is real money → TOON wins.
→ CLI callers are humans / shells → `jq` & readability win → JSON wins.

**Do NOT propose flipping MCP default from `toon` to `json`** — the cost analysis is settled.

## Formatter Architecture

Each formatter inherits from `formatters/base_formatter.py`:

```python
class BaseFormatter(ABC):
    def format(self, result: AnalysisResult) -> str: ...
    def _format_full(self, ...) -> str: ...
    def _format_compact(self, ...) -> str: ...
    def _format_csv(self, ...) -> str: ...
```

Per-language formatter mixins live alongside (`_java_formatter_*_mixin.py`,
`_cpp_formatter_*_mixin.py`, etc.) and are composed into the concrete formatter
classes via Python's MRO.

## TOON Format

TOON (Token-Optimized Object Notation) emits indentation-aware key:value lines without
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

Same data in JSON: ~30% more chars, ~73% more tokens for typical AST outputs.

Serialization helpers: `formatters/toon_formatter.py:_emit_*` (extracted in r37dm dogfood).

## Format Stability Contract

Format changes are tracked by:

- `docs/format_specifications.md` — canonical schema
- `docs/SMART_JSON_COMPARISON_SYSTEM.md` — diff tooling
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
