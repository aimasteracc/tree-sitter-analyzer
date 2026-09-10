"""Shared limits for project-indexing entry points."""

from __future__ import annotations

DEFAULT_INDEX_MAX_FILES = 20_000
KNOWLEDGE_INDEX_MAX_FILES = 1_000_000


def normalize_index_max_files(
    value: object | None,
    *,
    default: int = DEFAULT_INDEX_MAX_FILES,
) -> int:
    """Return a positive project-index file limit.

    ``None`` means that the caller omitted the option and therefore selects the
    supplied positive default. Zero is deliberately invalid rather than an
    alias for either "no work" or "unlimited"; callers that need an unlimited
    operation must choose an explicit, bounded positive limit.
    """
    candidate: object = default if value is None else value
    if isinstance(candidate, bool):
        raise ValueError(
            "max_files must be a positive integer; "
            f"got {candidate!r} ({type(candidate).__name__})"
        )
    if isinstance(candidate, int):
        normalized = candidate
    elif isinstance(candidate, float) and candidate.is_integer():
        normalized = int(candidate)
    elif isinstance(candidate, str):
        try:
            normalized = int(candidate, 10)
        except ValueError as exc:
            raise ValueError(
                "max_files must be a positive integer; "
                f"got {candidate!r} ({type(candidate).__name__})"
            ) from exc
    else:
        raise ValueError(
            "max_files must be a positive integer; "
            f"got {candidate!r} ({type(candidate).__name__})"
        )
    if normalized <= 0:
        raise ValueError(
            "max_files must be a positive integer; "
            f"got {candidate!r} ({type(candidate).__name__})"
        )
    return normalized


def parse_index_max_files(value: str) -> int:
    """Argparse converter for :func:`normalize_index_max_files`."""
    try:
        parsed = int(value, 10)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_files must be a positive integer") from exc
    return normalize_index_max_files(parsed)
