"""YAML mapping, sequence, and utility helpers — extracted from yaml_plugin.py."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from ..encoding_utils import read_file_safe
from ..models import AnalysisResult, CodeElement
from ..utils import log_debug, log_error, log_info


class YAMLElement(CodeElement):
    """YAML-specific code element."""

    @dataclass(frozen=False)
    class _Config:
        """Configuration carrier for YAMLElement construction."""

        name: str
        start_line: int
        end_line: int
        raw_text: str
        language: str = "yaml"
        element_type: str = "yaml"
        key: str | None = None
        value: str | None = None
        value_type: str | None = None
        anchor_name: str | None = None
        alias_target: str | None = None
        nesting_level: int = 0
        document_index: int = 0
        child_count: int | None = None
        docstring: str | None = None

        @classmethod
        def from_kwargs(cls, **kwargs: Any) -> "YAMLElement._Config":
            return cls(
                name=kwargs.pop("name"),
                start_line=kwargs.pop("start_line"),
                end_line=kwargs.pop("end_line"),
                raw_text=kwargs.pop("raw_text"),
                language=kwargs.pop("language", "yaml"),
                element_type=kwargs.pop("element_type", "yaml"),
                key=kwargs.pop("key", None),
                value=kwargs.pop("value", None),
                value_type=kwargs.pop("value_type", None),
                anchor_name=kwargs.pop("anchor_name", None),
                alias_target=kwargs.pop("alias_target", None),
                nesting_level=kwargs.pop("nesting_level", 0),
                document_index=kwargs.pop("document_index", 0),
                child_count=kwargs.pop("child_count", None),
                docstring=kwargs.pop("docstring", None),
            )

    def __init__(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize a YAML element with YAML-specific metadata.

        Supports both legacy constructor style:
        - ``YAMLElement(name=..., start_line=..., ...)``
        - internal ``YAMLElement(YAMLElement._Config(...), ...)``
        """
        if len(args) > 1:
            raise TypeError(
                "YAMLElement accepts at most 1 positional argument: YAMLElement._Config"
            )

        if args:
            config = args[0]
            if not isinstance(config, YAMLElement._Config):
                raise TypeError(
                    "Expected YAMLElement._Config when passing positional argument"
                )
            if kwargs:
                config = replace(config, **kwargs)
        else:
            config = YAMLElement._Config.from_kwargs(**kwargs)

        super().__init__(
            name=config.name,
            start_line=config.start_line,
            end_line=config.end_line,
            raw_text=config.raw_text,
            language=config.language,
            docstring=config.docstring,
        )
        self.element_type = config.element_type
        self.key = config.key
        self.value = config.value
        self.value_type = config.value_type
        self.anchor_name = config.anchor_name
        self.alias_target = config.alias_target
        self.nesting_level = config.nesting_level
        self.document_index = config.document_index
        self.child_count = config.child_count

    @classmethod
    def from_legacy_kwargs(cls, **kwargs: Any) -> "YAMLElement":
        """Build a YAMLElement from the historical named-argument constructor."""
        return cls(**kwargs)


@dataclass
class _MappingNodeContext:
    """State carried when assigning flow or block mapping nodes."""

    found_colon: bool
    key_node: Any | None
    value_node: Any | None
    anchor_name: str | None
    get_node_text: Callable[..., str]


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


def iter_sequence_nodes(nodes: list[Any]) -> list[Any]:
    """Return YAML sequence nodes from a traversed node list."""
    return [node for node in nodes if node.type in ("block_sequence", "flow_sequence")]


def append_sequence_element(
    elements: list[YAMLElement],
    node: Any,
    get_node_text: Callable[[Any], str],
    get_document_index_func: Callable[[Any], int],
    calculate_nesting_level_func: Callable[[Any], int],
) -> None:
    """Append a YAML sequence element, preserving extractor fault tolerance."""
    try:
        elements.append(
            build_sequence_element(
                node,
                get_node_text,
                get_document_index_func,
                calculate_nesting_level_func,
            )
        )
    except Exception as exc:
        log_debug(f"Skipped YAML sequence node: {exc}")


def build_sequence_element(
    node: Any,
    get_node_text: Callable[[Any], str],
    get_document_index_func: Callable[[Any], int],
    calculate_nesting_level_func: Callable[[Any], int],
) -> YAMLElement:
    """Build a YAML sequence element from a tree-sitter sequence node."""
    return YAMLElement(
        name="sequence",
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        raw_text=_truncate_raw_text(get_node_text(node)),
        element_type="sequence",
        key=extract_sequence_key(node, get_node_text),
        value_type="sequence",
        nesting_level=calculate_nesting_level_func(node),
        document_index=get_document_index_func(node),
        child_count=count_sequence_children(node),
    )


def iter_nodes_by_type(nodes: list[Any], node_type: str) -> list[Any]:
    """Return nodes with the requested tree-sitter type."""
    return [node for node in nodes if node.type == node_type]


