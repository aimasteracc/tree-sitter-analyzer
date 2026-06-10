"""Theme-A regression: Go method receiver reaches the API consumer.

2026-06-10 quality-audit finding: GoElementExtractor fills
``receiver``/``receiver_type`` correctly (verified: receiver='c',
receiver_type='*Counter'), but ``element_to_dict``'s
``_OPTIONAL_ELEM_FIELDS`` allowlist dropped both — an agent saw
``is_method: True`` but could never tell WHICH type the method belongs
to. Same serializer-allowlist bug class as the ``interfaces`` drop
(#424).
"""

from __future__ import annotations

import tree_sitter
import tree_sitter_go

from tree_sitter_analyzer._api_result_helpers import element_to_dict
from tree_sitter_analyzer.languages.go_plugin import GoElementExtractor

GO_SRC = """\
package main

type Counter struct{ n int }

func (c *Counter) Inc() { c.n++ }
func (c Counter) Get() int { return c.n }
func Standalone() {}
"""


def _functions():
    lang = tree_sitter.Language(tree_sitter_go.language())
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(GO_SRC.encode())
    extractor = GoElementExtractor()
    return {f.name: f for f in extractor.extract_functions(tree, GO_SRC)}


def test_extractor_fills_receiver() -> None:
    """The extractor layer was always correct — pin it."""
    funcs = _functions()
    assert funcs["Inc"].receiver == "c"
    assert funcs["Inc"].receiver_type == "*Counter"
    assert funcs["Get"].receiver_type == "Counter"
    assert funcs["Standalone"].receiver is None


def test_receiver_survives_api_serialization() -> None:
    """The serializer allowlist must pass receiver/receiver_type through."""
    funcs = _functions()
    inc = element_to_dict(funcs["Inc"])
    assert inc.get("receiver") == "c"
    assert inc.get("receiver_type") == "*Counter"
    standalone = element_to_dict(funcs["Standalone"])
    assert "receiver" not in standalone or standalone.get("receiver") is None
