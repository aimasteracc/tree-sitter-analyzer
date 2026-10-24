"""Unified, evidence-carrying query language for tree-sitter-analyzer (RFC-0041).

One grammar (TQL selectors + pipeline stages), one IR (:mod:`.ir`), one
parser (:mod:`.parser`). The engine, stages and the ``search action=uql``
adapter land in the follow-up PR.
"""

from __future__ import annotations

from .parser import parse_chain, parse_query

__all__ = ["parse_chain", "parse_query"]
