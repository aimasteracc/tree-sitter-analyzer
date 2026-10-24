"""Parse query text into the unified IR — the single interpretation owner.

RFC-0041 §2 grammar::

    query     := selector | pipeline
    selector  := TQL selector               (first char in . # * [ :)
    pipeline  := source ('.' stage)*
    source    := select('<selector>') | symbol('<name>' | [names], file=?)
                 | search('<name>' | [names])            (chain alias)
    stage     := relation | refinement
    relation  := callers(depth=1..5) | callees() | tests() | impact(depth=1..10)
    refinement:= filter(k=v, ...) | exclude(k=v, ...) | untested() | tested()
                 | take(n) | sort(by='name'|'file'|'line', desc=false)

Both dialects share :mod:`.steps` for splitting and literal arguments.
``parse_chain`` is the legacy ``search action=chain`` grammar (its own step
vocabulary, same lexical owner); ``parse_query`` is the unified grammar.
"""

from __future__ import annotations

import difflib
from typing import Any

from . import steps as _steps
from .errors import (
    BARE_WORD,
    CHAIN_ONLY_STAGE,
    EMPTY_QUERY,
    INVALID_ARGUMENT,
    INVALID_ORDER,
    QUERY_TOO_LONG,
    TOO_MANY_STAGES,
    UNKNOWN_STAGE,
    Err,
    Ok,
    QueryError,
    Result,
)
from .ir import (
    REFINEMENT_STAGES,
    SOURCE_STAGES,
    HasTests,
    Query,
    RawStep,
    Refine,
    Relate,
    Select,
    Sort,
    Stage,
    SymbolSource,
    Take,
)
from .selector import parse_selector

MAX_QUERY_LENGTH = 4096
MAX_STEPS = 20
MAX_CALLERS_DEPTH = 5
MAX_IMPACT_DEPTH = 10
DEFAULT_IMPACT_DEPTH = 10
SELECTOR_START = frozenset(".#*[:")

# -- legacy chain vocabulary (unchanged surface) ------------------------------
_CHAIN_FILTER_KWARGS = frozenset(
    {"name", "kind", "file", "path", "language", "test", "generated", "regex", "case"}
)
_CHAIN_INCLUDE_KWARGS = frozenset(
    {
        "source",
        "callers",
        "callees",
        "complexity",
        "health",
        "risk",
        "affected_tests",
        "max_files",
        "max_symbols",
        "include_code",
        "limit",
    }
)
CHAIN_KWARGS: dict[str, frozenset[str]] = {
    "search": frozenset({"query", "limit"}),
    "semantic": frozenset({"query", "limit"}),
    "explore": frozenset({"query", "max_files", "max_symbols", "include_code"}),
    "callers": frozenset({"depth", "limit"}),
    "callees": frozenset({"depth", "limit"}),
    "related": frozenset({"depth", "limit"}),
    "filter": _CHAIN_FILTER_KWARGS,
    "where": _CHAIN_FILTER_KWARGS,
    "exclude": _CHAIN_FILTER_KWARGS,
    "not": _CHAIN_FILTER_KWARGS,
    "has": _CHAIN_FILTER_KWARGS | frozenset({"callers", "callees", "depth", "limit"}),
    "take": frozenset({"limit"}),
    "sort": frozenset({"by", "desc"}),
    "include": _CHAIN_INCLUDE_KWARGS,
    "with": _CHAIN_INCLUDE_KWARGS,
    "uml": frozenset({"direction", "limit", "max_edges"}),
    "answer": frozenset({"compact"}),
}

# -- unified vocabulary --------------------------------------------------------
_UQL_FILTER_KWARGS = frozenset(
    {"name", "kind", "file", "path", "language", "test", "regex", "case"}
)
UQL_KWARGS: dict[str, frozenset[str]] = {
    "select": frozenset({"selector"}),
    "symbol": frozenset({"name", "file"}),
    "search": frozenset({"query"}),
    "callers": frozenset({"depth"}),
    "callees": frozenset(),
    "tests": frozenset(),
    "impact": frozenset({"depth"}),
    "filter": _UQL_FILTER_KWARGS,
    "where": _UQL_FILTER_KWARGS,
    "exclude": _UQL_FILTER_KWARGS,
    "not": _UQL_FILTER_KWARGS,
    "untested": frozenset(),
    "tested": frozenset(),
    "take": frozenset({"limit"}),
    "sort": frozenset({"by", "desc"}),
}
_CHAIN_ONLY = frozenset(CHAIN_KWARGS) - frozenset(UQL_KWARGS)


