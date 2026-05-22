"""CSS declaration, at-rule, and utility helpers — extracted from css_plugin.py."""

from collections.abc import Callable
from typing import Any

from ..models import StyleElement
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


def extract_css_selector(node: Any, get_node_text: Callable[..., str]) -> str:
    """Extract selector from CSS rule_set node."""
    try:
        if hasattr(node, "children"):
            for child in node.children:
                if hasattr(child, "type") and child.type == "selectors":
                    return get_node_text(child).strip()

        node_text = get_node_text(node)
        if "{" in node_text:
            return node_text.split("{")[0].strip()
        return "unknown"
    except Exception:
        return "unknown"


def extract_css_properties(
    node: Any, get_node_text: Callable[..., str]
) -> dict[str, str]:
    """Extract properties from CSS rule_set node.

    r37cj (dogfood): tool flagged this at nesting depth 8 (L126). The
    inner declaration scan moved into ``_collect_css_block_declarations``.
    """
    properties: dict[str, str] = {}
    try:
        if not hasattr(node, "children"):
            return properties
        for child in node.children:
            if hasattr(child, "type") and child.type == "block":
                _collect_css_block_declarations(child, get_node_text, properties)
    except Exception as e:
        log_debug(f"Failed to extract properties: {e}")
    return properties


def _collect_css_block_declarations(
    block_node: Any,
    get_node_text: Callable[..., str],
    properties: dict[str, str],
) -> None:
    """Append each ``declaration`` child to ``properties``.

    r37cj: extracted from ``extract_css_properties`` so the inner walk
    of a CSS block reads as a flat for-if rather than depth-8 nesting.
    """
    for grandchild in block_node.children:
        if not (hasattr(grandchild, "type") and grandchild.type == "declaration"):
            continue
        prop_name, prop_value = parse_declaration(grandchild, get_node_text)
        if prop_name:
            properties[prop_name] = prop_value


def create_style_element(
    node: Any,
    get_node_text: Callable[..., str],
    property_categories: dict[str, list[str]],
) -> StyleElement | None:
    """Create StyleElement from tree-sitter node."""
    try:
        if node.type == "rule_set":
            selector = extract_css_selector(node, get_node_text)
            properties = extract_css_properties(node, get_node_text)
            element_class = classify_rule(properties, property_categories)
            name = selector or "unknown_rule"
        elif node.type in (
            "at_rule",
            "media_statement",
            "import_statement",
            "keyframes_statement",
        ):
            selector = extract_at_rule_name(node, get_node_text)
            properties = {}
            element_class = "at_rule"
            name = selector or "unknown_at_rule"
        else:
            selector = get_node_text(node)[:50]
            properties = {}
            element_class = "other"
            name = selector or "unknown"

        raw_text = get_node_text(node)

        return StyleElement(
            name=name,
            start_line=node.start_point[0] + 1 if hasattr(node, "start_point") else 0,
            end_line=node.end_point[0] + 1 if hasattr(node, "end_point") else 0,
            raw_text=raw_text,
            language="css",
            selector=selector,
            properties=properties,
            element_class=element_class,
        )
    except Exception as e:
        log_debug(f"Failed to create StyleElement: {e}")
        return None
