from typing import TYPE_CHECKING, Any

from ..encoding_utils import extract_text_slice, safe_encode
from ..models import Class, Function, Import, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_error

if TYPE_CHECKING:
    import tree_sitter


class CElementExtractor(ElementExtractor):
    def __init__(self) -> None:
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self._node_text_cache: dict[int, str] = {}

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._node_text_cache.clear()  # Clear cache for fresh extraction
        results: list[Function] = []
        self._traverse_and_extract(
            tree.root_node, {"function_definition": self._extract_function}, results
        )
        return results

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._node_text_cache.clear()  # Clear cache for fresh extraction
        results: list[Class] = []
        extractors = {
            "struct_specifier": lambda n: self._extract_type(n, "struct"),
            "union_specifier": lambda n: self._extract_type(n, "union"),
            "enum_specifier": lambda n: self._extract_type(n, "enum"),
        }
        self._traverse_and_extract(tree.root_node, extractors, results)
        return results

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._node_text_cache.clear()  # Clear cache for fresh extraction
        results: list[Variable] = []
        self._traverse_and_extract(
            tree.root_node, {"declaration": self._extract_variable}, results
        )
        return results

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._node_text_cache.clear()  # Clear cache for fresh extraction
        results: list[Import] = []
        self._traverse_and_extract(
            tree.root_node, {"preproc_include": self._extract_include}, results
        )
        return results

    def _traverse_and_extract(
        self, node: Any, extractors: dict[str, Any], results: list[Any]
    ) -> None:
        if node is None:
            return
        if node.type in extractors:
            try:
                element = extractors[node.type](node)
                if element:
                    results.append(element)
            except Exception as e:
                log_error(f"c extractor error: {e}")
        for child in getattr(node, "children", []) or []:
            self._traverse_and_extract(child, extractors, results)

    def _get_node_text(self, node: "tree_sitter.Node") -> str:
        node_id = id(node)
        if node_id in self._node_text_cache:
            return self._node_text_cache[node_id]
        try:
            start_byte = node.start_byte
            end_byte = node.end_byte
            content_bytes = safe_encode("\n".join(self.content_lines), "utf-8")
            text = extract_text_slice(content_bytes, start_byte, end_byte, "utf-8")
            self._node_text_cache[node_id] = text
            return text
        except Exception:
            return ""

    def _find_identifier(self, node: "tree_sitter.Node") -> str | None:
        """Find the first identifier in a node using BFS (breadth-first search).

        This ensures we find the function/type name identifier before
        descending into parameter lists or other nested structures.
        """
        from collections import deque

        queue: deque[tree_sitter.Node] = deque([node])
        while queue:
            cur = queue.popleft()
            if getattr(cur, "type", "") in ("identifier", "type_identifier"):
                return self._get_node_text(cur)
            for ch in getattr(cur, "children", []) or []:
                queue.append(ch)
        return None

    def _extract_function(self, node: "tree_sitter.Node") -> Function | None:
        try:
            name = None
            decl = node.child_by_field_name("declarator")
            if decl:
                name = self._find_identifier(decl)
            ret = None
            specs = node.child_by_field_name("type") or node.child_by_field_name(
                "declaration_specifiers"
            )
            if specs:
                ret = self._get_node_text(specs).strip()
            params = []
            if decl:
                params_node = decl.child_by_field_name("parameters")
                if params_node:
                    params = [
                        self._get_node_text(c).strip()
                        for c in getattr(params_node, "children", []) or []
                        if self._get_node_text(c).strip()
                    ]
            raw = self._get_node_text(node)
            return Function(
                name=name or "",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=raw,
                language="c",
                parameters=params,
                return_type=ret or "",
            )
        except Exception as e:
            log_error(f"c function error: {e}")
            return None

    def _extract_type(self, node: "tree_sitter.Node", kind: str) -> Class | None:
        try:
            # Skip type specifiers that are part of variable declarations
            # (e.g., local variables like "struct Point p = {1, 2};")
            # Only extract top-level type definitions that have a body
            parent = getattr(node, "parent", None)
            if parent is not None and parent.type == "declaration":
                # This is a type used in a declaration, not a definition
                return None

            # Check if this is a type definition (has a body/field list)
            has_body = False
            for child in getattr(node, "children", []) or []:
                if child.type in ("field_declaration_list", "enumerator_list"):
                    has_body = True
                    break

            if not has_body:
                # This is just a type reference, not a definition
                return None

            name = self._find_identifier(node)
            raw = self._get_node_text(node)
            return Class(
                name=name or kind,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=raw,
                language="c",
                class_type=kind,
            )
        except Exception as e:
            log_error(f"c type error: {e}")
            return None

    def _extract_variable(self, node: "tree_sitter.Node") -> Variable | None:
        try:
            # Only extract top-level (global) variable declarations
            # Skip local variables inside function bodies
            parent = getattr(node, "parent", None)
            if parent is not None and parent.type != "translation_unit":
                return None

            type_text = None
            # In C, the type is a direct child, not a field
            for child in getattr(node, "children", []) or []:
                if child.type in (
                    "primitive_type",
                    "type_identifier",
                    "struct_specifier",
                    "union_specifier",
                    "enum_specifier",
                ):
                    type_text = self._get_node_text(child).strip()
                    break

            name = None
            init_list = [
                c
                for c in getattr(node, "children", []) or []
                if c.type == "init_declarator"
            ]
            if init_list:
                # Find the identifier directly in init_declarator children
                for child in getattr(init_list[0], "children", []) or []:
                    if child.type == "identifier":
                        name = self._get_node_text(child)
                        break

            if not name:
                return None

            raw = self._get_node_text(node)
            return Variable(
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=raw,
                language="c",
                variable_type=type_text or "",
            )
        except Exception as e:
            log_error(f"c var error: {e}")
            return None

    def _extract_include(self, node: "tree_sitter.Node") -> Import | None:
        try:
            raw = self._get_node_text(node)
            return Import(
                name=raw,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=raw,
                language="c",
                import_statement=raw,
            )
        except Exception as e:
            log_error(f"c include error: {e}")
            return None


