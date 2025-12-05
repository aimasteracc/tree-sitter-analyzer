from typing import TYPE_CHECKING, Any

from ..encoding_utils import extract_text_slice, safe_encode
from ..models import Class, Function, Import, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_error

if TYPE_CHECKING:
    import tree_sitter


class CppElementExtractor(ElementExtractor):
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
        extractors = {
            "function_definition": self._extract_function,
            "function_declaration": self._extract_function,
        }
        self._traverse_and_extract(tree.root_node, extractors, results)
        return results

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._node_text_cache.clear()  # Clear cache for fresh extraction
        results: list[Class] = []
        extractors = {
            "class_specifier": lambda n: self._extract_type(n, "class"),
            "struct_specifier": lambda n: self._extract_type(n, "struct"),
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
        extractors = {
            "preproc_include": self._extract_include,
            "using_declaration": self._extract_using,
            "namespace_definition": self._extract_namespace_import,
        }
        self._traverse_and_extract(tree.root_node, extractors, results)
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
                log_error(f"cpp extractor error: {e}")
        for child in getattr(node, "children", []) or []:
            self._traverse_and_extract(child, extractors, results)

    def _get_node_text(self, node: "tree_sitter.Node") -> str:
        node_id = id(node)
        if node_id in self._node_text_cache:
            return self._node_text_cache[node_id]
        try:
            content_bytes = safe_encode("\n".join(self.content_lines), "utf-8")
            text = extract_text_slice(
                content_bytes, node.start_byte, node.end_byte, "utf-8"
            )
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
            # Include field_identifier for C++ method names inside classes
            if getattr(cur, "type", "") in (
                "identifier",
                "type_identifier",
                "field_identifier",
            ):
                return self._get_node_text(cur)
            for ch in getattr(cur, "children", []) or []:
                queue.append(ch)
        return None

    def _extract_function(self, node: "tree_sitter.Node") -> Function | None:
        try:
            name = None
            decl = (
                node.child_by_field_name("declarator")
                or node.child_by_field_name("declaration")
                or node.child_by_field_name("declarator")
            )
            if decl:
                name = self._find_identifier(decl)
            ret = None
            type_node = node.child_by_field_name("type")
            if type_node:
                ret = self._get_node_text(type_node).strip()
            params: list[str] = []
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
                language="cpp",
                parameters=params,
                return_type=ret or "",
            )
        except Exception as e:
            log_error(f"cpp function error: {e}")
            return None

    def _extract_type(self, node: "tree_sitter.Node", kind: str) -> Class | None:
        try:
            # Skip type specifiers that are part of variable declarations
            # Only extract top-level type definitions that have a body
            parent = getattr(node, "parent", None)
            if parent is not None and parent.type == "declaration":
                return None

            # Check if this is a type definition (has a body/field list)
            has_body = False
            for child in getattr(node, "children", []) or []:
                if child.type in ("field_declaration_list", "declaration_list"):
                    has_body = True
                    break

            if not has_body:
                return None

            name = self._find_identifier(node)
            raw = self._get_node_text(node)
            return Class(
                name=name or kind,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=raw,
                language="cpp",
                class_type=kind,
            )
        except Exception as e:
            log_error(f"cpp type error: {e}")
            return None

    def _extract_variable(self, node: "tree_sitter.Node") -> Variable | None:
        try:
            # Only extract top-level (global/namespace-level) variable declarations
            # Skip local variables inside function bodies and class members
            parent = getattr(node, "parent", None)
            if parent is not None and parent.type not in (
                "translation_unit",
                "namespace_definition",
                "declaration_list",
            ):
                return None

            type_text = None
            # In C++, look for type in children
            for child in getattr(node, "children", []) or []:
                if child.type in (
                    "primitive_type",
                    "type_identifier",
                    "qualified_identifier",
                    "template_type",
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
                language="cpp",
                variable_type=type_text or "",
            )
        except Exception as e:
            log_error(f"cpp var error: {e}")
            return None

    def _extract_include(self, node: "tree_sitter.Node") -> Import | None:
        try:
            raw = self._get_node_text(node)
            return Import(
                name=raw,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=raw,
                language="cpp",
                import_statement=raw,
            )
        except Exception as e:
            log_error(f"cpp include error: {e}")
            return None

    def _extract_using(self, node: "tree_sitter.Node") -> Import | None:
        try:
            raw = self._get_node_text(node)
            return Import(
                name=raw,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=raw,
                language="cpp",
                import_statement=raw,
            )
        except Exception:
            return None

    def _extract_namespace_import(self, node: "tree_sitter.Node") -> Import | None:
        """Extract namespace definition as an import-like element.

        Note: This only extracts the namespace declaration line, not its full body.
        """
        try:
            # Find namespace name
            name = None
            for child in getattr(node, "children", []) or []:
                if child.type == "identifier":
                    name = self._get_node_text(child)
                    break

            if not name:
                return None

            # Create a short representation (just the namespace declaration)
            import_stmt = f"namespace {name}"
            return Import(
                name=import_stmt,
                start_line=node.start_point[0] + 1,
                end_line=node.start_point[0] + 1,  # Only the namespace line
                raw_text=import_stmt,
                language="cpp",
                import_statement=import_stmt,
            )
        except Exception:
            return None


class CppPlugin(LanguagePlugin):
    def __init__(self) -> None:
        super().__init__()
        self._cached_language: Any | None = None

    def get_language_name(self) -> str:
        return "cpp"

    def get_file_extensions(self) -> list[str]:
        return [".cpp", ".cxx", ".cc", ".hpp", ".hxx", ".hh"]

    def create_extractor(self) -> ElementExtractor:
        return CppElementExtractor()

    async def analyze_file(self, file_path: str, request: Any) -> Any:
        from ..models import AnalysisResult, CodeElement

        try:
            from ..encoding_utils import read_file_safe

            content, _ = read_file_safe(file_path)
            language = self.get_tree_sitter_language()
            if language is None:
                return AnalysisResult(
                    file_path=file_path,
                    language="cpp",
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
                language="cpp",
                elements=elements,
                line_count=len(content.splitlines()),
                node_count=node_count,
                source_code=content,
            )
        except Exception as e:
            log_error(f"cpp analyze error: {e}")
            from ..models import AnalysisResult

            return AnalysisResult(
                file_path=file_path,
                language="cpp",
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
            import tree_sitter_cpp

            caps = tree_sitter_cpp.language()
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
            log_error(f"cpp language load error: {e}")
            return None
