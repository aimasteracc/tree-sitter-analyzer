"""Typed query errors and the ``Result`` type for the unified query language.

RFC-0041 §4: unknown input is parsed at the boundary and every expected
failure is a value, not an exception. A :class:`QueryError` names the failure
with a code from the closed :data:`ERROR_CODES` set, points at the offending
fragment, and carries a concrete suggested fix (often a corrected query the
agent can resend as-is). Partial facts survive: an error raised after some
stages ran carries them in ``partial``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")

#: The query text is empty or not a string.
EMPTY_QUERY = "UQL_EMPTY_QUERY"
#: The query is longer than the parser accepts.
QUERY_TOO_LONG = "UQL_QUERY_TOO_LONG"
#: Steps were joined with ``|`` (or another separator) instead of ``.``.
WRONG_SEPARATOR = "UQL_WRONG_SEPARATOR"
#: Quotes or parentheses do not balance.
UNBALANCED = "UQL_UNBALANCED"
#: A step is not of the form ``name(args)``.
INVALID_STEP = "UQL_INVALID_STEP"
#: A step name is not part of the language.
UNKNOWN_STAGE = "UQL_UNKNOWN_STAGE"
#: A step exists only in the legacy ``chain`` dialect.
CHAIN_ONLY_STAGE = "UQL_CHAIN_ONLY_STAGE"
#: A keyword argument is not accepted by its stage.
UNKNOWN_ARGUMENT = "UQL_UNKNOWN_ARGUMENT"
#: An argument has the wrong type or is out of range.
INVALID_ARGUMENT = "UQL_INVALID_ARGUMENT"
#: The stage order is invalid (for example a relation before any source).
INVALID_ORDER = "UQL_INVALID_ORDER"
#: A bare word was given where a query was expected.
BARE_WORD = "UQL_BARE_WORD"
#: The TQL selector inside ``select(...)`` (or a bare selector) is malformed.
SELECTOR_SYNTAX = "UQL_SELECTOR_SYNTAX"
#: The selector names a pseudo-class the evaluator does not implement.
UNKNOWN_PSEUDO_CLASS = "UQL_UNKNOWN_PSEUDO_CLASS"
#: Too many steps.
TOO_MANY_STAGES = "UQL_TOO_MANY_STAGES"
#: A continuation cursor is malformed, belongs to another query, or is stale.
INVALID_CURSOR = "UQL_INVALID_CURSOR"
#: The source generation changed since the cursor was issued.
STALE_CURSOR = "UQL_STALE_CURSOR"
#: No usable index for the project.
INDEX_UNAVAILABLE = "UQL_INDEX_UNAVAILABLE"
#: A tool argument outside the query text (limit, detail, ...) is invalid.
INVALID_TOOL_ARGUMENT = "UQL_INVALID_TOOL_ARGUMENT"

#: Closed set of error codes; tests pin it so a new code is a conscious change.
ERROR_CODES = frozenset(
    {
        EMPTY_QUERY,
        QUERY_TOO_LONG,
        WRONG_SEPARATOR,
        UNBALANCED,
        INVALID_STEP,
        UNKNOWN_STAGE,
        CHAIN_ONLY_STAGE,
        UNKNOWN_ARGUMENT,
        INVALID_ARGUMENT,
        INVALID_ORDER,
        BARE_WORD,
        SELECTOR_SYNTAX,
        UNKNOWN_PSEUDO_CLASS,
        TOO_MANY_STAGES,
        INVALID_CURSOR,
        STALE_CURSOR,
        INDEX_UNAVAILABLE,
        INVALID_TOOL_ARGUMENT,
    }
)


@dataclass(frozen=True)
class QueryError:
    """One typed failure with the fragment it concerns and a suggested fix."""

    code: str
    message: str
    stage_index: int | None = None
    fragment: str | None = None
    suggestion: str | None = None
    fixed_query: str | None = None
    partial: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.code not in ERROR_CODES:
            raise ValueError(f"unregistered UQL error code: {self.code}")

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "message": self.message}
        for key in ("stage_index", "fragment", "suggestion", "fixed_query"):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        if self.partial:
            out["partial"] = self.partial
        return out


@dataclass(frozen=True)
class Ok(Generic[T]):
    value: T

    @property
    def ok(self) -> bool:
        return True


@dataclass(frozen=True)
class Err:
    error: QueryError

    @property
    def ok(self) -> bool:
        return False


Result = Ok[T] | Err
