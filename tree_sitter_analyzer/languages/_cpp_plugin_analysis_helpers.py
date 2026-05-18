"""C++ plugin analysis helpers."""

from typing import Any

from ..models import AnalysisResult
from ..utils import log_error


def empty_cpp_analysis_result(file_path: str, file_content: str) -> AnalysisResult:
    return AnalysisResult(
        file_path=file_path,
        language="cpp",
        line_count=len(file_content.split("\n")),
        elements=[],
        source_code=file_content,
    )


def cpp_parser_failure_result(
    file_path: str,
    file_content: str,
    error: Exception,
) -> AnalysisResult:
    return AnalysisResult(
        file_path=file_path,
        language="cpp",
        line_count=len(file_content.split("\n")),
        elements=[],
        source_code=file_content,
        error_message=f"Parser creation failed: {error}",
        success=False,
    )


def create_cpp_parser(
    language: Any, file_path: str, file_content: str
) -> tuple[Any, None] | tuple[None, AnalysisResult]:
    import tree_sitter

    parser = tree_sitter.Parser()
    if hasattr(parser, "set_language"):
        parser.set_language(language)
        return parser, None
    if hasattr(parser, "language"):
        parser.language = language
        return parser, None

    try:
        return tree_sitter.Parser(language), None
    except Exception as exc:
        log_error(f"Failed to create parser with language: {exc}")
        return None, cpp_parser_failure_result(file_path, file_content, exc)


def load_cpp_tree_sitter_language() -> Any | None:
    try:
        import tree_sitter
        import tree_sitter_cpp

        return _coerce_cpp_language(tree_sitter_cpp.language(), tree_sitter.Language)
    except ImportError as exc:
        log_error(f"tree-sitter-cpp not available: {exc}")
        return None
    except Exception as exc:
        log_error(f"Failed to load tree-sitter language for C++: {exc}")
        return None


def _coerce_cpp_language(caps_or_lang: Any, language_factory: Any) -> Any | None:
    if hasattr(caps_or_lang, "__class__") and "Language" in str(type(caps_or_lang)):
        return caps_or_lang

    try:
        return language_factory(caps_or_lang)
    except Exception as exc:
        log_error(f"Failed to create Language object from PyCapsule: {exc}")
        return None


def build_cpp_analysis_result(
    file_path: str,
    file_content: str,
    elements_dict: dict[str, Any],
    node_count: int,
) -> AnalysisResult:
    return AnalysisResult(
        file_path=file_path,
        language="cpp",
        line_count=len(file_content.split("\n")),
        elements=flatten_cpp_elements(elements_dict),
        node_count=node_count,
        source_code=file_content,
    )


def flatten_cpp_elements(elements_dict: dict[str, Any]) -> list[Any]:
    all_elements = []
    for key in ("functions", "classes", "variables", "imports", "packages"):
        all_elements.extend(elements_dict.get(key, []))
    return all_elements


def cpp_analysis_error_result(file_path: str, error: Exception) -> AnalysisResult:
    return AnalysisResult(
        file_path=file_path,
        language="cpp",
        line_count=0,
        elements=[],
        source_code="",
        error_message=str(error),
        success=False,
    )
