"""Syntax plumbing shared by the grep oracle: parsers, tree walks, the repo view.

Runs under the gate interpreter (``tree_sitter`` and the grammars are imported
lazily, so the module itself is importable anywhere).
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GRAMMAR_BY_EXT = {
    ".java": "java",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".kt": "kotlin",
    ".kts": "kotlin",
}
TS_EXTS = (".ts", ".tsx", ".mts", ".cts", ".js", ".mjs", ".cjs", ".jsx")
KOTLIN_EXTS = (".kt", ".kts")
CLASS_TYPES = {
    "class_declaration",
    "abstract_class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
    "class",
}
INTERFACE_TYPES = {"interface_declaration"}


def make_parser(grammar: str) -> Any:
    from tree_sitter import Language, Parser

    if grammar == "java":
        import tree_sitter_java as mod

        return Parser(Language(mod.language()))
    if grammar in ("typescript", "tsx"):
        import tree_sitter_typescript as ts

        return Parser(
            Language(
                ts.language_typescript()
                if grammar == "typescript"
                else ts.language_tsx()
            )
        )
    if grammar == "javascript":
        import tree_sitter_javascript as js

        return Parser(Language(js.language()))
    if grammar == "kotlin":
        import tree_sitter_kotlin as kt

        return Parser(Language(kt.language()))
    raise ValueError(grammar)


def family(grammar: str) -> str:
    if grammar in ("java", "kotlin"):
        return grammar
    return "ts"


def text(node: Any) -> str:
    return (
        node.text.decode("utf-8", "replace")
        if node is not None and node.text is not None
        else ""
    )


def walk(node: Any) -> Iterator[Any]:
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(current.children)


def chain(node: Any) -> Iterator[Any]:
    current = node
    while current is not None:
        yield current
        current = current.parent


def is_field(node: Any, parent: Any, name: str) -> bool:
    """``node`` is ``parent``'s child in field ``name``."""
    child = parent.child_by_field_name(name) if parent is not None else None
    return child is not None and child.id == node.id


def grammar_of(rel: str) -> str | None:
    return next((g for ext, g in GRAMMAR_BY_EXT.items() if rel.endswith(ext)), None)


@dataclass
class Repo:
    """A git checkout seen by the oracle (parsed files are memoized)."""

    root: Path
    parsers: dict[str, Any] = field(default_factory=dict)
    trees: dict[str, tuple[Any, bytes, str]] = field(default_factory=dict)
    memo: dict[str, Any] = field(default_factory=dict)

    def git(self, *args: str) -> str:
        proc = subprocess.run(
            ["git", "-C", str(self.root), *args], capture_output=True, check=False
        )
        if proc.returncode not in (0, 1):  # 1 = grep found nothing
            raise RuntimeError(
                f"git {args} failed: {proc.stderr.decode('utf-8', 'replace')}"
            )
        return proc.stdout.decode("utf-8", "replace")

    def tracked(self) -> set[str]:
        if "tracked" not in self.memo:
            self.memo["tracked"] = {
                f for f in self.git("ls-files", "-z").split("\0") if f
            }
        tracked: set[str] = self.memo["tracked"]
        return tracked

    def tree(self, rel: str) -> tuple[Any, bytes, str] | None:
        if rel in self.trees:
            return self.trees[rel]
        grammar = grammar_of(rel)
        if grammar is None:
            return None
        if grammar not in self.parsers:
            self.parsers[grammar] = make_parser(grammar)
        src = (self.root / rel).read_bytes()
        parsed = (self.parsers[grammar].parse(src), src, grammar)
        self.trees[rel] = parsed
        return parsed

    def files(self, fam: str) -> list[str]:
        exts = {"java": (".java",), "kotlin": KOTLIN_EXTS}.get(fam, TS_EXTS)
        return sorted(
            f
            for f in self.tracked()
            if f.endswith(exts) and not f.endswith(".d.ts.map")
        )
