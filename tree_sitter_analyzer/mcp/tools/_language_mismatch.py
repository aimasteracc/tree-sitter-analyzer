"""Language-mismatch detection helpers for MCP tools.

O3 / O8 (round-30 dogfood): tools that accept an explicit ``language``
parameter previously analysed e.g. ``foo.py`` as ``java`` whenever the
caller passed ``language='java'`` — every downstream analyser returned
zero classes/methods/fields and the tool happily emitted
``success=true`` with a clean ``SAFE`` verdict. Agents passing the
wrong language tag had no signal that something went wrong.

Extracted from ``base_tool.py`` to give language-mismatch logic a
dedicated module with a minimal import surface. ``base_tool`` re-exports
both functions for backward compatibility — all existing callers continue
to work unchanged.
"""

from __future__ import annotations

from typing import Any


def detect_language_mismatch(
    file_path: str,
    explicit_language: str | None,
    *,
    project_root: str | None = None,
) -> str | None:
    """Return a warning message if explicit ``language`` disagrees with the file extension.

    O3 / O8 (round-30 dogfood): tools that accept an explicit ``language``
    parameter previously analysed e.g. ``foo.py`` as ``java`` whenever the
    caller passed ``language='java'`` — every downstream analyser returned
    zero classes/methods/fields and the tool happily emitted
    ``success=true`` with a clean ``SAFE`` verdict. Agents passing the
    wrong language tag had no signal that something went wrong.

    Returns ``None`` when there is no mismatch to flag:

    * ``explicit_language`` is ``None`` / empty (no override)
    * ``explicit_language`` matches the detected language (case-insensitive)
    * the file extension is unknown — we can't compare, so trust the caller

    Otherwise returns a warning string suitable for surfacing in an error
    envelope. Comparison is case-insensitive (``Python`` matches
    ``python``). Detector failures fall back to "no warning" because we
    can't be sure of the mismatch; the underlying analyser will still
    raise on truly unsupported input.
    """
    if not explicit_language or not isinstance(explicit_language, str):
        return None
    if not file_path or not isinstance(file_path, str):
        return None

    # Local import: avoid a top-level cycle (base_tool is imported by every
    # tool module, including ones loaded before ``language_detector``).
    try:
        from ...language_detector import detect_language_from_file
    except Exception:  # nosec B110 — detector import failure means no warning
        return None

    try:
        detected = detect_language_from_file(file_path, project_root=project_root)
    except Exception:  # nosec B110 — detector failure means no warning
        return None
    if not detected or detected.lower() == "unknown":
        return None
    if detected.lower() == explicit_language.lower():
        return None
    return (
        f"language={explicit_language!r} doesn't match detected language "
        f"{detected!r} from extension. Analysis may be wrong."
    )


def language_mismatch_error_response(
    *,
    tool_name: str,
    file_path: str,
    warning: str,
) -> dict[str, Any]:
    """Canonical strict error envelope for the language-mismatch gate.

    Shared so every tool that opts into the gate emits a byte-identical
    shape. Cross-tool agents branching on ``error_type=='validation'``
    can recover the same way regardless of which tool tripped the gate.

    Why strict (Option A): silent acceptance was the original bug class.
    Returning ``success=False`` forces the caller to make a deliberate
    choice — either omit ``language`` to auto-detect, or fix the
    mismatch. The envelope still carries ``agent_summary`` so the
    response shape stays uniform with other validation failures.
    """
    summary_line = f"{tool_name}: {warning}"
    next_step = (
        f"Use the correct --language for {file_path!r} or omit it to auto-detect."
    )
    return {
        "success": False,
        "error_type": "validation",
        "error": warning,
        "file_path": file_path,
        "summary_line": summary_line,
        "language_mismatch_warning": warning,
        "agent_summary": {
            "verdict": "ERROR",
            "summary_line": summary_line,
            "next_step": next_step,
        },
    }


__all__ = [
    "detect_language_mismatch",
    "language_mismatch_error_response",
]
