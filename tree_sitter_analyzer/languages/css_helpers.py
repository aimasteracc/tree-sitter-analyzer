"""CSS declaration, at-rule, and utility helpers — extracted from css_plugin.py."""

from collections.abc import Callable
from typing import Any

from ..utils import log_debug


def extract_node_text(node: Any, source_code: str) -> str:
    """Extract text content from a tree-sitter node."""
    try:
        if hasattr(node, "start_byte") and hasattr(node, "end_byte"):
            source_bytes = source_code.encode("utf-8")
            node_bytes = source_bytes[node.start_byte : node.end_byte]
            return node_bytes.decode("utf-8", errors="replace")
        return ""
    except Exception as e:
        log_debug(f"Failed to extract node text: {e}")
        return ""


def parse_declaration(
    decl_node: Any,
    get_node_text: Callable[..., str],
) -> tuple[str, str]:
    """Parse individual CSS declaration."""
    try:
        prop_name = ""
        prop_value = ""

        if hasattr(decl_node, "children"):
            for child in decl_node.children:
                if hasattr(child, "type"):
                    if child.type == "property_name":
                        prop_name = get_node_text(child).strip()
                    elif child.type in ("value", "values"):
                        prop_value = get_node_text(child).strip()

        if not prop_name:
            decl_text = get_node_text(decl_node)
            if ":" in decl_text:
                parts = decl_text.split(":", 1)
                prop_name = parts[0].strip()
                prop_value = parts[1].strip().rstrip(";")

        return prop_name, prop_value
    except Exception:
        return "", ""


def extract_at_rule_name(
    node: Any,
    get_node_text: Callable[..., str],
) -> str:
    """Extract at-rule name from CSS at-rule node."""
    try:
        node_text = get_node_text(node)
        if node_text.startswith("@"):
            if "{" in node_text:
                return node_text.split("{")[0].strip()
            parts = node_text.split()
            if parts:
                if parts[0] in ("@media", "@keyframes", "@supports"):
                    first_line = node_text.split("\n")[0].strip()
                    if "{" in first_line:
                        return first_line.split("{")[0].strip()
                    return first_line
                return parts[0]
        return node_text[:50]
    except Exception:
        return "unknown"


def classify_rule(
    properties: dict[str, str],
    property_categories: dict[str, list[str]],
) -> str:
    """Classify CSS rule based on properties."""
    if not properties:
        return "other"

    category_scores = dict.fromkeys(property_categories, 0)

    for prop_name in properties:
        prop_name_lower = prop_name.lower()
        for category, props in property_categories.items():
            if any(prop in prop_name_lower for prop in props):
                category_scores[category] += 1

    best_category = max(category_scores, key=lambda k: category_scores[k])
    return best_category if category_scores[best_category] > 0 else "other"
