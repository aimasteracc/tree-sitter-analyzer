#!/usr/bin/env python3
"""
Framework Middleware & Interceptor Detection.

Discovers middleware/interceptor chains across web frameworks using
Tree-sitter AST parsing:

- Python: Flask (@app.before_request/after_request/errorhandler),
      Django (MIDDLEWARE list in settings), FastAPI (@app.middleware)
- JavaScript/TypeScript: Express (app.use(), router.use())
- Java: Spring (@ControllerAdvice, @ExceptionHandler, Filter impls,
      HandlerInterceptor impls)

CodeGraph parity: extends route detection to cover the full request pipeline.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._route_detector_helpers import unquote, walk
from .core.parser import Parser
from .project_graph import _language_from_ext

logger = logging.getLogger(__name__)

_EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "htmlcov",
    ".cache",
    ".eggs",
    ".idea",
    ".vscode",
    ".claude",
    "vendor",
    "target",
    ".gradle",
    ".mvn",
}

_SOURCE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".java"}

_MIDDLEWARE_TYPES = frozenset(
    {
        "before_request",
        "after_request",
        "errorhandler",
        "middleware",
        "use_middleware",
        "settings_middleware",
        "interceptor",
        "controller_advice",
        "exception_handler",
        "filter",
        "handler_interceptor",
    }
)


@dataclass
class MiddlewareInfo:
    http_method: str
    url_pattern: str
    middleware_name: str
    middleware_type: str
    file_path: str
    line_number: int
    framework: str
    language: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "http_method": self.http_method,
            "url_pattern": self.url_pattern,
            "middleware_name": self.middleware_name,
            "middleware_type": self.middleware_type,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "framework": self.framework,
            "language": self.language,
            **self.extra,
        }


class MiddlewareDetector:
    """
    Detect middleware/interceptor declarations across web frameworks.

    Usage:
        detector = MiddlewareDetector("/path/to/project")
        middlewares = detector.detect_all()
        for mw in middlewares:
            print(f"{mw.middleware_type}: {mw.middleware_name} ({mw.framework})")
    """

    def __init__(self, project_root: str) -> None:
        self.project_root = Path(project_root).resolve()
        self._parser = Parser()
        self._middlewares: list[MiddlewareInfo] | None = None

    def detect_all(self) -> list[MiddlewareInfo]:
        if self._middlewares is not None:
            return self._middlewares
        middlewares: list[MiddlewareInfo] = []
        for file_path in self._walk_source_files():
            try:
                middlewares.extend(self.detect_file(str(file_path)))
            except Exception as exc:
                logger.debug("middleware detection failed for %s: %s", file_path, exc)
        self._middlewares = middlewares
        return middlewares

    def detect_file(self, file_path: str) -> list[MiddlewareInfo]:
        lang = _language_from_ext(file_path)
        if not lang:
            return []
        if lang == "python":
            return self._detect_python_middleware(file_path)
        if lang in ("javascript", "typescript"):
            return self._detect_js_middleware(file_path, lang)
        if lang == "java":
            return self._detect_java_middleware(file_path)
        return []

    def summary(self) -> dict[str, Any]:
        mws = self.detect_all()
        by_framework: dict[str, int] = {}
        by_type: dict[str, int] = {}
        for m in mws:
            by_framework[m.framework] = by_framework.get(m.framework, 0) + 1
            by_type[m.middleware_type] = by_type.get(m.middleware_type, 0) + 1
        return {
            "total_middlewares": len(mws),
            "by_framework": by_framework,
            "by_type": by_type,
            "file_count": len({m.file_path for m in mws}),
        }

    def lookup_by_url_prefix(self, prefix: str) -> list[MiddlewareInfo]:
        if not prefix.startswith("/"):
            prefix = "/" + prefix
        mws = self.detect_all()
        return [m for m in mws if m.url_pattern.startswith(prefix)]

    def _walk_source_files(self) -> list[Path]:
        import os as _os

        files: list[Path] = []
        stack: list[str] = [str(self.project_root)]
        while stack:
            current = stack.pop()
            try:
                it = _os.scandir(current)
            except OSError:
                continue
            with it:
                for entry in it:
                    name = entry.name
                    if name in _EXCLUDE_DIRS:
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    dot = name.rfind(".")
                    if dot == -1:
                        continue
                    if name[dot:].lower() not in _SOURCE_EXTENSIONS:
                        continue
                    files.append(Path(entry.path))
        return files

    def _parse_tree(self, file_path: str, language: str) -> Any | None:
        result = self._parser.parse_file(file_path, language)
        if not result.success or result.tree is None:
            return None
        return result.tree

    def _detect_python_middleware(self, file_path: str) -> list[MiddlewareInfo]:
        tree = self._parse_tree(file_path, "python")
        if not tree:
            return []
        source = tree.root_node.text.decode()
        root = tree.root_node
        rel = str(Path(file_path).relative_to(self.project_root))
        mws: list[MiddlewareInfo] = []
        mws.extend(self._scan_flask_hooks(root, rel, source))
        mws.extend(self._scan_fastapi_middleware(root, rel, source))
        mws.extend(self._scan_django_settings(root, rel, source))
        return mws

    def _scan_flask_hooks(
        self, root: Any, file_path: str, source: str
    ) -> list[MiddlewareInfo]:
        results: list[MiddlewareInfo] = []
        hook_patterns = {
            "before_request": re.compile(r"@\s*[\w.]+\s*\.\s*before_request"),
            "after_request": re.compile(r"@\s*[\w.]+\s*\.\s*after_request"),
            "errorhandler": re.compile(
                r"@\s*[\w.]+\s*\.\s*errorhandler\s*\(\s*(\d+)\s*\)"
            ),
            "teardown_request": re.compile(r"@\s*[\w.]+\s*\.\s*teardown_request"),
            "before_first_request": re.compile(
                r"@\s*[\w.]+\s*\.\s*before_first_request"
            ),
        }
        for node in walk(root):
            if node.type != "decorator":
                continue
            text = node.text.decode()
            for hook_type, pattern in hook_patterns.items():
                m = pattern.match(text)
                if not m:
                    continue
                handler = self._func_name_after_decorator(node)
                status_code = ""
                if hook_type == "errorhandler":
                    status_code = m.group(1)
                results.append(
                    MiddlewareInfo(
                        http_method="*",
                        url_pattern="/*",
                        middleware_name=handler,
                        middleware_type=hook_type,
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                        framework="flask",
                        language="python",
                        extra={"status_code": status_code} if status_code else {},
                    )
                )
                break
        return results

    def _scan_fastapi_middleware(
        self, root: Any, file_path: str, source: str
    ) -> list[MiddlewareInfo]:
        results: list[MiddlewareInfo] = []
        for node in walk(root):
            if node.type != "decorator":
                continue
            text = node.text.decode()
            m = re.match(
                r"@\s*[\w.]+\s*\.\s*middleware\s*\(\s*[\"'](\w+)[\"']\s*\)",
                text,
            )
            if not m:
                continue
            handler = self._func_name_after_decorator(node)
            results.append(
                MiddlewareInfo(
                    http_method="*",
                    url_pattern="/*",
                    middleware_name=handler,
                    middleware_type="middleware",
                    file_path=file_path,
                    line_number=node.start_point[0] + 1,
                    framework="fastapi",
                    language="python",
                    extra={"http_type": m.group(1)},
                )
            )
        return results

    def _scan_django_settings(
        self, root: Any, file_path: str, source: str
    ) -> list[MiddlewareInfo]:
        results: list[MiddlewareInfo] = []
        fname = Path(file_path).name
        if fname not in ("settings.py", "settings", "base.py"):
            return results
        for node in walk(root):
            if node.type != "assignment":
                continue
            left = node.child_by_field_name("left")
            if left is None or left.text.decode() != "MIDDLEWARE":
                continue
            right = node.child_by_field_name("right")
            if right is None or right.type != "list":
                continue
            for child in right.children:
                if child.type != "string":
                    continue
                mw_class = unquote(child.text.decode())
                if not mw_class:
                    continue
                short_name = mw_class.rsplit(".", 1)[-1]
                results.append(
                    MiddlewareInfo(
                        http_method="*",
                        url_pattern="/*",
                        middleware_name=short_name,
                        middleware_type="settings_middleware",
                        file_path=file_path,
                        line_number=child.start_point[0] + 1,
                        framework="django",
                        language="python",
                        extra={"full_class": mw_class},
                    )
                )
        return results

    def _detect_js_middleware(
        self, file_path: str, language: str
    ) -> list[MiddlewareInfo]:
        tree = self._parse_tree(file_path, language)
        if not tree:
            return []
        rel = str(Path(file_path).relative_to(self.project_root))
        return self._scan_express_middleware(tree.root_node, rel, language)

    def _scan_express_middleware(
        self, root: Any, file_path: str, language: str
    ) -> list[MiddlewareInfo]:
        results: list[MiddlewareInfo] = []
        for node in walk(root):
            if node.type != "call_expression":
                continue
            func = node.child_by_field_name("function")
            if func is None:
                continue
            func_text = func.text.decode()
            parts = func_text.rsplit(".", 1)
            if len(parts) != 2:
                continue
            method_name = parts[1].lower()
            if method_name != "use":
                continue
            args_node = node.child_by_field_name("arguments")
            if args_node is None:
                continue
            url_pattern = "/*"
            arg_idx = 0
            for child in args_node.children:
                if child.type in (",", "(", ")"):
                    continue
                if arg_idx == 0 and child.type in ("string", "template_string"):
                    url_pattern = self._extract_js_string(child)
                    arg_idx += 1
                    continue
                if child.type in (
                    "identifier",
                    "call_expression",
                    "arrow_function",
                    "function_expression",
                ):
                    mw_name = self._extract_mw_name(child)
                    results.append(
                        MiddlewareInfo(
                            http_method="*",
                            url_pattern=url_pattern,
                            middleware_name=mw_name,
                            middleware_type="use_middleware",
                            file_path=file_path,
                            line_number=node.start_point[0] + 1,
                            framework="express",
                            language=language,
                        )
                    )
                arg_idx += 1
        return results

    def _detect_java_middleware(self, file_path: str) -> list[MiddlewareInfo]:
        tree = self._parse_tree(file_path, "java")
        if not tree:
            return []
        rel = str(Path(file_path).relative_to(self.project_root))
        root = tree.root_node
        results: list[MiddlewareInfo] = []
        results.extend(self._scan_spring_controller_advice(root, rel))
        results.extend(self._scan_spring_filters(root, rel))
        results.extend(self._scan_spring_interceptors(root, rel))
        return results

    def _scan_spring_controller_advice(
        self, root: Any, file_path: str
    ) -> list[MiddlewareInfo]:
        results: list[MiddlewareInfo] = []
        for node in walk(root):
            if node.type not in ("marker_annotation", "annotation"):
                continue
            name_node = node.child_by_field_name("name")
            if name_node is None:
                continue
            ann_name = name_node.text.decode()
            simple = ann_name.rsplit(".", 1)[-1]
            if simple == "ControllerAdvice":
                class_name = self._java_class_containing(node)
                results.append(
                    MiddlewareInfo(
                        http_method="*",
                        url_pattern="/*",
                        middleware_name=class_name,
                        middleware_type="controller_advice",
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                        framework="spring",
                        language="java",
                    )
                )
            elif simple == "ExceptionHandler":
                method_name = self._java_method_after_annotation(node)
                results.append(
                    MiddlewareInfo(
                        http_method="*",
                        url_pattern="/*",
                        middleware_name=method_name,
                        middleware_type="exception_handler",
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                        framework="spring",
                        language="java",
                    )
                )
        return results

    def _scan_spring_filters(self, root: Any, file_path: str) -> list[MiddlewareInfo]:
        results: list[MiddlewareInfo] = []
        for node in walk(root):
            if node.type != "class_declaration":
                continue
            implements = self._java_class_implements(node)
            if not implements:
                continue
            for iface in implements:
                simple = iface.rsplit(".", 1)[-1]
                if simple == "Filter":
                    name_node = None
                    for child in node.children:
                        if child.type == "identifier":
                            name_node = child
                            break
                    class_name = name_node.text.decode() if name_node else "<unknown>"
                    results.append(
                        MiddlewareInfo(
                            http_method="*",
                            url_pattern="/*",
                            middleware_name=class_name,
                            middleware_type="filter",
                            file_path=file_path,
                            line_number=node.start_point[0] + 1,
                            framework="spring",
                            language="java",
                        )
                    )
        return results

    def _scan_spring_interceptors(
        self, root: Any, file_path: str
    ) -> list[MiddlewareInfo]:
        results: list[MiddlewareInfo] = []
        for node in walk(root):
            if node.type != "class_declaration":
                continue
            implements = self._java_class_implements(node)
            if not implements:
                continue
            for iface in implements:
                simple = iface.rsplit(".", 1)[-1]
                if simple == "HandlerInterceptor":
                    name_node = None
                    for child in node.children:
                        if child.type == "identifier":
                            name_node = child
                            break
                    class_name = name_node.text.decode() if name_node else "<unknown>"
                    results.append(
                        MiddlewareInfo(
                            http_method="*",
                            url_pattern="/*",
                            middleware_name=class_name,
                            middleware_type="handler_interceptor",
                            file_path=file_path,
                            line_number=node.start_point[0] + 1,
                            framework="spring",
                            language="java",
                        )
                    )
        return results

    def _func_name_after_decorator(self, decorator_node: Any) -> str:
        parent = decorator_node.parent
        if parent is None:
            return "<unknown>"
        for child in parent.children:
            if child.type == "function_definition":
                name_node = child.child_by_field_name("name")
                if name_node:
                    name: str = name_node.text.decode()
                    return name
        return "<unknown>"

    def _extract_js_string(self, node: Any) -> str:
        text: str = node.text.decode()
        if node.type == "template_string":
            if text.startswith("`") and text.endswith("`"):
                return text[1:-1]
            return text
        return unquote(text)

    def _extract_mw_name(self, node: Any) -> str:
        if node.type == "identifier":
            decoded: str = node.text.decode()
            return decoded
        if node.type in ("arrow_function", "function_expression"):
            return "<anonymous>"
        text: str = node.text.decode()
        return text[:80]

    def _java_class_containing(self, node: Any) -> str:
        current = node.parent
        while current is not None:
            if current.type == "class_declaration":
                for child in current.children:
                    if child.type == "identifier":
                        cls_name: str = child.text.decode()
                        return cls_name
            current = current.parent
        return "<unknown>"

    def _java_method_after_annotation(self, node: Any) -> str:
        parent = node.parent
        if parent is None:
            return "<unknown>"
        for child in parent.children:
            if child.type == "method_declaration":
                for mc in child.children:
                    if mc.type == "identifier":
                        method_name: str = mc.text.decode()
                        return method_name
        return "<unknown>"

    def _java_class_implements(self, class_node: Any) -> list[str]:
        interfaces: list[str] = []
        in_implements = False
        for child in class_node.children:
            if child.type == "implements":
                in_implements = True
                continue
            if in_implements:
                if child.type == "type_identifier":
                    interfaces.append(child.text.decode())
                elif child.type == "generic_type":
                    for sc in child.children:
                        if sc.type == "type_identifier":
                            interfaces.append(sc.text.decode())
                elif child.type == "{":
                    break
        return interfaces
