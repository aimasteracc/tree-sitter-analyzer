#!/usr/bin/env python3
"""Lua plugin with an RFC-0010 resolver slot.

Lua's plugin and resolver remain self-contained, while advertising it through
the legacy CLI/parser discovery surfaces also requires central registry entries:
  1. This plugin package (``languages/lua_plugin/``)
  2. A resolver in ``synapse_resolver/languages/lua.py`` (moat slot)
  3. An entry-point in ``pyproject.toml``
  4. An optional dep ``tree-sitter-lua``
  5. Loader/detector mappings until those legacy registries become dynamic

Capability methods default to ``frozenset()`` / ``None`` so the plugin uses the Phase 2
plugin-dispatch paths in the central files without any central
``if-language==`` branch for "lua".

When ``tree-sitter-lua`` is not installed, ``get_tree_sitter_language``
returns ``None`` and the plugin falls back to ``DefaultExtractor``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...core.analysis_engine import AnalysisRequest
    from ...models import AnalysisResult

from ...plugins.base import ElementExtractor, LanguagePlugin
from ...utils import log_error
from .extractor import LuaElementExtractor


class LuaPlugin(LanguagePlugin):
    """Lua plugin with partial function/import extraction."""

    def get_language_name(self) -> str:
        return "lua"

    def get_file_extensions(self) -> list[str]:
        return [".lua"]

    def create_extractor(self) -> ElementExtractor:
        return LuaElementExtractor()

    def get_tree_sitter_language(self) -> Any:
        try:
            import tree_sitter
            import tree_sitter_lua as tslua

            return tree_sitter.Language(tslua.language())
        except ImportError:
            return None
        except Exception as exc:
            log_error(f"Failed to load Lua tree-sitter language: {exc}")
            return None

    async def analyze_file(
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        from ...models import AnalysisResult

        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                source = f.read()

            language = self.get_tree_sitter_language()
            if language is None:
                return AnalysisResult(
                    file_path=file_path,
                    language="lua",
                    success=False,
                    error_message="tree-sitter-lua not available",
                )

            import tree_sitter

            parser = tree_sitter.Parser()
            parser.language = language
            tree = parser.parse(bytes(source, "utf-8"))

            extractor = self.create_extractor()
            extractor.current_file = file_path
            elements: list[Any] = []
            elements.extend(extractor.extract_functions(tree, source))
            elements.extend(extractor.extract_classes(tree, source))
            elements.extend(extractor.extract_variables(tree, source))
            elements.extend(extractor.extract_imports(tree, source))

            return AnalysisResult(
                file_path=file_path,
                language="lua",
                success=True,
                elements=elements,
                line_count=len(source.splitlines()),
            )
        except Exception as exc:
            log_error(f"Error analyzing Lua file {file_path}: {exc}")
            return AnalysisResult(
                file_path=file_path,
                language="lua",
                success=False,
                error_message=str(exc),
            )

    # Capability methods intentionally omitted to demo default behaviour:
    # scope_body_node_types() -> frozenset()  (no function-scope gate)
    # import_extractor() -> None  (no import extraction)
    # module_path_resolver() -> None  (no module path registration)
    # function_name_resolver() -> None  (no parent-class lookup)