def append_anchor_element(
    elements: list[YAMLElement],
    node: Any,
    get_node_text: Callable[[Any], str],
    get_document_index_func: Callable[[Any], int],
    calculate_nesting_level_func: Callable[[Any], int],
) -> None:
    """Append a YAML anchor element, preserving extractor fault tolerance."""
    try:
        elements.append(
            build_anchor_element(
                node,
                get_node_text,
                get_document_index_func,
                calculate_nesting_level_func,
            )
        )
    except Exception as exc:
        log_debug(f"Skipped YAML anchor node: {exc}")


def build_anchor_element(
    node: Any,
    get_node_text: Callable[[Any], str],
    get_document_index_func: Callable[[Any], int],
    calculate_nesting_level_func: Callable[[Any], int],
) -> YAMLElement:
    """Build a YAML anchor element from a tree-sitter anchor node."""
    raw_text = get_node_text(node)
    anchor_name = raw_text.lstrip("&").strip()
    return YAMLElement(
        name=f"&{anchor_name}",
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        raw_text=raw_text,
        element_type="anchor",
        anchor_name=anchor_name,
        nesting_level=calculate_nesting_level_func(node),
        document_index=get_document_index_func(node),
    )


def append_alias_element(
    elements: list[YAMLElement],
    node: Any,
    get_node_text: Callable[[Any], str],
    get_document_index_func: Callable[[Any], int],
    calculate_nesting_level_func: Callable[[Any], int],
) -> None:
    """Append a YAML alias element, preserving extractor fault tolerance."""
    try:
        elements.append(
            build_alias_element(
                node,
                get_node_text,
                get_document_index_func,
                calculate_nesting_level_func,
            )
        )
    except Exception as exc:
        log_debug(f"Skipped YAML alias node: {exc}")


def build_alias_element(
    node: Any,
    get_node_text: Callable[[Any], str],
    get_document_index_func: Callable[[Any], int],
    calculate_nesting_level_func: Callable[[Any], int],
) -> YAMLElement:
    """Build a YAML alias element from a tree-sitter alias node."""
    raw_text = get_node_text(node)
    alias_target = raw_text.lstrip("*").strip()
    return YAMLElement(
        name=f"*{alias_target}",
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        raw_text=raw_text,
        element_type="alias",
        alias_target=alias_target,
        nesting_level=calculate_nesting_level_func(node),
        document_index=get_document_index_func(node),
    )


def append_comment_element(
    elements: list[YAMLElement],
    node: Any,
    get_node_text: Callable[[Any], str],
    get_document_index_func: Callable[[Any], int],
) -> None:
    """Append a YAML comment element, preserving extractor fault tolerance."""
    try:
        elements.append(
            build_comment_element(node, get_node_text, get_document_index_func)
        )
    except Exception as exc:
        log_debug(f"Skipped YAML comment node: {exc}")