class CPlugin(LanguagePlugin):
    def __init__(self) -> None:
        super().__init__()
        self._cached_language: Any | None = None

    def get_language_name(self) -> str:
        return "c"

    def get_file_extensions(self) -> list[str]:
        return [".c", ".h"]

    def create_extractor(self) -> ElementExtractor:
        return CElementExtractor()

    async def analyze_file(self, file_path: str, request: Any) -> Any:
        from ..models import AnalysisResult, CodeElement

        try:
            from ..encoding_utils import read_file_safe

            content, _ = read_file_safe(file_path)
            language = self.get_tree_sitter_language()
            if language is None:
                return AnalysisResult(
                    file_path=file_path,
                    language="c",
                    elements=[],
                    line_count=len(content.splitlines()),
                    node_count=0,
                    source_code=content,
                )
            import tree_sitter

            parser = tree_sitter.Parser()
            if hasattr(parser, "set_language"):
                parser.set_language(language)
            else:
                parser.language = language
            tree = parser.parse(content.encode("utf-8"))
            extractor = self.create_extractor()
            funcs = extractor.extract_functions(tree, content)
            classes = extractor.extract_classes(tree, content)
            vars_ = extractor.extract_variables(tree, content)
            imps = extractor.extract_imports(tree, content)
            from typing import cast

            elements = cast(list[CodeElement], funcs + classes + vars_ + imps)
            node_count = self._count_nodes(tree.root_node)
            return AnalysisResult(
                file_path=file_path,
                language="c",
                elements=elements,
                line_count=len(content.splitlines()),
                node_count=node_count,
                source_code=content,
            )
        except Exception as e:
            log_error(f"c analyze error: {e}")
            from ..models import AnalysisResult

            return AnalysisResult(
                file_path=file_path,
                language="c",
                elements=[],
                line_count=0,
                node_count=0,
                source_code="",
                success=False,
                error_message=str(e),
            )

    def _count_nodes(self, node: Any) -> int:
        if node is None:
            return 0
        count = 1
        for ch in getattr(node, "children", []) or []:
            count += self._count_nodes(ch)
        return count

    def get_tree_sitter_language(self) -> Any | None:
        if self._cached_language is not None:
            return self._cached_language
        try:
            import tree_sitter
            import tree_sitter_c

            caps = tree_sitter_c.language()
            try:
                self._cached_language = (
                    caps
                    if hasattr(caps, "__class__") and "Language" in str(type(caps))
                    else tree_sitter.Language(caps)
                )
            except Exception:
                self._cached_language = tree_sitter.Language(caps)
            return self._cached_language
        except Exception as e:
            log_error(f"c language load error: {e}")
            return None