# -- chain dialect --------------------------------------------------------------
def _chain_unknown(name: str, index: int, part: str) -> QueryError:
    close = difflib.get_close_matches(name, sorted(CHAIN_KWARGS), n=1)
    return QueryError(
        UNKNOWN_STAGE,
        f"unsupported chain step: {name}",
        stage_index=index,
        fragment=part,
        suggestion=f"Did you mean {close[0]}()?" if close else None,
    )


def parse_chain(query: str) -> Result[list[RawStep]]:
    """Legacy chain grammar (``search action=chain``) as a ``Result``."""
    if len(query) > MAX_QUERY_LENGTH:
        return Err(
            QueryError(QUERY_TOO_LONG, f"query exceeds {MAX_QUERY_LENGTH} characters")
        )
    # #574: '|' is the natural-but-wrong separator agents reach for.
    if _steps.has_unquoted_pipe(query):
        return Err(_steps.pipe_error(query))
    if "(" not in query:
        return Ok([RawStep("explore", [query], {}), RawStep("related", [], {})])
    split = _steps.split_steps(query)
    if isinstance(split, Err):
        return split
    parts = split.value
    if len(parts) > MAX_STEPS:
        return Err(
            QueryError(TOO_MANY_STAGES, f"query exceeds {MAX_STEPS} chain steps")
        )
    out: list[RawStep] = []
    for index, part in enumerate(parts):
        step = _steps.parse_step(
            part, index=index, allowed_kwargs=CHAIN_KWARGS, unknown_step=_chain_unknown
        )
        if isinstance(step, Err):
            return step
        out.append(step.value)
    if not out:
        return Err(QueryError(EMPTY_QUERY, "query has no chain steps"))
    return Ok(out)


# -- unified dialect ------------------------------------------------------------
def _uql_unknown(name: str, index: int, part: str) -> QueryError:
    if name in _CHAIN_ONLY:
        return QueryError(
            CHAIN_ONLY_STAGE,
            f"{name}() exists only in the legacy chain dialect",
            stage_index=index,
            fragment=part,
            suggestion=(
                f"Run it with search action=chain, or use the unified stages: "
                f"{', '.join(sorted(UQL_KWARGS))}."
            ),
        )
    close = difflib.get_close_matches(name, sorted(UQL_KWARGS), n=1)
    return QueryError(
        UNKNOWN_STAGE,
        f"unknown stage {name}()",
        stage_index=index,
        fragment=part,
        suggestion=f"Did you mean {close[0]}()?" if close else None,
    )


def parse_query(text: Any) -> Result[Query]:
    """Parse the unified language: a bare TQL selector or a pipeline."""
    if not isinstance(text, str) or not text.strip():
        return Err(
            QueryError(
                EMPTY_QUERY,
                "query is required and must be a non-empty string",
                suggestion="e.g. symbol('parse').callers().tests()",
            )
        )
    query = text.strip()
    if len(query) > MAX_QUERY_LENGTH:
        return Err(
            QueryError(QUERY_TOO_LONG, f"query exceeds {MAX_QUERY_LENGTH} characters")
        )
    if query[0] in SELECTOR_START:
        selector = parse_selector(query)
        if isinstance(selector, Err):
            return selector
        return Ok(Query(query, (Select(query, selector.value),), "tql"))
    if _steps.has_unquoted_pipe(query):
        return Err(_steps.pipe_error(query))
    if "(" not in query:
        word = query.split()[0]
        return Err(
            QueryError(
                BARE_WORD,
                f"{query!r} is not a query",
                fragment=query[:80],
                suggestion="Name a source stage first.",
                fixed_query=f"symbol({word!r})",
            )
        )
    split = _steps.split_steps(query)
    if isinstance(split, Err):
        return split
    parts = split.value
    if len(parts) > MAX_STEPS:
        return Err(QueryError(TOO_MANY_STAGES, f"query exceeds {MAX_STEPS} steps"))
    stages: list[Stage] = []
    for index, part in enumerate(parts):
        raw = _steps.parse_step(
            part, index=index, allowed_kwargs=UQL_KWARGS, unknown_step=_uql_unknown
        )
        if isinstance(raw, Err):
            return raw
        stage = _to_stage(raw.value, index, part)
        if isinstance(stage, Err):
            return stage
        stages.append(stage.value)
    order = _check_order(stages, parts)
    if order is not None:
        return Err(order)
    return Ok(Query(query, tuple(stages), "uql"))


