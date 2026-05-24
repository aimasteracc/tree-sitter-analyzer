"""Small payload builders for read_partial_tool tests."""

from typing import Any


def batch_request(
    file_path: str,
    sections: Any | None = None,
) -> dict[str, Any]:
    """Build a single batch request without deeply nested test literals."""
    if sections is None:
        sections = [{"start_line": 1}]
    return {"file_path": file_path, "sections": sections}


def batch_args(
    *requests: dict[str, Any],
    **options: Any,
) -> dict[str, Any]:
    """Build batch arguments without inline nested request lists."""
    return {"requests": list(requests), **options}
