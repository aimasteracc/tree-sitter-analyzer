#!/usr/bin/env python3
"""Enumerate the MCP tool-name surface and the CLI flag surface.

Support tool for ``scripts/codemap-sync-check.sh``. The gate compares the
*surface set* before and after a staged change instead of pattern-matching added
diff lines, because added-line matching is wrong from both ends: a comment or a
docstring mentioning the old shape triggers it, while a dict-literal or
``append``-in-a-loop registration slips past it. Set comparison is immune to
comments, docstrings, reordering, renames, literal shape and — unlike
added-line matching — it also detects *removals*.

Extraction is static (``ast``), never an import, so the pre-commit path costs no
package-import time (importing ``cli_main`` to build the real parser measures
~640 ms; see ``--help`` of the shell gate for the split rationale). The static
extractor is not trusted on faith: ``codemap-sync-check.sh --self-check``
asserts exact set equality between what this script extracts and the
authoritative runtime enumerations from ``CLAUDE.md``
(``create_argument_parser()`` option strings; ``create_tool_registry('.')``).
If a future code shape defeats static extraction, that equality fails loudly.

Revisions are read through ``git cat-file --batch`` (one subprocess for any
number of paths), so no shell quoting, ``core.quotePath`` or ``diff.noprefix``
setting can affect the result.
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

# --- watched surface (single source of truth, consumed by the shell gate) ----
MCP_REGISTRY = "tree_sitter_analyzer/mcp/_tool_registry.py"

# The CLI flag surface is *all* of tree_sitter_analyzer/cli/**. Narrowing this to
# argument_groups/ would leave the find-and-grep / list-files / search-content
# console scripts — documented entry points in docs/CODEMAPS/cli.md — unwatched.
CLI_PREFIX = "tree_sitter_analyzer/cli/"

# argparse synthesises these; no source line defines them.
ARGPARSE_IMPLICIT_FLAGS = frozenset({"-h", "--help"})

WORKTREE = "WORKTREE"
INDEX = "INDEX"


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True, encoding="utf-8"
    ).stdout


def list_paths(rev: str) -> list[str]:
    """Every tracked ``.py`` path in the watched surface at ``rev``."""
    if rev in (WORKTREE, INDEX):
        # ls-files reads the index, which is what "staged" means; for WORKTREE the
        # index path set is the same modulo untracked files, which cannot be staged.
        out = _git("ls-files", "-z", "--", MCP_REGISTRY, CLI_PREFIX)
    else:
        out = _git("ls-tree", "-r", "-z", "--name-only", rev)
    paths = [p for p in out.split("\0") if p]
    return sorted(
        p
        for p in paths
        if p.endswith(".py") and (p == MCP_REGISTRY or p.startswith(CLI_PREFIX))
    )


def read_blobs(rev: str, paths: list[str]) -> dict[str, str]:
    """Read many paths at ``rev`` in one subprocess.

    ``rev`` may be ``WORKTREE`` (read from disk), ``INDEX`` (the staged tree, spelled
    ``:path`` to git) or any revision (``HEAD:path``).
    """
    if not paths:
        return {}
    if rev == WORKTREE:
        result = {}
        for p in paths:
            try:
                result[p] = Path(p).read_text(encoding="utf-8")
            except OSError:
                continue
        return result

    prefix = "" if rev == INDEX else rev
    specs = "".join(f"{prefix}:{p}\n" for p in paths)
    proc = subprocess.run(
        ["git", "cat-file", "--batch"],
        input=specs.encode("utf-8"),
        capture_output=True,
        check=True,
    )
    return _parse_batch(proc.stdout, paths)


def _parse_batch(raw: bytes, paths: list[str]) -> dict[str, str]:
    """Decode ``git cat-file --batch`` output, in request order."""
    result: dict[str, str] = {}
    pos = 0
    for path in paths:
        nl = raw.find(b"\n", pos)
        if nl == -1:
            break
        header = raw[pos:nl].decode("utf-8", "replace")
        if header.endswith(("missing", "ambiguous")):
            pos = nl + 1
            continue
        try:
            size = int(header.rsplit(" ", 1)[1])
        except (IndexError, ValueError):
            break
        body = raw[nl + 1 : nl + 1 + size]
        result[path] = body.decode("utf-8", "replace")
        pos = nl + 1 + size + 1  # trailing newline after each blob
    return result


# --- extraction ------------------------------------------------------------
def extract_mcp_names(source: str) -> set[str]:
    """Registered MCP tool names.

    Matches the *semantic* registration shape — a string key paired with a value —
    in every literal form the registry has used or might use: a list of
    ``("name", build_x_facade(root))`` tuples, a ``{"name": ...}`` dict literal, or
    ``.append(("name", ...))`` inside a loop. Docstrings and comments are not AST
    nodes of this shape, so prose about an old registration cannot trigger.
    """
    names: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return names
    for node in ast.walk(tree):
        if isinstance(node, ast.Tuple) and len(node.elts) == 2:
            first = node.elts[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                names.add(first.value)
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    names.add(key.value)
    return names


def extract_cli_flags(source: str) -> set[str]:
    """Option strings passed to any ``*.add_argument(...)`` call.

    Positional arguments (no leading ``-``) are excluded: they are not flags and
    docs/CODEMAPS/cli.md counts flags.
    """
    flags: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return flags
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
        ):
            for arg in node.args:
                if (
                    isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and arg.value.startswith("-")
                ):
                    flags.add(arg.value)
    return flags


def surface(rev: str, kind: str) -> set[str]:
    paths = list_paths(rev)
    if kind == "mcp":
        paths = [p for p in paths if p == MCP_REGISTRY]
        extract = extract_mcp_names
    else:
        paths = [p for p in paths if p.startswith(CLI_PREFIX)]
        extract = extract_cli_flags
    blobs = read_blobs(rev, paths)
    out: set[str] = set()
    for source in blobs.values():
        out |= extract(source)
    return out


def compare(base: str, head: str) -> list[str]:
    """Report surface set differences between two revisions, one line per change.

    Output is ``<kind> <added|removed> <item>``. An empty result means no surface
    changed, which is the only thing the gate needs to decide whether to fire.
    """
    lines: list[str] = []
    for kind in ("mcp", "cli"):
        before = surface(base, kind)
        after = surface(head, kind)
        lines.extend(f"{kind} added {item}" for item in sorted(after - before))
        lines.extend(f"{kind} removed {item}" for item in sorted(before - after))
    return lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["mcp", "cli", "paths", "compare"])
    parser.add_argument("--base", default="HEAD", help="compare mode: base revision")
    parser.add_argument("--head", default=INDEX, help="compare mode: head revision")
    parser.add_argument(
        "--rev",
        default=WORKTREE,
        help="git revision, INDEX for the staged tree, or WORKTREE (default)",
    )
    args = parser.parse_args(argv)

    if args.kind == "compare":
        for line in compare(args.base, args.head):
            print(line)
        return 0
    if args.kind == "paths":
        for path in list_paths(args.rev):
            print(path)
        return 0
    for item in sorted(surface(args.rev, args.kind)):
        print(item)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
