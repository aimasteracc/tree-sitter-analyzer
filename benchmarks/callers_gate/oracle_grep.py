"""``git grep -w`` oracle for changed TS/JS/Java ``complete`` answers.

Every occurrence of the target's bare name in a tracked text file is put in
exactly one class. Only ``residual`` needs a human; every other class is a
proof that the occurrence is not an unlisted caller:

``caller``          its innermost enclosing definition (by tree-sitter byte
                    range, see :mod:`.oracle_scope`) is a listed caller, by
                    exact name and start line; the answer's ``end_line`` is
                    never used
``own_declaration`` the name token of the target's own declaration
``declaration``     the name token of another declaration (not a use)
``import_export``   an un-aliased import / export specifier (a binding, not a
                    call), or an aliased import whose every local use is proven
``comment``         inside a comment (tree-sitter)
``string``          inside a string literal whose text is not exactly the name
``non_code``        a docs/data file (``.md``, ``.json``, ...)
``other_symbol``    provably a different symbol: ``X.name`` / ``this.name`` on
                    a project class (bound in that file to the class of that
                    name) with no inheritance relation to the target's class,
                    or a bare name bound only by imports of external modules
``residual``        anything else, with the reason it could not be proven

A hit inside a parse error is residual before any other check. Default
exports and aliased re-exports are residual: importers may bind them under a
name that ``git grep`` never sees.

Runs under the gate interpreter (needs ``tree_sitter`` and the grammars)::

    python -s -P -m benchmarks.callers_gate.oracle_grep <request.json> <response.json>
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .oracle_bindings import (
    bound_only_by_external_imports,
    name_binds_class_java,
    name_binds_class_ts,
)
from .oracle_classes import (
    all_enclosing_classes,
    class_of_target,
    class_table,
    enclosing_class,
    innermost_named_class,
    java_packages,
)
from .oracle_kotlin import classify_kotlin
from .oracle_scope import listed, owner_at
from .oracle_syntax import CLASS_TYPES, Repo, chain, family, is_field, text, walk

__all__ = ["CLASSES", "Item", "Repo", "check_item", "classify", "site_covered"]

CLASSES = (
    "caller",
    "own_declaration",
    "declaration",
    "import_export",
    "comment",
    "string",
    "non_code",
    "other_symbol",
    "residual",
)
NON_CODE_EXTS = (
    ".md",
    ".mdx",
    ".markdown",
    ".rst",
    ".txt",
    ".json",
    ".jsonc",
    ".yml",
    ".yaml",
    ".toml",
    ".lock",
    ".csv",
    ".svg",
    ".html.snap",
    ".snap",
    ".properties",
    ".xml",
    ".gradle",
    ".cfg",
    ".ini",
    ".api",  # Kotlin binary-compatibility API dumps (kotlinpoet)
)
STRING_TYPES = {
    "string",
    "string_literal",
    "template_string",
    "text_block",
    "character_literal",
    "string_fragment",
    "multiline_string_literal",  # Kotlin """...""" (its ${...} stays code)
    "string_content",
}
INTERPOLATION_TYPES = {"template_substitution", "interpolation"}
DECL_TYPES = {
    "method_declaration",
    "constructor_declaration",
    "function_declaration",
    "generator_function_declaration",
    "method_definition",
    "method_signature",
    "abstract_method_signature",
    "function_signature",
    "class_declaration",
    "abstract_class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
    "annotation_type_declaration",
    "annotation_type_element_declaration",
    "type_alias_declaration",
    "variable_declarator",
    "public_field_definition",
    "enum_constant",
}
#: Import / re-export syntax only. Not ``export_statement``: ``export const a = f()`` is a call.
IMPORT_TYPES = {
    "import_statement",
    "import_declaration",
    "import_specifier",
    "export_specifier",
    "export_clause",
    "namespace_import",
    "import_clause",
}
#: Classes of an aliased name's local uses that prove the use is not an unlisted call.
ALIAS_PROVEN = {"caller", "comment", "string", "declaration"}
WORD = rb"[A-Za-z0-9_$]"


@dataclass
class Item:
    key: list[str]
    name: str
    file: str
    qual: str
    callers: list[dict[str, Any]]


def _string_ancestor(node: Any) -> Any | None:
    current = node
    while current is not None:
        if current.type in INTERPOLATION_TYPES:
            return None
        if current.type in STRING_TYPES:
            outer = current
            while outer.parent is not None and outer.parent.type in STRING_TYPES:
                outer = outer.parent
            return outer
        current = current.parent
    return None


def _in_parse_error(node: Any) -> bool:
    return any(a.type == "ERROR" or a.is_missing for a in chain(node))


def _default_export(node: Any) -> bool:
    parent = node.parent
    return (
        parent is not None
        and parent.type == "export_statement"
        and any(c.type == "default" for c in parent.children)
    )


def classify(
    repo: Repo,
    item: Item,
    rel: str,
    line: int,
    start: int,
    end: int,
    *,
    alias_mode: bool = False,
) -> tuple[str, str]:
    if rel.lower().endswith(NON_CODE_EXTS):
        return "non_code", ""
    parsed = repo.tree(rel)
    if parsed is None:
        return "residual", "file type the oracle cannot parse"
    tree, _src, grammar = parsed
    fam = family(grammar)
    node = tree.root_node.descendant_for_byte_range(start, end)
    if node is None:
        return "residual", "no syntax node at the occurrence"
    if _in_parse_error(node):
        return "residual", "parse error around the occurrence"
    if listed(item.callers, rel, owner_at(node, fam, line)):
        return "caller", ""
    if any("comment" in a.type for a in chain(node)):
        return "comment", ""
    string = _string_ancestor(node)
    if string is not None:
        literal = text(string).strip().strip("'\"`")
        if literal == item.name:
            return (
                "residual",
                "string literal equal to the name (possible dynamic dispatch)",
            )
        return "string", ""
    if fam == "kotlin":
        return classify_kotlin(repo, item, rel, node)
    parent = node.parent
    if (
        parent is not None
        and parent.type in DECL_TYPES
        and is_field(node, parent, "name")
    ):
        return _declaration(item, rel, fam, parent)
    if any(a.type in IMPORT_TYPES for a in chain(node)):
        return _import_export(repo, item, rel, node, alias_mode)
    if (
        parent is not None
        and parent.type == "export_statement"
        and is_field(node, parent, "value")
    ):
        return "residual", "default export of the name (importers may bind any name)"
    return _member_or_binding(repo, item, rel, fam, node, tree.root_node)


def _declaration(item: Item, rel: str, fam: str, decl: Any) -> tuple[str, str]:
    if rel != item.file:
        return "declaration", ""
    owner = enclosing_class(decl, fam)[0] if decl.type not in CLASS_TYPES else None
    target_cls = class_of_target(item.qual)
    if not (target_cls is None or owner == target_cls or decl.type in CLASS_TYPES):
        return "declaration", ""
    if _default_export(decl):
        return "residual", "default-exported declaration (importers may bind any name)"
    return "own_declaration", ""


def _import_export(
    repo: Repo, item: Item, rel: str, node: Any, alias_mode: bool
) -> tuple[str, str]:
    parent = node.parent
    if alias_mode:
        return "residual", f"`{item.name}` is imported or exported again"
    if parent is not None and parent.type == "export_specifier":
        alias = parent.child_by_field_name("alias")
        if (
            is_field(node, parent, "name")
            and alias is not None
            and text(alias) != item.name
        ):
            return (
                "residual",
                f"re-exported as `{text(alias)}` (importers use that name)",
            )
        return "import_export", ""
    if parent is not None and parent.type == "import_specifier":
        alias = parent.child_by_field_name("alias")
        if (
            is_field(node, parent, "name")
            and alias is not None
            and text(alias) != item.name
        ):
            proven, why = _follow_alias(repo, item, rel, alias)
            if not proven:
                return "residual", f"imported as `{text(alias)}`: {why}"
            return (
                "import_export",
                f"imported as `{text(alias)}`; every local use is proven",
            )
    return "import_export", ""


def _follow_alias(repo: Repo, item: Item, rel: str, alias: Any) -> tuple[bool, str]:
    """Classify every use of an import alias in its file; all must be proven."""
    name = text(alias)
    derived = Item(key=item.key, name=name, file="", qual=name, callers=item.callers)
    for orel, oline, ostart, oend, _t in occurrences(repo, name, files=[rel]):
        if ostart == alias.start_byte:
            continue
        cls, why = classify(repo, derived, orel, oline, ostart, oend, alias_mode=True)
        if cls not in ALIAS_PROVEN:
            return False, f"its use at line {oline} is not proven ({why or cls})"
    return True, ""


def _receiver_of(node: Any) -> Any | None:
    parent = node.parent
    if parent is None or parent.type not in (
        "member_expression",
        "field_access",
        "method_invocation",
    ):
        return None
    prop = (
        parent.child_by_field_name("property")
        or parent.child_by_field_name("field")
        or parent.child_by_field_name("name")
    )
    if prop is None or prop.id != node.id:
        return None
    receiver = parent.child_by_field_name("object")
    if receiver is None and parent.type == "method_invocation":
        return "<implicit>"
    return receiver


def _member_or_binding(
    repo: Repo, item: Item, rel: str, fam: str, node: Any, root: Any
) -> tuple[str, str]:
    parent = node.parent
    receiver = _receiver_of(node)
    if receiver is None:
        if parent is not None and parent.type in ("member_expression", "field_access"):
            return "residual", "the name is the receiver, not the member"
        if _external_binding(repo, rel, fam, root, item.name):
            return "other_symbol", "bound only by imports of external modules"
        return "residual", "bare name use"
    target_cls = class_of_target(item.qual)
    if target_cls is None:
        return "residual", "member use of a non-method target"
    table = class_table(repo, fam)
    _anc, closed = table.ancestors(target_cls)
    if target_cls not in table or not closed:
        return "residual", f"the ancestry of {target_cls} does not fully resolve"
    if not declared_directly_in(repo, item, fam, target_cls):
        return (
            "residual",
            f"the target is not declared directly in class {target_cls} "
            "(anonymous class, object literal, or not found)",
        )
    if receiver == "<implicit>":
        return _implicit_receiver(table, target_cls, node, root, item.name)
    if receiver.type in ("this",):
        owner, why = enclosing_class(node, fam)
        if owner is None:
            return "residual", f"`this` not provable ({why})"
        if table.related(owner, target_cls):
            return "residual", f"`this` of {owner}, related to {target_cls}"
        return "other_symbol", f"`this` of {owner}, unrelated to {target_cls}"
    if receiver.type in ("identifier", "type_identifier"):
        rname = text(receiver)
        binds = name_binds_class_java if fam == "java" else name_binds_class_ts
        if rname in table and binds(repo, rel, rname):
            if table.related(rname, target_cls):
                return "residual", f"receiver class {rname} is related to {target_cls}"
            return "other_symbol", f"static receiver {rname}, unrelated to {target_cls}"
        if rname in table:
            return (
                "residual",
                f"receiver `{rname}` is not provably the class {rname} in this file",
            )
    return "residual", "member access on a receiver of unknown type"


def _implicit_receiver(
    table: Any, target_cls: str, node: Any, root: Any, name: str
) -> tuple[str, str]:
    # Java: an unqualified call resolves in the innermost class, then each
    # enclosing class (and their supertypes), or through a static import.
    if _static_import_of(root, name):
        return "residual", "a static import may bind the name"
    owners = all_enclosing_classes(node)
    if owners is None:
        return "residual", "unqualified call inside an anonymous class"
    if not owners:
        return "residual", "unqualified call outside any class"
    if any(table.related(o, target_cls) for o in owners):
        return "residual", f"unqualified call inside {owners}, related to {target_cls}"
    return (
        "other_symbol",
        f"unqualified call inside {owners}, unrelated to {target_cls}",
    )


def declared_directly_in(repo: Repo, item: Item, fam: str, cls: str) -> bool:
    """Whether every declaration of the target in its file sits directly in class ``cls``.

    ``qual`` drops anonymous classes: a method of ``new Base() {...}`` inside
    ``Outer`` is reported as ``Outer.m`` although its dynamic class is a
    subclass of ``Base``. Such a target has no provable class, so no
    member / ``this`` use can be proven to miss it.
    """
    parsed = repo.tree(item.file)
    if parsed is None:
        return False
    found = False
    for node in walk(parsed[0].root_node):
        if node.type not in DECL_TYPES or node.type in CLASS_TYPES:
            continue
        name = node.child_by_field_name("name")
        if name is None or text(name) != item.name:
            continue
        if innermost_named_class(node) != cls:
            continue
        if enclosing_class(node, fam)[0] != cls:
            return False  # declared under cls, but inside an anonymous scope
        found = True
    return found


def _external_binding(repo: Repo, rel: str, fam: str, root: Any, name: str) -> bool:
    """Whether the file binds bare ``name`` only via imports from external modules."""
    if fam == "ts":
        return bound_only_by_external_imports(repo, rel, name)
    found_external = False
    for node in walk(root):
        if node.type != "import_declaration" or "static" not in text(node).split():
            continue
        m = re.search(r"import\s+static\s+([A-Za-z0-9_.]+)\s*;", text(node))
        if not m or not m.group(1).endswith("." + name):
            continue
        pkg = m.group(1).rsplit(".", 2)[0]
        if any(pkg == p or pkg.startswith(p + ".") for p in java_packages(repo)):
            return False
        found_external = True
    return found_external


def _static_import_of(root: Any, name: str) -> bool:
    for node in walk(root):
        if (
            node.type == "import_declaration"
            and "static" in text(node).split()
            and re.search(r"\." + re.escape(name) + r"\s*;", text(node))
        ):
            return True
    return False


def _word(name: str) -> re.Pattern[bytes]:
    return re.compile(
        rb"(?<!" + WORD + rb")" + re.escape(name.encode()) + rb"(?!" + WORD + rb")"
    )


def occurrences(
    repo: Repo, name: str, files: list[str] | None = None
) -> Iterator[tuple[str, int, int, int, str]]:
    """(file, 1-based line, byte start, byte end, line text) of every word occurrence."""
    if files is None:
        listed_files = repo.git("grep", "-l", "-z", "-I", "-w", "-F", "-e", name)
        files = sorted(f for f in listed_files.split("\0") if f)
    pattern = _word(name)
    for rel in files:
        data = (repo.root / rel).read_bytes()
        offset = 0
        for number, raw in enumerate(data.split(b"\n"), start=1):
            for m in pattern.finditer(raw):
                yield (
                    rel,
                    number,
                    offset + m.start(),
                    offset + m.end(),
                    raw.decode("utf-8", "replace").strip()[:160],
                )
            offset += len(raw) + 1


def check_item(repo: Repo, item: Item) -> dict[str, Any]:
    hits = []
    for rel, line, start, end, line_text in occurrences(repo, item.name):
        cls, why = classify(repo, item, rel, line, start, end)
        hits.append(
            {"file": rel, "line": line, "class": cls, "why": why, "text": line_text}
        )
    counts = {c: sum(1 for h in hits if h["class"] == c) for c in CLASSES}
    return {"key": item.key, "name": item.name, "counts": counts, "hits": hits}


def site_covered(
    repo: Repo, rel: str, line: int, name: str, callers: list[dict[str, Any]]
) -> bool:
    """A labelled call site (file, line) is inside a listed caller, by innermost owner.

    Every occurrence of ``name`` on the line must belong to a listed caller
    (two definitions can share a line); without one, the line's first token
    is used. Anything unparsable is not covered.
    """
    parsed = repo.tree(rel)
    if parsed is None:
        return False
    tree, src, grammar = parsed
    lines = src.split(b"\n")
    if not 1 <= line <= len(lines):
        return False
    offset = sum(len(raw) + 1 for raw in lines[: line - 1])
    raw = lines[line - 1]
    positions = [offset + m.start() for m in _word(name).finditer(raw)]
    if not positions:
        positions = [offset + len(raw) - len(raw.lstrip())]
    for pos in positions:
        node = tree.root_node.descendant_for_byte_range(pos, pos + max(1, len(name)))
        if node is None or _in_parse_error(node):
            return False
        if not listed(callers, rel, owner_at(node, family(grammar), line)):
            return False
    return True


def main() -> None:
    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    repo = Repo(Path(request["root"]))
    if request.get("mode") == "cover":
        out: list[Any] = [
            site_covered(repo, s["file"], s["line"], s["name"], s["callers"])
            for s in request["sites"]
        ]
    else:
        out = [check_item(repo, Item(**item)) for item in request["items"]]
    Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
