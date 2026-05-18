"""YAML mapping, sequence, and utility helpers — extracted from yaml_plugin.py."""

from collections.abc import Callable
from typing import Any

from ..encoding_utils import read_file_safe
from ..models import AnalysisResult, CodeElement
from ..utils import log_debug, log_error, log_info


class YAMLElement(CodeElement):
    """YAML-specific code element."""

    def __init__(
        self,
        name: str,
        start_line: int,
        end_line: int,
        raw_text: str,
        language: str = "yaml",
        element_type: str = "yaml",
        key: str | None = None,
        value: str | None = None,
        value_type: str | None = None,
        anchor_name: str | None = None,
        alias_target: str | None = None,
        nesting_level: int = 0,
        document_index: int = 0,
        child_count: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a YAML element with YAML-specific metadata."""
        super().__init__(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language=language,
            **kwargs,
        )
        self.element_type = element_type
        self.key = key
        self.value = value
        self.value_type = value_type
        self.anchor_name = anchor_name
        self.alias_target = alias_target
        self.nesting_level = nesting_level
        self.document_index = document_index
        self.child_count = child_count


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


def calculate_nesting_level(node: Any) -> int:
    """Calculate AST-based logical nesting level."""
    level = 0
    current = node.parent
    while current is not None:
        if current.type in (
            "block_mapping",
            "block_sequence",
            "flow_mapping",
            "flow_sequence",
        ):
            level += 1
        current = getattr(current, "parent", None)
        if current is None:
            break
    return level


def get_document_index(node: Any) -> int:
    """Get document index for a node."""
    current = node
    while current is not None:
        if current.type == "document":
            index = 0
            sibling = current.prev_sibling
            while sibling is not None:
                if sibling.type == "document":
                    index += 1
                sibling = sibling.prev_sibling
            return index
        current = getattr(current, "parent", None)
        if current is None:
            break
    return 0


def traverse_nodes(node: Any) -> list[Any]:
    """Traverse all nodes in the tree."""
    nodes = [node]
    for child in node.children:
        nodes.extend(traverse_nodes(child))
    return nodes


def count_document_children(document_node: Any) -> int:
    """Count meaningful top-level YAML document children."""
    count = 0
    for child in document_node.children:
        if child.type in ("---", "...", "comment"):
            continue
        count += _count_top_level_document_child(child)
    return count


def _count_top_level_document_child(node: Any) -> int:
    if node.type == "block_node":
        return sum(_count_block_node_child(child) for child in node.children)
    if node.type == "block_mapping":
        return _count_mapping_pairs(node)
    return 0


def _count_block_node_child(node: Any) -> int:
    if node.type == "block_mapping":
        return _count_mapping_pairs(node)
    if node.type in ("block_sequence", "flow_sequence"):
        return 1
    return 0


def _count_mapping_pairs(node: Any) -> int:
    return sum(1 for child in node.children if child.type == "block_mapping_pair")


def count_sequence_children(sequence_node: Any) -> int:
    """Count meaningful YAML sequence children."""
    if sequence_node.type == "block_sequence":
        return sum(
            1 for child in sequence_node.children if child.type == "block_sequence_item"
        )
    return len(sequence_node.children)


def build_document_element(
    node: Any,
    get_node_text: Callable[[Any], str],
    get_document_index_func: Callable[[Any], int],
) -> YAMLElement:
    """Build a YAML document element from a tree-sitter document node."""
    raw_text = get_node_text(node)
    document_index = get_document_index_func(node)
    return YAMLElement(
        name=f"Document {document_index}",
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        raw_text=_truncate_raw_text(raw_text),
        element_type="document",
        document_index=document_index,
        child_count=count_document_children(node),
        nesting_level=0,
    )


def iter_document_nodes(nodes: list[Any]) -> list[Any]:
    """Return YAML document nodes from a traversed node list."""
    return [node for node in nodes if node.type == "document"]


def append_document_element(
    elements: list[YAMLElement],
    node: Any,
    get_node_text: Callable[[Any], str],
    get_document_index_func: Callable[[Any], int],
) -> None:
    """Append a YAML document element, preserving extractor fault tolerance."""
    try:
        elements.append(
            build_document_element(node, get_node_text, get_document_index_func)
        )
    except Exception as exc:
        log_debug(f"Skipped YAML document node: {exc}")


def iter_mapping_nodes(nodes: list[Any]) -> list[Any]:
    """Return YAML mapping pair nodes from a traversed node list."""
    return [node for node in nodes if node.type in ("block_mapping_pair", "flow_pair")]


def append_mapping_element(
    elements: list[YAMLElement],
    node: Any,
    get_node_text: Callable[[Any], str],
    get_document_index_func: Callable[[Any], int],
    calculate_nesting_level_func: Callable[[Any], int],
) -> None:
    """Append a YAML mapping element, preserving extractor fault tolerance."""
    try:
        elements.append(
            build_mapping_element(
                node,
                get_node_text,
                get_document_index_func,
                calculate_nesting_level_func,
            )
        )
    except Exception as exc:
        log_debug(f"Skipped YAML mapping node: {exc}")


def build_mapping_element(
    node: Any,
    get_node_text: Callable[[Any], str],
    get_document_index_func: Callable[[Any], int],
    calculate_nesting_level_func: Callable[[Any], int],
) -> YAMLElement:
    """Build a YAML mapping element from a tree-sitter mapping pair node."""
    key, value, value_type, child_count, anchor_name = extract_mapping_key_and_value(
        node,
        get_node_text,
    )
    return YAMLElement(
        name=key or "mapping",
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        raw_text=get_node_text(node),
        element_type="mapping",
        key=key,
        value=value,
        value_type=value_type,
        nesting_level=calculate_nesting_level_func(node),
        document_index=get_document_index_func(node),
        child_count=child_count,
        anchor_name=anchor_name,
    )


def _truncate_raw_text(raw_text: str, limit: int = 200) -> str:
    if len(raw_text) > limit:
        return raw_text[:limit] + "..."
    return raw_text


def is_number(text: str) -> bool:
    """Check if text represents a number."""
    try:
        float(text)
        return True
    except ValueError:
        return False


def extract_value_info(
    node: Any,
    get_node_text: Callable[..., str],
) -> tuple[str | None, str | None, int | None]:
    """Extract value information from a node.

    Returns:
        Tuple of (value, value_type, child_count)
    """
    if node is None:
        return None, None, None

    node_type = node.type
    text = get_node_text(node).strip()

    if node_type in ("plain_scalar", "double_quote_scalar", "single_quote_scalar"):
        if text.lower() in ("true", "false", "yes", "no", "on", "off"):
            return text, "boolean", None
        elif text.lower() in ("null", "~", ""):
            return text if text else None, "null", None
        elif is_number(text):
            return text, "number", None
        else:
            return text, "string", None
    elif node_type == "block_scalar":
        return text, "string", None
    elif node_type in ("block_mapping", "flow_mapping"):
        child_count = len(
            [c for c in node.children if c.type in ("block_mapping_pair", "flow_pair")]
        )
        return None, "mapping", child_count
    elif node_type in ("block_sequence", "flow_sequence"):
        child_count = len(
            [c for c in node.children if c.type in ("block_sequence_item",)]
            or node.children
        )
        return None, "sequence", child_count
    elif node_type == "alias":
        alias_name = text.lstrip("*")
        return f"*{alias_name}", "alias", None

    return text, "unknown", None


def _drill_to_scalar(node: Any, get_node_text: Callable[..., str]) -> str | None:
    """Drill down through flow_node/block_node wrappers to get scalar text."""
    current = node
    while current and current.type in ("flow_node", "block_node") and current.children:
        current = current.children[0]
    if current:
        return get_node_text(current).strip()
    return None


def extract_mapping_key_and_value(
    node: Any,
    get_node_text: Callable[..., str],
) -> tuple[str | None, str | None, str | None, int | None, str | None]:
    """Extract key, value, value_type, child_count, and anchor from a mapping pair node.

    Returns:
        Tuple of (key, value, value_type, child_count, anchor_name)
    """
    key = None
    value = None
    value_type = None
    child_count = None
    anchor_name = None

    key_node = None
    value_node = None
    found_colon = False

    for child in node.children:
        if child.type == ":":
            found_colon = True
        elif child.type in ("flow_node", "block_node"):
            if not found_colon:
                key_node = child
            else:
                value_node = child
                for subchild in child.children:
                    if subchild.type == "anchor":
                        anchor_text = get_node_text(subchild)
                        anchor_name = anchor_text.lstrip("&").strip()
        elif child.type == "key":
            if child.children:
                key_node = child.children[0]
            else:
                key_node = child
        elif child.type == "value":
            if child.children:
                value_node = child.children[0]
            else:
                value_node = child
            for subchild in child.children:
                if subchild.type == "anchor":
                    anchor_text = get_node_text(subchild)
                    anchor_name = anchor_text.lstrip("&").strip()
        elif child.type == "anchor":
            anchor_text = get_node_text(child)
            anchor_name = anchor_text.lstrip("&").strip()

    if key_node is not None:
        key = _drill_to_scalar(key_node, get_node_text)

    if value_node is not None:
        scalar = _drill_to_scalar(value_node, get_node_text)
        if scalar:
            value, value_type, child_count = extract_value_info(
                _find_inner_node(value_node), get_node_text
            )
        else:
            value, value_type, child_count = extract_value_info(
                _find_inner_node(value_node), get_node_text
            )

    return key, value, value_type, child_count, anchor_name


# Search for patterns or elements: _find_inner_node
def _find_inner_node(node: Any) -> Any:
    """Find the inner content node by drilling through wrappers."""
    current = node
    while current and current.type in ("flow_node", "block_node") and current.children:
        current = current.children[0]
    return current


# Extract elements from AST: extract_sequence_key
def extract_sequence_key(
    node: Any,
    get_node_text: Callable[..., str],
) -> str | None:
    """Try to find the key for a sequence by checking parent mapping."""
    key = None
    parent = node.parent
    while parent is not None:
        if parent.type in ("block_mapping_pair", "flow_pair"):
            for child in parent.children:
                if child.type in ("flow_node", "block_node"):
                    found_colon = False
                    for sibling in parent.children:
                        if sibling.type == ":":
                            found_colon = True
                            break
                    if (
                        not found_colon
                        or child.start_byte < parent.children[1].start_byte
                    ):
                        key = _drill_to_scalar(child, get_node_text)
                        break
            break
        parent = getattr(parent, "parent", None)
    return key


def analyze_yaml_file(
    *,
    file_path: str,
    create_extractor: Callable[[], Any],
    yaml_available: bool,
    parser: Any,
    parser_lock: Any,
) -> AnalysisResult:
    """Analyze a YAML file using the shared parser and extractor factory."""
    if not yaml_available:
        log_error("tree-sitter-yaml not available")
        return _yaml_failure_result(
            file_path,
            "YAML support not available. Install tree-sitter-yaml.",
        )

    try:
        content, _encoding = read_file_safe(file_path)
        tree = _parse_yaml_content(content, parser, parser_lock)
        yaml_extractor = create_extractor()
        elements = yaml_extractor.extract_yaml_elements(tree, content)

        log_info(f"Extracted {len(elements)} YAML elements from {file_path}")

        return AnalysisResult(
            file_path=file_path,
            language="yaml",
            line_count=len(content.splitlines()),
            elements=elements,
            node_count=len(elements),
            query_results={},
            source_code=content,
            success=True,
            error_message=None,
        )

    except Exception as exc:
        log_error(f"Failed to analyze YAML file {file_path}: {exc}")
        return _yaml_failure_result(file_path, str(exc))


def _parse_yaml_content(content: str, parser: Any, parser_lock: Any) -> Any:
    """Parse YAML content while respecting the shared parser lock."""
    if parser is None or parser_lock is None:
        raise RuntimeError("YAML parser is not initialized")
    with parser_lock:
        return parser.parse(content.encode("utf-8"))


def _yaml_failure_result(file_path: str, error_message: str) -> AnalysisResult:
    """Build a consistent YAML analysis failure result."""
    return AnalysisResult(
        file_path=file_path,
        language="yaml",
        line_count=0,
        elements=[],
        node_count=0,
        query_results={},
        source_code="",
        success=False,
        error_message=error_message,
    )
