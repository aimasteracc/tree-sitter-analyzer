"""Issue #459 regression: TypeScript abstract class members extracted.

Theme I — container missing members.  An ``abstract class`` parses as
``abstract_class_declaration`` (not ``class_declaration``), and its abstract
methods parse as ``abstract_method_signature`` (not ``method_signature``).
Neither node type was handled, so abstract classes appeared as containers
with empty ``methods:[]`` in structure outlines.
"""

from __future__ import annotations

import tree_sitter
from tree_sitter_typescript import language_typescript

from tree_sitter_analyzer.languages.typescript_plugin.extractor import (
    TypeScriptElementExtractor,
)

# ─── Source fixture ──────────────────────────────────────────────────────────

ABSTRACT_CLASS_SRC = """\
abstract class BaseEntity {
    constructor(private id: string) {}
    abstract validate(): boolean;
    protected updateTimestamp(): void {}
    public getId(): string { return this.id; }
}

class Concrete extends BaseEntity {
    validate(): boolean { return true; }
}

interface IFoo {
    bar(): void;
}
"""


def _parse(src: str = ABSTRACT_CLASS_SRC) -> tree_sitter.Tree:
    lang = tree_sitter.Language(language_typescript())
    parser = tree_sitter.Parser(lang)
    return parser.parse(src.encode())


def _extract_classes(src: str = ABSTRACT_CLASS_SRC) -> dict[str, str]:
    extractor = TypeScriptElementExtractor()
    return {c.name: c.class_type for c in extractor.extract_classes(_parse(src), src)}


def _extract_function_names(src: str = ABSTRACT_CLASS_SRC) -> list[str]:
    extractor = TypeScriptElementExtractor()
    return [f.name for f in extractor.extract_functions(_parse(src), src)]


# ─── Class-level tests ───────────────────────────────────────────────────────


def test_abstract_class_extracted_with_correct_type() -> None:
    """Abstract class itself must be extracted as class_type='abstract_class'."""
    found = _extract_classes()
    assert found.get("BaseEntity") == "abstract_class", f"got {sorted(found)}"


def test_concrete_class_still_extracted() -> None:
    """Regular class inside same file must not be affected."""
    found = _extract_classes()
    assert found.get("Concrete") == "class", f"got {sorted(found)}"


def test_interface_still_extracted() -> None:
    """Interface inside same file must not be affected."""
    found = _extract_classes()
    assert found.get("IFoo") == "interface", f"got {sorted(found)}"


# ─── Method-level tests ──────────────────────────────────────────────────────


def test_abstract_class_yields_four_methods() -> None:
    """BaseEntity has exactly 4 members: constructor, validate, updateTimestamp, getId.

    NOTE: The fixture also has a Concrete subclass with its own ``validate``
    method, so ``validate`` appears twice in the full file extraction.  We
    assert all four names are present (set coverage) plus that the unambiguous
    names (constructor, updateTimestamp, getId) appear exactly once.
    """
    names = _extract_function_names()
    abstract_methods = {"constructor", "validate", "updateTimestamp", "getId"}
    found = set(names) & abstract_methods
    assert found == abstract_methods, f"missing {abstract_methods - found}; got {names}"
    assert names.count("constructor") == 1
    # validate appears in both BaseEntity (abstract) and Concrete (concrete)
    assert names.count("validate") == 2
    assert names.count("updateTimestamp") == 1
    assert names.count("getId") == 1


def test_abstract_method_signature_extracted() -> None:
    """``abstract validate()`` (abstract_method_signature node) must appear in functions."""
    names = _extract_function_names()
    assert "validate" in names, f"abstract method missing; got {names}"


def test_constructor_in_abstract_class_extracted() -> None:
    """``constructor`` (method_definition inside abstract class) must be extracted."""
    names = _extract_function_names()
    assert "constructor" in names, f"constructor missing; got {names}"


