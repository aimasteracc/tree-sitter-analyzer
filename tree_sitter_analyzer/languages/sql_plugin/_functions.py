"""SQL element extraction mixin — functions."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter

from ...models import (
    Function,
    SQLElement,
    SQLFunction,
    SQLParameter,
)
from ...utils import log_debug
from ._base import _SQLExtractorBase


class FunctionsMixin(_SQLExtractorBase):

    def _extract_sql_functions(
        self, root_node: tree_sitter.Node, functions: list[Function]
    ) -> None:
        """
        Extract CREATE FUNCTION statements from SQL AST.

        Functions are properly parsed as create_function nodes, so we search
        for these nodes and extract the function name from object_reference > identifier.

        Args:
            root_node: Root node of the SQL AST
            functions: List to append extracted function Function elements to
        """
        for node in self._traverse_nodes(root_node):
            if node.type == "create_function":
                func_name = None
                # Only use the FIRST object_reference as the function name
                for child in node.children:
                    if child.type == "object_reference":
                        # Only process the first object_reference
                        for subchild in child.children:
                            if subchild.type == "identifier":
                                func_name = self._get_node_text(subchild).strip()
                                if func_name and self._is_valid_identifier(func_name):
                                    break
                                else:
                                    func_name = None
                        break  # Stop after first object_reference

                # Fallback: Parse from raw text if AST parsing failed or returned invalid name
                if not func_name:
                    raw_text = self._get_node_text(node)
                    import re

                    match = re.search(
                        r"CREATE\s+FUNCTION\s+(\w+)\s*\(", raw_text, re.IGNORECASE
                    )
                    if match:
                        potential_name = match.group(1).strip()
                        if self._is_valid_identifier(potential_name):
                            func_name = potential_name

                if func_name:
                    try:
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1
                        raw_text = self._get_node_text(node)
                        func = Function(
                            name=func_name,
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            language="sql",
                        )
                        functions.append(func)
                    except Exception as e:
                        log_debug(f"Failed to extract function: {e}")

    def _extract_sql_functions_enhanced(
        self, root_node: tree_sitter.Node, sql_elements: list[SQLElement]
    ) -> None:
        """Extract CREATE FUNCTION statements with enhanced metadata."""
        # Use regex-based approach to find all functions in the source code
        import re

        lines = self.source_code.split("\n")

        # Pattern to match CREATE FUNCTION statements - requires opening parenthesis
        function_pattern = re.compile(
            r"^\s*CREATE\s+FUNCTION\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
            re.IGNORECASE,
        )

        i = 0
        inside_function = False

        while i < len(lines):
            # Skip lines if we're inside a function body
            if inside_function:
                if lines[i].strip().upper() in ["END;", "END$"] or lines[
                    i
                ].strip().upper().startswith("END;"):
                    inside_function = False
                i += 1
                continue

            # Only check for CREATE FUNCTION when not inside a function
            match = function_pattern.match(lines[i])
            if match:
                func_name = match.group(1)

                # Validate the function name using the centralized validation method
                if not self._is_valid_identifier(func_name):
                    i += 1
                    continue

                start_line = i + 1
                inside_function = True

                # Find the end of the function (look for END; or END$$)
                end_line = start_line
                nesting_level = 0

                for j in range(i + 1, len(lines)):
                    line_stripped = lines[j].strip().upper()

                    # Skip comments to avoid false positives
                    if line_stripped.startswith("--") or line_stripped.startswith("#"):
                        continue

                    # Handle nesting of BEGIN ... END blocks
                    # This is a heuristic: if we see BEGIN, we expect a matching END;
                    # We use word boundaries to avoid matching BEGIN in other contexts if possible
                    if re.search(r"\bBEGIN\b", line_stripped):
                        nesting_level += 1

                    is_end = False
                    if line_stripped in ["END;", "END$", "END"]:
                        is_end = True
                    elif line_stripped.startswith("END;"):
                        is_end = True

                    if is_end:
                        if nesting_level > 0:
                            nesting_level -= 1

                        if nesting_level == 0:
                            end_line = j + 1
                            inside_function = False
                            break

                # Extract the full function text
                func_lines = lines[i:end_line]
                raw_text = "\n".join(func_lines)


                parameters: list[SQLParameter] = []
                dependencies: list[str] = []
                return_type = None

                # Extract parameters, return type and dependencies from the text
                self._extract_procedure_parameters(raw_text, parameters)

                # Extract return type
                returns_match = re.search(
                    r"RETURNS\s+([A-Z]+(?:\([^)]*\))?)", raw_text, re.IGNORECASE
                )
                if returns_match:
                    return_type = returns_match.group(1)

                try:
                    function = SQLFunction(
                        name=func_name,
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=raw_text,
                        language="sql",
                        parameters=parameters,
                        dependencies=dependencies,
                        return_type=return_type,
                    )
                    sql_elements.append(function)
                    log_debug(
                        f"Extracted function: {func_name} at lines {start_line}-{end_line}"
                    )
                except Exception as e:
                    log_debug(f"Failed to extract enhanced function: {e}")

                i = end_line
            else:
                i += 1

        # Also try the original tree-sitter approach as fallback
        for node in self._traverse_nodes(root_node):
            if node.type == "create_function":
                func_name = None
                return_type = None

                # Extract function name - only from the FIRST object_reference child
                # This should be the function name, not references within the function body
                found_first_object_ref = False
                for child in node.children:
                    if child.type == "object_reference" and not found_first_object_ref:
                        found_first_object_ref = True
                        for subchild in child.children:
                            if subchild.type == "identifier":
                                func_name = self._get_node_text(subchild).strip()
                                # Validate function name using centralized validation
                                if func_name and self._is_valid_identifier(func_name):
                                    break
                                else:
                                    func_name = None
                        if func_name:
                            break

                if func_name:
                    # Check if this function was already extracted by regex
                    already_extracted = any(
                        hasattr(elem, "name") and elem.name == func_name
                        for elem in sql_elements
                        if hasattr(elem, "sql_element_type")
                        and elem.sql_element_type.value == "function"
                    )

                    if not already_extracted:
                        # Extract return type and other metadata
                        self._extract_function_metadata(
                            node, parameters, return_type, dependencies
                        )

                        try:
                            start_line = node.start_point[0] + 1
                            end_line = node.end_point[0] + 1
                            raw_text = self._get_node_text(node)

                            function = SQLFunction(
                                name=func_name,
                                start_line=start_line,
                                end_line=end_line,
                                raw_text=raw_text,
                                language="sql",
                                parameters=parameters,
                                dependencies=dependencies,
                                return_type=return_type,
                            )
                            sql_elements.append(function)
                        except Exception as e:
                            log_debug(f"Failed to extract enhanced function: {e}")

    def _extract_function_metadata(
        self,
        func_node: tree_sitter.Node,
        parameters: list[SQLParameter],
        return_type: str | None,
        dependencies: list[str],
    ) -> None:
        """Extract function metadata including parameters and return type."""
        func_text = self._get_node_text(func_node)

        # Extract return type
        import re

        returns_match = re.search(
            r"RETURNS\s+([A-Z]+(?:\([^)]*\))?)", func_text, re.IGNORECASE
        )
        if returns_match:
            _return_type = returns_match.group(1)  # Reserved for future use

        # Extract parameters (similar to procedure parameters)
        self._extract_procedure_parameters(func_text, parameters)

        # Extract dependencies
        self._extract_procedure_dependencies(func_node, dependencies)
