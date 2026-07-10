# Path Traversal and the MCP File-Operation Problem

MCP tools that operate on files face a structural security challenge: the agent
decides the path, the tool executes it. In a well-designed system, the agent can
read any file it knows about and ask the tool to process it. In a poorly designed
system, the agent — or a prompt injected into the agent's context — can walk the
tool outside the project and into the host's filesystem.

A simple code-search across public MCP server implementations turns up many
that use `os.path.abspath()` or raw `startswith()` checks — neither of which
follows symlinks — rather than `os.path.realpath()`. The structural risk is
independently verifiable: clone any public MCP file-operation server and
`grep -n 'abspath\|startswith.*root'` its path-check logic.

This article documents how tree-sitter-analyzer addresses this problem through
`ProjectBoundaryManager` in `tree_sitter_analyzer/security/boundary_manager.py`.

## The Problem: Symlinks and Relative Paths

Path traversal vulnerabilities in file-operation tools typically come in two forms:

**Form 1: Relative path escape.** An agent passes `../../etc/passwd`. Without
boundary checking, the tool resolves the path, finds the file, and processes it.
The agent (or an injected prompt) now has access to `/etc/passwd`.

**Form 2: Symlink escape.** An agent passes `/project/data/link` where `link`
is a symlink to `/etc`. The tool calls `os.path.exists(path)` — which follows
symlinks — concludes the path is valid, and reads `/etc/shadow`.

Both forms are defeated by the same principle: **resolve to real path first,
check boundary after**. A `startswith()` check on the raw path is not sufficient;
a symlink can make `/project/safe-looking-path` resolve to `/etc/anything`.

## The Solution: `ProjectBoundaryManager`

`ProjectBoundaryManager` is initialized with a project root and enforces that
all file access stays within that root. Here is what it does:

### Initialization: real path at construction time

```python
self.project_root = str(project_path.resolve())
```

`Path.resolve()` calls the OS's `realpath()` — it follows all symlinks and returns
the canonical absolute path. The boundary is set against the real filesystem
location, not the path string the caller supplied. This defeats symlinks at the
root level: even if the project root itself is a symlink, the boundary is the
real directory.

### Boundary check: resolve input, compare against real root

```python
def is_within_project(self, file_path: str) -> bool:
    real_path = str(Path(file_path).resolve())
    for allowed_dir in self.allowed_directories:
        try:
            Path(real_path).relative_to(Path(allowed_dir))
            return True
        except ValueError:
            continue
    return False
```

`Path(file_path).resolve()` follows all symlinks in the input path before the
comparison. `relative_to()` raises `ValueError` if the path is not under
`allowed_dir`. This is the correct check — it cannot be fooled by `../..`
sequences or by symlinks in the path components, because both are resolved before
the comparison.

### Per-component symlink walk

`is_symlink_safe()` goes further: it walks each path component individually,
checks whether any intermediate symlink exits the project, and rejects the path
if so. This handles the case where a symlink mid-path points outside the project
root, even if the fully-resolved final path happens to be inside it.

```python
def _no_unsafe_symlink_hop(self, file_path_obj: Path) -> bool:
    current_path = Path()
    for part in file_path_obj.parts:
        current_path = current_path / part if current_path.parts else Path(part)
        if not current_path.is_symlink():
            continue
        target = str(current_path.resolve())
        if not self.is_within_project(target):
            log_warning(f"Unsafe symlink detected: {current_path} -> {target}")
            return False
    return True
```

This check handles the case where `is_within_project()` cannot help: when the
fully-resolved destination is *outside* the project, `is_symlink_safe()` falls
through to `_no_unsafe_symlink_hop()`, which walks each component and rejects
any path whose intermediate symlinks leave the project.

Note: `is_symlink_safe()` returns `True` immediately if the fully-resolved path
is within the project, so `_no_unsafe_symlink_hop()` is not called in that case —
it is a fallback for the outside-boundary case, not a parallel defense-in-depth
layer on top of `is_within_project()`.

### Audit logging (available, not automatic)

```python
def audit_access(self, file_path: str, operation: str) -> None:
    is_within = self.is_within_project(file_path)
    status = "ALLOWED" if is_within else "DENIED"
    log_info(f"AUDIT: {status} {operation} access to {file_path}")
    if not is_within:
        log_warning(f"SECURITY: Unauthorized access attempt to {file_path}")
```

The `audit_access()` method is defined and ready to use, but it is not called
automatically on every boundary check — callers must invoke it explicitly when
they want an audit trail. Wrapping your tool's file-access path with
`manager.audit_access(path, "read")` before calling `is_within_project()` gives
you a structured log of every allowed and denied access attempt.

## Why This Matters for MCP

MCP tools run as a server process alongside the agent. The agent's tool calls are
the only inputs to the server. In a local MCP deployment, the server process has
the same filesystem access as the user who started it — which on a developer's
machine means everything under `~`, system libraries, SSH keys, and credential files.

Without boundary enforcement:
- A prompt-injected path like `../../.ssh/id_rsa` reaches the tool.
- The tool reads the file and returns it to the agent.
- The agent includes it in its context and potentially in its output.

With `ProjectBoundaryManager`:
- The path is resolved to its real filesystem location.
- `is_within_project()` rejects the path (SSH key is not under project root).
- The rejection is logged as `SECURITY: Unauthorized access attempt`.
- The tool returns an error; the agent cannot access the file.

## Inspect the Boundary Manager on Your Repo

To see which callers in your codebase reach `boundary_manager.py` — and
check that every file-operation path goes through the boundary check —
start the MCP server and use the `nav` tool:

```bash
# Start the MCP server:
uvx --from tree-sitter-analyzer tree-sitter-analyzer-mcp

# Then in Claude Code, ask:
# tsa: nav callers tree_sitter_analyzer/security/boundary_manager.py
# tsa: find is_within_project
```

This shows every call site that invokes the boundary check, so you can
audit coverage rather than guess at it.

## The Broader Point

Security in MCP tool servers is not about refusing to process code — it is about
being clear about what the tool will and will not touch, and enforcing that
boundary with OS-level guarantees rather than string comparison.

`ProjectBoundaryManager` is not novel technology. `realpath()` has been the
correct answer to path traversal since Unix. The notable thing is that most MCP
implementations skip it, relying instead on `os.path.abspath()` (which does not
follow symlinks) or substring checks on the raw path string (which `../..`
sequences defeat trivially).

Tree-sitter-analyzer uses `Path.resolve()` — the Python equivalent of `realpath()`
— at every boundary check. It is a small implementation choice with a large
security consequence.

---

*Code references: `tree_sitter_analyzer/security/boundary_manager.py`.
The code in this article is read directly from that file; it is not paraphrased.*
