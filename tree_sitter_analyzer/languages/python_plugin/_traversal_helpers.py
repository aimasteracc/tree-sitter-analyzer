"""Traversal helpers for the Python language extractor."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

_CONTAINER_NODE_TYPES = frozenset(
    {
        "module",
        "class_definition",
        "function_definition",
        "decorated_definition",
        "if_statement",
        "else_clause",
        "elif_clause",
        "for_statement",
        "while_statement",
        "with_statement",
        "try_statement",
        "except_clause",
        "finally_clause",
        "block",
    }
)
_MAX_TRAVERSAL_DEPTH = 50


@dataclass(slots=True)
class TraversalRuntime:
    extractors: dict[str, Any]
    results: list[Any]
    element_type: str
    element_cache: dict[tuple[int, str], Any]
    processed_node_ids: set[int]
    log_debug_fn: Callable[[str], None]
    log_warning_fn: Callable[[str], None]


def run_iterative_traversal(root_node: Any | None, runtime: TraversalRuntime) -> None:
    """Traverse the tree iteratively and append extracted elements."""
    if not root_node:
        return

    context = _TraversalContext(
        extractors=runtime.extractors,
        results=runtime.results,
        element_type=runtime.element_type,
        element_cache=runtime.element_cache,
        processed_node_ids=runtime.processed_node_ids,
        log_warning_fn=runtime.log_warning_fn,
    )
    context.run(root_node)
    runtime.log_debug_fn(
        f"Iterative traversal processed {context.processed_nodes} nodes"
    )


@dataclass(slots=True)
class _TraversalContext:
    extractors: dict[str, Any]
    results: list[Any]
    element_type: str
    element_cache: dict[tuple[int, str], Any]
    processed_node_ids: set[int]
    log_warning_fn: Callable[[str], None]
    target_node_types: set[str] = field(init=False)
    processed_nodes: int = 0
    max_depth: int = _MAX_TRAVERSAL_DEPTH

    def __post_init__(self) -> None:
        self.target_node_types = set(self.extractors.keys())

    def run(self, root_node: Any) -> None:
        node_stack = [(root_node, 0)]

        while node_stack:
            current_node, depth = node_stack.pop()

            if depth > self.max_depth:
                self.log_warning_fn(
                    f"Maximum traversal depth ({self.max_depth}) exceeded"
                )
                continue

            self.processed_nodes += 1
            node_type = current_node.type

            if not self._should_visit_node_type(node_type, depth):
                continue

            if self._is_cached_target(current_node, node_type):
                continue

            _push_child_nodes(node_stack, current_node, depth)

    def _should_visit_node_type(self, node_type: str, depth: int) -> bool:
        return depth == 0 or node_type in self.target_node_types | _CONTAINER_NODE_TYPES

    def _is_cached_target(self, current_node: Any, node_type: str) -> bool:
        if node_type not in self.target_node_types:
            return False

        node_id = id(current_node)
        if node_id in self.processed_node_ids:
            return True

        cache_key = (node_id, self.element_type)
        if cache_key in self.element_cache:
            self._append_element(self.element_cache[cache_key])
            self.processed_node_ids.add(node_id)
            return True

        self._extract_uncached_target(current_node, node_type, cache_key, node_id)
        return False

    def _extract_uncached_target(
        self,
        current_node: Any,
        node_type: str,
        cache_key: tuple[int, str],
        node_id: int,
    ) -> None:
        extractor = self.extractors.get(node_type)
        if not extractor:
            return

        try:
            element = extractor(current_node)
            self.element_cache[cache_key] = element
            self._append_element(element)
        except Exception:
            pass
        finally:
            self.processed_node_ids.add(node_id)

    def _append_element(self, element: Any) -> None:
        if not element:
            return
        if isinstance(element, list):
            self.results.extend(element)
        else:
            self.results.append(element)


def _push_child_nodes(
    node_stack: list[tuple[Any, int]], current_node: Any, depth: int
) -> None:
    for child in _iter_child_nodes(current_node):
        node_stack.append((child, depth + 1))


def _iter_child_nodes(current_node: Any) -> Iterator[Any]:
    children = current_node.children
    if not children:
        return iter(())

    try:
        return reversed(list(children))
    except TypeError:
        return iter(())
