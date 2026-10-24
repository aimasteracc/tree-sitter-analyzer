"""The single intermediate representation of the unified query language.

RFC-0041 §2: TQL selectors and chain pipelines parse into this one IR, owned
by :mod:`tree_sitter_analyzer.uql.parser`. The MCP adapters (``search
action=uql`` / ``tql_execute`` / ``chain``) and the CLI flags all consume it;
none of them reinterprets query text.

A :class:`Query` is an ordered tuple of stages:

* a **source** (:class:`Select`, :class:`SymbolSource`) opens the pipeline;
* a **relation** (:class:`Relate`) replaces the current set with related
  symbols and opens a new output group;
* a **refinement** (:class:`Refine`, :class:`HasTests`, :class:`Take`,
  :class:`Sort`) narrows or orders the current group in place.

All nodes are frozen so a parsed query is a hashable, side-effect-free value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from ..hyphae.ast import SelectorList

RelationName = Literal["callers", "callees", "tests", "impact"]


@dataclass(frozen=True)
class RawStep:
    """One ``name(args)`` step exactly as written (chain-dialect IR)."""

    name: str
    args: list[Any]
    kwargs: dict[str, Any]


@dataclass(frozen=True)
class Select:
    """Source: a TQL selector evaluated over the symbol index."""

    text: str
    selector: SelectorList


@dataclass(frozen=True)
class SymbolSource:
    """Source: definitions with an exact name (``Class.method`` allowed)."""

    names: tuple[str, ...]
    file: str | None = None


@dataclass(frozen=True)
class Relate:
    """Relation: callers / callees / tests / impact of the current set."""

    relation: RelationName
    depth: int = 1


@dataclass(frozen=True)
class Refine:
    """Refinement: keep (``filter``) or drop (``exclude``) by attribute."""

    op: Literal["filter", "exclude"]
    predicates: tuple[tuple[str, Any], ...]


@dataclass(frozen=True)
class HasTests:
    """Refinement: keep symbols with (``tested``) or without (``untested``) tests."""

    want_tests: bool


@dataclass(frozen=True)
class Take:
    """Refinement: keep the first ``n`` symbols of the current group."""

    n: int


@dataclass(frozen=True)
class Sort:
    """Refinement: order the current group."""

    by: Literal["name", "file", "line"]
    desc: bool = False


Stage = Select | SymbolSource | Relate | Refine | HasTests | Take | Sort
SOURCE_STAGES = (Select, SymbolSource)
REFINEMENT_STAGES = (Refine, HasTests, Take, Sort)


@dataclass(frozen=True)
class Query:
    """A parsed, validated query."""

    text: str
    stages: tuple[Stage, ...]
    dialect: Literal["uql", "tql"] = "uql"


def stage_name(stage: Stage) -> str:
    """The surface name of a stage, used in output keys and reason prefixes."""
    if isinstance(stage, Select):
        return "select"
    if isinstance(stage, SymbolSource):
        return "symbol"
    if isinstance(stage, Relate):
        return stage.relation
    if isinstance(stage, Refine):
        return stage.op
    if isinstance(stage, HasTests):
        return "tested" if stage.want_tests else "untested"
    if isinstance(stage, Take):
        return "take"
    return "sort"
