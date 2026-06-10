"""Theme-C regression: Ruby and PHP inheritance capture.

2026-06-10 quality-audit finding, CLI-verified:
- Ruby: ``_find_ruby_superclass`` returned ``children[0]`` of the
  ``superclass`` node — which is the ``<`` OPERATOR TOKEN, not the name.
  ``class Dog < Animal`` reported ``superclass="<"`` (wrong data, worse
  than missing).
- PHP: ``extends`` / ``implements`` were never extracted — ``class Dog
  extends Animal implements Walkable`` reported superclass=None,
  interfaces=None.
"""

from __future__ import annotations

import tree_sitter
import tree_sitter_php
import tree_sitter_ruby

from tree_sitter_analyzer.languages.php_plugin import PHPElementExtractor
from tree_sitter_analyzer.languages.ruby_plugin import RubyElementExtractor

RUBY_SRC = """\
class Animal; end

module Walkable; end

class Dog < Animal
  include Walkable
  def bark; end
end

class Scoped < Base::Animal
end
"""

PHP_SRC = """\
<?php
interface Walkable {}
interface Runnable {}
class Animal {}
class Dog extends Animal implements Walkable, Runnable {
    public function bark() {}
}
"""


def _ruby_classes() -> dict[str, object]:
    lang = tree_sitter.Language(tree_sitter_ruby.language())
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(RUBY_SRC.encode())
    extractor = RubyElementExtractor()
    return {c.name: c for c in extractor.extract_classes(tree, RUBY_SRC)}


def _php_classes() -> dict[str, object]:
    lang = tree_sitter.Language(tree_sitter_php.language_php())
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(PHP_SRC.encode())
    extractor = PHPElementExtractor()
    return {c.name: c for c in extractor.extract_classes(tree, PHP_SRC)}


def test_ruby_superclass_is_name_not_operator() -> None:
    found = _ruby_classes()
    assert found["Dog"].superclass == "Animal", (
        f"got {found['Dog'].superclass!r} (the '<' operator bug)"
    )


def test_ruby_scoped_superclass() -> None:
    found = _ruby_classes()
    assert found["Scoped"].superclass == "Base::Animal", (
        f"got {found['Scoped'].superclass!r}"
    )


def test_ruby_no_superclass_stays_none() -> None:
    found = _ruby_classes()
    assert found["Animal"].superclass is None


def test_php_extends_captured() -> None:
    found = _php_classes()
    assert found["Dog"].superclass == "Animal", f"got {found['Dog'].superclass!r}"


def test_php_implements_captured() -> None:
    found = _php_classes()
    assert found["Dog"].interfaces == ["Walkable", "Runnable"], (
        f"got {found['Dog'].interfaces!r}"
    )


def test_php_no_inheritance_stays_empty() -> None:
    found = _php_classes()
    assert found["Animal"].superclass is None
    assert not found["Animal"].interfaces


def test_interfaces_survive_api_serialization() -> None:
    """Theme-C tail: plugins collected interfaces but element_to_dict dropped
    them (field missing from _OPTIONAL_ELEM_FIELDS) — agents never saw
    implements/mixins for ANY language."""
    from tree_sitter_analyzer._api_result_helpers import element_to_dict

    dog = _php_classes()["Dog"]
    as_dict = element_to_dict(dog)
    assert as_dict.get("superclass") == "Animal"
    assert as_dict.get("interfaces") == ["Walkable", "Runnable"]


def test_php_interface_multi_extends_all_parents_captured() -> None:
    """Review fix: ``interface I extends A, B`` must keep ALL parents —
    the first pass routed only base_classes[0] to superclass and silently
    dropped the rest (worse: it looked like single inheritance)."""
    lang = tree_sitter.Language(tree_sitter_php.language_php())
    parser = tree_sitter.Parser(lang)
    src = "<?php\ninterface I extends A, B, C {}\n"
    extractor = PHPElementExtractor()
    classes = {
        c.name: c for c in extractor.extract_classes(parser.parse(src.encode()), src)
    }
    iface = classes["I"]
    assert iface.superclass is None
    assert iface.interfaces == ["A", "B", "C"]
