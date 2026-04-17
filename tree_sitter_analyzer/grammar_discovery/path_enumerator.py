"""
Path Enumeration Module

Discovers syntactic paths from code samples.
Records (node_type, parent_path) tuples up to a specified depth.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from tree_sitter import Language, Node


@dataclass(frozen=True)
class SyntacticPath:
    """A syntactic path from root to a specific node type."""

    node_type: str
    parent_path: tuple[str, ...]
    depth: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_type": self.node_type,
            "parent_path": " > ".join(self.parent_path),
            "depth": self.depth,
        }


class PathEnumerator:
    """
    Enumerates syntactic paths from code samples.

    Traverses AST nodes and records the path from root to each node.
    Useful for understanding grammar structure and discovering common patterns.
    """

    def __init__(self, language: Language, max_depth: int = 3) -> None:
        """
        Initialize the path enumerator.

        Args:
            language: Tree-sitter Language
            max_depth: Maximum depth to record paths (default 3)
        """
        self._language = language
        self._max_depth = max_depth

    def enumerate_paths(
        self,
        root_node: Node,
    ) -> list[SyntacticPath]:
        """
        Enumerate all syntactic paths in a code sample.

        Args:
            root_node: The root node of parsed code

        Returns:
            List of SyntacticPath objects representing unique paths
        """
        paths: set[tuple[str, ...]] = set()

        def traverse(node: Node, current_path: tuple[str, ...], depth: int) -> None:
            if depth > self._max_depth:
                return

            node_path = current_path + (node.type,)
            paths.add(node_path)

            for child in node.children:
                traverse(child, node_path, depth + 1)

        traverse(root_node, (), 0)

        # Convert to SyntacticPath objects
        return [
            SyntacticPath(
                node_type=path[-1] if path else "",
                parent_path=path[:-1],
                depth=len(path) - 1,
            )
            for path in paths
        ]

    def enumerate_paths_from_samples(
        self,
        code_samples: list[Node],
    ) -> dict[str, list[SyntacticPath]]:
        """
        Enumerate paths across multiple code samples.

        Args:
            code_samples: List of root nodes from parsed code

        Returns:
            Dictionary mapping node types to their paths
        """
        all_paths: dict[str, list[SyntacticPath]] = defaultdict(list)

        for root_node in code_samples:
            paths = self.enumerate_paths(root_node)
            for path in paths:
                all_paths[path.node_type].append(path)

        # Deduplicate paths within each node type
        unique_paths: dict[str, list[SyntacticPath]] = {}
        for node_type, path_list in all_paths.items():
            seen: set[tuple[str, ...]] = set()
            unique: list[SyntacticPath] = []
            for path in path_list:
                path_key = path.parent_path
                if path_key not in seen:
                    seen.add(path_key)
                    unique.append(path)
            unique_paths[node_type] = unique

        return unique_paths

    def get_path_summary(
        self,
        paths: list[SyntacticPath] | dict[str, list[SyntacticPath]],
    ) -> dict[str, Any]:
        """
        Get summary statistics about enumerated paths.

        Args:
            paths: Either a list of paths or dict from enumerate_paths_from_samples

        Returns:
            Dictionary with path statistics
        """
        if isinstance(paths, dict):
            flat_paths = []
            for path_list in paths.values():
                flat_paths.extend(path_list)
        else:
            flat_paths = paths

        unique_node_types = {p.node_type for p in flat_paths}
        depth_distribution: dict[int, int] = defaultdict(int)

        for path in flat_paths:
            depth_distribution[path.depth] += 1

        return {
            "total_paths": len(flat_paths),
            "unique_node_types": len(unique_node_types),
            "max_depth": max(depth_distribution.keys()) if depth_distribution else 0,
            "depth_distribution": dict(depth_distribution),
        }

    def find_common_patterns(
        self,
        paths: dict[str, list[SyntacticPath]],
        min_occurrences: int = 2,
    ) -> list[tuple[str, int, list[tuple[str, ...]]]]:
        """
        Find common syntactic patterns across node types.

        Args:
            paths: Dictionary from enumerate_paths_from_samples
            min_occurrences: Minimum times a pattern must appear

        Returns:
            List of (node_type, count, parent_paths) tuples
        """
        patterns: list[tuple[str, int, list[tuple[str, ...]]]] = []

        for node_type, path_list in paths.items():
            if len(path_list) >= min_occurrences:
                parent_paths = [p.parent_path for p in path_list]
                patterns.append((node_type, len(path_list), parent_paths))

        # Sort by occurrence count descending
        return sorted(patterns, key=lambda x: x[1], reverse=True)
