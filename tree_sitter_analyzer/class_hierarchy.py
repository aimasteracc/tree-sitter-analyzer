#!/usr/bin/env python3
"""
Class Hierarchy — Cache-backed type inheritance analysis.

Builds a directed graph of class inheritance relationships from the
pre-indexed AST cache. Enables:

- subclasses_of(ClassName): find all descendants (transitive)
- superclasses_of(ClassName): find the full inheritance chain above
- hierarchy_tree(ClassName): full subtree rooted at a class
- hierarchy_impact(ClassName): risk analysis for modifying a base class

CodeGraph parity: equivalent to CodeGraph's type-hierarchy feature.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ClassInfo:
    name: str
    file: str
    line: int
    end_line: int
    language: str
    parents: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "file": self.file,
            "line": self.line,
            "end_line": self.end_line,
            "language": self.language,
        }
        if self.parents:
            d["parents"] = self.parents
        return d


@dataclass
class HierarchyImpact:
    target_class: str
    direct_subclass_count: int
    total_subclass_count: int
    affected_files: list[str]
    risk_level: str
    risk_score: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_class": self.target_class,
            "direct_subclass_count": self.direct_subclass_count,
            "total_subclass_count": self.total_subclass_count,
            "affected_files": self.affected_files,
            "risk_level": self.risk_level,
            "risk_score": self.risk_score,
        }


class ClassHierarchy:
    """Cache-backed class inheritance hierarchy analysis.

    Reads class definitions (with parent class names) from the AST
    cache's ``symbols_json`` column and builds a bidirectional graph
    of inheritance relationships.

    Usage::

        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.class_hierarchy import ClassHierarchy

        cache = ASTCache("/path/to/project")
        hierarchy = ClassHierarchy(cache)
        hierarchy.build()

        subs = hierarchy.subclasses_of("BaseWidget")
        chain = hierarchy.superclasses_of("MyWidget")
        impact = hierarchy.hierarchy_impact("BaseWidget")
    """

    def __init__(self, cache: Any) -> None:
        self._cache = cache
        self._classes: dict[str, list[ClassInfo]] = defaultdict(list)
        self._children: dict[str, list[str]] = defaultdict(list)
        self._parent_map: dict[str, list[str]] = defaultdict(list)
        self._built = False

    def build(self) -> None:
        if self._built:
            return
        self._load_from_cache()
        self._build_edges()
        self._built = True

    def _load_from_cache(self) -> None:
        try:
            conn = self._cache._get_conn()
            rows = conn.execute(
                "SELECT file_path, symbols_json, language FROM ast_index"
            ).fetchall()
        except Exception:
            return

        for row in rows:
            file_path = row["file_path"]
            language = row["language"]
            try:
                symbols = json.loads(row["symbols_json"])
            except (json.JSONDecodeError, TypeError):
                continue
            for sym in symbols.get("symbols", []):
                if sym.get("kind") != "class":
                    continue
                name = sym.get("name", "")
                if not name:
                    continue
                parents = sym.get("parents", [])
                info = ClassInfo(
                    name=name,
                    file=file_path,
                    line=sym.get("line", 0),
                    end_line=sym.get("end_line", 0),
                    language=language,
                    parents=parents,
                )
                self._classes[name].append(info)
                if parents:
                    self._parent_map[name] = parents

    def _build_edges(self) -> None:
        for child_name, parent_names in self._parent_map.items():
            for parent_name in parent_names:
                base = parent_name.rsplit(".", 1)[-1]
                if base in self._classes or parent_name in self._classes:
                    self._children[parent_name].append(child_name)
                    if base != parent_name and base not in self._children:
                        pass
                    self._children.setdefault(base, []).append(child_name)

        for key in self._children:
            self._children[key] = sorted(set(self._children[key]))

    def subclasses_of(
        self,
        class_name: str,
        max_depth: int = 10,
    ) -> list[dict[str, Any]]:
        """Find all classes that inherit from ``class_name`` (transitively).

        Returns list of dicts with name, file, line, depth, and language.
        """
        self.build()
        visited: set[str] = set()
        result: list[dict[str, Any]] = []
        queue: deque[tuple[str, int]] = deque([(class_name, 0)])

        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for child_name in self._children.get(current, []):
                if child_name in visited:
                    continue
                visited.add(child_name)
                for info in self._classes.get(child_name, []):
                    result.append(
                        {"depth": depth + 1, **info.to_dict()}
                    )
                queue.append((child_name, depth + 1))

        return result

    def superclasses_of(self, class_name: str) -> list[dict[str, Any]]:
        """Find the inheritance chain above ``class_name``.

        Returns list of dicts with name, file, line, depth, and language.
        """
        self.build()
        visited: set[str] = set()
        result: list[dict[str, Any]] = []
        queue: deque[tuple[str, int]] = deque([(class_name, 0)])

        while queue:
            current, depth = queue.popleft()
            for parent_name in self._parent_map.get(current, []):
                base = parent_name.rsplit(".", 1)[-1]
                candidates = self._classes.get(parent_name, []) or self._classes.get(base, [])
                for info in candidates:
                    key = f"{info.name}:{info.file}"
                    if key in visited:
                        continue
                    visited.add(key)
                    result.append(
                        {"depth": depth + 1, **info.to_dict()}
                    )
                    queue.append((info.name, depth + 1))

        return result

    def hierarchy_tree(self, class_name: str) -> dict[str, Any]:
        """Get the full subtree rooted at ``class_name``.

        Returns a nested dict with the class and all its descendants.
        """
        self.build()
        return self._build_tree(class_name, set(), max_depth=15)

    def _build_tree(
        self, class_name: str, visited: set[str], max_depth: int = 15
    ) -> dict[str, Any]:
        if class_name in visited or max_depth <= 0:
            return {"name": class_name, "circular": True}
        visited = visited | {class_name}

        infos = self._classes.get(class_name, [])
        children_names = self._children.get(class_name, [])

        node: dict[str, Any] = {
            "name": class_name,
            "instances": len(infos),
        }
        if infos:
            first = infos[0]
            node["file"] = first.file
            node["line"] = first.line
            node["language"] = first.language
            if first.parents:
                node["parents"] = first.parents

        child_nodes: list[dict[str, Any]] = []
        for child_name in children_names:
            child_nodes.append(
                self._build_tree(child_name, visited, max_depth - 1)
            )
        if child_nodes:
            node["subclasses"] = child_nodes
        return node

    def hierarchy_impact(self, class_name: str) -> HierarchyImpact:
        """Risk analysis for modifying a class.

        Counts direct and transitive subclasses, affected files, and
        computes a risk score (0-100).
        """
        self.build()

        direct = self._children.get(class_name, [])
        all_subs = self.subclasses_of(class_name, max_depth=15)
        total = len(all_subs)

        affected_files_set: set[str] = set()
        for info in self._classes.get(class_name, []):
            affected_files_set.add(info.file)
        for sub in all_subs:
            affected_files_set.add(sub.get("file", ""))

        score = 0
        if len(direct) >= 10:
            score += 40
        elif len(direct) >= 5:
            score += 25
        elif len(direct) >= 2:
            score += 10
        score += min(30, total * 3)
        if len(affected_files_set) >= 5:
            score += 20
        elif len(affected_files_set) >= 2:
            score += 10
        score = min(100, score)

        if score >= 60:
            level = "critical"
        elif score >= 40:
            level = "high"
        elif score >= 20:
            level = "medium"
        else:
            level = "low"

        return HierarchyImpact(
            target_class=class_name,
            direct_subclass_count=len(direct),
            total_subclass_count=total,
            affected_files=sorted(f for f in affected_files_set if f),
            risk_level=level,
            risk_score=score,
        )

    def all_classes(self) -> list[dict[str, Any]]:
        """Return all discovered class definitions."""
        self.build()
        result: list[dict[str, Any]] = []
        for _name, infos in sorted(self._classes.items()):
            for info in infos:
                result.append(info.to_dict())
        return result

    def summary(self) -> dict[str, Any]:
        """Return hierarchy summary statistics."""
        self.build()
        total_classes = sum(len(v) for v in self._classes.values())
        roots = [
            name
            for name in self._classes
            if not self._parent_map.get(name)
        ]
        leaves = [
            name
            for name in self._classes
            if not self._children.get(name)
        ]
        max_depth = 0
        for name in self._classes:
            depth = self._measure_depth(name, set())
            max_depth = max(max_depth, depth)
        return {
            "total_classes": total_classes,
            "unique_class_names": len(self._classes),
            "root_classes": len(roots),
            "leaf_classes": len(leaves),
            "max_inheritance_depth": max_depth,
            "classes_with_parents": sum(
                1 for v in self._parent_map.values() if v
            ),
        }

    def _measure_depth(self, name: str, visited: set[str]) -> int:
        if name in visited:
            return 0
        visited.add(name)
        children = self._children.get(name, [])
        if not children:
            return 0
        return 1 + max(
            self._measure_depth(c, visited) for c in children
        )
