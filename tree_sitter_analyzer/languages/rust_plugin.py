#!/usr/bin/env python3
"""
Rust Language Plugin

Provides Rust-specific parsing and element extraction functionality.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

    from ..core.analysis_engine import AnalysisRequest
    from ..models import AnalysisResult

from ..encoding_utils import extract_text_slice, safe_encode
from ..models import Class, Function, Import, Package, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error
from ..utils.tree_sitter_compat import count_nodes_iterative
from .shared.complexity import CyclomaticCounter
from .shared.traversal import collect_named_nodes, node_range

# AST node types that each add one decision point to cyclomatic complexity.
# Loop/branch constructs count once (matching the Swift/Go plugin convention),
# and the "&&"/"||" leaf tokens count the short-circuit boolean operators.
_RUST_DECISION_NODE_TYPES: frozenset[str] = frozenset(
    {
        "if_expression",
        "for_expression",
        "while_expression",
        "loop_expression",
        "match_expression",
        "&&",
        "||",
    }
)

_rust_complexity_counter = CyclomaticCounter(_RUST_DECISION_NODE_TYPES)


def _rust_calculate_complexity(node: Any) -> int:
    """Return cyclomatic complexity (1 + decision points) for a Rust fn node."""
    return _rust_complexity_counter.count(node).cyclomatic


def _rust_function_is_async(node: tree_sitter.Node) -> bool:
    """Return ``True`` when ``node`` carries an ``async`` modifier.

    r37bz (dogfood): extracted from ``_extract_function`` to flatten its
    nesting (was 7-deep nested for-if-for-if-break loop). Handles both
    the modern ``function_modifiers`` wrapper node and older
    tree-sitter-rust versions that exposed ``async`` as a direct child.
    """
    for child in node.children:
        if child.type == "function_modifiers":
            for modifier in child.children:
                if modifier.type == "async":
                    return True
        elif child.type == "async":
            return True
    return False


class RustElementExtractor(ElementExtractor):
    """Rust-specific element extractor"""

    def __init__(self) -> None:
        """Initialize the Rust element extractor."""
        self.current_module: str = ""
        self.current_file: str = ""
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self._node_text_cache: dict[tuple[int, int], str] = {}
        self._content_bytes: bytes | None = None
        self.impl_blocks: list[dict[str, Any]] = []
        self.modules: list[dict[str, Any]] = []

    def extract_functions(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Function]:
        """Extract Rust function declarations"""
        self._setup(source_code)
        functions: list[Function] = []
        _fn_extractors = {
            "function_item": self._extract_function,
            "function_signature_item": self._extract_function_signature,
        }
        for node in collect_named_nodes(tree.root_node, "function_item", "function_signature_item"):
            fn = _fn_extractors[node.type](node)
            if fn is not None:
                functions.append(fn)
        log_debug(f"Extracted {len(functions)} Rust functions")
        return functions

    def _setup(self, source_code: str) -> None:
        """Set source code and reset caches."""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

    def extract_classes(self, tree: tree_sitter.Tree, source_code: str) -> list[Class]:
        """Extract Rust struct, enum, trait, and impl definitions"""
        self._setup(source_code)
        self._extract_modules(tree.root_node)
        classes: list[Class] = []
        _class_extractors = {
            "struct_item": self._extract_struct,
            "enum_item": self._extract_enum,
            "trait_item": self._extract_trait,
            "impl_item": self._extract_impl,
        }
        for node in collect_named_nodes(
            tree.root_node, "struct_item", "enum_item", "trait_item", "impl_item"
        ):
            result = _class_extractors[node.type](node)
            if result is not None:
                classes.append(result)
        log_debug(f"Extracted {len(classes)} Rust structs/enums/traits")
        return classes

    def extract_variables(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Variable]:
        """Extract Rust struct fields and enum variants.

        Two separate passes to avoid struct-like enum variant bodies (#796/#960):
        Pass 1 collects field_declaration (struct fields, skipping enum_item subtrees).
        Pass 2 collects enum variants directly without recursing into variant bodies.
        """
        self._setup(source_code)
        variables: list[Variable] = []
        self._collect_struct_fields(tree.root_node, variables)
        self._collect_enum_variants(tree.root_node, variables)
        log_debug(f"Extracted {len(variables)} Rust fields/variants")
        return variables

    def _collect_enum_variants(
        self, node: tree_sitter.Node, results: list[Variable]
    ) -> None:
        """Recurse into non-enum children; extract variants from enum_item directly."""
        if node.type == "enum_item":
            variants = self._extract_enum_variants(node)
            if variants:
                results.extend(variants)
            return  # Do not recurse: enum body fully handled above.
        for child in node.children:
            self._collect_enum_variants(child, results)

    def _collect_struct_fields(
        self, node: tree_sitter.Node, results: list[Variable]
    ) -> None:
        """Walk the AST for struct fields, skipping enum_item subtrees (#960)."""
        if node.type == "enum_item":
            return
        if node.type == "field_declaration":
            field = self._extract_field(node)
            if field is not None:
                results.append(field)
            return
        for child in node.children:
            self._collect_struct_fields(child, results)

    def extract_imports(self, tree: tree_sitter.Tree, source_code: str) -> list[Import]:
        """Extract Rust use declarations"""
        self._setup(source_code)
        imports: list[Import] = []
        for node in collect_named_nodes(tree.root_node, "use_declaration"):
            imp = self._extract_import(node)
            if imp is not None:
                imports.append(imp)
        log_debug(f"Extracted {len(imports)} Rust imports")
        return imports

    def extract_packages(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Package]:
        """Extract Rust ``mod`` blocks as Package containers (issue #589)."""
        self._setup(source_code)
        packages: list[Package] = []
        for node in collect_named_nodes(tree.root_node, "mod_item"):
            pkg = self._extract_mod_package(node)
            if pkg is not None:
                packages.append(pkg)
        log_debug(f"Extracted {len(packages)} Rust modules")
        return packages

    def _extract_mod_package(self, node: tree_sitter.Node) -> Package | None:
        """Build a Package element from a ``mod_item`` node."""
        try:
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return None
            start_line, end_line = node_range(node)
            return Package(
                name=self._get_node_text(name_node),
                start_line=start_line,
                end_line=end_line,
                raw_text=self._get_node_text(node),
                language="rust",
            )
        except Exception as e:
            log_error(f"Error extracting Rust mod as package: {e}")
            return None

    def _extract_import(self, node: tree_sitter.Node) -> Import | None:
        """Extract import statement (use declaration)"""
        try:
            raw_text = self._get_node_text(node)
            start_line, end_line = node_range(node)

            # Extract name (the path)
            # use std::collections::HashMap;
            # The actual path is within the node children.
            # Typically we can just use raw text or try to parse it.
            # For simplicity, we'll use raw text as the import statement.

            return Import(
                name=raw_text,  # Use full statement as name for now, or parse better
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="rust",
                import_statement=raw_text,
            )
        except Exception as e:
            log_error(f"Error extracting Rust import: {e}")
            return None

    def _reset_caches(self) -> None:
        """Reset performance caches"""
        self._node_text_cache.clear()
        self._content_bytes = None
        # Modules and impls persist across extraction calls within the same file analysis
        # but we clear them here if we assume sequential full extraction calls.
        # Ideally, we should call extract_modules separately or share state.
        # For simplicity in this architecture, we might re-extract or just check if empty.
        if not self.source_code:
            self.modules.clear()
            self.impl_blocks.clear()

    def _extract_modules(self, node: tree_sitter.Node) -> None:
        """Populate self.modules from mod_item nodes."""
        if node.type == "mod_item":
            self._extract_module(node)
        for child in node.children:
            self._extract_modules(child)

    def _extract_module(self, node: tree_sitter.Node) -> None:
        """Extract single module"""
        try:
            name_node = node.child_by_field_name("name")
            if name_node:
                name = self._get_node_text(name_node)
                visibility = self._extract_visibility(node)
                start_line, end_line = node_range(node)

                self.modules.append(
                    {
                        "name": name,
                        "visibility": visibility,
                        "line_range": {
                            "start": start_line,
                            "end": end_line,
                        },
                    }
                )
        except Exception as e:
            log_error(f"Error extracting module: {e}")

    def _build_function_core(
        self, node: tree_sitter.Node
    ) -> Function | None:
        """Build a Function from a ``function_item`` or ``function_signature_item``.

        Shared logic for both node types: name, line range, parameters,
        return type, visibility, docstring, raw text.  Callers attach
        type-specific attributes (is_async, is_abstract, receiver_type …).
        """
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._get_node_text(name_node)
        start_line, end_line = node_range(node)
        parameters = self._extract_rust_parameters(
            node.child_by_field_name("parameters")
        )
        return_type = "()"
        ret_node = node.child_by_field_name("return_type")
        if ret_node:
            return_type = self._get_node_text(ret_node)
            if return_type.startswith("->"):
                return_type = return_type[2:].strip()
        return Function(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=self._get_node_text(node),
            language="rust",
            parameters=parameters,
            return_type=return_type,
            visibility=self._extract_visibility(node),
            docstring=self._extract_docstring(node),
            complexity_score=_rust_calculate_complexity(node),
        )

    def _extract_function(self, node: tree_sitter.Node) -> Function | None:
        """Extract function_item (implemented function)."""
        try:
            func = self._build_function_core(node)
            if func is None:
                return None
            func.is_async = _rust_function_is_async(node)
            # Theme-A (2026-06-10): impl-block ownership.
            owner = self._find_impl_owner(node)
            if owner:
                func.receiver_type = owner
                self_param = self._find_self_parameter(node)
                if self_param:
                    func.receiver = self_param
                    func.is_method = True
            return func
        except Exception as e:
            log_error(f"Error extracting Rust function: {e}")
            return None

    def _inside_trait(self, node: tree_sitter.Node) -> bool:
        """True when *node* sits inside a ``trait_item`` body.

        Depth-capped (MagicMock OOM guard, 2026-06-10). ``impl_item`` /
        ``foreign_mod_item`` terminate the walk early.
        """
        parent = node.parent
        for _ in range(256):
            if parent is None:
                return False
            if parent.type == "trait_item":
                return True
            if parent.type in ("impl_item", "foreign_mod_item"):
                return False
            parent = parent.parent
        return False

    def _find_impl_owner(self, node: tree_sitter.Node) -> str | None:
        """Return the impl target type name for a fn nested in an impl block.

        Depth-capped (MagicMock OOM guard, 2026-06-10).
        """
        parent = node.parent
        for _ in range(256):
            if parent is None:
                return None
            if parent.type == "impl_item":
                type_node = parent.child_by_field_name("type")
                return self._get_node_text(type_node) if type_node else None
            if parent.type == "source_file":
                return None
            parent = parent.parent
        return None

    def _find_self_parameter(self, node: tree_sitter.Node) -> str | None:
        """Return the self-parameter text (``&self`` / ``&mut self`` / ...)."""
        params = node.child_by_field_name("parameters")
        if params is None:
            return None
        for child in params.children:
            if child.type == "self_parameter":
                return self._get_node_text(child)
            if child.type == "parameter":
                pattern = child.child_by_field_name("pattern")
                if pattern is not None and self._get_node_text(pattern) == "self":
                    return self._get_node_text(child)
        return None

    def _extract_function_signature(self, node: tree_sitter.Node) -> Function | None:
        """Extract a trait abstract method (``function_signature_item``).

        Only nodes inside a ``trait_item`` are extracted (Codex P2 on #583).
        """
        try:
            if not self._inside_trait(node):
                return None
            func = self._build_function_core(node)
            if func is None:
                return None
            func.is_abstract = True
            return func
        except Exception as e:
            log_error(f"Error extracting Rust abstract function: {e}")
            return None

    def _extract_struct(self, node: tree_sitter.Node) -> Class | None:
        """Extract struct information"""
        return self._extract_type_def(node, "struct")

    def _extract_enum(self, node: tree_sitter.Node) -> Class | None:
        """Extract enum information"""
        return self._extract_type_def(node, "enum")

    def _extract_trait(self, node: tree_sitter.Node) -> Class | None:
        """Extract trait information"""
        return self._extract_type_def(node, "trait")

    def _extract_type_def(self, node: tree_sitter.Node, type_name: str) -> Class | None:
        """Generic type definition extractor"""
        try:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text(name_node)
            start_line, end_line = node_range(node)
            visibility = self._extract_visibility(node)

            raw_text = self._get_node_text(node)

            cls = Class(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="rust",
                class_type=type_name,
                visibility=visibility,
            )

            # Extract implemented traits (for structs/enums) or supertraits (for traits)
            # This is complex in Rust as impls are separate.
            # We can scan for derive macros here.
            derives = self._extract_derives(node)
            if derives:
                # Add derives to implemented interfaces list for display
                cls.implements_interfaces = derives

            return cls

        except Exception as e:
            log_error(f"Error extracting Rust {type_name}: {e}")
            return None

    def _extract_impl(self, node: tree_sitter.Node) -> None:
        """Extract impl block information"""
        try:
            trait_node = node.child_by_field_name("trait")
            type_node = node.child_by_field_name("type")

            trait_name = self._get_node_text(trait_node) if trait_node else None
            type_name = self._get_node_text(type_node) if type_node else None

            if type_name:
                start_line, end_line = node_range(node)
                self.impl_blocks.append(
                    {
                        "type": type_name,
                        "trait": trait_name,
                        "line_range": {
                            "start": start_line,
                            "end": end_line,
                        },
                    }
                )
        except Exception as e:
            log_error(f"Error extracting impl block: {e}")

    def _extract_field(self, node: tree_sitter.Node) -> Variable | None:
        """Extract struct field"""
        try:
            name_node = node.child_by_field_name("name")
            type_node = node.child_by_field_name("type")

            if not name_node or not type_node:
                return None

            name = self._get_node_text(name_node)
            field_type = self._get_node_text(type_node)
            start_line, end_line = node_range(node)
            visibility = self._extract_visibility(node)

            raw_text = self._get_node_text(node)
            docstring = self._extract_docstring(node)

            return Variable(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="rust",
                variable_type=field_type,
                visibility=visibility,
                docstring=docstring,
            )
        except Exception as e:
            log_error(f"Error extracting Rust field: {e}")
            return None

    def _extract_enum_variants(self, node: tree_sitter.Node) -> list[Variable] | None:
        """Extract each enum variant from an ``enum_item`` node as a Variable.

        Bug #796: enum variants were previously invisible. Returns a list so
        callers can extend results directly.
        """
        try:
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return None
            enum_name = self._get_node_text(name_node)
            enum_visibility = self._extract_visibility(node)

            # Walk children looking for the enum_variant_list node.
            variant_list = None
            for child in node.children:
                if child.type == "enum_variant_list":
                    variant_list = child
                    break
            if variant_list is None:
                return None

            variants: list[Variable] = []
            for child in variant_list.children:
                if child.type != "enum_variant":
                    continue
                variant_name_node = child.child_by_field_name("name")
                if variant_name_node is None:
                    continue
                variant_name = self._get_node_text(variant_name_node)
                start_line, end_line = node_range(child)
                raw_text = self._get_node_text(child)

                var = Variable(
                    name=variant_name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language="rust",
                    variable_type="enum_variant",
                    visibility=enum_visibility,
                    receiver_type=enum_name,
                )
                variants.append(var)
            return variants if variants else None
        except Exception as e:
            log_error(f"Error extracting Rust enum variants: {e}")
            return None

    def _extract_rust_parameters(
        self, params_node: tree_sitter.Node | None
    ) -> list[str]:
        """Return parameter texts from a Rust function ``parameters`` node.

        Returns empty list when ``params_node`` is ``None`` (the function
        takes no arguments). Handles two node types: ``parameter`` (named
        args, emitted as their raw text including the type) and
        ``self_parameter`` (``self`` / ``&self`` / ``&mut self``, emitted
        as the literal ``"self"`` to keep symbol search consistent).

        r37ds (dogfood): lifted out of ``_extract_function`` to flatten
        nesting 6 → 3.
        """
        if params_node is None:
            return []
        parameters: list[str] = []
        for child in params_node.children:
            if child.type == "parameter":
                parameters.append(self._get_node_text(child))
            elif child.type == "self_parameter":
                parameters.append("self")
        return parameters

    def _extract_visibility(self, node: tree_sitter.Node) -> str:
        """Extract visibility modifier"""
        for child in node.children:
            if child.type == "visibility_modifier":
                return self._get_node_text(child)
        return "private"  # Default in Rust

    def _extract_docstring(self, node: tree_sitter.Node) -> str | None:
        """Extract doc comments (/// or /** ... */)"""
        # In tree-sitter-rust, doc comments are often 'line_comment' or 'block_comment'
        # preceding the item, or attributes.
        # But often they are just comments attached to the node if we look at previous siblings
        # or they are part of the node as 'outer attributes' which are 'attribute_item'

        docs = []
        # Look for attribute items that are doc comments
        # This simple implementation might need refinement based on actual tree structure
        for child in node.children:
            if child.type == "line_comment" and self._get_node_text(child).startswith(
                "///"
            ):
                docs.append(self._get_node_text(child)[3:].strip())
            elif child.type == "block_comment" and self._get_node_text(
                child
            ).startswith("/**"):
                content = self._get_node_text(child)
                # Strip /** and */
                if content.startswith("/**") and content.endswith("*/"):
                    stripped = content[3:-2]
                    docs.append(stripped.strip())

        if docs:
            return "\n".join(docs)

        # Fallback: check source lines before start_line (similar to Java)
        start_line = node.start_point[0]
        if start_line > 0:
            # Check previous lines
            pass

        return None

    def _extract_derives(self, node: tree_sitter.Node) -> list[str]:
        """Extract derived traits from attributes.

        r37ds (dogfood): flattened nesting 6 → 3 via early-continue gates.
        """
        derives: list[str] = []
        for child in node.children:
            if child.type != "attribute_item":
                continue
            text = self._get_node_text(child)
            if "derive" not in text:
                continue
            # Naive parsing of #[derive(Debug, Clone)]
            match = re.search(r"derive\((.*?)\)", text)
            if match is None:
                continue
            traits = match.group(1).split(",")
            derives.extend([t.strip() for t in traits if t.strip()])
        return derives

    def _get_node_text(self, node: tree_sitter.Node) -> str:
        """Get node text with caching using position-based keys"""
        cache_key = (node.start_byte, node.end_byte)
        if cache_key in self._node_text_cache:
            return self._node_text_cache[cache_key]

        try:
            start_byte = node.start_byte
            end_byte = node.end_byte
            encoding = "utf-8"  # Default
            # Encode the source ONCE per extraction run. Re-encoding the
            # whole file on every cache miss is O(file_size) per node —
            # O(n^2) overall (the 37b39136 bug class; tripped the 5s
            # per-test budget when receiver extraction added new call sites).
            if self._content_bytes is None:
                self._content_bytes = safe_encode(
                    "\n".join(self.content_lines), encoding
                )
            text = extract_text_slice(
                self._content_bytes, start_byte, end_byte, encoding
            )
            self._node_text_cache[cache_key] = text
            return text
        except Exception:
            return ""


class RustPlugin(LanguagePlugin):
    """Rust language plugin implementation"""

    def __init__(self) -> None:
        """Initialize the Rust language plugin."""
        super().__init__()
        self.extractor = RustElementExtractor()
        self.language = "rust"
        self.supported_extensions = self.get_file_extensions()
        self._cached_language: Any | None = None

    def get_language_name(self) -> str:
        """Get the language name."""
        return "rust"

    def get_file_extensions(self) -> list[str]:
        """Get supported file extensions."""
        return [".rs"]

    def create_extractor(self) -> ElementExtractor:
        """Create a new element extractor instance."""
        return RustElementExtractor()

    def _make_parser(self, language: Any) -> Any:
        """Construct a tree_sitter.Parser bound to *language* across API shapes."""
        import tree_sitter

        parser = tree_sitter.Parser()
        if hasattr(parser, "set_language"):
            parser.set_language(language)
            return parser
        if hasattr(parser, "language"):
            parser.language = language
            return parser
        return tree_sitter.Parser(language)

    async def analyze_file(
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        """Analyze Rust code and return structured results."""
        from ..models import AnalysisResult

        try:
            from ..encoding_utils import read_file_safe

            file_content, _enc = read_file_safe(file_path)
            language = self.get_tree_sitter_language()
            if language is None:
                return AnalysisResult(
                    file_path=file_path,
                    language="rust",
                    line_count=len(file_content.splitlines()),
                    elements=[],
                    source_code=file_content,
                )

            tree = self._make_parser(language).parse(file_content.encode("utf-8"))
            extractor = self.create_extractor()
            all_elements: list[Any] = []
            all_elements.extend(extractor.extract_functions(tree, file_content))
            all_elements.extend(extractor.extract_classes(tree, file_content))
            all_elements.extend(extractor.extract_variables(tree, file_content))
            all_elements.extend(extractor.extract_imports(tree, file_content))
            all_elements.extend(extractor.extract_packages(tree, file_content))

            node_count = (
                count_nodes_iterative(tree.root_node) if tree and tree.root_node else 0
            )
            result = AnalysisResult(
                file_path=file_path,
                language="rust",
                line_count=len(file_content.splitlines()),
                elements=all_elements,
                node_count=node_count,
                source_code=file_content,
            )
            if isinstance(extractor, RustElementExtractor):
                result.modules = extractor.modules
                result.impls = extractor.impl_blocks
            return result

        except Exception as e:
            log_error(f"Error analyzing Rust file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language="rust",
                line_count=0,
                elements=[],
                source_code="",
                error_message=str(e),
                success=False,
            )

    def _count_tree_nodes(self, node: Any) -> int:
        """Count all nodes in the subtree. Delegates to count_nodes_iterative."""
        if node is None:
            return 0
        return count_nodes_iterative(node)

    def get_tree_sitter_language(self) -> Any | None:
        """Get the tree-sitter language for Rust."""
        if self._cached_language is not None:
            return self._cached_language

        try:
            import tree_sitter
            import tree_sitter_rust

            caps_or_lang = tree_sitter_rust.language()

            if hasattr(caps_or_lang, "__class__") and "Language" in str(
                type(caps_or_lang)
            ):
                self._cached_language = caps_or_lang
            else:
                try:
                    self._cached_language = tree_sitter.Language(caps_or_lang)
                except Exception as e:
                    log_error(f"Failed to create Language object: {e}")
                    return None

            return self._cached_language
        except ImportError as e:
            log_error(f"tree-sitter-rust not available: {e}")
            return None
        except Exception as e:
            log_error(f"Failed to load tree-sitter language for Rust: {e}")
            return None

    def extract_elements(self, tree: Any | None, source_code: str) -> dict[str, Any]:
        """Extract all elements."""
        if tree is None:
            return {"functions": [], "classes": [], "variables": []}
        try:
            extractor = self.create_extractor()
            return {
                "functions": extractor.extract_functions(tree, source_code),
                "classes": extractor.extract_classes(tree, source_code),
                "variables": extractor.extract_variables(tree, source_code),
                "imports": extractor.extract_imports(tree, source_code),
                "packages": extractor.extract_packages(tree, source_code),
            }
        except Exception as e:
            log_error(f"Error extracting elements: {e}")
            return {"functions": [], "classes": [], "variables": []}