def _bad(index: int, part: str, message: str, suggestion: str) -> Err:
    return Err(
        QueryError(
            INVALID_ARGUMENT,
            message,
            stage_index=index,
            fragment=part,
            suggestion=suggestion,
        )
    )


def _names(step: RawStep, key: str) -> list[str]:
    value: Any = step.args[0] if step.args else step.kwargs.get(key)
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [v.strip() for v in value if isinstance(v, str) and v.strip()]


def _int(step: RawStep, key: str, default: int) -> int | None:
    value = step.args[0] if step.args else step.kwargs.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _to_stage(step: RawStep, index: int, part: str) -> Result[Stage]:
    name = step.name
    if name == "select":
        value = step.args[0] if step.args else step.kwargs.get("selector")
        if not isinstance(value, str) or not value.strip():
            return _bad(
                index,
                part,
                "select() needs a selector string",
                "select('.function:in(src/)')",
            )
        parsed = parse_selector(value.strip())
        if isinstance(parsed, Err):
            return Err(
                QueryError(
                    parsed.error.code,
                    parsed.error.message,
                    stage_index=index,
                    fragment=parsed.error.fragment,
                    suggestion=parsed.error.suggestion,
                )
            )
        return Ok(Select(value.strip(), parsed.value))
    if name in ("symbol", "search"):
        names = _names(step, "name" if name == "symbol" else "query")
        if not names:
            return _bad(index, part, f"{name}() needs a symbol name", "symbol('parse')")
        file = step.kwargs.get("file")
        if file is not None and not isinstance(file, str):
            return _bad(
                index, part, "file must be a string", "symbol('parse', file='src/a.py')"
            )
        return Ok(SymbolSource(tuple(names), file or None))
    if name in ("callers", "impact"):
        cap = MAX_CALLERS_DEPTH if name == "callers" else MAX_IMPACT_DEPTH
        default = 1 if name == "callers" else DEFAULT_IMPACT_DEPTH
        depth = _int(step, "depth", default)
        if depth is None or not 1 <= depth <= cap:
            return _bad(
                index,
                part,
                f"{name}() depth must be an integer 1..{cap}",
                f"{name}(depth={min(2, cap)})",
            )
        return Ok(Relate(name, depth))  # type: ignore[arg-type]
    if name in ("callees", "tests"):
        if step.args:
            return _bad(index, part, f"{name}() takes no arguments", f"{name}()")
        return Ok(Relate(name))  # type: ignore[arg-type]
    if name in ("filter", "where", "exclude", "not"):
        if step.args or not step.kwargs:
            return _bad(
                index,
                part,
                f"{name}() takes keyword predicates",
                f"{name}(file='src/')",
            )
        op = "exclude" if name in ("exclude", "not") else "filter"
        return Ok(Refine(op, tuple(sorted(step.kwargs.items()))))  # type: ignore[arg-type]
    if name in ("untested", "tested"):
        return Ok(HasTests(want_tests=name == "tested"))
    if name == "take":
        n = _int(step, "limit", -1)
        if n is None or n < 1:
            return _bad(index, part, "take() needs a positive integer", "take(10)")
        return Ok(Take(n))
    by = step.args[0] if step.args else step.kwargs.get("by", "name")
    if by not in ("name", "file", "line"):
        return _bad(
            index, part, "sort() by must be 'name', 'file' or 'line'", "sort(by='file')"
        )
    return Ok(Sort(by, bool(step.kwargs.get("desc", False))))


def _check_order(stages: list[Stage], parts: list[str]) -> QueryError | None:
    if not isinstance(stages[0], SOURCE_STAGES):
        return QueryError(
            INVALID_ORDER,
            "a query must start with a source stage: select(...) or symbol(...)",
            stage_index=0,
            fragment=parts[0],
            suggestion="Prefix the pipeline with symbol('Name').",
            fixed_query=f"symbol('Name').{'.'.join(parts)}",
        )
    for index, stage in enumerate(stages[1:], start=1):
        if isinstance(stage, SOURCE_STAGES):
            return QueryError(
                INVALID_ORDER,
                "only the first stage may be a source",
                stage_index=index,
                fragment=parts[index],
                suggestion="Combine names in one source: symbol(['A', 'B']).",
            )
    return None


__all__ = [
    "CHAIN_KWARGS",
    "REFINEMENT_STAGES",
    "UQL_KWARGS",
    "parse_chain",
    "parse_query",
]
