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
from ..models import Class, Function, Import, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error


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
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        functions: list[Function] = []

        # Use tree traversal to find function_item (implemented) and
        # function_signature_item (abstract / trait-required method with no body).
        self._traverse_and_extract(
            tree.root_node,
            {
                "function_item": self._extract_function,
                "function_signature_item": self._extract_function_signature,
            },
            functions,
        )

        log_debug(f"Extracted {len(functions)} Rust functions")
        return functions

    def extract_classes(self, tree: tree_sitter.Tree, source_code: str) -> list[Class]:
        """Extract Rust struct, enum, trait, and impl definitions"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        # Extract modules first
        self._extract_modules(tree.root_node)

        classes: list[Class] = []

        extractors = {
            "struct_item": self._extract_struct,
            "enum_item": self._extract_enum,
            "trait_item": self._extract_trait,
            "impl_item": self._extract_impl,  # Impl blocks are treated as related to classes
        }

        self._traverse_and_extract(
            tree.root_node,
            extractors,
            classes,
        )

        # Process collected impl blocks and add them to classes list if they are standalone
        # Or we might want to return them as separate metadata.
        # For now, we'll include impl blocks as Class objects with type='impl' for visibility
        for _impl in self.impl_blocks:
            # Creating a Class object for impl block to represent it in the structure
            pass

        log_debug(f"Extracted {len(classes)} Rust structs/enums/traits")
        return classes

    def extract_variables(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Variable]:
        """Extract Rust struct fields"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        variables: list[Variable] = []

        # We extract fields from struct definitions
        extractors = {
            "field_declaration": self._extract_field,
        }

        self._traverse_and_extract(
            tree.root_node,
            extractors,
            variables,
        )

        log_debug(f"Extracted {len(variables)} Rust fields")
        return variables

    def extract_imports(self, tree: tree_sitter.Tree, source_code: str) -> list[Import]:
        """Extract Rust use declarations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        imports: list[Import] = []

        # We extract use declarations
        extractors = {
            "use_declaration": self._extract_import,
        }

        self._traverse_and_extract(
            tree.root_node,
            extractors,
            imports,
        )

        log_debug(f"Extracted {len(imports)} Rust imports")
        return imports

    def _extract_import(self, node: tree_sitter.Node) -> Import | None:
        """Extract import statement (use declaration)"""
        try:
            raw_text = self._get_node_text(node)
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

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

    def _traverse_and_extract(
        self,
        node: tree_sitter.Node,
        extractors: dict[str, Any],
        results: list[Any],
    ) -> None:
        """Recursive traversal to find and extract elements"""
        if node.type in extractors:
            element = extractors[node.type](node)
            if element:
                results.append(element)

        for child in node.children:
            self._traverse_and_extract(child, extractors, results)

    def _extract_modules(self, node: tree_sitter.Node) -> None:
        """Extract module information"""
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
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1

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

    def _extract_function(self, node: tree_sitter.Node) -> Function | None:
        """Extract function information"""
        try:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text(name_node)
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # r37ds (dogfood): extract parameters via helper.
            parameters = self._extract_rust_parameters(
                node.child_by_field_name("parameters")
            )

            # Return type
            return_type = "()"
            ret_node = node.child_by_field_name("return_type")
            if ret_node:
                return_type = self._get_node_text(ret_node)
                # Remove "->" prefix if captured
                if return_type.startswith("->"):
                    return_type = return_type[2:].strip()

            # Visibility
            visibility = self._extract_visibility(node)

            # Async detection via function_modifiers node or direct child.
            is_async = _rust_function_is_async(node)

            # Docstring
            docstring = self._extract_docstring(node)

            # Raw text
            raw_text = self._get_node_text(node)

            # Add to Function object
            # Note: We're using dynamic attributes for Rust-specific fields
            func = Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="rust",
                parameters=parameters,
                return_type=return_type,
                visibility=visibility,
                docstring=docstring,
            )
            # Attach Rust-specific attributes
            func.is_async = is_async

            # Theme-A (2026-06-10): impl-block ownership. Functions inside
            # ``impl Counter { ... }`` were flattened to top-level with no
            # receiver — an agent could not tell ``inc`` belongs to
            # ``Counter``. Any fn in an impl gets receiver_type = the impl
            # target; is_method/receiver only when a self_parameter exists
            # (self-less impl fns are associated functions, not methods).
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

        Depth-capped for the same reason as ``_find_impl_owner`` (MagicMock
        endless-parent-chain OOM, 2026-06-10). ``impl_item`` / ``foreign_mod_item``
        terminate the walk early: a signature inside them is not trait-required.
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

        Walks the parent chain (function_item → declaration_list →
        impl_item); the impl's ``type`` field is the implementing type for
        both inherent (``impl Counter``) and trait (``impl Greet for
        Counter``) impls.

        The walk is depth-capped: a real tree-sitter parent chain always
        terminates at source_file/None, but a non-conforming node object
        (e.g. a MagicMock in unit tests, whose .parent auto-generates an
        endless chain) must not send this into an unbounded
        memory-allocating loop (2026-06-10 140GB OOM incident).
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
        """Return the self-parameter text (``&self`` / ``&mut self`` / ...).

        Shorthand receivers parse as ``self_parameter``; verbose receivers
        (``self: Pin<&mut Self>`` / ``self: Box<Self>``) parse as a plain
        ``parameter`` whose ``pattern`` field is the bare ``self`` token.
        """
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

        These are required-method declarations inside a trait body that carry
        no default implementation — they end with ``;`` rather than a block.
        The ``function_item`` handler covers default-impl methods; this one
        covers the missing half (issue #538, Rust N2).

        ``extern`` blocks also emit ``function_signature_item`` for foreign
        function declarations — those are linked FFI APIs, not trait-required
        methods, so only nodes inside a ``trait_item`` are extracted here
        (Codex P2 on #583).
        """
        try:
            if not self._inside_trait(node):
                return None

            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text(name_node)
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            parameters = self._extract_rust_parameters(
                node.child_by_field_name("parameters")
            )
            return_type = "()"
            ret_node = node.child_by_field_name("return_type")
            if ret_node:
                return_type = self._get_node_text(ret_node)
                if return_type.startswith("->"):
                    return_type = return_type[2:].strip()

            visibility = self._extract_visibility(node)
            raw_text = self._get_node_text(node)

            func = Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="rust",
                parameters=parameters,
                return_type=return_type,
                visibility=visibility,
            )
            func.is_abstract = True

            owner = self._find_impl_owner(node)
            if owner:
                func.receiver_type = owner
                self_param = self._find_self_parameter(node)
                if self_param:
                    func.receiver = self_param
                    func.is_method = True

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
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
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
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
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
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
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

    async def analyze_file(
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        """Analyze Rust code and return structured results."""

        from ..models import AnalysisResult

        try:
            from ..encoding_utils import read_file_safe

            file_content, detected_encoding = read_file_safe(file_path)

            # Get tree-sitter language and parse
            language = self.get_tree_sitter_language()
            if language is None:
                return AnalysisResult(
                    file_path=file_path,
                    language="rust",
                    line_count=len(file_content.splitlines()),
                    elements=[],
                    source_code=file_content,
                )

            import tree_sitter

            parser = tree_sitter.Parser()

            # Set language
            if hasattr(parser, "set_language"):
                parser.set_language(language)
            elif hasattr(parser, "language"):
                parser.language = language
            else:
                parser = tree_sitter.Parser(language)

            tree = parser.parse(file_content.encode("utf-8"))

            # Extract elements
            extractor = self.create_extractor()
            all_elements: list[Any] = []
            all_elements.extend(extractor.extract_functions(tree, file_content))
            all_elements.extend(extractor.extract_classes(tree, file_content))
            all_elements.extend(extractor.extract_variables(tree, file_content))
            all_elements.extend(extractor.extract_imports(tree, file_content))

            node_count = (
                self._count_tree_nodes(tree.root_node) if tree and tree.root_node else 0
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
        """Recursively count nodes."""
        if node is None:
            return 0
        count = 1
        if hasattr(node, "children"):
            for child in node.children:
                count += self._count_tree_nodes(child)
        return count

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

            result = {
                "functions": extractor.extract_functions(tree, source_code),
                "classes": extractor.extract_classes(tree, source_code),
                "variables": extractor.extract_variables(tree, source_code),
                "imports": extractor.extract_imports(tree, source_code),
            }

            return result

        except Exception as e:
            log_error(f"Error extracting elements: {e}")
            return {"functions": [], "classes": [], "variables": []}
