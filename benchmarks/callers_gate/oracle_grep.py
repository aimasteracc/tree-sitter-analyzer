"""``git grep -w`` oracle for new TS/JS/Java ``complete`` answers.

Every occurrence of the target's bare name in a tracked text file is put in
exactly one class. Only ``residual`` needs a human; every other class is a
proof that the occurrence is not an unlisted caller:

``caller``          inside a listed caller's span (``line``..``end_line``)
``own_declaration`` the name token of the target's own declaration
``declaration``     the name token of another declaration (not a use)
``import_export``   an import / export specifier (a binding, not a call)
``comment``         inside a comment (tree-sitter)
``string``          inside a string literal whose text is not exactly the name
``non_code``        a docs/data file (``.md``, ``.json``, ...)
``other_symbol``    provably a different symbol: ``X.name`` / ``this.name``
                    inside or on a project class with no inheritance relation
                    to the target's class (whose whole ancestry resolves), or
                    a bare name bound by an import from an external module
``residual``        anything else, with the reason it could not be proven

Runs under the gate interpreter (needs ``tree_sitter`` and the grammars)::

    python -s -P oracle_grep.py <request.json> <response.json>
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
)
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
}
STRING_TYPES = {
    "string",
    "string_literal",
    "template_string",
    "text_block",
    "character_literal",
    "string_fragment",
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
CLASS_TYPES = {
    "class_declaration",
    "abstract_class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
    "class",
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
#: Supertype names that are never project code (their ancestry cannot reach a project class).
BUILTIN_SUPERTYPES = {
    "java": {
        "Object",
        "Exception",
        "RuntimeException",
        "Error",
        "Throwable",
        "Enum",
        "Record",
        "Comparable",
        "Iterable",
        "Serializable",
        "Cloneable",
        "AutoCloseable",
        "Closeable",
        "Runnable",
    },
    "ts": {
        "Error",
        "Object",
        "Array",
        "Map",
        "Set",
        "Promise",
        "EventTarget",
        "TypeError",
        "RangeError",
        "Function",
        "ReadableStream",
        "WritableStream",
        "TransformStream",
        "Response",
        "Request",
        "Headers",
    },
}
WORD = rb"[A-Za-z0-9_$]"


def _parser(grammar: str) -> Any:
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
    raise ValueError(grammar)


def _family(grammar: str) -> str:
    return "java" if grammar == "java" else "ts"


def _text(node: Any) -> str:
    return (
        node.text.decode("utf-8", "replace")
        if node is not None and node.text is not None
        else ""
    )


def _simple_type(text: str) -> str:
    text = re.sub(r"<.*", "", text.strip())
    return text.rsplit(".", 1)[-1].strip()


@dataclass
class ClassInfo:
    supers: set[str] = field(default_factory=set)


@dataclass
class Repo:
    root: Path
    parsers: dict[str, Any] = field(default_factory=dict)
    trees: dict[str, tuple[Any, bytes, str]] = field(default_factory=dict)
    _classes: dict[str, dict[str, ClassInfo]] = field(default_factory=dict)
    _packages: set[str] | None = None
    _js_names: set[str] | None = None

    def git(self, *args: str) -> str:
        proc = subprocess.run(
            ["git", "-C", str(self.root), *args], capture_output=True, check=False
        )
        if proc.returncode not in (0, 1):  # 1 = grep found nothing
            raise RuntimeError(
                f"git {args} failed: {proc.stderr.decode('utf-8', 'replace')}"
            )
        return proc.stdout.decode("utf-8", "replace")

    def tree(self, rel: str) -> tuple[Any, bytes, str] | None:
        if rel in self.trees:
            return self.trees[rel]
        grammar = next(
            (g for ext, g in GRAMMAR_BY_EXT.items() if rel.endswith(ext)), None
        )
        if grammar is None:
            return None
        if grammar not in self.parsers:
            self.parsers[grammar] = _parser(grammar)
        src = (self.root / rel).read_bytes()
        parsed = (self.parsers[grammar].parse(src), src, grammar)
        self.trees[rel] = parsed
        return parsed

    def files(self, family: str) -> list[str]:
        exts = (
            (".java",)
            if family == "java"
            else (".ts", ".tsx", ".mts", ".cts", ".js", ".mjs", ".cjs", ".jsx")
        )
        return [
            f
            for f in self.git("ls-files", "-z").split("\0")
            if f.endswith(exts) and not f.endswith(".d.ts.map")
        ]

    def declared_directly_in(self, item: Item, family: str, cls: str) -> bool:
        """Whether every declaration of the target in its file sits directly in class ``cls``.

        ``qual`` drops anonymous classes: a method of ``new Base() {...}`` inside
        ``Outer`` is reported as ``Outer.m`` although its dynamic class is a
        subclass of ``Base``. Such a target has no provable class, so no
        member / ``this`` use can be proven to miss it.
        """
        parsed = self.tree(item.file)
        if parsed is None:
            return False
        found = False
        for node in _walk(parsed[0].root_node):
            if node.type not in DECL_TYPES or node.type in CLASS_TYPES:
                continue
            name = node.child_by_field_name("name")
            if name is None or _text(name) != item.name:
                continue
            owner, _why = _enclosing_class(node, family)
            innermost = _innermost_named_class(node)
            if innermost != cls:
                continue
            if owner != cls:
                return False  # declared under cls, but inside an anonymous scope
            found = True
        return found

    def classes(self, family: str) -> dict[str, ClassInfo]:
        """Simple class name -> union of declared supertype names (over every same-named class)."""
        if family in self._classes:
            return self._classes[family]
        table: dict[str, ClassInfo] = {}
        for rel in self.files(family):
            parsed = self.tree(rel)
            if parsed is None:
                continue
            for node in _walk(parsed[0].root_node):
                if node.type in CLASS_TYPES:
                    name = node.child_by_field_name("name")
                    if name is not None:
                        table.setdefault(_text(name), ClassInfo()).supers.update(
                            _supertypes(node)
                        )
        self._classes[family] = table
        return table

    def java_packages(self) -> set[str]:
        if self._packages is None:
            out = self.git(
                "grep", "-h", "-E", r"^\s*package\s+[A-Za-z0-9_.]+\s*;", "--", "*.java"
            )
            self._packages = {
                m.group(1) for m in re.finditer(r"package\s+([A-Za-z0-9_.]+)", out)
            }
        return self._packages

    def js_package_names(self) -> set[str]:
        if self._js_names is None:
            names = set()
            for rel in self.git(
                "ls-files", "-z", "--", "*package.json", "*jsr.json", "*deno.json"
            ).split("\0"):
                if not rel:
                    continue
                try:
                    data = json.loads((self.root / rel).read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if isinstance(data, dict) and isinstance(data.get("name"), str):
                    names.add(data["name"])
            self._js_names = names
        return self._js_names


def _walk(node: Any) -> Iterator[Any]:
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(current.children)


def _supertypes(node: Any) -> set[str]:
    out: set[str] = set()
    for child in node.children:
        if child.type in (
            "superclass",
            "super_interfaces",
            "extends_interfaces",
            "class_heritage",
            "extends_clause",
            "implements_clause",
            "extends_type_clause",
        ):
            for sub in _walk(child):
                if sub.type in (
                    "type_identifier",
                    "identifier",
                    "scoped_type_identifier",
                    "generic_type",
                    "member_expression",
                    "call_expression",
                    "nested_type_identifier",
                ):
                    if sub.type == "call_expression":
                        out.add("<mixin>")  # e.g. extends Mixin(Base): unresolvable
                        break
                    if (
                        sub.parent is not None
                        and sub.parent.type
                        in (
                            "generic_type",
                            "type_arguments",
                            "scoped_type_identifier",
                            "member_expression",
                            "nested_type_identifier",
                        )
                        and sub.parent is not child
                    ):
                        continue
                    out.add(_simple_type(_text(sub)))
    return {s for s in out if s}


def _ancestors(
    name: str, table: dict[str, ClassInfo], builtins: set[str]
) -> tuple[set[str], bool]:
    """(transitive supertypes, whether every one of them resolved to a project or builtin type)."""
    seen: set[str] = set()
    closed = True
    stack = [name]
    while stack:
        current = stack.pop()
        info = table.get(current)
        if info is None:
            if current not in builtins:
                closed = False  # an unknown name may be an alias of a project class
            continue
        for sup in info.supers:
            if sup not in seen:
                seen.add(sup)
                stack.append(sup)
    return seen, closed


def related(a: str, b: str, table: dict[str, ClassInfo], builtins: set[str]) -> bool:
    """True unless ``a`` and ``b`` are *provably* unrelated by inheritance.

    Provably unrelated: different names, both project classes, both ancestries
    fully resolve, and neither is an ancestor of the other.
    """
    if a == b:
        return True
    anc_a, closed_a = _ancestors(a, table, builtins)
    anc_b, closed_b = _ancestors(b, table, builtins)
    if a not in table or b not in table or not (closed_a and closed_b):
        return True
    return b in anc_a or a in anc_b


def _enclosing_class(node: Any, family: str) -> tuple[str | None, str]:
    """Name of the class whose ``this`` the node sees, or (None, why)."""
    current = node.parent
    while current is not None:
        if (
            family == "java"
            and current.type == "class_body"
            and current.parent is not None
            and current.parent.type in ("object_creation_expression", "enum_constant")
        ):
            return None, "inside an anonymous class body"
        if family == "ts" and current.type in (
            "function_expression",
            "function_declaration",
            "generator_function",
            "generator_function_declaration",
            "function",
        ):
            return None, "inside a non-arrow function (its own `this`)"
        if family == "ts" and current.type == "object":
            return None, "inside an object literal"
        if current.type in CLASS_TYPES:
            name = current.child_by_field_name("name")
            return (_text(name) or None), ("anonymous class" if name is None else "")
        current = current.parent
    return None, "not inside a class"


def _all_enclosing_classes(node: Any) -> list[str] | None:
    """Every named Java class around ``node`` (innermost first); None inside an anonymous class."""
    out = []
    current = node.parent
    while current is not None:
        if (
            current.type == "class_body"
            and current.parent is not None
            and current.parent.type in ("object_creation_expression", "enum_constant")
        ):
            return None
        if current.type in CLASS_TYPES:
            name = current.child_by_field_name("name")
            if name is None:
                return None
            out.append(_text(name))
        current = current.parent
    return out


def _innermost_named_class(node: Any) -> str | None:
    current = node.parent
    while current is not None:
        if current.type in CLASS_TYPES:
            name = current.child_by_field_name("name")
            if name is not None:
                return _text(name)
        current = current.parent
    return None


def _class_of_target(qual: str) -> str | None:
    parts = qual.strip('"').split(".")
    return parts[-2] if len(parts) >= 2 else None


@dataclass
class Item:
    key: list[str]
    name: str
    file: str
    qual: str
    callers: list[dict[str, Any]]


def _in_caller(item: Item, rel: str, line: int) -> bool:
    for c in item.callers:
        if c.get("file") == rel and (c.get("line") or 0) <= line <= (
            c.get("end_line") or c.get("line") or 0
        ):
            return True
    return False


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


def _external_binding(repo: Repo, family: str, root: Any, name: str) -> bool:
    """Whether the file binds bare ``name`` only via an import from an external module."""
    found_external = False
    for node in _walk(root):
        if family == "ts" and node.type == "import_statement":
            source = node.child_by_field_name("source")
            spec = _text(source).strip("'\"`")
            binds = any(
                n.type in ("identifier",) and _text(n) == name and _bound_by_import(n)
                for n in _walk(node)
            )
            if not binds:
                continue
            if _is_external_js(spec, repo):
                found_external = True
            else:
                return False
        elif family == "java" and node.type == "import_declaration":
            text = _text(node)
            if "static" not in text.split():
                continue
            m = re.search(r"import\s+static\s+([A-Za-z0-9_.]+)\s*;", text)
            if not m or not m.group(1).endswith("." + name):
                continue
            pkg = m.group(1).rsplit(".", 2)[0]
            if any(pkg == p or pkg.startswith(p + ".") for p in repo.java_packages()):
                return False
            found_external = True
    return found_external


def _bound_by_import(node: Any) -> bool:
    """The identifier is the *local* binding of an import specifier / clause."""
    parent = node.parent
    if parent is None:
        return False
    if parent.type == "import_specifier":
        alias = parent.child_by_field_name("alias")
        return alias is None or alias.id == node.id
    return parent.type in ("import_clause", "namespace_import")


def _is_external_js(spec: str, repo: Repo) -> bool:
    if not spec or spec.startswith((".", "/", "@/", "~", "#")):
        return False
    spec = re.sub(r"^(npm|jsr|node):", "", spec)
    parts = spec.split("/")
    package = "/".join(parts[:2]) if spec.startswith("@") else parts[0]
    return package not in repo.js_package_names()


def classify(
    repo: Repo, item: Item, rel: str, line: int, start: int, end: int
) -> tuple[str, str]:
    if _in_caller(item, rel, line):
        return "caller", ""
    if rel.lower().endswith(NON_CODE_EXTS):
        return "non_code", ""
    parsed = repo.tree(rel)
    if parsed is None:
        return "residual", "file type the oracle cannot parse"
    tree, src, grammar = parsed
    family = _family(grammar)
    node = tree.root_node.descendant_for_byte_range(start, end)
    if node is None:
        return "residual", "no syntax node at the occurrence"
    for anc in _chain(node):
        if "comment" in anc.type:
            return "comment", ""
    string = _string_ancestor(node)
    if string is not None:
        literal = _text(string).strip().strip("'\"`")
        if literal == item.name:
            return (
                "residual",
                "string literal equal to the name (possible dynamic dispatch)",
            )
        return "string", ""
    if node.type == "ERROR" or any(a.type == "ERROR" for a in _chain(node)):
        return "residual", "parse error around the occurrence"
    parent = node.parent
    if (
        parent is not None
        and parent.type in DECL_TYPES
        and parent.child_by_field_name("name") is not None
        and parent.child_by_field_name("name").id == node.id
    ):
        if rel == item.file:
            owner = (
                _enclosing_class(parent, family)[0]
                if parent.type not in CLASS_TYPES
                else None
            )
            target_cls = _class_of_target(item.qual)
            if target_cls is None or owner == target_cls or parent.type in CLASS_TYPES:
                return "own_declaration", ""
        return "declaration", ""
    if any(a.type in IMPORT_TYPES for a in _chain(node)):
        return "import_export", ""
    return _member_or_binding(repo, item, family, node, tree.root_node)


def _chain(node: Any) -> Iterator[Any]:
    current = node
    while current is not None:
        yield current
        current = current.parent


def _member_or_binding(
    repo: Repo, item: Item, family: str, node: Any, root: Any
) -> tuple[str, str]:
    parent = node.parent
    target_cls = _class_of_target(item.qual)
    table = repo.classes(family) if target_cls is not None else {}
    builtins = BUILTIN_SUPERTYPES[family]
    receiver = None
    if parent is not None and parent.type in (
        "member_expression",
        "field_access",
        "method_invocation",
    ):
        prop = (
            parent.child_by_field_name("property")
            or parent.child_by_field_name("field")
            or parent.child_by_field_name("name")
        )
        if prop is not None and prop.id == node.id:
            receiver = parent.child_by_field_name("object")
            if receiver is None and parent.type == "method_invocation":
                receiver = "<implicit>"
    if receiver is None:
        if parent is not None and parent.type in ("member_expression", "field_access"):
            return "residual", "the name is the receiver, not the member"
        if _external_binding(repo, family, root, item.name):
            return "other_symbol", "bound by an import from an external module"
        return "residual", "bare name use"
    if target_cls is None:
        return "residual", "member use of a non-method target"
    _anc, closed = _ancestors(target_cls, table, builtins)
    if target_cls not in table or not closed:
        return "residual", f"the ancestry of {target_cls} does not fully resolve"
    if not repo.declared_directly_in(item, family, target_cls):
        return (
            "residual",
            f"the target is not declared directly in class {target_cls} "
            "(anonymous class, object literal, or not found)",
        )
    if receiver == "<implicit>":
        # Java: an unqualified call resolves in the innermost class, then each
        # enclosing class (and their supertypes), or through a static import.
        if _static_import_of(root, item.name):
            return "residual", "a static import may bind the name"
        owners = _all_enclosing_classes(node)
        if owners is None:
            return "residual", "unqualified call inside an anonymous class"
        if not owners:
            return "residual", "unqualified call outside any class"
        if any(related(o, target_cls, table, builtins) for o in owners):
            return (
                "residual",
                f"unqualified call inside {owners}, related to {target_cls}",
            )
        return (
            "other_symbol",
            f"unqualified call inside {owners}, unrelated to {target_cls}",
        )
    if not isinstance(receiver, str) and receiver.type == "this":
        owner, why = _enclosing_class(node, family)
        if owner is None:
            return "residual", f"`this` not provable ({why})"
        if related(owner, target_cls, table, builtins):
            return "residual", f"`this` of {owner}, related to {target_cls}"
        return "other_symbol", f"`this` of {owner}, unrelated to {target_cls}"
    if not isinstance(receiver, str) and receiver.type in (
        "identifier",
        "type_identifier",
    ):
        rname = _text(receiver)
        if rname in table and rname[:1].isupper():
            if related(rname, target_cls, table, builtins):
                return "residual", f"receiver class {rname} is related to {target_cls}"
            return "other_symbol", f"static receiver {rname}, unrelated to {target_cls}"
    return "residual", "member access on a receiver of unknown type"


def _static_import_of(root: Any, name: str) -> bool:
    for node in _walk(root):
        if (
            node.type == "import_declaration"
            and "static" in _text(node).split()
            and re.search(r"\." + re.escape(name) + r"\s*;", _text(node))
        ):
            return True
    return False


def occurrences(repo: Repo, name: str) -> Iterator[tuple[str, int, int, int, str]]:
    """(file, 1-based line, byte start, byte end, line text) of every word occurrence."""
    listed = repo.git("grep", "-l", "-z", "-I", "-w", "-F", "-e", name)
    pattern = re.compile(
        rb"(?<!" + WORD + rb")" + re.escape(name.encode()) + rb"(?!" + WORD + rb")"
    )
    for rel in sorted(f for f in listed.split("\0") if f):
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
    for rel, line, start, end, text in occurrences(repo, item.name):
        cls, why = classify(repo, item, rel, line, start, end)
        hits.append({"file": rel, "line": line, "class": cls, "why": why, "text": text})
    counts = {c: sum(1 for h in hits if h["class"] == c) for c in CLASSES}
    return {"key": item.key, "name": item.name, "counts": counts, "hits": hits}


SPAN_TYPES = DECL_TYPES - CLASS_TYPES - {"enum_constant", "type_alias_declaration"}


def caller_end_line(repo: Repo, file: str, line: int, name: str) -> int | None:
    """Last line of the declaration named ``name`` that starts on ``line`` (or None).

    TS/JS caller entries carry no ``end_line``; without the span a call inside
    the caller would look uncovered. Only an exact (name, start line) match
    counts, so an unresolvable caller keeps its single line (conservative).
    """
    if not name or name.startswith("<"):
        return None
    parsed = repo.tree(file)
    if parsed is None:
        return None
    best: int | None = None
    for node in _walk(parsed[0].root_node):
        if node.type not in SPAN_TYPES:
            continue
        ident = node.child_by_field_name("name")
        if ident is None or _text(ident) != name:
            continue
        starts = {node.start_point[0] + 1, ident.start_point[0] + 1}
        outer = node.parent
        if outer is not None and outer.type in (
            "lexical_declaration",
            "variable_declaration",
            "export_statement",
        ):
            starts.add(outer.start_point[0] + 1)
        if line in starts:
            end = node.end_point[0] + 1
            best = end if best is None else max(best, end)
    return best


def main() -> None:
    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    repo = Repo(Path(request["root"]))
    if request.get("mode") == "spans":
        spans = [
            caller_end_line(repo, c["file"], c["line"], c["name"])
            for c in request["callers"]
        ]
        Path(sys.argv[2]).write_text(json.dumps(spans), encoding="utf-8")
        return
    out = [check_item(repo, Item(**item)) for item in request["items"]]
    Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
