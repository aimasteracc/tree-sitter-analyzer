## MCP Tools: list_files, search_content, find_and_grep

Purpose: Provide a safe, composable file/name search and content search capability via fd and ripgrep, unified behind consistent MCP tool interfaces.

### Principles
- Simple, consistent inputs; machine-readable outputs.
- Security: enforce project-root boundaries, result caps, timeouts, and filesize limits.
- Composability: allow fd-only, rg-only, or fd→rg in one call.

### Common Safety Defaults
- roots must lie within project root; reject paths outside.
- limit caps: list_files.limit default 2000, hard-cap 10000.
- file_limit default 2000, hard-cap 10000.
- rg --max-filesize default 10M; overridable but hard-capped to 200M.
- rg timeout default 4000 ms; hard-capped at 30000 ms.
- Hidden/ignore: by default respect .gitignore; hidden=false; no_ignore=false.

### Tool 1: list_files (fd)
Input schema (subset):
- roots: string[] (required)
- pattern?: string; glob?: boolean=false
- types?: string[] (fd -t f/d/l/x/e)
- extensions?: string[] (fd -e)
- exclude?: string[] (glob -> fd -E)
- depth?: number (fd -d)
- follow_symlinks?: boolean (fd -L)
- hidden?: boolean (fd -H)
- no_ignore?: boolean (fd -I)
- size?: string[] (fd -S, eg +10M)
- changed_within?: string (eg 2d)
- changed_before?: string
- full_path_match?: boolean (-p)
- absolute?: boolean (-a)
- limit?: number

Output:
- JSON array of { path, is_dir, size_bytes?, mtime?, ext? }
- All paths absolute.

Mapping to fd:
- Use fd with --color=never and templated --format to produce machine-readable TSV/JSONL.
- For cross-platform stability, prefer TSV and parse.

### Tool 2: search_content (ripgrep)
Input:
- roots?: string[] or files?: string[] (one required)
- query: string (required)
- regex?: boolean=true; fixed_strings?: boolean; word?: boolean
- case?: "smart"|"insensitive"|"sensitive"
- multiline?: boolean
- include_globs?: string[]; exclude_globs?: string[]
- follow_symlinks?: boolean; hidden?: boolean; no_ignore?: boolean
- max_filesize?: string (default 10M, hard-cap 200M)
- context_before?: number; context_after?: number
- encoding?: string; max_count?: number; timeout_ms?: number (default 4000)

Output:
- Array of matches: { file, abs_path, line_number, line, submatches:[{start,end,match}] }
- Only emit match events from rg --json.

Mapping to ripgrep:
- Always pass --json --no-heading --color=never.
- case -> -S/-i/-s; fixed -> -F; word -> -w; multiline -> -U.
- include_globs/exclude_globs -> repeated -g patterns; exclusions prefixed with '!'.
- Respect hidden/no_ignore/follow_symlinks.

### Tool 3: find_and_grep (fd→rg)
Input:
- All relevant list_files inputs + search_content core inputs
- file_limit?: number (truncate fd outputs before rg)
- sort?: "path"|"mtime"|"size"

Output:
- Same as search_content plus meta: { searched_file_count, truncated, fd_elapsed_ms, rg_elapsed_ms }

Implementation Notes
- SecurityValidator: validate roots under project boundary; reject absolute roots outside.
- Use PathResolver to normalize/absolutize. De-duplicate files.
- For large sets, write file list to a temporary file; pass via rg --files-from.
- Enforce caps and timeouts at both subprocess level (rg --timeout) and asyncio wait_for.
- Windows/macOS/Linux compatible; ensure UTF-8 I/O; no color codes.

Testing Strategy
- Unit tests: argument validation, boundary checks, flag mapping, JSON parsing.
- Mocked subprocess for fd/rg happy-path and error-path.
- Integration smoke test gated by environment (skipped on CI if binaries missing).

Version Bounds
- fd ≥ 10.x; ripgrep ≥ 13.x. Tools degrade gracefully with clear error messages if missing.

