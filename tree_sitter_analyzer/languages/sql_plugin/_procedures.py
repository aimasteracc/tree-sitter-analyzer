"""SQL element extraction mixin — procedures."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter

from ...models import (
    Function,
    SQLElement,
    SQLParameter,
    SQLProcedure,
)
from ...utils import log_debug
from ._base import _SQLExtractorBase


class ProceduresMixin(_SQLExtractorBase):

    def _extract_procedures(
        self, root_node: tree_sitter.Node, functions: list[Function]
    ) -> None:
        """
        Extract CREATE PROCEDURE statements from SQL AST.

        Since tree-sitter-sql doesn't fully support PROCEDURE syntax, these
        appear as ERROR nodes. The PROCEDURE keyword is not tokenized, so we
        need to check the raw text content of ERROR nodes that contain
        keyword_create and look for "PROCEDURE" in the text.

        Args:
            root_node: Root node of the SQL AST
            functions: List to append extracted procedure Function elements to
        """
        for node in self._traverse_nodes(root_node):
            if node.type == "ERROR":
                # Check if this ERROR node contains CREATE and PROCEDURE in text
                has_create = False
                node_text = self._get_node_text(node)
                node_text_upper = node_text.upper()

                # Look for keyword_create child
                for child in node.children:
                    if child.type == "keyword_create":
                        has_create = True
                        break

                # Check if the text contains PROCEDURE
                if has_create and "PROCEDURE" in node_text_upper:
                    # Extract procedure name from the text (preserve original case)
                    # Use finditer to find ALL procedures in the ERROR node
                    import re

                    matches = re.finditer(
                        r"CREATE\s+PROCEDURE\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                        node_text,
                        re.IGNORECASE,
                    )

                    for match in matches:
                        proc_name = match.group(1)

                        if proc_name:
                            try:
                                # Calculate start line based on match position
                                newlines_before = node_text[: match.start()].count("\n")
                                start_line = node.start_point[0] + 1 + newlines_before
                                end_line = node.end_point[0] + 1

                                # Use specific text for this procedure if possible,
                                # but for legacy extraction we often just use the whole node text
                                # or we could slice it. For now, keeping whole node text is safer for legacy
                                raw_text = self._get_node_text(node)

                                func = Function(
                                    name=proc_name,
                                    start_line=start_line,
                                    end_line=end_line,
                                    raw_text=raw_text,
                                    language="sql",
                                )
                                functions.append(func)
                            except Exception as e:
                                log_debug(f"Failed to extract procedure: {e}")

    def _extract_sql_procedures(
        self, root_node: tree_sitter.Node, sql_elements: list[SQLElement]
    ) -> None:
        """Extract CREATE PROCEDURE statements with enhanced metadata."""
        # Use regex-based approach to find all procedures in the source code
        import re

        lines = self.source_code.split("\n")

        # Pattern to match CREATE PROCEDURE statements
        procedure_pattern = re.compile(
            r"^\s*CREATE\s+PROCEDURE\s+([a-zA-Z_][a-zA-Z0-9_]*)",
            re.IGNORECASE | re.MULTILINE,
        )

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.upper().startswith("CREATE") and "PROCEDURE" in line.upper():
                match = procedure_pattern.match(lines[i])
                if match:
                    proc_name = match.group(1)
                    start_line = i + 1

                    # Find the end of the procedure (look for END; or END$$)
                    end_line = start_line
                    for j in range(i + 1, len(lines)):
                        if lines[j].strip().upper() in ["END;", "END$$", "END"]:
                            end_line = j + 1
                            break
                        elif lines[j].strip().upper().startswith("END;"):
                            end_line = j + 1
                            break

                    # Extract the full procedure text
                    proc_lines = lines[i:end_line]
                    raw_text = "\n".join(proc_lines)


                    proc_parameters: list[SQLParameter] = []
                    proc_dependencies: list[str] = []

                    # Extract parameters and dependencies from the text
                    self._extract_procedure_parameters(raw_text, proc_parameters)

                    try:
                        procedure = SQLProcedure(
                            name=proc_name,
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            language="sql",
                            parameters=proc_parameters,
                            dependencies=proc_dependencies,
                        )
                        sql_elements.append(procedure)
                        log_debug(
                            f"Extracted procedure: {proc_name} at lines {start_line}-{end_line}"
                        )
                    except Exception as e:
                        log_debug(f"Failed to extract enhanced procedure: {e}")

                    i = end_line
                else:
                    i += 1
            else:
                i += 1

        # Also try the original tree-sitter approach as fallback
        for node in self._traverse_nodes(root_node):
            if node.type == "ERROR":
                has_create = False
                node_text = self._get_node_text(node)
                node_text_upper = node_text.upper()

                for child in node.children:
                    if child.type == "keyword_create":
                        has_create = True
                        break

                if has_create and "PROCEDURE" in node_text_upper:
                    # Extract procedure name
                    # Use finditer to find ALL procedures in the ERROR node
                    matches = re.finditer(
                        r"CREATE\s+PROCEDURE\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                        node_text,
                        re.IGNORECASE,
                    )

                    for match in matches:
                        proc_name = match.group(1)

                        # Check if this procedure was already extracted by regex
                        already_extracted = any(
                            hasattr(elem, "name") and elem.name == proc_name
                            for elem in sql_elements
                            if hasattr(elem, "sql_element_type")
                            and elem.sql_element_type.value == "procedure"
                        )

                        if not already_extracted:
                            # Extract parameters
                            # Note: This extracts parameters from the WHOLE node text, which might be wrong
                            # if there are multiple procedures. Ideally we should slice the text.
                            # But _extract_procedure_parameters parses the whole text.
                            # For now, we use the text starting from the match.
                            current_proc_text = node_text[match.start() :]

                            # Reset parameters and dependencies for each procedure
                            iteration_parameters: list[SQLParameter] = []
                            iteration_dependencies: list[str] = []

                            self._extract_procedure_parameters(
                                current_proc_text, iteration_parameters
                            )

                            # Extract dependencies (table references)
                            # This still uses the whole node for dependencies, which is hard to fix without
                            # proper parsing, but acceptable for fallback.
                            self._extract_procedure_dependencies(
                                node, iteration_dependencies
                            )

                            try:
                                # Calculate start line
                                newlines_before = node_text[: match.start()].count("\n")
                                start_line = node.start_point[0] + 1 + newlines_before
                                end_line = node.end_point[0] + 1

                                # Use current_proc_text as raw_text
                                raw_text = current_proc_text

                                procedure = SQLProcedure(
                                    name=proc_name,
                                    start_line=start_line,
                                    end_line=end_line,
                                    raw_text=raw_text,
                                    language="sql",
                                    parameters=iteration_parameters,
                                    dependencies=iteration_dependencies,
                                )
                                sql_elements.append(procedure)
                            except Exception as e:
                                log_debug(f"Failed to extract enhanced procedure: {e}")

    def _extract_procedure_parameters(
        self, proc_text: str, parameters: list[SQLParameter]
    ) -> None:
        """Extract parameters from procedure definition."""
        import re

        # First, extract the parameter section from the procedure/function definition
        # Look for the parameter list in parentheses after the procedure/function name
        param_section_match = re.search(
            r"(?:PROCEDURE|FUNCTION)\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\(([^)]*)\)",
            proc_text,
            re.IGNORECASE | re.DOTALL,
        )

        if not param_section_match:
            return

        param_section = param_section_match.group(1).strip()
        if not param_section:
            return

        # Look for parameter patterns like: IN param_name TYPE
        # Only search within the parameter section to avoid SQL statement content
        # Ensure IN/OUT/INOUT is followed by space to avoid ambiguity
        param_matches = re.findall(
            r"(?:(?:IN|OUT|INOUT)\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s+([A-Z]+(?:\([^)]*\))?)",
            param_section,
            re.IGNORECASE,
        )
        for match in param_matches:
            param_name = match[0]
            data_type = match[1]

            # Skip common SQL keywords and column names that might be incorrectly matched
            if param_name.upper() in (
                "SELECT",
                "FROM",
                "WHERE",
                "INTO",
                "VALUES",
                "SET",
                "UPDATE",
                "INSERT",
                "DELETE",
                "CREATED_AT",
                "UPDATED_AT",
                "ID",
                "NAME",
                "EMAIL",
                "STATUS",
                "IN",
                "OUT",
                "INOUT",
            ):
                continue

            # Determine direction from the original text
            direction = "IN"  # Default
            if f"OUT {param_name}" in param_section:
                direction = "OUT"
            elif f"INOUT {param_name}" in param_section:
                direction = "INOUT"

            parameter = SQLParameter(
                name=param_name,
                data_type=data_type,
                direction=direction,
            )
            parameters.append(parameter)

    def _extract_procedure_dependencies(
        self, proc_node: tree_sitter.Node, dependencies: list[str]
    ) -> None:
        """Extract table dependencies from procedure body."""
        for node in self._traverse_nodes(proc_node):
            if node.type == "object_reference":
                for child in node.children:
                    if child.type == "identifier":
                        table_name = self._get_node_text(child).strip()
                        if table_name and table_name not in dependencies:
                            # Simple heuristic: if it's referenced in FROM, UPDATE, INSERT, etc.
                            dependencies.append(table_name)
