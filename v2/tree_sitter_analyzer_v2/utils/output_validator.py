"""
Output Validator - Validate MCP tool output format correctness.

Simple validator to ensure TOON format outputs are clean and don't
contain redundant fields.
"""

from typing import Any


def validate_toon_output(result: dict[str, Any]) -> dict[str, Any]:
    """
    Validate that TOON format output is clean (no redundant fields).

    A clean TOON output should only contain:
    - format: "toon"
    - toon_content: <the TOON string>

    Any other fields mean the data is duplicated (once in outer dict,
    once inside toon_content).

    Args:
        result: MCP tool result dictionary

    Returns:
        Dict with:
            - valid: True if output is clean
            - reason: Explanation
            - extra_fields: List of redundant fields (if invalid)
            - suggestion: How to fix (if invalid)
    """
    # Not TOON format - skip validation
    if result.get("format") != "toon":
        return {
            "valid": True,
            "reason": "Not TOON format (no validation needed)",
        }

    # Missing toon_content
    if "toon_content" not in result:
        return {
            "valid": False,
            "reason": "TOON format must have 'toon_content' field",
        }

    # Check for extra fields
    allowed = {"format", "toon_content"}
    extra = set(result.keys()) - allowed

    if extra:
        return {
            "valid": False,
            "reason": f"TOON output contains redundant fields: {sorted(extra)}",
            "extra_fields": sorted(extra),
            "suggestion": "Remove these fields from outer dict - they should only be in toon_content",
        }

    return {
        "valid": True,
        "reason": "Clean TOON output (no redundant fields)",
    }


def estimate_token_waste(result: dict[str, Any]) -> dict[str, Any]:
    """
    Estimate token waste from redundant fields in TOON output.

    Args:
        result: MCP tool result dictionary

    Returns:
        Dict with:
            - total_chars: Total characters in output
            - redundant_chars: Characters in redundant fields
            - waste_percentage: Percentage of waste
    """
    import json

    validation = validate_toon_output(result)

    if validation["valid"]:
        return {
            "total_chars": len(json.dumps(result)),
            "redundant_chars": 0,
            "waste_percentage": 0.0,
        }

    # Calculate redundant data size
    extra_fields = validation.get("extra_fields", [])
    redundant_data = {k: result[k] for k in extra_fields}
    redundant_chars = len(json.dumps(redundant_data))
    total_chars = len(json.dumps(result))

    return {
        "total_chars": total_chars,
        "redundant_chars": redundant_chars,
        "waste_percentage": round(redundant_chars / total_chars * 100, 1),
    }
