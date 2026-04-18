"""
Logging Pattern Analyzer.

Detects logging anti-patterns that make production debugging harder.
Catches the gap between "errors are handled" and "errors are debuggable".

Smells detected:
  - silent_catch: catch/except block with no logging call (HIGH)
  - print_logging: using print() instead of a proper logger (LOW)
  - sensitive_in_log: potential secrets in log arguments (HIGH)
  - bare_raise: re-raise without logging the original error (MEDIUM)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tree_sitter

from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go",
}

_LANGUAGE_MODULES: dict[str, str] = {
    ".py": "tree_sitter_python",
    ".js": "tree_sitter_javascript",
    ".ts": "tree_sitter_typescript",
    ".tsx": "tree_sitter_typescript",
    ".jsx": "tree_sitter_javascript",
    ".java": "tree_sitter_java",
    ".go": "tree_sitter_go",
}

_LANGUAGE_FUNCS: dict[str, str] = {
    ".ts": "language_typescript",
    ".tsx": "language_tsx",
}

SMELL_SILENT_CATCH = "silent_catch"
SMELL_PRINT_LOGGING = "print_logging"
SMELL_SENSITIVE_IN_LOG = "sensitive_in_log"
SMELL_BARE_RAISE = "bare_raise"

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"

_SMELL_SEVERITY: dict[str, str] = {
    SMELL_SILENT_CATCH: SEVERITY_HIGH,
    SMELL_PRINT_LOGGING: SEVERITY_LOW,
    SMELL_SENSITIVE_IN_LOG: SEVERITY_HIGH,
    SMELL_BARE_RAISE: SEVERITY_MEDIUM,
}

_SENSITIVE_NAMES: frozenset[str] = frozenset({
    "password", "passwd", "pwd", "secret", "token", "api_key", "apikey",
    "access_token", "refresh_token", "private_key", "secret_key",
    "auth_token", "session_id", "cookie", "credential",
})

_PY_LOGGING_METHODS: frozenset[str] = frozenset({
    "debug", "info", "warning", "warn", "error", "critical", "exception",
    "log", "fatal",
})

_PY_LOGGER_OBJECTS: frozenset[str] = frozenset({
    "logging", "logger", "log", "LOGGER", "LOG",
})

_JS_LOGGING_CALLS: frozenset[str] = frozenset({
    "log", "warn", "error", "info", "debug", "trace",
})

_JS_LOGGER_OBJECTS: frozenset[str] = frozenset({
    "console", "logger", "Logger", "log", "winston",
})

_JAVA_LOGGING_METHODS: frozenset[str] = frozenset({
    "debug", "info", "warn", "error", "trace", "fatal",
})

_JAVA_LOGGER_OBJECTS: frozenset[str] = frozenset({
    "log", "logger", "LOG", "LOGGER",
})

_GO_SLOG_METHODS: frozenset[str] = frozenset({
    "Info", "Warn", "Error", "Debug",
})


@dataclass(frozen=True)
class LoggingSmell:
    """A single logging smell detected in a catch/handler block."""
    smell_type: str
    context_name: str
    line_number: int
    severity: str
    detail: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "smell_type": self.smell_type,
            "context_name": self.context_name,
            "line_number": self.line_number,
            "severity": self.severity,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class CatchBlock:
    """A catch/except block analysis result."""
    start_line: int
    end_line: int
    handler_type: str
    has_logging: bool
    has_print: bool
    smells: tuple[LoggingSmell, ...]

    def to_dict(self) -> dict[str, str | int | bool | tuple[dict[str, str | int], ...]]:
        return {
            "start_line": self.start_line,
            "end_line": self.end_line,
            "handler_type": self.handler_type,
            "has_logging": self.has_logging,
            "has_print": self.has_print,
            "smells": tuple(s.to_dict() for s in self.smells),
        }


@dataclass(frozen=True)
class LoggingPatternResult:
    """Per-file analysis result."""
    file_path: str
    catch_blocks: tuple[CatchBlock, ...]
    print_logging_calls: tuple[LoggingSmell, ...]
    total_catch_blocks: int
    total_smells: int
    smell_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "catch_blocks": tuple(b.to_dict() for b in self.catch_blocks),
            "print_logging_calls": tuple(p.to_dict() for p in self.print_logging_calls),
            "total_catch_blocks": self.total_catch_blocks,
            "total_smells": self.total_smells,
            "smell_counts": self.smell_counts,
        }

    def get_smells_by_type(self, smell_type: str) -> tuple[LoggingSmell, ...]:
        return tuple(
            s for b in self.catch_blocks for s in b.smells
            if s.smell_type == smell_type
        ) + tuple(
            p for p in self.print_logging_calls
            if p.smell_type == smell_type
        )

    def get_high_severity_smells(self) -> tuple[LoggingSmell, ...]:
        return tuple(
            s for b in self.catch_blocks for s in b.smells
            if s.severity == SEVERITY_HIGH
        ) + tuple(
            p for p in self.print_logging_calls
            if p.severity == SEVERITY_HIGH
        )


def _empty_result(file_path: str) -> LoggingPatternResult:
    return LoggingPatternResult(
        file_path=file_path,
        catch_blocks=(),
        print_logging_calls=(),
        total_catch_blocks=0,
        total_smells=0,
        smell_counts={},
    )


def _severity_for(smell_type: str) -> str:
    return _SMELL_SEVERITY.get(smell_type, SEVERITY_LOW)


def _text(node: tree_sitter.Node, content: bytes) -> str:
    return content[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _find_child(node: tree_sitter.Node, child_type: str) -> tree_sitter.Node | None:
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _is_sensitive_name(name: str) -> bool:
    lower = name.lower().replace("-", "_")
    return any(s in lower for s in _SENSITIVE_NAMES)


class LoggingPatternAnalyzer:
    """Detects logging anti-patterns across Python, JS/TS, Java, and Go."""

    def __init__(self) -> None:
        self._parsers: dict[str, tree_sitter.Parser] = {}
        self._languages: dict[str, tree_sitter.Language] = {}

    def _get_parser(self, ext: str) -> tuple[tree_sitter.Language | None, tree_sitter.Parser | None]:
        if ext not in _LANGUAGE_MODULES:
            return None, None
        if ext not in self._parsers:
            module_name = _LANGUAGE_MODULES[ext]
            lang_module = __import__(module_name)
            func_name = _LANGUAGE_FUNCS.get(ext, "language")
            language_func = getattr(lang_module, func_name)
            language = tree_sitter.Language(language_func())
            parser = tree_sitter.Parser(language)
            self._languages[ext] = language
            self._parsers[ext] = parser
        return self._languages.get(ext), self._parsers.get(ext)

    def analyze_file(
        self,
        file_path: Path | str,
    ) -> LoggingPatternResult:
        path = Path(file_path)
        if not path.exists():
            return _empty_result(str(path))
        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return _empty_result(str(path))

        content = path.read_bytes()
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return _empty_result(str(path))

        tree = parser.parse(content)

        if ext == ".py":
            return self._analyze_python(tree.root_node, content, str(path))
        elif ext in {".js", ".ts", ".tsx", ".jsx"}:
            return self._analyze_javascript(tree.root_node, content, str(path))
        elif ext == ".java":
            return self._analyze_java(tree.root_node, content, str(path))
        elif ext == ".go":
            return self._analyze_go(tree.root_node, content, str(path))
        return _empty_result(str(path))

    # --- Python ---

    def _analyze_python(
        self,
        root: tree_sitter.Node,
        content: bytes,
        file_path: str,
    ) -> LoggingPatternResult:
        catch_blocks: list[CatchBlock] = []
        print_calls: list[LoggingSmell] = []

        self._walk_python(root, content, catch_blocks, print_calls)

        return self._build_result(file_path, catch_blocks, print_calls)

    def _walk_python(
        self,
        node: tree_sitter.Node,
        content: bytes,
        catch_blocks: list[CatchBlock],
        print_calls: list[LoggingSmell],
    ) -> None:
        if node.type == "except_clause":
            block = self._analyze_python_except(node, content)
            if block is not None:
                catch_blocks.append(block)

        if node.type == "call":
            func = node.child_by_field_name("function")
            if func is not None:
                func_text = _text(func, content)
                if func_text == "print":
                    print_calls.append(LoggingSmell(
                        smell_type=SMELL_PRINT_LOGGING,
                        context_name="print",
                        line_number=node.start_point[0] + 1,
                        severity=_severity_for(SMELL_PRINT_LOGGING),
                        detail="Using print() instead of logging",
                    ))

        for child in node.children:
            self._walk_python(child, content, catch_blocks, print_calls)

    def _analyze_python_except(
        self,
        node: tree_sitter.Node,
        content: bytes,
    ) -> CatchBlock | None:
        body = _find_child(node, "block")
        if body is None:
            return None

        handler_type = "Exception"
        as_pattern = _find_child(node, "as_pattern")
        if as_pattern is not None:
            for child in as_pattern.children:
                if child.type == "identifier":
                    handler_type = _text(child, content)
                    break
        else:
            for child in node.children:
                if child.type == "identifier" and child.is_named:
                    handler_type = _text(child, content)
                    break

        has_logging = self._has_python_logging(body, content)
        has_print = self._has_python_print(body, content)
        has_sensitive = self._check_python_sensitive(body, content)
        has_raise = self._check_python_raise(body)

        smells: list[LoggingSmell] = []
        if not has_logging and not has_print:
            smells.append(LoggingSmell(
                smell_type=SMELL_SILENT_CATCH,
                context_name=handler_type,
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_SILENT_CATCH),
                detail=f"except {handler_type} block has no logging",
            ))

        if has_sensitive:
            smells.append(LoggingSmell(
                smell_type=SMELL_SENSITIVE_IN_LOG,
                context_name=handler_type,
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_SENSITIVE_IN_LOG),
                detail="Potential sensitive data in logging call",
            ))

        if has_raise and not has_logging:
            smells.append(LoggingSmell(
                smell_type=SMELL_BARE_RAISE,
                context_name=handler_type,
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_BARE_RAISE),
                detail="Re-raise without logging original error",
            ))

        return CatchBlock(
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            handler_type=handler_type,
            has_logging=has_logging,
            has_print=has_print,
            smells=tuple(smells),
        )

    def _has_python_logging(self, node: tree_sitter.Node, content: bytes) -> bool:
        stack = [node]
        while stack:
            n = stack.pop()
            if n.type == "call":
                func = n.child_by_field_name("function")
                if func is not None:
                    if func.type == "attribute":
                        obj = func.child_by_field_name("object")
                        attr = func.child_by_field_name("attribute")
                        if obj is not None and attr is not None:
                            obj_text = _text(obj, content)
                            attr_text = _text(attr, content)
                            if obj_text in _PY_LOGGER_OBJECTS and attr_text in _PY_LOGGING_METHODS:
                                return True
            for child in n.children:
                stack.append(child)
        return False

    def _has_python_print(self, node: tree_sitter.Node, content: bytes) -> bool:
        stack = [node]
        while stack:
            n = stack.pop()
            if n.type == "call":
                func = n.child_by_field_name("function")
                if func is not None and _text(func, content) == "print":
                    return True
            for child in n.children:
                stack.append(child)
        return False

    def _check_python_sensitive(self, node: tree_sitter.Node, content: bytes) -> bool:
        stack = [node]
        while stack:
            n = stack.pop()
            if n.type == "call":
                func = n.child_by_field_name("function")
                if func is not None and func.type == "attribute":
                    obj = func.child_by_field_name("object")
                    attr = func.child_by_field_name("attribute")
                    if obj is not None and attr is not None:
                        obj_text = _text(obj, content)
                        attr_text = _text(attr, content)
                        if obj_text in _PY_LOGGER_OBJECTS and attr_text in _PY_LOGGING_METHODS:
                            args = n.child_by_field_name("arguments")
                            if args is not None and self._has_sensitive_args(args, content):
                                return True
            for child in n.children:
                stack.append(child)
        return False

    def _check_python_raise(self, node: tree_sitter.Node) -> bool:
        stack = [node]
        while stack:
            n = stack.pop()
            if n.type == "raise_statement":
                return True
            for child in n.children:
                stack.append(child)
        return False

    def _has_sensitive_args(self, args_node: tree_sitter.Node, content: bytes) -> bool:
        for child in args_node.children:
            if child.type == "identifier":
                if _is_sensitive_name(_text(child, content)):
                    return True
            if child.type == "keyword_argument":
                name_node = child.child_by_field_name("name")
                if name_node is not None and _is_sensitive_name(_text(name_node, content)):
                    return True
            if child.type in ("string", "concatenated_string"):
                text = _text(child, content).lower()
                if any(s in text for s in _SENSITIVE_NAMES):
                    return True
            if child.type == "binary_operator":
                left = child.child_by_field_name("left")
                if left is not None and left.type == "identifier":
                    if _is_sensitive_name(_text(left, content)):
                        return True
                right = child.child_by_field_name("right")
                if right is not None and right.type in ("string", "identifier"):
                    if _is_sensitive_name(_text(right, content)):
                        return True
        return False

    # --- JavaScript / TypeScript ---

    def _analyze_javascript(
        self,
        root: tree_sitter.Node,
        content: bytes,
        file_path: str,
    ) -> LoggingPatternResult:
        catch_blocks: list[CatchBlock] = []
        print_calls: list[LoggingSmell] = []

        self._walk_javascript(root, content, catch_blocks, print_calls)

        return self._build_result(file_path, catch_blocks, print_calls)

    def _walk_javascript(
        self,
        node: tree_sitter.Node,
        content: bytes,
        catch_blocks: list[CatchBlock],
        print_calls: list[LoggingSmell],
    ) -> None:
        if node.type == "catch_clause":
            block = self._analyze_js_catch(node, content)
            if block is not None:
                catch_blocks.append(block)

        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func is not None:
                func_text = _text(func, content)
                if func_text == "console.log":
                    print_calls.append(LoggingSmell(
                        smell_type=SMELL_PRINT_LOGGING,
                        context_name="console.log",
                        line_number=node.start_point[0] + 1,
                        severity=_severity_for(SMELL_PRINT_LOGGING),
                        detail="Using console.log() instead of proper logger",
                    ))

        for child in node.children:
            self._walk_javascript(child, content, catch_blocks, print_calls)

    def _analyze_js_catch(
        self,
        node: tree_sitter.Node,
        content: bytes,
    ) -> CatchBlock | None:
        body = _find_child(node, "statement_block")
        if body is None:
            body = _find_child(node, "block")
        if body is None:
            return None

        handler_type = "catch"
        param = node.child_by_field_name("parameter")
        if param is not None:
            handler_type = _text(param, content)

        has_logging = self._has_js_logging(body, content)
        has_print = self._has_js_print(body, content)
        has_sensitive = self._check_js_sensitive(body, content)

        smells: list[LoggingSmell] = []
        if not has_logging and not has_print:
            smells.append(LoggingSmell(
                smell_type=SMELL_SILENT_CATCH,
                context_name=handler_type,
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_SILENT_CATCH),
                detail="catch block has no logging",
            ))

        if has_sensitive:
            smells.append(LoggingSmell(
                smell_type=SMELL_SENSITIVE_IN_LOG,
                context_name=handler_type,
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_SENSITIVE_IN_LOG),
                detail="Potential sensitive data in logging call",
            ))

        return CatchBlock(
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            handler_type=handler_type,
            has_logging=has_logging,
            has_print=has_print,
            smells=tuple(smells),
        )

    def _has_js_logging(self, node: tree_sitter.Node, content: bytes) -> bool:
        stack = [node]
        while stack:
            n = stack.pop()
            if n.type == "call_expression":
                func = n.child_by_field_name("function")
                if func is not None:
                    if func.type == "member_expression":
                        obj = func.child_by_field_name("object")
                        prop = func.child_by_field_name("property")
                        if obj is not None and prop is not None:
                            obj_text = _text(obj, content)
                            prop_text = _text(prop, content)
                            if obj_text in _JS_LOGGER_OBJECTS and prop_text in _JS_LOGGING_CALLS:
                                return True
                    else:
                        func_text = _text(func, content)
                        if func_text in _JS_LOGGER_OBJECTS:
                            return True
            for child in n.children:
                stack.append(child)
        return False

    def _has_js_print(self, node: tree_sitter.Node, content: bytes) -> bool:
        stack = [node]
        while stack:
            n = stack.pop()
            if n.type == "call_expression":
                func = n.child_by_field_name("function")
                if func is not None:
                    func_text = _text(func, content)
                    if func_text in ("console.log", "print"):
                        return True
            for child in n.children:
                stack.append(child)
        return False

    def _check_js_sensitive(self, node: tree_sitter.Node, content: bytes) -> bool:
        stack = [node]
        while stack:
            n = stack.pop()
            if n.type == "call_expression":
                func = n.child_by_field_name("function")
                if func is not None:
                    is_log = False
                    if func.type == "member_expression":
                        obj = func.child_by_field_name("object")
                        prop = func.child_by_field_name("property")
                        if obj is not None and prop is not None:
                            obj_text = _text(obj, content)
                            prop_text = _text(prop, content)
                            if obj_text in _JS_LOGGER_OBJECTS and prop_text in _JS_LOGGING_CALLS:
                                is_log = True
                    if is_log:
                        args = n.child_by_field_name("arguments")
                        if args is not None and self._has_sensitive_args_js(args, content):
                            return True
            for child in n.children:
                stack.append(child)
        return False

    def _has_sensitive_args_js(self, args_node: tree_sitter.Node, content: bytes) -> bool:
        for child in args_node.children:
            if child.type == "identifier":
                if _is_sensitive_name(_text(child, content)):
                    return True
            if child.type in ("string", "template_string"):
                text = _text(child, content).lower()
                if any(s in text for s in _SENSITIVE_NAMES):
                    return True
            if child.type == "member_expression":
                prop = child.child_by_field_name("property")
                if prop is not None and _is_sensitive_name(_text(prop, content)):
                    return True
            if child.type == "property_identifier":
                if _is_sensitive_name(_text(child, content)):
                    return True
        return False

    # --- Java ---

    def _analyze_java(
        self,
        root: tree_sitter.Node,
        content: bytes,
        file_path: str,
    ) -> LoggingPatternResult:
        catch_blocks: list[CatchBlock] = []
        print_calls: list[LoggingSmell] = []

        self._walk_java(root, content, catch_blocks, print_calls)

        return self._build_result(file_path, catch_blocks, print_calls)

    def _walk_java(
        self,
        node: tree_sitter.Node,
        content: bytes,
        catch_blocks: list[CatchBlock],
        print_calls: list[LoggingSmell],
    ) -> None:
        if node.type == "catch_clause":
            block = self._analyze_java_catch(node, content)
            if block is not None:
                catch_blocks.append(block)

        if node.type == "method_invocation":
            obj = node.child_by_field_name("object")
            name = node.child_by_field_name("name")
            if obj is not None and name is not None:
                obj_text = _text(obj, content)
                name_text = _text(name, content)
                if obj_text == "System.out" and name_text in ("println", "printf", "print"):
                    print_calls.append(LoggingSmell(
                        smell_type=SMELL_PRINT_LOGGING,
                        context_name="System.out",
                        line_number=node.start_point[0] + 1,
                        severity=_severity_for(SMELL_PRINT_LOGGING),
                        detail="Using System.out instead of logger",
                    ))

        for child in node.children:
            self._walk_java(child, content, catch_blocks, print_calls)

    def _analyze_java_catch(
        self,
        node: tree_sitter.Node,
        content: bytes,
    ) -> CatchBlock | None:
        body = node.child_by_field_name("body")
        if body is None:
            body = _find_child(node, "block")
        if body is None:
            return None

        handler_type = "Exception"
        for child in node.children:
            if child.type == "catch_formal_parameter":
                for cp in child.children:
                    if cp.type in ("type_identifier", "generic_type", "union_type"):
                        handler_type = _text(cp, content)
                        break

        has_logging = self._has_java_logging(body, content)
        has_print = self._has_java_print(body, content)
        has_sensitive = self._check_java_sensitive(body, content)

        smells: list[LoggingSmell] = []
        if not has_logging and not has_print:
            smells.append(LoggingSmell(
                smell_type=SMELL_SILENT_CATCH,
                context_name=handler_type,
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_SILENT_CATCH),
                detail=f"catch({handler_type}) block has no logging",
            ))

        if has_sensitive:
            smells.append(LoggingSmell(
                smell_type=SMELL_SENSITIVE_IN_LOG,
                context_name=handler_type,
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_SENSITIVE_IN_LOG),
                detail="Potential sensitive data in logging call",
            ))

        return CatchBlock(
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            handler_type=handler_type,
            has_logging=has_logging,
            has_print=has_print,
            smells=tuple(smells),
        )

    def _has_java_logging(self, node: tree_sitter.Node, content: bytes) -> bool:
        stack = [node]
        while stack:
            n = stack.pop()
            if n.type == "method_invocation":
                obj = n.child_by_field_name("object")
                name = n.child_by_field_name("name")
                if obj is not None and name is not None:
                    obj_text = _text(obj, content)
                    name_text = _text(name, content)
                    if obj_text in _JAVA_LOGGER_OBJECTS and name_text in _JAVA_LOGGING_METHODS:
                        return True
            for child in n.children:
                stack.append(child)
        return False

    def _has_java_print(self, node: tree_sitter.Node, content: bytes) -> bool:
        stack = [node]
        while stack:
            n = stack.pop()
            if n.type == "method_invocation":
                obj = n.child_by_field_name("object")
                name = n.child_by_field_name("name")
                if obj is not None and name is not None:
                    obj_text = _text(obj, content)
                    name_text = _text(name, content)
                    if obj_text == "System.out" and name_text in ("println", "printf", "print"):
                        return True
            for child in n.children:
                stack.append(child)
        return False

    def _check_java_sensitive(self, node: tree_sitter.Node, content: bytes) -> bool:
        stack = [node]
        while stack:
            n = stack.pop()
            if n.type == "method_invocation":
                obj = n.child_by_field_name("object")
                name = n.child_by_field_name("name")
                if obj is not None and name is not None:
                    obj_text = _text(obj, content)
                    name_text = _text(name, content)
                    if obj_text in _JAVA_LOGGER_OBJECTS and name_text in _JAVA_LOGGING_METHODS:
                        args = n.child_by_field_name("arguments")
                        if args is not None and self._has_sensitive_args_java(args, content):
                            return True
            for child in n.children:
                stack.append(child)
        return False

    def _has_sensitive_args_java(self, args_node: tree_sitter.Node, content: bytes) -> bool:
        for child in args_node.children:
            if child.type == "identifier":
                if _is_sensitive_name(_text(child, content)):
                    return True
            if child.type == "string_literal":
                text = _text(child, content).lower()
                if any(s in text for s in _SENSITIVE_NAMES):
                    return True
            if child.type == "field_access":
                name = child.child_by_field_name("field")
                if name is not None and _is_sensitive_name(_text(name, content)):
                    return True
            if child.type == "binary_expression" or child.type == "additive_expression":
                left = child.child_by_field_name("left")
                right = child.child_by_field_name("right")
                if left is not None and left.type == "string_literal":
                    text = _text(left, content).lower()
                    if any(s in text for s in _SENSITIVE_NAMES):
                        return True
                if right is not None and right.type == "identifier":
                    if _is_sensitive_name(_text(right, content)):
                        return True
        return False

    # --- Go ---

    def _analyze_go(
        self,
        root: tree_sitter.Node,
        content: bytes,
        file_path: str,
    ) -> LoggingPatternResult:
        catch_blocks: list[CatchBlock] = []
        print_calls: list[LoggingSmell] = []

        self._walk_go(root, content, catch_blocks, print_calls)

        return self._build_result(file_path, catch_blocks, print_calls)

    def _walk_go(
        self,
        node: tree_sitter.Node,
        content: bytes,
        catch_blocks: list[CatchBlock],
        print_calls: list[LoggingSmell],
    ) -> None:
        if node.type == "if_statement":
            block = self._analyze_go_error_check(node, content)
            if block is not None:
                catch_blocks.append(block)

        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func is not None:
                func_text = _text(func, content)
                if func_text in ("fmt.Println", "fmt.Printf"):
                    print_calls.append(LoggingSmell(
                        smell_type=SMELL_PRINT_LOGGING,
                        context_name="fmt.Print",
                        line_number=node.start_point[0] + 1,
                        severity=_severity_for(SMELL_PRINT_LOGGING),
                        detail="Using fmt.Println instead of log/slog",
                    ))

        for child in node.children:
            self._walk_go(child, content, catch_blocks, print_calls)

    def _analyze_go_error_check(
        self,
        node: tree_sitter.Node,
        content: bytes,
    ) -> CatchBlock | None:
        condition = node.child_by_field_name("condition")
        if condition is None:
            return None

        cond_text = _text(condition, content)
        if "err" not in cond_text and "nil" not in cond_text:
            return None

        consequence = node.child_by_field_name("consequence")
        if consequence is None:
            return None

        has_logging = self._has_go_logging(consequence, content)
        has_print = self._has_go_print(consequence, content)
        has_sensitive = self._check_go_sensitive(consequence, content)

        smells: list[LoggingSmell] = []
        if not has_logging and not has_print:
            smells.append(LoggingSmell(
                smell_type=SMELL_SILENT_CATCH,
                context_name="err != nil",
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_SILENT_CATCH),
                detail="Error check block has no logging",
            ))

        if has_sensitive:
            smells.append(LoggingSmell(
                smell_type=SMELL_SENSITIVE_IN_LOG,
                context_name="err != nil",
                line_number=node.start_point[0] + 1,
                severity=_severity_for(SMELL_SENSITIVE_IN_LOG),
                detail="Potential sensitive data in logging call",
            ))

        return CatchBlock(
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            handler_type="err != nil",
            has_logging=has_logging,
            has_print=has_print,
            smells=tuple(smells),
        )

    def _has_go_logging(self, node: tree_sitter.Node, content: bytes) -> bool:
        stack = [node]
        while stack:
            n = stack.pop()
            if n.type == "call_expression":
                func = n.child_by_field_name("function")
                if func is not None:
                    if func.type == "selector_expression":
                        obj = func.child_by_field_name("operand")
                        field = func.child_by_field_name("field")
                        if obj is not None and field is not None:
                            obj_text = _text(obj, content)
                            field_text = _text(field, content)
                            if obj_text == "log" or obj_text == "slog":
                                return True
                            if obj_text == "slog" and field_text in _GO_SLOG_METHODS:
                                return True
                    else:
                        func_text = _text(func, content)
                        if func_text.startswith("log.") or func_text.startswith("slog."):
                            return True
            for child in n.children:
                stack.append(child)
        return False

    def _has_go_print(self, node: tree_sitter.Node, content: bytes) -> bool:
        stack = [node]
        while stack:
            n = stack.pop()
            if n.type == "call_expression":
                func = n.child_by_field_name("function")
                if func is not None:
                    func_text = _text(func, content)
                    if func_text.startswith("fmt."):
                        return True
            for child in n.children:
                stack.append(child)
        return False

    def _check_go_sensitive(self, node: tree_sitter.Node, content: bytes) -> bool:
        stack = [node]
        while stack:
            n = stack.pop()
            if n.type == "call_expression":
                func = n.child_by_field_name("function")
                if func is not None:
                    func_text = _text(func, content)
                    if func_text.startswith("log.") or func_text.startswith("slog."):
                        args = n.child_by_field_name("arguments")
                        if args is not None:
                            for child in args.children:
                                if child.type == "identifier" and _is_sensitive_name(_text(child, content)):
                                    return True
                                if child.type in ("interpreted_string_literal", "raw_string_literal"):
                                    text = _text(child, content).lower()
                                    if any(s in text for s in _SENSITIVE_NAMES):
                                        return True
            for child in n.children:
                stack.append(child)
        return False

    # --- Result builder ---

    def _build_result(
        self,
        file_path: str,
        catch_blocks: list[CatchBlock],
        print_calls: list[LoggingSmell],
    ) -> LoggingPatternResult:
        total_smells = (
            sum(len(b.smells) for b in catch_blocks)
            + len(print_calls)
        )
        smell_counts: dict[str, int] = {}
        for b in catch_blocks:
            for s in b.smells:
                smell_counts[s.smell_type] = smell_counts.get(s.smell_type, 0) + 1
        for p in print_calls:
            smell_counts[p.smell_type] = smell_counts.get(p.smell_type, 0) + 1

        return LoggingPatternResult(
            file_path=file_path,
            catch_blocks=tuple(catch_blocks),
            print_logging_calls=tuple(print_calls),
            total_catch_blocks=len(catch_blocks),
            total_smells=total_smells,
            smell_counts=smell_counts,
        )
