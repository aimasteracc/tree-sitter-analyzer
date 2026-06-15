"""Tests for Go extraction bugs #749 and #750.

Bug #749 — Go interface method specifications should be marked is_abstract=True.
  Interface method specs (``method_elem`` children of ``interface_type``) have no
  body and no concrete implementation.  They are abstract signatures, so the
  ``is_abstract`` flag must be set to ``True`` to let consumers distinguish them
  from concrete method declarations.

Bug #750 — Go method with generic receiver ``*Stack[T]`` loses its receiver.
  A method defined as ``func (s *Stack[T]) Push(item T) { ... }`` has receiver
  name ``s`` and receiver type ``*Stack`` (the ``[T]`` type-parameter suffix must
  be stripped).  The previous regex ``r'\\(\\s*(\\w+)\\s+(\\*?\\w+)\\s*\\)'``
  failed to match the generic suffix, leaving ``receiver=None`` and
  ``receiver_type=None`` so the method was orphaned from its type.
"""

from __future__ import annotations

import pytest

pytest.importorskip("tree_sitter_go", reason="tree-sitter-go not installed")


def _parse_and_extract(src: str):
    """Run the Go extractor over ``src`` and return all functions."""
    import tree_sitter
    import tree_sitter_go

    from tree_sitter_analyzer.languages.go_plugin import GoElementExtractor

    lang = tree_sitter.Language(tree_sitter_go.language())
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(src.encode())
    extractor = GoElementExtractor()
    return extractor.extract_functions(tree, src)


# ---------------------------------------------------------------------------
# Bug #749 — interface method specs must be marked is_abstract=True
# ---------------------------------------------------------------------------


class TestInterfaceSpecIsAbstract:
    """Interface method signatures must carry is_abstract=True (#749)."""

    SRC = """\
package main

type Reader interface {
    Read(p []byte) (n int, err error)
    Close() error
}
"""

    def test_read_is_abstract(self) -> None:
        functions = _parse_and_extract(self.SRC)
        by_name = {f.name: f for f in functions}
        assert "Read" in by_name, f"Read not found in {[f.name for f in functions]}"
        assert by_name["Read"].is_abstract is True

    def test_close_is_abstract(self) -> None:
        functions = _parse_and_extract(self.SRC)
        by_name = {f.name: f for f in functions}
        assert "Close" in by_name, f"Close not found in {[f.name for f in functions]}"
        assert by_name["Close"].is_abstract is True

    def test_receiver_type_still_set(self) -> None:
        """The #588 fix (receiver_type = interface name) must be preserved."""
        functions = _parse_and_extract(self.SRC)
        by_name = {f.name: f for f in functions}
        assert by_name["Read"].receiver_type == "Reader"
        assert by_name["Close"].receiver_type == "Reader"

    def test_receiver_is_none(self) -> None:
        """Interface specs have no receiver variable."""
        functions = _parse_and_extract(self.SRC)
        by_name = {f.name: f for f in functions}
        assert by_name["Read"].receiver is None
        assert by_name["Close"].receiver is None

    def test_is_method_true(self) -> None:
        functions = _parse_and_extract(self.SRC)
        by_name = {f.name: f for f in functions}
        assert by_name["Read"].is_method is True
        assert by_name["Close"].is_method is True

    def test_concrete_method_not_abstract(self) -> None:
        """Concrete method on a struct must NOT have is_abstract=True."""
        src = """\
package main

type Counter struct{ n int }

func (c *Counter) Inc() { c.n++ }
"""
        functions = _parse_and_extract(src)
        by_name = {f.name: f for f in functions}
        assert "Inc" in by_name
        assert by_name["Inc"].is_abstract is False


class TestMultiMethodInterface:
    """Multiple interface specs all carry is_abstract=True."""

    SRC = """\
package main

type ReadWriter interface {
    Read(p []byte) (n int, err error)
    Write(p []byte) (n int, err error)
    Flush() error
}
"""

    def test_all_three_specs_are_abstract(self) -> None:
        functions = _parse_and_extract(self.SRC)
        abstract = [f for f in functions if f.is_abstract]
        assert len(abstract) == 3, (
            f"Expected exactly 3 abstract specs, got {[(f.name, f.is_abstract) for f in functions]}"
        )
        names = {f.name for f in abstract}
        assert names == {"Read", "Write", "Flush"}


# ---------------------------------------------------------------------------
# Bug #750 — generic receiver *Stack[T] must not lose receiver/receiver_type
# ---------------------------------------------------------------------------