def build_comment_element(
    node: Any,
    get_node_text: Callable[[Any], str],
    get_document_index_func: Callable[[Any], int],
) -> YAMLElement:
    """Build a YAML comment element from a tree-sitter comment node."""
    raw_text = get_node_text(node)
    comment_text = raw_text.lstrip("#").strip()
    return YAMLElement(
        name=_truncate_raw_text(comment_text, limit=50),
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        raw_text=raw_text,
        element_type="comment",
        value=comment_text,
        value_type="comment",
        document_index=get_document_index_func(node),
        nesting_level=0,
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
        return _extract_scalar_value_info(text)
    if node_type == "block_scalar":
        return text, "string", None
    if node_type in ("block_mapping", "flow_mapping"):
        return None, "mapping", _count_value_mapping_children(node)
    if node_type in ("block_sequence", "flow_sequence"):
        return None, "sequence", _count_value_sequence_children(node)
    if node_type == "alias":
        return _extract_alias_value_info(text)

    return text, "unknown", None


def _extract_scalar_value_info(text: str) -> tuple[str | None, str, None]:
    lowered = text.lower()
    if lowered in ("true", "false", "yes", "no", "on", "off"):
        return text, "boolean", None
    if lowered in ("null", "~", ""):
        return text if text else None, "null", None
    if is_number(text):
        return text, "number", None
    return text, "string", None


def _count_value_mapping_children(node: Any) -> int:
    return sum(
        1
        for child in node.children
        if child.type in ("block_mapping_pair", "flow_pair")
    )


def _count_value_sequence_children(node: Any) -> int:
    sequence_items = [
        child for child in node.children if child.type == "block_sequence_item"
    ]
    return len(sequence_items or node.children)


def _extract_alias_value_info(text: str) -> tuple[str, str, None]:
    alias_name = text.lstrip("*")
    return f"*{alias_name}", "alias", None


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
    key_node, value_node, anchor_name = _extract_mapping_nodes(
        node.children,
        get_node_text,
    )
    key = _drill_to_scalar(key_node, get_node_text) if key_node is not None else None
    value, value_type, child_count = _extract_mapping_value_info(
        value_node,
        get_node_text,
    )

    return key, value, value_type, child_count, anchor_name


def _extract_mapping_nodes(
    children: list[Any],
    get_node_text: Callable[..., str],
) -> tuple[Any | None, Any | None, str | None]:
    key_node = None
    value_node = None
    anchor_name = None
    found_colon = False

    for child in children:
        if child.type == ":":
            found_colon = True
            continue
        if child.type in ("flow_node", "block_node"):
            mapping_state = _MappingNodeContext(
                found_colon=found_colon,
                key_node=key_node,
                value_node=value_node,
                anchor_name=anchor_name,
                get_node_text=get_node_text,
            )
            key_node, value_node, anchor_name = _assign_flow_or_block_mapping_node(
                child,
                mapping_state,
            )
            continue
        if child.type == "key":
            key_node = _first_child_or_self(child)
            continue
        if child.type == "value":
            value_node = _first_child_or_self(child)
            anchor_name = (
                _find_anchor_name(child.children, get_node_text) or anchor_name
            )
            continue
        if child.type == "anchor":
            anchor_name = _anchor_name(child, get_node_text)

    return key_node, value_node, anchor_name


def _assign_flow_or_block_mapping_node(
    child: Any,
    state: _MappingNodeContext,
) -> tuple[Any | None, Any | None, str | None]:
    if not state.found_colon:
        return child, state.value_node, state.anchor_name
    anchor_name = (
        _find_anchor_name(child.children, state.get_node_text) or state.anchor_name
    )
    return state.key_node, child, anchor_name


def _extract_mapping_value_info(
    value_node: Any | None,
    get_node_text: Callable[..., str],
) -> tuple[str | None, str | None, int | None]:
    if value_node is None:
        return None, None, None
    return extract_value_info(_find_inner_node(value_node), get_node_text)


def _first_child_or_self(node: Any) -> Any:
    if node.children:
        return node.children[0]
    return node


def _find_anchor_name(
    children: list[Any], get_node_text: Callable[..., str]
) -> str | None:
    for child in children:
        if child.type == "anchor":
            return _anchor_name(child, get_node_text)
    return None


def _anchor_name(node: Any, get_node_text: Callable[..., str]) -> str:
    anchor_text = get_node_text(node)
    return anchor_text.lstrip("&").strip()


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
    parent = _find_parent_mapping_pair(node)
    if parent is None:
        return None

    key_node = _find_sequence_key_node(parent)
    if key_node is None:
        return None
    return _drill_to_scalar(key_node, get_node_text)


def _find_parent_mapping_pair(node: Any) -> Any | None:
    parent = node.parent
    while parent is not None:
        if parent.type in ("block_mapping_pair", "flow_pair"):
            return parent
        parent = getattr(parent, "parent", None)
    return None


def _find_sequence_key_node(parent: Any) -> Any | None:
    found_colon = any(sibling.type == ":" for sibling in parent.children)
    for child in parent.children:
        if child.type not in ("flow_node", "block_node"):
            continue
        if _is_sequence_key_child(child, parent, found_colon):
            return child
    return None


def _is_sequence_key_child(child: Any, parent: Any, found_colon: bool) -> bool:
    if not found_colon:
        return True
    if len(parent.children) < 2:
        return False
    return bool(child.start_byte < parent.children[1].start_byte)


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
        content, elements = _extract_yaml_file_elements(
            file_path=file_path,
            create_extractor=create_extractor,
            parser=parser,
            parser_lock=parser_lock,
        )
        log_info(f"Extracted {len(elements)} YAML elements from {file_path}")
        return _yaml_success_result(file_path, content, elements)

    except Exception as exc:
        log_error(f"Failed to analyze YAML file {file_path}: {exc}")
        return _yaml_failure_result(file_path, str(exc))


def _extract_yaml_file_elements(
    *,
    file_path: str,
    create_extractor: Callable[[], Any],
    parser: Any,
    parser_lock: Any,
) -> tuple[str, list[Any]]:
    content, _encoding = read_file_safe(file_path)
    tree = _parse_yaml_content(content, parser, parser_lock)
    yaml_extractor = create_extractor()
    return content, yaml_extractor.extract_yaml_elements(tree, content)


def _parse_yaml_content(content: str, parser: Any, parser_lock: Any) -> Any:
    """Parse YAML content while respecting the shared parser lock."""
    if parser is None or parser_lock is None:
        raise RuntimeError("YAML parser is not initialized")
    with parser_lock:
        return parser.parse(content.encode("utf-8"))


def _yaml_success_result(
    file_path: str,
    content: str,
    elements: list[Any],
) -> AnalysisResult:
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