def test_protected_method_in_abstract_class_extracted() -> None:
    """``protected updateTimestamp()`` (method_definition) must be extracted."""
    names = _extract_function_names()
    assert "updateTimestamp" in names, f"protected method missing; got {names}"


def test_public_method_in_abstract_class_extracted() -> None:
    """``public getId()`` (method_definition) must be extracted."""
    names = _extract_function_names()
    assert "getId" in names, f"public method missing; got {names}"


def test_concrete_class_methods_still_extracted() -> None:
    """Concrete subclass method must still be extracted."""
    names = _extract_function_names()
    assert "validate" in names  # from Concrete too (deduplication not expected here)


def test_interface_method_still_extracted() -> None:
    """Interface method (method_signature) must still be extracted."""
    names = _extract_function_names()
    assert "bar" in names, f"interface method missing; got {names}"


# ─── Exact-count assertions (Theme A — no approximate bounds) ────────────────


def test_exact_method_count_for_base_entity_abstract_methods_only() -> None:
    """Isolated snippet with only the two abstract members — exact count == 2."""
    src = """\
abstract class Minimal {
    abstract alpha(): void;
    abstract beta(): string;
}
"""
    names = _extract_function_names(src)
    assert names.count("alpha") == 1
    assert names.count("beta") == 1
    assert len(names) == 2


def test_visibility_on_abstract_method_signature() -> None:
    """abstract_method_signature carries visibility from the node text."""
    extractor = TypeScriptElementExtractor()
    src = """\
abstract class V {
    public abstract pub(): void;
    protected abstract prot(): void;
    private abstract priv(): void;
    abstract implicit(): void;
}
"""
    tree = _parse(src)
    funcs = extractor.extract_functions(tree, src)
    by_name = {f.name: f for f in funcs}
    assert by_name["pub"].visibility == "public"
    assert by_name["prot"].visibility == "protected"
    assert by_name["priv"].visibility == "private"
    assert by_name["implicit"].visibility == "public"


# ─── extract_abstract_method_signature defensive branches ────────────────────


def _abstract_sig_node() -> tree_sitter.Node:
    """Return the abstract_method_signature node from the fixture parse."""
    tree = _parse()

    def find(node: tree_sitter.Node) -> tree_sitter.Node | None:
        if node.type == "abstract_method_signature":
            return node
        for child in node.children:
            hit = find(child)
            if hit is not None:
                return hit
        return None

    node = find(tree.root_node)
    assert node is not None
    return node


def test_abstract_signature_parse_returning_none_yields_none() -> None:
    from tree_sitter_analyzer.languages.typescript_plugin._function_helpers import (
        extract_abstract_method_signature,
    )

    result = extract_abstract_method_signature(
        _abstract_sig_node(),
        parse_signature=lambda node: None,
        extract_tsdoc=lambda line: "",
        get_node_text=lambda node: "",
        framework_type="",
    )
    assert result is None


def test_abstract_signature_nameless_parse_yields_none() -> None:
    from tree_sitter_analyzer.languages.typescript_plugin._function_helpers import (
        extract_abstract_method_signature,
    )

    nameless = (None, [], False, False, False, False, False, "void", "public", None)
    result = extract_abstract_method_signature(
        _abstract_sig_node(),
        parse_signature=lambda node: nameless,
        extract_tsdoc=lambda line: "",
        get_node_text=lambda node: "",
        framework_type="",
    )
    assert result is None


def test_abstract_signature_parse_raising_yields_none() -> None:
    from tree_sitter_analyzer.languages.typescript_plugin._function_helpers import (
        extract_abstract_method_signature,
    )

    def boom(node: tree_sitter.Node) -> None:
        raise RuntimeError("synthetic parse failure")

    result = extract_abstract_method_signature(
        _abstract_sig_node(),
        parse_signature=boom,
        extract_tsdoc=lambda line: "",
        get_node_text=lambda node: "",
        framework_type="",
    )
    assert result is None
