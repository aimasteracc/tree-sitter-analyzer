"""Theme-A regression: Rust impl-block method ownership.

2026-06-10 quality-audit finding: functions inside ``impl Counter { ... }``
were extracted with no ``receiver_type``, no ``receiver``, and
``is_method=False`` — flattened to top-level, indistinguishable from free
functions. An agent could not tell ``inc`` belongs to ``Counter``.

Semantics pinned here:
- any fn inside an impl block gets ``receiver_type`` = the impl target
  (associated functions belong to the type too);
- ``is_method`` / ``receiver`` only when a ``self_parameter`` exists
  (Rust calls self-less impl fns "associated functions", not methods).
"""

from __future__ import annotations

import tree_sitter
import tree_sitter_rust

from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

RUST_SRC = """\
struct Counter { n: i32 }

impl Counter {
    fn inc(&mut self) { self.n += 1; }
    fn get(&self) -> i32 { self.n }
    fn new() -> Counter { Counter { n: 0 } }
}

trait Greet { fn hi(&self); }

impl Greet for Counter {
    fn hi(&self) {}
}

impl Counter {
    fn into_box(self: Box<Self>) {}
    fn poll(self: Pin<&mut Self>) {}
}

fn standalone() {}
"""


def _functions():
    lang = tree_sitter.Language(tree_sitter_rust.language())
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(RUST_SRC.encode())
    extractor = RustElementExtractor()
    return {f.name: f for f in extractor.extract_functions(tree, RUST_SRC)}


def test_impl_method_gets_receiver_type() -> None:
    funcs = _functions()
    assert funcs["inc"].receiver_type == "Counter", (
        f"got {funcs['inc'].receiver_type!r}"
    )
    assert funcs["inc"].is_method is True
    assert funcs["inc"].receiver == "&mut self"


def test_impl_method_shared_ref() -> None:
    funcs = _functions()
    assert funcs["get"].receiver == "&self"
    assert funcs["get"].is_method is True


def test_associated_function_owned_but_not_method() -> None:
    """fn new() has no self — owned by Counter but not a method."""
    funcs = _functions()
    assert funcs["new"].receiver_type == "Counter"
    assert funcs["new"].is_method is False
    assert funcs["new"].receiver is None


def test_trait_impl_method_receiver_type() -> None:
    funcs = _functions()
    assert funcs["hi"].receiver_type == "Counter", f"got {funcs['hi'].receiver_type!r}"
    assert funcs["hi"].is_method is True


def test_verbose_self_receiver_is_method() -> None:
    """``self: Box<Self>`` / ``self: Pin<&mut Self>`` parse as plain
    ``parameter`` nodes (not ``self_parameter``) — adversarial-review P2:
    they are still receivers and must be classified as methods."""
    funcs = _functions()
    assert funcs["into_box"].is_method is True
    assert funcs["into_box"].receiver == "self: Box<Self>"
    assert funcs["into_box"].receiver_type == "Counter"
    assert funcs["poll"].is_method is True
    assert funcs["poll"].receiver == "self: Pin<&mut Self>"


def test_free_function_unowned() -> None:
    funcs = _functions()
    assert funcs["standalone"].receiver_type is None
    assert funcs["standalone"].is_method is False


def test_receiver_survives_api_serialization() -> None:
    """End-to-end Theme-A: the serializer allowlist (landed with the Go
    companion fix) must carry the Rust receiver binding to API consumers."""
    from tree_sitter_analyzer.internal_api.result_helpers import element_to_dict

    funcs = _functions()
    inc = element_to_dict(funcs["inc"])
    assert inc["receiver"] == "&mut self"
    assert inc["receiver_type"] == "Counter"
    assert inc["is_method"] is True
