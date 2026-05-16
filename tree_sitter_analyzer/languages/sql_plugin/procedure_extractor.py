"""Enhanced SQL procedure extraction — extracted from sql_plugin/extractor.py."""

import re
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

from ...models import SQLParameter, SQLProcedure
from ...utils import log_debug


# Extract elements from AST: extract_sql_procedures
# Section: imports and module configuration
# Section: main class definition
# Section: helper functions
# Section: data processing methods
# Section: output formatting methods
# Section: validation and error handling
def extract_sql_procedures(
    root_node: "tree_sitter.Node",
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
    source_code: str,
    sql_elements: list[Any],
) -> None:
    """Extract CREATE PROCEDURE statements with enhanced metadata."""
    lines = source_code.split("\n")

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

                end_line = start_line
                for j in range(i + 1, len(lines)):
                    if lines[j].strip().upper() in ["END;", "END$$", "END"]:
                        end_line = j + 1
                        break
                    elif lines[j].strip().upper().startswith("END;"):
                        end_line = j + 1
                        break

                proc_lines = lines[i:end_line]
                raw_text = "\n".join(proc_lines)

                proc_parameters: list[SQLParameter] = []
                proc_dependencies: list[str] = []

                extract_procedure_parameters(raw_text, proc_parameters)

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
    for node in traverse_nodes(root_node):
        if node.type == "ERROR":
            has_create = False
            node_text = get_node_text(node)
            node_text_upper = node_text.upper()

            for child in node.children:
                if child.type == "keyword_create":
                    has_create = True
                    break

            if has_create and "PROCEDURE" in node_text_upper:
                matches = re.finditer(
                    r"CREATE\s+PROCEDURE\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                    node_text,
                    re.IGNORECASE,
                )

                for match in matches:
                    proc_name = match.group(1)

                    already_extracted = any(
                        hasattr(elem, "name") and elem.name == proc_name
                        for elem in sql_elements
                        if hasattr(elem, "sql_element_type")
                        and elem.sql_element_type.value == "procedure"
                    )

                    if not already_extracted:
                        current_proc_text = node_text[match.start() :]

                        iteration_parameters: list[SQLParameter] = []
                        iteration_dependencies: list[str] = []

                        extract_procedure_parameters(
                            current_proc_text, iteration_parameters
                        )

                        _extract_procedure_dependencies(
                            node, iteration_dependencies, traverse_nodes, get_node_text
                        )

                        try:
                            newlines_before = node_text[: match.start()].count("\n")
                            start_line = node.start_point[0] + 1 + newlines_before
                            end_line = node.end_point[0] + 1

                            procedure = SQLProcedure(
                                name=proc_name,
                                start_line=start_line,
                                end_line=end_line,
                                raw_text=current_proc_text,
                                language="sql",
                                parameters=iteration_parameters,
                                dependencies=iteration_dependencies,
                            )
                            sql_elements.append(procedure)
                        except Exception as e:
                            log_debug(f"Failed to extract enhanced procedure: {e}")


# Extract elements from AST: extract_procedure_parameters
def extract_procedure_parameters(
    proc_text: str, parameters: list[SQLParameter]
) -> None:
    """Extract parameters from procedure/function definition."""
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

    param_matches = re.findall(
        r"(?:(?:IN|OUT|INOUT)\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s+([A-Z]+(?:\([^)]*\))?)",
        param_section,
        re.IGNORECASE,
    )
    for match in param_matches:
        param_name = match[0]
        data_type = match[1]

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

        direction = "IN"
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


# Extract elements from AST: _extract_procedure_dependencies
def _extract_procedure_dependencies(
    proc_node: "tree_sitter.Node",
    dependencies: list[str],
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
) -> None:
    """Extract table dependencies from procedure body."""
    for node in traverse_nodes(proc_node):
        if node.type == "object_reference":
            for child in node.children:
                if child.type == "identifier":
                    table_name = get_node_text(child).strip()
                    if table_name and table_name not in dependencies:
                        dependencies.append(table_name)


