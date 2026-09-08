"""使用新鲜 Python AST 和词法标记规划保守的重命名。"""

from __future__ import annotations

import ast
import io
import keyword
import re
import tokenize
import unicodedata
from pathlib import Path
from typing import Any


def read_source(path: Path) -> tuple[bytes, str, str]:
    """按源文件声明解码，同时保存原始字节。"""
    raw = path.read_bytes()
    encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
    return raw, raw.decode(encoding), encoding


def plan_python(root: str, old: str, new: str) -> tuple[list[Any], dict[str, bytes]]:
    """支持唯一的模块级函数、类及直接导入；遇到不明确绑定立即拒绝。"""
    from .ast_cache import _walk_source_files
    from .rename_symbol import RenameSite

    if not old.isidentifier() or not new.isidentifier() or keyword.iskeyword(new):
        raise ValueError("Only unqualified Python identifiers are supported")
    if new == "__debug__" or any(
        unicodedata.normalize("NFKC", name) != name
        or (name.startswith("__") and not name.endswith("__"))
        for name in (old, new)
    ):
        raise ValueError("Reserved or non-normalized identifiers are unsupported")
    base = Path(root).resolve()
    sources = {}
    definitions: list[
        tuple[Path, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef]
    ] = []
    for filename in _walk_source_files(root):
        path = Path(filename).resolve()
        if not path.is_relative_to(base):
            raise ValueError("Source path is outside project root")
        if path.suffix != ".py":
            if re.search(
                rb"\b" + re.escape(old.encode("utf-8")) + rb"\b", path.read_bytes()
            ):
                raise ValueError("Potential non-Python references are unsupported")
            continue
        raw, text, encoding = read_source(path)
        tree = ast.parse(text, filename=str(path))
        sources[path] = (raw, text, encoding, tree)
        definitions.extend(
            (path, node)
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.name == old
        )
    if not definitions:
        if any(
            getattr(node, "name", None) == old
            or (isinstance(node, ast.Name) and node.id == old)
            for _, _, _, tree in sources.values()
            for node in ast.walk(tree)
        ):
            raise ValueError("Only module-level functions and classes are supported")
        return [], {}
    if len(definitions) != 1:
        raise ValueError("Ambiguous symbol: multiple definitions")
    target_path, target = definitions[0]
    if isinstance(target, ast.ClassDef):
        for node in ast.walk(target):
            if isinstance(node, ast.Name) and node.id == "__slots__":
                raise ValueError("Classes with __slots__ are unsupported")
            for field in ("name", "id", "attr", "arg"):
                identifier = getattr(node, field, None)
                if (
                    isinstance(identifier, str)
                    and identifier.startswith("__")
                    and not identifier.endswith("__")
                ):
                    raise ValueError(
                        "Classes with private name mangling are unsupported"
                    )
    module = ".".join(target_path.relative_to(base).with_suffix("").parts)
    sites = []
    backups = {}
    for path, (raw, text, _encoding, tree) in sources.items():
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
        imported = []
        for node in ast.walk(tree):
            if getattr(node, "type_params", None):
                raise ValueError("Generic type parameter bindings are unsupported")
            for annotation in (
                getattr(node, "annotation", None),
                getattr(node, "returns", None),
            ):
                if annotation is not None and any(
                    isinstance(part, ast.Constant)
                    and isinstance(part.value, str)
                    and re.search(r"\b" + re.escape(old) + r"\b", part.value)
                    for part in ast.walk(annotation)
                ):
                    raise ValueError("String forward references are unsupported")
            if isinstance(node, ast.Name) and node.id == "__all__":
                raise ValueError("Explicit export lists are unsupported")
            if isinstance(node, ast.MatchMapping) and node.rest in {old, new}:
                raise ValueError("Pattern binding is unsupported")
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "*":
                        raise ValueError("Wildcard imports are unsupported")
                    if alias.name == old:
                        if node.level or node.module != module or node not in tree.body:
                            raise ValueError("Unsupported or ambiguous import")
                        imported.append(alias)
        active = path == target_path or any(a.asname is None for a in imported)
        if len(imported) > 1 or (path == target_path and imported):
            raise ValueError("Ambiguous import binding")
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == old:
                raise ValueError(
                    "Attribute references require unsupported binding resolution"
                )
            if isinstance(node, (ast.Global, ast.Nonlocal)) and (
                {old, new} & set(node.names)
            ):
                raise ValueError("Global/nonlocal declarations are unsupported")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id
                in {"eval", "exec", "globals", "locals", "getattr", "setattr"}
            ):
                raise ValueError("Dynamic symbol access is unsupported")
            if not active:
                continue
            if isinstance(node, ast.Name) and node.id in {old, new}:
                if node.id == new or not isinstance(node.ctx, ast.Load):
                    raise ValueError("Conflicting or shadowed symbol binding")
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and node.name in {old, new}
                and node is not target
            ):
                raise ValueError("Conflicting or shadowed definition")
            if isinstance(node, ast.arg) and node.arg in {old, new}:
                raise ValueError("Shadowed parameter binding is unsupported")
            if (
                isinstance(node, ast.alias)
                and (node.asname or node.name.split(".")[0]) in {old, new}
                and node not in imported
            ):
                raise ValueError("Conflicting import binding")
            if isinstance(
                node, (ast.MatchAs, ast.MatchStar, ast.ExceptHandler)
            ) and node.name in {old, new}:
                raise ValueError("Pattern or exception binding is unsupported")
        selected = []
        if path == target_path:
            selected.append((target.lineno, target.col_offset, "definition"))
        selected.extend((a.lineno, a.col_offset, "import") for a in imported)
        if active:
            selected.extend(
                (n.lineno, n.col_offset, "reference")
                for n in ast.walk(tree)
                if isinstance(n, ast.Name) and n.id == old
            )
        lines = text.split("\n")
        for line, byte_col, kind in selected:
            col = len(lines[line - 1].encode("utf-8")[:byte_col].decode("utf-8"))
            matches = [
                t
                for t in tokens
                if t.type == tokenize.NAME
                and t.string == old
                and t.start[0] == line
                and (t.start[1] >= col if kind == "definition" else t.start[1] == col)
            ]
            if not matches:
                raise ValueError("Cannot locate exact identifier token")
            token = matches[0]
            sites.append(
                RenameSite(str(path.relative_to(base)), line, token.start[1], old, kind)
            )
            backups[str(path)] = raw
    sites.sort(key=lambda s: (s.file, s.line, s.column))
    return sites, backups