class TestGenericReceiverExtraction:
    """Methods with generic receivers must have receiver and receiver_type (#750)."""

    SRC = """\
package main

type Stack[T any] struct {
    items []T
}

func (s *Stack[T]) Push(item T) {
    s.items = append(s.items, item)
}

func (s *Stack[T]) Pop() (T, bool) {
    if len(s.items) == 0 {
        var zero T
        return zero, false
    }
    item := s.items[len(s.items)-1]
    s.items = s.items[:len(s.items)-1]
    return item, true
}
"""

    def test_push_receiver_name(self) -> None:
        functions = _parse_and_extract(self.SRC)
        by_name = {f.name: f for f in functions}
        assert "Push" in by_name, f"Push not found in {[f.name for f in functions]}"
        assert by_name["Push"].receiver == "s", (
            f"Expected receiver='s', got {by_name['Push'].receiver!r}"
        )

    def test_push_receiver_type_strips_type_param(self) -> None:
        functions = _parse_and_extract(self.SRC)
        by_name = {f.name: f for f in functions}
        assert by_name["Push"].receiver_type == "*Stack", (
            f"Expected receiver_type='*Stack', got {by_name['Push'].receiver_type!r}"
        )

    def test_pop_receiver_name(self) -> None:
        functions = _parse_and_extract(self.SRC)
        by_name = {f.name: f for f in functions}
        assert "Pop" in by_name
        assert by_name["Pop"].receiver == "s"

    def test_pop_receiver_type_strips_type_param(self) -> None:
        functions = _parse_and_extract(self.SRC)
        by_name = {f.name: f for f in functions}
        assert by_name["Pop"].receiver_type == "*Stack"

    def test_is_method_true_for_generic_methods(self) -> None:
        functions = _parse_and_extract(self.SRC)
        by_name = {f.name: f for f in functions}
        assert by_name["Push"].is_method is True
        assert by_name["Pop"].is_method is True


class TestGenericReceiverValueType:
    """Value (non-pointer) generic receiver: ``(s Stack[T])``."""

    SRC = """\
package main

type Pair[A, B any] struct {
    first  A
    second B
}

func (p Pair[A, B]) First() interface{} {
    return p.first
}
"""

    def test_value_receiver_name(self) -> None:
        functions = _parse_and_extract(self.SRC)
        by_name = {f.name: f for f in functions}
        assert "First" in by_name
        assert by_name["First"].receiver == "p"

    def test_value_receiver_type_strips_type_params(self) -> None:
        functions = _parse_and_extract(self.SRC)
        by_name = {f.name: f for f in functions}
        # receiver_type should be "Pair" not "Pair[A, B]"
        assert by_name["First"].receiver_type == "Pair"


class TestNonGenericReceiverUnchanged:
    """Existing non-generic receivers must not be affected by the fix."""

    SRC = """\
package main

type Counter struct{ n int }

func (c *Counter) Inc() { c.n++ }
func (c Counter) Get() int { return c.n }
"""

    def test_pointer_receiver_unchanged(self) -> None:
        functions = _parse_and_extract(self.SRC)
        by_name = {f.name: f for f in functions}
        assert by_name["Inc"].receiver == "c"
        assert by_name["Inc"].receiver_type == "*Counter"

    def test_value_receiver_unchanged(self) -> None:
        functions = _parse_and_extract(self.SRC)
        by_name = {f.name: f for f in functions}
        assert by_name["Get"].receiver == "c"
        assert by_name["Get"].receiver_type == "Counter"


# ---------------------------------------------------------------------------
# Unit-level regex tests for extract_method_receiver
# ---------------------------------------------------------------------------


class TestExtractMethodReceiverRegex:
    """Unit tests for the extract_method_receiver helper (#750)."""

    def _extract(self, receiver_text: str):
        """Invoke extract_method_receiver with a fake node yielding receiver_text."""
        from unittest.mock import MagicMock

        from tree_sitter_analyzer.languages._go_common_helpers import (
            extract_method_receiver,
        )

        receiver_node = MagicMock()
        receiver_node.parent = None
        method_node = MagicMock()
        method_node.parent = None
        method_node.child_by_field_name.return_value = receiver_node

        return extract_method_receiver(method_node, lambda n: receiver_text)

    def test_pointer_generic_two_type_params(self) -> None:
        recv, rtype = self._extract("(p *Pair[A, B])")
        assert recv == "p"
        assert rtype == "*Pair"

    def test_pointer_generic_single_type_param(self) -> None:
        recv, rtype = self._extract("(s *Stack[T])")
        assert recv == "s"
        assert rtype == "*Stack"

    def test_value_generic(self) -> None:
        recv, rtype = self._extract("(p Pair[A, B])")
        assert recv == "p"
        assert rtype == "Pair"

    def test_non_generic_pointer_unchanged(self) -> None:
        recv, rtype = self._extract("(c *Counter)")
        assert recv == "c"
        assert rtype == "*Counter"

    def test_non_generic_value_unchanged(self) -> None:
        recv, rtype = self._extract("(c Counter)")
        assert recv == "c"
        assert rtype == "Counter"

    def test_no_receiver_returns_none(self) -> None:
        from unittest.mock import MagicMock

        from tree_sitter_analyzer.languages._go_common_helpers import (
            extract_method_receiver,
        )

        method_node = MagicMock()
        method_node.parent = None
        method_node.child_by_field_name.return_value = None

        recv, rtype = extract_method_receiver(method_node, lambda n: "")
        assert recv is None
        assert rtype is None
