# Sprint 3: Incremental Scan — Design

## Architecture

### Cache Structure (in-memory, on `ProjectCodeMap` instance)

```python
@dataclass
class _FileCache:
    mtime: float          # os.stat st_mtime
    module: ModuleInfo    # parsed result

class ProjectCodeMap:
    _file_cache: dict[str, _FileCache]  # rel_path -> cache entry
    _last_project_dir: str | None       # to invalidate on project switch
```

### Algorithm

```
scan(project_dir):
    if project_dir != _last_project_dir:
        _file_cache.clear()       # project switched, full reset
        _last_project_dir = project_dir

    discovered = _discover_files(root, extensions, exclude_dirs)
    discovered_rel = {rel_path(f) for f in discovered}

    # 1. Remove cached entries for deleted files
    for cached_path in list(_file_cache):
        if cached_path not in discovered_rel:
            del _file_cache[cached_path]

    # 2. Parse only new/changed files
    modules = []
    for file_path in discovered:
        rel = rel_path(file_path)
        current_mtime = file_path.stat().st_mtime
        cached = _file_cache.get(rel)

        if cached and cached.mtime == current_mtime:
            modules.append(cached.module)    # HIT: skip parse
        else:
            module = self._parse_file(root, file_path)  # MISS: parse
            if module:
                _file_cache[rel] = _FileCache(mtime=current_mtime, module=module)
                modules.append(module)

    # 3. Rebuild result from modules (fast, <50ms for 100+ files)
    result = CodeMapResult(project_dir=project_dir)
    result.modules = modules
    self._build_symbol_index(result)
    self._build_dependencies(result)
    self._detect_entry_points(result)
    self._detect_dead_code(result)
    self._compute_hot_spots(result)
    return result
```

### Key Decisions

1. **In-memory only** — No pickle/disk cache. Simpler, avoids stale cache issues.
   Disk cache is a Phase A2/A3 enhancement.

2. **mtime equality check** — Using `==` not `>`. If mtime went backwards
   (e.g., git checkout), we re-parse. This is the safest approach.

3. **Full index rebuild** — Even with cached modules, we rebuild symbols/deps/dead_code.
   This is O(N) where N=number of symbols (~500 for 100K LOC) and takes <50ms.
   The expensive part is `_parse_file` (Tree-sitter parse), which we skip.

4. **Thread safety** — Not addressed (same as current). MCP server is single-threaded.

### Test Plan

| Test | Scenario | Assertion |
|------|----------|-----------|
| T1 | Two scans, no changes | Second scan <500ms, results identical |
| T2 | One file modified between scans | Only that module re-parsed, count correct |
| T3 | File deleted between scans | Module removed from results |
| T4 | New file added between scans | New module appears in results |
| T5 | Different project_dir | Cache cleared, full re-scan |
| T6 | Result correctness | Incremental result == full result (symbol-by-symbol) |
