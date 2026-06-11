### TSA Mis-Wire Scorecard

| field | value |
|---|---|
| repo | `<repo-name>` |
| languages | `<e.g. Rust+Py+TS>` |
| call edges | `<N>` |
| name-only mis-wires (genuine floor) | `<N> (<X.XX%>)` |
| TSA mis-wires | `<N> (<X.XX%>)` |
| multiplier | `<Nx cleaner>` |
| TSA version | `<uv run python -m tree_sitter_analyzer --version>` |
| indexed at commit | `<git rev-parse --short HEAD>` |

**Run command:**
```bash
uvx --from tree-sitter-analyzer miswire-audit . --card
```
