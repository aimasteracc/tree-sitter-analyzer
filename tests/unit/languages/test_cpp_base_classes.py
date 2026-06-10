"""Theme-C regression: C++ base classes (extends) capture.

2026-06-10 adversarial-review finding (PR #424 review, task 4):
``class D : public B`` reported superclass=None. Root cause:
``extract_base_classes`` searched the ``base_class_clause`` for
``base_specifier`` children, but tree-sitter-cpp 0.23 puts the
``access_specifier`` / ``type_identifier`` tokens DIRECTLY under the
clause — there is no ``base_specifier`` wrapper, so the loop matched
nothing for every C++ class.
"""

from __future__ import annotations

import tree_sitter
import tree_sitter_cpp

from tree_sitter_analyzer.languages.cpp_plugin import CppElementExtractor

CPP_SRC = """\
class Base {};
class Mixin {};

class D : public Base, private Mixin {
public:
    void run() {}
};

struct S : Base {};

template <typename T> class Box {};
class Wrap : public Box<int> {};

namespace NS { class NBase {}; }
class Q : public NS::NBase {};

class Plain {};
"""


def _classes():
    lang = tree_sitter.Language(tree_sitter_cpp.language())
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(CPP_SRC.encode())
    extractor = CppElementExtractor()
    return {c.name: c for c in extractor.extract_classes(tree, CPP_SRC)}


def test_single_public_base_captured() -> None:
    found = _classes()
    assert found["D"].superclass == "Base", f"got {found['D'].superclass!r}"


def test_multiple_bases_preserved() -> None:
    found = _classes()
    assert found["D"].interfaces == ["Mixin"], f"got {found['D'].interfaces!r}"


def test_struct_base_captured() -> None:
    found = _classes()
    assert found["S"].superclass == "Base", f"got {found['S'].superclass!r}"


def test_template_base_captured() -> None:
    found = _classes()
    assert found["Wrap"].superclass == "Box<int>", f"got {found['Wrap'].superclass!r}"


def test_qualified_base_captured() -> None:
    found = _classes()
    assert found["Q"].superclass == "NS::NBase", f"got {found['Q'].superclass!r}"


def test_no_base_stays_none() -> None:
    found = _classes()
    assert found["Plain"].superclass is None


def test_legacy_base_specifier_wrapper_still_handled() -> None:
    """Older tree-sitter-cpp grammars wrap each base in a base_specifier
    node — the compatibility branch must still collect names from it."""
    from unittest.mock import Mock

    from tree_sitter_analyzer.languages._cpp_variable_helpers import (
        extract_base_classes,
    )

    name = Mock()
    name.type = "type_identifier"
    spec = Mock()
    spec.type = "base_specifier"
    spec.children = [name]
    clause = Mock()
    clause.children = [spec]
    assert extract_base_classes(clause, lambda n: "Base") == ["Base"]
