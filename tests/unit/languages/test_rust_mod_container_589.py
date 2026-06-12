"""Issue #589 — Rust ``mod`` blocks captured as container elements (RED→GREEN).

``mod sample_module { ... }`` previously produced no container element: items
inside were extracted but the module itself was invisible. The fix mirrors the
C++ namespace → Package convention (`extract_cpp_namespaces` →
``extract_packages`` on the extractor, wired into ``analyze_file`` /
``extract_elements``).

Decision (documented): declaration-only ``mod tests;`` (no body) IS emitted,
with its span being the declaration line itself. Rationale: it is the only
trace of the file-module mapping in lib.rs/mod.rs — skipping it reproduces the
exact invisibility this issue fixes; and a one-line span cannot mis-claim
nested items under the innermost-span ownership rule.
"""

from __future__ import annotations

import asyncio

import pytest


def _rust_lang():
    try:
        import tree_sitter
        import tree_sitter_rust

        return tree_sitter.Language(tree_sitter_rust.language())
    except Exception:
        return None


pytestmark = pytest.mark.skipif(
    _rust_lang() is None,
    reason="tree-sitter-rust not available; tracked: optional local grammar dependency",
)


def _parse(src: str):
    import tree_sitter

    return tree_sitter.Parser(_rust_lang()).parse(src.encode())


NAMED_MOD_SRC = (
    "pub mod sample_module {\n"
    "    pub struct User {\n"
    "        pub id: u64,\n"
    "    }\n"
    "\n"
    "    pub fn helper() -> u64 {\n"
    "        42\n"
    "    }\n"
    "}\n"
)


def test_named_mod_extracted_as_package() -> None:
    """A named mod block must yield exactly one Package-like container."""
    from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

    packages = RustElementExtractor().extract_packages(
        _parse(NAMED_MOD_SRC), NAMED_MOD_SRC
    )

    assert len(packages) == 1
    pkg = packages[0]
    assert pkg.name == "sample_module"
    assert pkg.element_type == "package"
    assert pkg.language == "rust"
    assert pkg.start_line == 1
    assert pkg.end_line == 9


def test_nested_items_still_extracted() -> None:
    """Items inside the mod stay owned/extracted exactly as before."""
    from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

    extractor = RustElementExtractor()
    tree = _parse(NAMED_MOD_SRC)

    functions = extractor.extract_functions(tree, NAMED_MOD_SRC)
    assert len(functions) == 1
    assert functions[0].name == "helper"

    classes = extractor.extract_classes(tree, NAMED_MOD_SRC)
    assert len(classes) == 1
    assert classes[0].name == "User"


def test_empty_mod_extracted() -> None:
    """``mod empty {}`` still emits its container."""
    from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

    src = "mod empty {}\n"
    packages = RustElementExtractor().extract_packages(_parse(src), src)

    assert len(packages) == 1
    assert packages[0].name == "empty"
    assert packages[0].start_line == 1
    assert packages[0].end_line == 1


def test_declaration_only_mod_emitted_with_declaration_span() -> None:
    """``mod tests;`` (body=None) is emitted; span == the declaration line."""
    from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

    src = "mod tests;\n"
    packages = RustElementExtractor().extract_packages(_parse(src), src)

    assert len(packages) == 1
    assert packages[0].name == "tests"
    assert packages[0].start_line == 1
    assert packages[0].end_line == 1


def test_nested_mods_both_extracted() -> None:
    """Nested mod blocks each emit a container."""
    from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

    src = "mod outer {\n    mod inner {}\n}\n"
    packages = RustElementExtractor().extract_packages(_parse(src), src)

    assert len(packages) == 2
    assert [p.name for p in packages] == ["outer", "inner"]
    assert (packages[0].start_line, packages[0].end_line) == (1, 3)
    assert (packages[1].start_line, packages[1].end_line) == (2, 2)


class _NamelessModNode:
    """Stub mod_item with no name field (grammar ERROR recovery shape)."""

    type = "mod_item"
    parent = None  # explicit: never let a mock auto-generate a parent chain
    children: list = []

    def child_by_field_name(self, _field: str):
        return None


class _ExplodingModNode:
    """Stub mod_item whose name lookup raises (defensive except branch)."""

    type = "mod_item"
    parent = None
    children: list = []

    def child_by_field_name(self, _field: str):
        raise RuntimeError("boom")


def test_nameless_mod_node_yields_none() -> None:
    from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

    assert RustElementExtractor()._extract_mod_package(_NamelessModNode()) is None


def test_exploding_mod_node_yields_none() -> None:
    from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

    assert RustElementExtractor()._extract_mod_package(_ExplodingModNode()) is None


def test_plugin_extract_elements_carries_packages_key() -> None:
    """RustPlugin.extract_elements exposes the 'packages' group (go/kotlin parity)."""
    from tree_sitter_analyzer.languages.rust_plugin import RustPlugin

    result = RustPlugin().extract_elements(_parse(NAMED_MOD_SRC), NAMED_MOD_SRC)

    assert "packages" in result
    assert len(result["packages"]) == 1
    assert result["packages"][0].name == "sample_module"


def test_analyze_file_includes_package_element(tmp_path) -> None:
    """analyze_file surfaces the mod container in the flat element list."""
    from tree_sitter_analyzer.core.request import AnalysisRequest
    from tree_sitter_analyzer.languages.rust_plugin import RustPlugin
    from tree_sitter_analyzer.models import Package

    rs_file = tmp_path / "lib.rs"
    rs_file.write_text(NAMED_MOD_SRC, encoding="utf-8", newline="\n")

    result = asyncio.run(
        RustPlugin().analyze_file(str(rs_file), AnalysisRequest(file_path=str(rs_file)))
    )

    packages = [e for e in result.elements if isinstance(e, Package)]
    assert len(packages) == 1
    assert packages[0].name == "sample_module"
    # functions(1) + classes(1) + variables(1: id field) + imports(0) + packages(1)
    assert len(result.elements) == 4
