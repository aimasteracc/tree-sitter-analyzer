#!/usr/bin/env python3
"""
Call Graph Builder for Code Intelligence Graph.

Extracts function/method call relationships from Python source code
using tree-sitter parsing and builds caller/callee graphs.
"""

from __future__ import annotations

from typing import Any

from .models import CallSite

try:
    import tree_sitter
    import tree_sitter_python

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False


class CallGraphBuilder:
    """Builds call graphs from Python source code using tree-sitter."""

    def __init__(self, analysis_engine: Any = None) -> None:
        self._engine = analysis_engine
        self._call_sites: dict[str, list[CallSite]] = {}
        self._parser: Any = None

    def _get_parser(self) -> Any:
        """Get or create a tree-sitter parser for Python."""
        if self._parser is not None:
            return self._parser

        if not TREE_SITTER_AVAILABLE:
            return None

        try:
            from tree_sitter import Parser

            language = tree_sitter.Language(tree_sitter_python.language())
            parser = Parser()
            if hasattr(parser, "set_language"):
                parser.set_language(language)
            else:
                parser.language = language
            self._parser = parser
            return parser
        except Exception:
            return None

    def extract_calls_from_source(
        self, source_code: str, file_path: str
    ) -> list[CallSite]:
        """
        Extract all function/method call sites from Python source code.

        Args:
            source_code: Python source code string
            file_path: Path of the source file

        Returns:
            List of CallSite objects
        """
        parser = self._get_parser()
        if parser is None:
            return []

        tree = parser.parse(source_code.encode("utf-8"))
        calls: list[CallSite] = []

        self._walk_tree_for_calls(tree.root_node, file_path, source_code, calls)

        # Store for later lookup
        self._call_sites[file_path] = calls
        return calls

    def _walk_tree_for_calls(
        self,
        node: Any,
        file_path: str,
        source_code: str,
        calls: list[CallSite],
        current_function: str | None = None,
    ) -> None:
        """Recursively walk the AST looking for call nodes."""
        # Track current function context
        if node.type in ("function_definition", "async_function_definition"):
            for child in node.children:
                if child.type == "identifier":
                    current_function = (
                        child.text.decode("utf-8")
                        if isinstance(child.text, bytes)
                        else child.text
                    )
                    break

        if node.type == "call":
            call_site = self._extract_call_site(
                node, file_path, source_code, current_function
            )
            if call_site:
                calls.append(call_site)

        for child in node.children:
            self._walk_tree_for_calls(
                child, file_path, source_code, calls, current_function
            )

    def _extract_call_site(
        self,
        node: Any,
        file_path: str,
        source_code: str,
        current_function: str | None,
    ) -> CallSite | None:
        """Extract a CallSite from a call node."""
        func_node = None
        for child in node.children:
            if child.type not in ("argument_list", "(", ")"):
                func_node = child
                break

        if func_node is None:
            return None

        line = node.start_point[0] + 1
        raw_text = (
            source_code[node.start_byte : node.end_byte]
            if hasattr(node, "start_byte")
            else ""
        )

        def _node_text(n: Any) -> str:
            t = getattr(n, "text", b"")
            return t.decode("utf-8") if isinstance(t, bytes) else str(t)

        # Simple function call: foo()
        if func_node.type == "identifier":
            callee_name = _node_text(func_node)
            return CallSite(
                caller_file=file_path,
                caller_function=current_function,
                callee_name=callee_name,
                callee_object=None,
                line=line,
                raw_text=raw_text,
            )

        # Method call: obj.method()
        if func_node.type == "attribute":
            children = [c for c in func_node.children if c.type == "identifier"]
            if len(children) >= 2:
                obj_text = _node_text(children[0])
                method_text = _node_text(children[-1])
                return CallSite(
                    caller_file=file_path,
                    caller_function=current_function,
                    callee_name=method_text,
                    callee_object=obj_text,
                    line=line,
                    raw_text=raw_text,
                )
            if len(children) == 1:
                return CallSite(
                    caller_file=file_path,
                    caller_function=current_function,
                    callee_name=_node_text(children[0]),
                    callee_object=None,
                    line=line,
                    raw_text=raw_text,
                )

        # For other complex expressions, try to get a name
        text = _node_text(func_node)
        if text:
            return CallSite(
                caller_file=file_path,
                caller_function=current_function,
                callee_name=text,
                callee_object=None,
                line=line,
                raw_text=raw_text,
            )

        return None

    def find_callers(self, symbol_name: str, depth: int = 1) -> list[CallSite]:
        """Find call sites that call symbol_name, up to depth levels transitively."""
        result: list[CallSite] = []
        visited_callers: set[str] = set()
        current_targets: set[str] = {symbol_name}
        for _ in range(depth):
            next_targets: set[str] = set()
            for sites in self._call_sites.values():
                for site in sites:
                    if (
                        site.callee_name in current_targets
                        and site.caller_function not in visited_callers
                    ):
                        result.append(site)
                        if site.caller_function:
                            visited_callers.add(site.caller_function)
                            next_targets.add(site.caller_function)
            current_targets = next_targets
            if not current_targets:
                break
        return result

    def find_callees(self, function_name: str, depth: int = 1) -> list[CallSite]:
        """Find call sites called by function_name, up to depth levels transitively."""
        result: list[CallSite] = []
        visited_callees: set[str] = set()
        current_callers: set[str] = {function_name}
        for _ in range(depth):
            next_callers: set[str] = set()
            for sites in self._call_sites.values():
                for site in sites:
                    if (
                        site.caller_function in current_callers
                        and site.callee_name not in visited_callees
                    ):
                        result.append(site)
                        visited_callees.add(site.callee_name)
                        next_callers.add(site.callee_name)
            current_callers = next_callers
            if not current_callers:
                break
        return result
