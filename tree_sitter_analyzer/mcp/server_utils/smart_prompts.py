"""SMART workflow prompt builders for AI agent self-discovery.

r37dx (dogfood): flatten dict-literal nesting depth 6 → 3 by lifting
the long instruction strings to module constants and the message-shape
boilerplate to ``_smart_user_message``. Tool callers see the same
JSON-RPC payload — the dict layout (``description`` + ``messages[].role``
+ ``content.type/text``) is preserved exactly.
"""

from typing import Any

_ANALYZE_INSTRUCTIONS_TEMPLATE = (
    "I want to analyze {file_path}. {question}\n\n"
    "Follow the SMART workflow:\n"
    "1. S - Call check_code_scale to understand file size and complexity\n"
    "2. M - Already done (file located)\n"
    "3. A - Call analyze_code_structure for a detailed table\n"
    "4. R - Call extract_code_section or query_code for specific parts\n"
    "   If you see a class/function name and want to find where it's defined "
    "or used elsewhere, call query_code(symbol='ClassName') for cross-file search\n"
    "5. T - Call analyze_dependencies mode=blast_radius to see impact\n"
    "   Call check_file_health to see if refactoring is needed\n\n"
    "Start with step 1 and follow the guidance in each response."
)

_EXPLORE_INSTRUCTIONS_TEMPLATE = (
    "I want to understand the project at {project_root}.\n\n"
    "Follow the SMART workflow:\n"
    "1. S - Call set_project_path with the project root\n"
    "2. M - Call get_project_overview to see language distribution, "
    "largest files, and directory structure\n"
    "3. A - Call check_code_scale on the most interesting files\n"
    "4. R - Call analyze_code_structure or query_code for detailed analysis\n"
    "   When you encounter a class/function name you want to trace, "
    "call query_code(symbol='TheName') to find all definitions across the project\n"
    "5. T - Call analyze_dependencies mode=summary to see the dependency graph\n\n"
    "Start with step 1 and follow the guidance in each response."
)


def _smart_user_message(text: str) -> dict[str, Any]:
    """Wrap ``text`` in the MCP ``messages[]`` user-text envelope."""
    return {
        "role": "user",
        "content": {"type": "text", "text": text},
    }


def build_smart_analyze_response(file_path: str, question: str) -> dict[str, Any]:
    """Build the SMART analyze prompt response for AI agents."""
    text = _ANALYZE_INSTRUCTIONS_TEMPLATE.format(file_path=file_path, question=question)
    return {
        "description": "SMART Workflow: Systematic code analysis",
        "messages": [_smart_user_message(text)],
    }


def build_smart_explore_response(project_root: str) -> dict[str, Any]:
    """Build the SMART explore prompt response for AI agents."""
    text = _EXPLORE_INSTRUCTIONS_TEMPLATE.format(project_root=project_root)
    return {
        "description": "SMART Workflow: Explore a new project",
        "messages": [_smart_user_message(text)],
    }
