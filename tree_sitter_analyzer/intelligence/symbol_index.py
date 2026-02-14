#!/usr/bin/env python3
"""
Symbol Index for Code Intelligence Graph.

Maintains a project-wide index of all symbol definitions and references,
supporting lookup by name, file, and type.
"""

from __future__ import annotations

from collections.abc import Callable

from .models import SymbolDefinition, SymbolReference


class SymbolIndex:
    """Project-wide symbol index for definitions and references."""

    def __init__(self) -> None:
        # name -> list of definitions
        self._definitions: dict[str, list[SymbolDefinition]] = {}
        # name -> list of references
        self._references: dict[str, list[SymbolReference]] = {}
        # class_name -> parent_class_name
        self._class_parents: dict[str, str] = {}
        # parent_class -> list of child classes
        self._class_children: dict[str, list[str]] = {}

    def add_definition(self, definition: SymbolDefinition) -> None:
        """Add a symbol definition to the index."""
        if definition.name not in self._definitions:
            self._definitions[definition.name] = []
        self._definitions[definition.name].append(definition)

    def add_reference(self, reference: SymbolReference) -> None:
        """Add a symbol reference to the index."""
        if reference.symbol_name not in self._references:
            self._references[reference.symbol_name] = []
        self._references[reference.symbol_name].append(reference)

    def lookup_definition(
        self, name: str, file_hint: str | None = None
    ) -> list[SymbolDefinition]:
        """
        Look up symbol definitions by name.

        Args:
            name: Symbol name to search for
            file_hint: Optional file path to filter results

        Returns:
            List of matching definitions
        """
        defs = self._definitions.get(name, [])
        if file_hint:
            defs = [
                d
                for d in defs
                if d.file_path == file_hint or d.file_path.endswith(file_hint)
            ]
        return defs

    def lookup_references(
        self,
        name: str,
        ref_type: str | None = None,
        file_filter: Callable[[str], bool] | None = None,
    ) -> list[SymbolReference]:
        """
        Look up symbol references by name.

        Args:
            name: Symbol name to search for
            ref_type: Optional reference type filter ("call", "import", etc.)
            file_filter: Optional callable that receives a file path and returns
                True to include the reference. Useful for filtering to test or
                source files only.

        Returns:
            List of matching references
        """
        refs = self._references.get(name, [])
        if ref_type:
            refs = [r for r in refs if r.ref_type == ref_type]
        if file_filter:
            refs = [r for r in refs if file_filter(r.file_path)]
        return refs

    def set_class_parent(self, class_name: str, parent_name: str) -> None:
        """Record a class inheritance relationship."""
        self._class_parents[class_name] = parent_name
        if parent_name not in self._class_children:
            self._class_children[parent_name] = []
        if class_name not in self._class_children[parent_name]:
            self._class_children[parent_name].append(class_name)

    def get_inheritance_chain(self, class_name: str) -> list[str]:
        """Get the inheritance chain for a class (parents only)."""
        chain: list[str] = []
        current = class_name
        visited: set[str] = set()
        while current in self._class_parents and current not in visited:
            visited.add(current)
            parent = self._class_parents[current]
            chain.append(parent)
            current = parent
        return chain

    def get_subclasses(self, class_name: str) -> list[str]:
        """Get direct subclasses of a class."""
        return self._class_children.get(class_name, [])

    def clear(self) -> None:
        """Clear the entire index."""
        self._definitions.clear()
        self._references.clear()
        self._class_parents.clear()
        self._class_children.clear()

    def get_all_definitions(self) -> dict[str, list[SymbolDefinition]]:
        """Get all definitions in the index."""
        return dict(self._definitions)

    def get_all_references(self) -> dict[str, list[SymbolReference]]:
        """Get all references in the index."""
        return dict(self._references)
