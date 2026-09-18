"""`search action=text` 的无索引实时文本检索实现。"""

from __future__ import annotations

import asyncio
from pathlib import Path, PurePosixPath
from typing import Any

from ...text_search import (
    TextSearchError,
    TextSearchRequest,
    search_text_bounded,
)
from .base_tool import BaseMCPTool

DEFAULT_TEXT_SEARCH_LIMIT = 100
MAX_TEXT_SEARCH_LIMIT = 1000


class TextSearchTool(BaseMCPTool):
    """通过认证项目边界执行完整的实时字面量检索。"""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "text_search",
            "description": (
                "Search live project files for an exact literal line match without an "
                "AST index. Returns deterministic source-linked rows and exact counts."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Literal text to find (1-4096 UTF-8 bytes)",
                },
                "root": {
                    "type": "string",
                    "default": ".",
                    "description": "Project-relative directory scope",
                },
                "case_mode": {
                    "type": "string",
                    "enum": ["smart", "sensitive", "insensitive"],
                    "default": "smart",
                },
                "word_match": {"type": "boolean", "default": False},
                "include_globs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 64,
                    "default": [],
                },
                "exclude_globs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 64,
                    "default": [],
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_TEXT_SEARCH_LIMIT,
                    "default": DEFAULT_TEXT_SEARCH_LIMIT,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json"],
                    "default": "json",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        query = arguments.get("query")
        if not isinstance(query, str) or not query:
            raise ValueError("query is required")
        try:
            query_bytes = len(query.encode("utf-8"))
        except UnicodeError as exc:
            raise ValueError("query must be valid UTF-8 text") from exc
        if query_bytes > 4096 or any(char in query for char in "\x00\r\n"):
            raise ValueError("query must be 1-4096 UTF-8 bytes without NUL or newlines")
        case_mode = arguments.get("case_mode", "smart")
        if case_mode not in {"smart", "sensitive", "insensitive"}:
            raise ValueError("case_mode must be smart, sensitive, or insensitive")
        if not isinstance(arguments.get("word_match", False), bool):
            raise ValueError("word_match must be a boolean")
        for name in ("include_globs", "exclude_globs"):
            values = arguments.get(name, [])
            if not isinstance(values, list) or len(values) > 64:
                raise ValueError(f"{name} must be a list with at most 64 items")
            if any(
                not isinstance(value, str)
                or not value
                or len(value.encode("utf-8")) > 256
                or value.startswith("!")
                for value in values
            ):
                raise ValueError(f"{name} contains an invalid glob")
        limit = arguments.get("limit", DEFAULT_TEXT_SEARCH_LIMIT)
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 1000
        ):
            raise ValueError("limit must be an integer from 1 to 1000")
        if arguments.get("output_format", "json") != "json":
            raise ValueError("output_format must be json")
        root = arguments.get("root", ".")
        if not isinstance(root, str) or not root:
            raise ValueError("root must be a non-empty project-relative path")
        try:
            root_bytes = len(root.encode("utf-8"))
        except UnicodeError as exc:
            raise ValueError("root must be valid UTF-8 text") from exc
        if root_bytes > 4096:
            raise ValueError("root must be a non-empty project-relative path")
        normalized_root = root.replace("\\", "/")
        root_path = PurePosixPath(normalized_root)
        if (
            "\x00" in root
            or root_path.is_absolute()
            or ".." in root_path.parts
            or (
                len(normalized_root) >= 3
                and normalized_root[1] == ":"
                and normalized_root[2] == "/"
            )
        ):
            raise ValueError("root must be a non-empty project-relative path")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = arguments.get("query")
        error_query = query if isinstance(query, str) else ""
        try:
            self.validate_arguments(arguments)
        except ValueError:
            return self._error_response(error_query, "INVALID_ARGUMENT")
        if not self.project_root:
            return self._error_response(error_query, "PROJECT_ROOT_NOT_SET")
        raw_project_root = Path(self.project_root)
        if raw_project_root.is_symlink():
            return self._error_response(error_query, "SOURCE_ROOT_SYMLINK")
        try:
            project_root = raw_project_root.resolve(strict=True)
        except OSError:
            return self._error_response(error_query, "SOURCE_ROOT_UNAVAILABLE")
        raw_root = arguments.get("root", ".").replace("\\", "/")
        candidate = project_root.joinpath(*PurePosixPath(raw_root).parts)
        try:
            resolved_scope = Path(
                self.resolve_and_validate_directory_path(raw_root)
            ).resolve(strict=True)
        except (OSError, ValueError):
            return self._error_response(
                error_query, self._scope_error_code(project_root, candidate)
            )
        try:
            resolved_scope.relative_to(project_root)
        except ValueError:
            return self._error_response(error_query, "SOURCE_ROOT_OUTSIDE_PROJECT")
        request = TextSearchRequest(
            project_root=str(project_root),
            root=PurePosixPath(raw_root).as_posix(),
            query=arguments["query"],
            case_mode=arguments.get("case_mode", "smart"),
            word_match=arguments.get("word_match", False),
            include_globs=tuple(arguments.get("include_globs", [])),
            exclude_globs=tuple(arguments.get("exclude_globs", [])),
        )
        try:
            report = await asyncio.to_thread(search_text_bounded, request)
        except TextSearchError as exc:
            return self._error_response(arguments["query"], exc.code)

        limit = arguments.get("limit", DEFAULT_TEXT_SEARCH_LIMIT)
        displayed = report.hits[:limit]
        verdict = "INFO" if report.hits else "NOT_FOUND"
        truncated = report.total_count > len(displayed)
        if truncated:
            next_step = (
                f"Showing {len(displayed)} of {report.total_count} matching lines; "
                "raise limit or narrow root/globs."
            )
        elif report.hits:
            next_step = "Use structure action=read for bounded surrounding context."
        else:
            next_step = "No matching line exists in the complete admitted live scope."
        result = {
            "success": True,
            "verdict": verdict,
            "query": arguments["query"],
            "match_mode": "literal",
            "effective_case_sensitive": self._effective_case_sensitive(arguments),
            "data_source": "live_source",
            "engine_used": "native",
            "source_evidence": {
                "consistency": "per_file_live",
                "index_used": False,
                "scan_complete": True,
            },
            "total_count": report.total_count,
            "displayed_count": len(displayed),
            "file_count": report.file_count,
            "listed_cap": limit,
            "truncated": truncated,
            "truncation_reason": "limit" if truncated else None,
            "results": [
                {
                    "file": hit.file,
                    "line": hit.line,
                    "column": hit.column,
                    "text": hit.text,
                }
                for hit in displayed
            ],
            "scan_stats": {
                "files_scanned": report.files_scanned,
                "bytes_scanned": report.bytes_scanned,
                "binary_files_skipped": report.binary_files_skipped,
            },
            "next_step": next_step,
        }
        result["agent_summary"] = {
            "verdict": verdict,
            "summary_line": (
                f"text search matched {report.total_count} line(s) in "
                f"{report.file_count} file(s); showing {len(displayed)}"
            ),
            "next_step": next_step,
        }
        return result

    @staticmethod
    def _effective_case_sensitive(arguments: dict[str, Any]) -> bool:
        mode = arguments.get("case_mode", "smart")
        return mode == "sensitive" or (
            mode == "smart" and any(char.isupper() for char in arguments["query"])
        )

    @staticmethod
    def _scope_error_code(project_root: Path, candidate: Path) -> str:
        """把 admission 失败稳定分类为缺失或越界。"""
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            return "SOURCE_ROOT_UNAVAILABLE"
        try:
            resolved.relative_to(project_root)
        except ValueError:
            return "SOURCE_ROOT_OUTSIDE_PROJECT"
        return "SOURCE_ROOT_UNAVAILABLE"

    @staticmethod
    def _error_response(query: str, code: str) -> dict[str, Any]:
        next_step = (
            "Narrow the root/globs or resolve the reported source error, then retry."
        )
        return {
            "success": False,
            "verdict": "ERROR",
            "error_code": code,
            "error": f"Text search failed: {code}",
            "query": query,
            "results": [],
            "source_evidence": {
                "consistency": "per_file_live",
                "index_used": False,
                "scan_complete": False,
            },
            "agent_summary": {
                "verdict": "ERROR",
                "summary_line": f"text search failed: {code}",
                "next_step": next_step,
            },
            "next_step": next_step,
        }
