# AGENTS.md

## Cursor Cloud specific instructions

### Project overview

Tree-sitter Analyzer is a Python-based code analysis tool using tree-sitter grammars (17 languages). It exposes functionality via CLI tools and an MCP (Model Context Protocol) server. Single-package Python project (not a monorepo).

### Prerequisites (system-level)

- **Python 3.10+** (runtime)
- **uv** (package manager; install via `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **fd** (file finder; on Ubuntu `apt install fd-find` then `ln -sf /usr/bin/fdfind /usr/local/bin/fd`)
- **rg** (ripgrep; typically pre-installed)

### Dependencies

```bash
uv sync --extra all --extra mcp
```

### Lint / Test / Build / Run

All standard commands are documented in `README.md` under the "Development" and "Testing" sections. Key commands:

| Task | Command |
|------|---------|
| Lint | `uv run ruff check .` |
| Unit tests | `uv run pytest tests/unit/ -v` |
| Integration tests | `uv run pytest tests/integration/ -v` |
| All tests | `uv run pytest tests/ -v` |
| CLI analysis | `uv run tree-sitter-analyzer examples/Sample.java --table full` |
| MCP server | `uv run tree-sitter-analyzer-mcp` (stdio-based, not a long-running network service) |
| Search content | `uv run search-content --roots . --query "pattern"` |
| Find and grep | `uv run find-and-grep --roots . --query "pattern" --extensions java` |
| List files | `uv run list-files <dir> --extensions java` |

### Non-obvious caveats

- On Ubuntu/Debian, `fd` is packaged as `fd-find` and the binary is named `fdfind`. The code expects the `fd` command, so a symlink is required: `sudo ln -sf /usr/bin/fdfind /usr/local/bin/fd`.
- The MCP server is a **stdio-based** process (not HTTP). It is launched by AI IDE clients (Cursor, Claude Desktop) and communicates via JSON-RPC over stdin/stdout. To test it manually, pipe JSON-RPC messages to `uv run tree-sitter-analyzer-mcp`.
- `list-files` CLI takes `roots` as a **positional** argument (not `--roots`), unlike other CLI tools.
- `pytest.ini` exists and adds `--strict-markers` and `--strict-config` by default. Do not use unregistered markers.
- The `pytest-asyncio` version used requires `asyncio_mode = "strict"` (set in `pyproject.toml`). Async tests must use `@pytest.mark.asyncio`.
