"""Import, package, and miscellaneous extraction mixin for Python."""

from __future__ import annotations

import os
from typing import Any

from ...models import Import, Package, Variable
from ...utils import log_debug, log_warning
from ...utils.tree_sitter_compat import get_node_text_safe
from ._extractor_helpers import (
    ImportExtractionRuntime,
    extract_imports_from_tree,
    import_node_context,
    node_raw_text,
    parse_from_import_parts,
)


class PythonImportPackageMixin:
    def extract_imports(self, tree: Any, source_code: str) -> list[Import]:
        """Extract Python import statements."""
        imports: list[Import] = []
        import_query = """
        (import_statement) @import_stmt
        (import_from_statement) @from_import_stmt
        """

        imports.extend(
            extract_imports_from_tree(
                ImportExtractionRuntime(
                    tree=tree,
                    source_code=source_code,
                    import_query=import_query,
                    extract_import_info=self._extract_import_info,
                    extract_imports_manual=self._extract_imports_manual,
                    log_debug_fn=log_debug,
                    log_warning_fn=log_warning,
                )
            )
        )

        return imports

    def _extract_imports_manual(self, root_node: Any, source_code: str) -> list[Import]:
        """Manual import extraction for tree-sitter 0.25.x compatibility."""
        imports: list[Import] = []
        self._walk_import_nodes(root_node, source_code, imports)
        return imports

    def _walk_import_nodes(
        self, node: Any, source_code: str, imports: list[Import]
    ) -> None:
        """Recursively walk AST to extract import nodes."""
        if node.type in ("import_statement", "import_from_statement"):
            try:
                self._parse_import_node(node, source_code, imports)
            except Exception as exc:
                log_warning(f"Failed to extract import manually: {exc}")

        for child in node.children:
            self._walk_import_nodes(child, source_code, imports)

    def _parse_import_node(
        self, node: Any, source_code: str, imports: list[Import]
    ) -> None:
        """Parse a single import_statement or import_from_statement node."""
        context = import_node_context(node, source_code)

        if node.type == "import_statement":
            self._parse_simple_import(node, context, imports)
        elif node.type == "import_from_statement":
            self._parse_from_import(node, context, imports)

    def extract_packages(self, tree: Any, source_code: str) -> list:
        """Extract Python package information from file path."""
        packages: list[Package] = []

        if self.current_file:
            file_path = os.path.abspath(self.current_file)
            current_dir = os.path.dirname(file_path)
            package_parts: list[str] = []

            check_dir = current_dir
            while check_dir:
                init_file = os.path.join(check_dir, "__init__.py")

                if os.path.exists(init_file):
                    package_parts.insert(0, os.path.basename(check_dir))
                    parent_dir = os.path.dirname(check_dir)
                    if parent_dir == check_dir:
                        break
                    check_dir = parent_dir
                else:
                    break

            if package_parts:
                package_name = ".".join(package_parts)
                self.current_module = package_name

                package = Package(
                    name=package_name,
                    start_line=1,
                    end_line=1,
                    raw_text=f"# Package: {package_name}",
                    language="python",
                )
                packages.append(package)

        return packages

    def _extract_variable_info(
        self, node: Any, source_code: str, assignment_type: str
    ) -> Variable | None:
        """Extract detailed variable information from AST node."""
        try:
            if not self._validate_node(node):
                return None

            # Use ``node_raw_text``: bytes-aware (multibyte-safe) + clamps
            # end_byte to source length for legacy callers that pass nodes
            # whose offsets exceed the source.
            variable_text = node_raw_text(node, source_code)

            if "=" in variable_text:
                name_part = variable_text.split("=")[0].strip()
                if assignment_type == "multiple_assignment" and "," in name_part:
                    name = name_part.split(",")[0].strip()
                else:
                    name = name_part
            else:
                name = "variable"

            return Variable(
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=variable_text,
                language="python",
                variable_type=assignment_type,
            )

        except Exception as exc:
            log_warning(f"Could not extract variable info: {exc}")
            return None

    def _extract_import_info(
        self, node: Any, source_code: str, import_type: str
    ) -> Import | None:
        """Extract detailed import information from AST node.

        J6: ``from X import (A, B as b, C)`` previously collapsed the entire
        parenthesised block — newlines, alias keyword, trailing comments and
        all — into a single ``name`` field. We now walk the child nodes to
        recover the bound identifiers and emit a clean comma-joined name
        (with ``imported_names`` populated for downstream consumers).
        """
        try:
            if not self._validate_node(node):
                return None

            # Tree-sitter node offsets are byte positions; slicing the source
            # string directly corrupts results when the file contains multi-byte
            # characters (e.g. em-dash in a docstring shifts every downstream
            # offset). Use the byte-aware helper instead.
            import_text = get_node_text_safe(node, source_code) or source_code

            module_name = ""
            imported_names: list[str] = []
            import_name = ""

            if import_type == "from_import":
                # Walk child nodes — robust against multi-line parenthesised
                # imports, aliases, and trailing comments. Falls back to a
                # cleaned text-slice when the children are unavailable.
                module_name, imported_names = parse_from_import_parts(node, source_code)
                if imported_names:
                    import_name = ", ".join(imported_names)
                else:
                    import_name = _clean_import_name_fallback(import_text)
            elif import_type == "aliased_import":
                import_name = _clean_import_name_fallback(import_text)
            else:
                import_name = _clean_import_name_fallback(
                    import_text.replace("import", "", 1)
                )
                # ``import a, b, c`` — populate imported_names from a clean text.
                if import_name and "," in import_name:
                    imported_names = [
                        token.strip()
                        for token in import_name.split(",")
                        if token.strip()
                    ]
                elif import_name:
                    imported_names = [import_name]

            return Import(
                name=import_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=import_text,
                language="python",
                module_name=module_name,
                imported_names=imported_names,
            )

        except Exception as exc:
            log_warning(f"Could not extract import info: {exc}")
            return None


def _clean_import_name_fallback(text: str) -> str:
    """Strip parens, newlines, and trailing comments from an import literal.

    Used only when child-node walking is unavailable (e.g. degraded parser
    or unexpected node shape). Returns a single-line comma-joined string.
    """
    if not text:
        return ""
    cleaned = text.replace("\n", " ").replace("\r", " ")
    # Drop the surrounding parens but keep the content for callers that
    # still want a one-liner.
    cleaned = cleaned.replace("(", " ").replace(")", " ")
    # Drop trailing ``# ...`` comments on each comma-separated item.
    parts: list[str] = []
    for token in cleaned.split(","):
        tok = token.strip()
        if "#" in tok:
            tok = tok.split("#", 1)[0].strip()
        if tok:
            parts.append(tok)
    return ", ".join(parts)
