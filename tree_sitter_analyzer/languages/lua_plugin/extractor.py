#!/usr/bin/env python3
"""Lua Element Extractor — tree-sitter query-based extraction."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

from ...models import Class as ModelClass
from ...models import Function as ModelFunction
from ...models import Import as ModelImport
from ...models import Variable as ModelVariable
from ...plugins.base import ElementExtractor
from ...utils import log_error
from ..shared.traversal import node_range

__all__ = ["LuaElementExtractor"]

# Tree-sitter query: named and anonymous function definitions.
_FUNCTION_QUERY = """
(function_definition name: (identifier) @name)
(local_function name: (identifier) @name)
"""

# Tree-sitter query: require() calls (Lua's import mechanism).
_IMPORT_QUERY = """
(function_call
  name: (identifier) @callee (#eq? @callee "require")
  arguments: (arguments (string content: (string_content) @path)))
"""


def _node_text(node: Any) -> str:
    """Return decoded text for a tree-sitter node, empty string on error."""
    text = getattr(node, "text", None)
    if isinstance(text, bytes):
        return text.decode("utf-8", errors="replace")
    if isinstance(text, str):
        return text
    return ""


class LuaElementExtractor(ElementExtractor):
    """Lua-specific element extractor using tree-sitter queries."""

    def __init__(self) -> None:
        """Initialize the Lua element extractor."""
        super().__init__()

    def _get_lua_language(self) -> Any | None:
        """Return a tree_sitter.Language for Lua, or None if not installed.

        Imports tree_sitter and tree_sitter_lua lazily so the extractor
        degrades gracefully when the Lua grammar package is absent.
        """
        try:
            import tree_sitter
            import tree_sitter_lua as tslua  # noqa: PLC0415

            return tree_sitter.Language(tslua.language())
        except ImportError:
            return None
        except Exception as exc:
            log_error(f"Failed to load Lua tree-sitter language: {exc}")
            return None

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelFunction]:
        """Extract Lua function and local-function definitions.

        Returns an empty list when tree_sitter_lua is not installed.
        """
        language = self._get_lua_language()
        if language is None:
            return []

        try:
            import tree_sitter as _ts
            query = _ts.Query(language, _FUNCTION_QUERY)
            captures: dict[str, list[Any]] = query.captures(tree.root_node)
            name_nodes: list[Any] = captures.get("name", [])

            functions: list[ModelFunction] = []
            for name_node in name_nodes:
                try:
                    fn_node = name_node.parent
                    if fn_node is None:
                        continue

                    name = _node_text(name_node)
                    if not name:
                        continue

                    start_line, end_line = node_range(fn_node)
                    raw_text = _node_text(fn_node)

                    functions.append(
                        ModelFunction(
                            name=name,
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            language="lua",
                        )
                    )
                except Exception as exc:
                    log_error(f"Error extracting Lua function node: {exc}")

            return functions

        except Exception as exc:
            log_error(f"Error in Lua function extraction: {exc}")
            return []

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelImport]:
        """Extract Lua require() calls as import elements.

        Returns an empty list when tree_sitter_lua is not installed.
        """
        language = self._get_lua_language()
        if language is None:
            return []

        try:
            import tree_sitter as _ts
            query = _ts.Query(language, _IMPORT_QUERY)
            captures: dict[str, list[Any]] = query.captures(tree.root_node)
            path_nodes: list[Any] = captures.get("path", [])

            imports: list[ModelImport] = []
            for path_node in path_nodes:
                try:
                    # Walk up from string_content → string → arguments → function_call
                    call_node = path_node.parent
                    while call_node is not None and call_node.type != "function_call":
                        call_node = call_node.parent

                    anchor = call_node if call_node is not None else path_node
                    module_path = _node_text(path_node)
                    start_line, end_line = node_range(anchor)
                    raw_text = _node_text(anchor)

                    imports.append(
                        ModelImport(
                            name=module_path,
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            language="lua",
                            module_name=module_path,
                            module_path=module_path,
                        )
                    )
                except Exception as exc:
                    log_error(f"Error extracting Lua import node: {exc}")

            return imports

        except Exception as exc:
            log_error(f"Error in Lua import extraction: {exc}")
            return []

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelClass]:
        """Lua has no class keyword; always returns an empty list."""
        return []

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelVariable]:
        """Variable extraction not implemented for Lua; returns an empty list."""
        return []
