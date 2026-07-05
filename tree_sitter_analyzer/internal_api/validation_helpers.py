"""Validation helpers for the public API facade."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..encoding_utils import read_file_safe


def validation_result_template(file_path: Path) -> dict[str, Any]:
    """Create the stable validation result shape."""
    return {
        "valid": False,
        "exists": file_path.exists(),
        "readable": False,
        "language": None,
        "supported": False,
        "size": 0,
        "errors": [],
    }


def mark_validation_readable(file_path: Path, result: dict[str, Any]) -> bool:
    """Populate readability and size validation fields."""
    if not file_path.exists():
        result["errors"].append("File does not exist")
        return False

    try:
        read_file_safe(file_path)
        result["readable"] = True
        result["size"] = file_path.stat().st_size
        return True
    except Exception as exc:
        result["errors"].append(f"File is not readable: {exc}")
        return False


def apply_language_validation(
    result: dict[str, Any],
    language: str,
    is_language_supported: Callable[[str], bool],
) -> None:
    """Populate language support validation fields."""
    result["language"] = language
    if language:
        result["supported"] = is_language_supported(language)
        if not result["supported"]:
            result["errors"].append(f"Language '{language}' is not supported")
    else:
        result["errors"].append("Could not detect programming language")
