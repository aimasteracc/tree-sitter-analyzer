"""
Async/Await Pattern Analyzer.

Detects async/await anti-patterns that cause silent bugs:
- Python: async without await, missing await, fire-and-forget async calls
- JavaScript/TypeScript: unhandled promises, missing await, promise chain mixing
- Java: @Async misuse, CompletableFuture anti-patterns
- Go: fire-and-forget goroutines, unchecked channel operations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger
from tree_sitter_analyzer.utils.tree_sitter_compat import TreeSitterQueryCompat

if TYPE_CHECKING:
    from tree_sitter import Tree

logger = setup_logger(__name__)

class PatternSeverity(Enum):
    """Severity level of detected pattern."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

class AsyncPatternType(Enum):
    """Type of async anti-pattern."""

    ASYNC_WITHOUT_AWAIT = "async_without_await"
    MISSING_AWAIT = "missing_await"
    FIRE_AND_FORGET = "fire_and_forget"
    UNHANDLED_PROMISE = "unhandled_promise"
    PROMISE_CHAIN_MIX = "promise_chain_mix"
    GOROUTINE_LEAK = "goroutine_leak"
    UNCHECKED_CHANNEL = "unchecked_channel"
    BLOCKING_IN_ASYNC = "blocking_in_async"

@dataclass(frozen=True)
class AsyncPatternMatch:
    """A detected async pattern."""

    pattern_type: AsyncPatternType
    severity: PatternSeverity
    file_path: str
    line: int
    column: int
    message: str
    function_name: str
    language: str
    suggestion: str

@dataclass
class AsyncPatternResult:
    """Result of async pattern analysis."""

    file_path: str
    language: str
    patterns: list[AsyncPatternMatch] = field(default_factory=list)
    total_async_functions: int = 0
    total_await_expressions: int = 0
    total_goroutines: int = 0

    @property
    def error_count(self) -> int:
        return sum(
            1 for p in self.patterns if p.severity == PatternSeverity.ERROR
        )

    @property
    def warning_count(self) -> int:
        return sum(
            1 for p in self.patterns if p.severity == PatternSeverity.WARNING
        )

    @property
    def info_count(self) -> int:
        return sum(
            1 for p in self.patterns if p.severity == PatternSeverity.INFO
        )

# --- Tree-sitter queries ---

# Python: async function definitions
_PYTHON_ASYNC_FUNC_QUERY = """
(function_definition
    "async" @async_keyword
    name: (identifier) @function_name
    parameters: (parameters) @parameters
    body: (block) @body) @async_function
"""

# Python: await expressions
_PYTHON_AWAIT_QUERY = """
(await
    (call) @awaited_call) @await_expr
"""

# Python: function calls (potential missing await)
_PYTHON_CALL_QUERY = """
(call
    function: (identifier) @func_name) @call_expr
"""

# Python: call expressions with attribute access
_PYTHON_ATTR_CALL_QUERY = """
(call
    function: (attribute
        object: (identifier)
        attribute: (identifier) @method_name)) @attr_call
"""

# JavaScript: async functions
_JS_ASYNC_FUNC_QUERY = """
(function_declaration
    "async" @async_keyword
    name: (identifier) @function_name
    parameters: (formal_parameters) @parameters
    body: (statement_block) @body) @async_function
"""

# JavaScript: arrow async functions
_JS_ASYNC_ARROW_QUERY = """
(arrow_function
    "async" @async_keyword
    body: (_) @body) @async_arrow
"""

# JavaScript: await expressions
_JS_AWAIT_QUERY = """
(await_expression) @await_expr
"""

# JavaScript: promise chains (.then/.catch/.finally)
_JS_PROMISE_CHAIN_QUERY = """
(call_expression
    function: (member_expression
        object: (call_expression) @chain_object
        property: (property_identifier) @chain_method)
    ) @promise_chain
"""

# JavaScript: new Promise without catch
_JS_NEW_PROMISE_QUERY = """
(new_expression
    constructor: (identifier) @promise_ctor
    arguments: (arguments) @promise_args) @new_promise
"""

# Go: goroutine statements
_GO_GOROUTINE_QUERY = """
(go_statement) @goroutine
"""

# Go: channel operations
_GO_CHANNEL_QUERY = """
(send_statement) @channel_send
"""

_GO_RECEIVE_QUERY = """
(receive_statement) @channel_receive
"""

# Go: select statements
_GO_SELECT_QUERY = """
(select_statement) @select
"""

class AsyncPatternAnalyzer(BaseAnalyzer):
    """Analyze async/await patterns in source code."""

    _LANGUAGE_NAMES: dict[str, str] = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".jsx": "javascript",
        ".java": "java",
        ".go": "go",
    }

    def analyze_file(self, file_path: str | Path) -> AsyncPatternResult:
        """Analyze a single file for async patterns."""
        file_path = Path(file_path)
        ext = file_path.suffix.lower()

        if ext not in self.SUPPORTED_EXTENSIONS:
            return AsyncPatternResult(
                file_path=str(file_path),
                language="unknown",
            )

        language = self._LANGUAGE_NAMES.get(ext, "unknown")
        source = file_path.read_bytes()

        language_obj, parser = self._get_parser(ext)
        if language_obj is None or parser is None:
            return AsyncPatternResult(
                file_path=str(file_path),
                language=language,
            )

        tree = parser.parse(source)

        result = AsyncPatternResult(
            file_path=str(file_path),
            language=language,
        )

        dispatch = {
            ".py": self._analyze_python,
            ".js": self._analyze_javascript,
            ".ts": self._analyze_javascript,
            ".tsx": self._analyze_javascript,
            ".jsx": self._analyze_javascript,
            ".java": self._analyze_java,
            ".go": self._analyze_go,
        }

        analyzer = dispatch.get(ext)
        if analyzer:
            analyzer(tree, source, str(file_path), language_obj, result)

        return result

    def _get_text(self, node: tree_sitter.Node, source: bytes) -> str:
        """Extract text from a node."""
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _get_line_col(self, node: tree_sitter.Node) -> tuple[int, int]:
        """Get line and column for a node."""
        return node.start_point.row + 1, node.start_point.column + 1

    # --- Python analysis ---

    def _analyze_python(
        self,
        tree: Tree,
        source: bytes,
        file_path: str,
        language: Any,
        result: AsyncPatternResult,
    ) -> None:
        """Analyze Python async patterns."""
        root = tree.root_node

        # Find all async functions
        async_funcs = TreeSitterQueryCompat.execute_query(
            language, _PYTHON_ASYNC_FUNC_QUERY, root,
        )

        # Find all await expressions
        await_exprs = TreeSitterQueryCompat.execute_query(
            language, _PYTHON_AWAIT_QUERY, root,
        )
        result.total_await_expressions = sum(
            1 for _, name in await_exprs if name == "await_expr"
        )

        # Track async functions by their name
        async_func_nodes: list[tuple[tree_sitter.Node, str]] = []
        for node, capture_name in async_funcs:
            if capture_name == "async_function":
                name_node = node.child_by_field_name("name")
                func_name = self._get_text(name_node, source) if name_node else "<anonymous>"
                async_func_nodes.append((node, func_name))

        result.total_async_functions = len(async_func_nodes)

        # Check: async functions without await
        for func_node, func_name in async_func_nodes:
            body_node = func_node.child_by_field_name("body")
            if body_node is None:
                continue

            has_await = self._node_contains_type(body_node, "await")
            if not has_await:
                line, col = self._get_line_col(func_node)
                result.patterns.append(
                    AsyncPatternMatch(
                        pattern_type=AsyncPatternType.ASYNC_WITHOUT_AWAIT,
                        severity=PatternSeverity.WARNING,
                        file_path=file_path,
                        line=line,
                        column=col,
                        message=f"Async function '{func_name}' has no await expressions",
                        function_name=func_name,
                        language="python",
                        suggestion="Add await expressions or remove async keyword",
                    ),
                )

        # Check: potential missing await on async function calls
        # Find function calls that are NOT awaited
        all_calls = TreeSitterQueryCompat.execute_query(
            language, _PYTHON_CALL_QUERY, root,
        )
        self._check_python_missing_await(
            all_calls, source, file_path, async_func_nodes, result,
        )

        attr_calls = TreeSitterQueryCompat.execute_query(
            language, _PYTHON_ATTR_CALL_QUERY, root,
        )
        self._check_python_missing_await(
            attr_calls, source, file_path, async_func_nodes, result,
        )

    def _check_python_missing_await(
        self,
        calls: list[tuple[tree_sitter.Node, str]],
        source: bytes,
        file_path: str,
        async_func_nodes: list[tuple[tree_sitter.Node, str]],
        result: AsyncPatternResult,
    ) -> None:
        """Check for missing await on calls within async functions."""
        await_names = {
            "asyncio.sleep", "asyncio.gather", "asyncio.wait",
            "asyncio.create_task", "asyncio.run",
            "aiohttp", "httpx", "aioredis",
        }

        for call_node, capture_name in calls:
            if capture_name not in ("call_expr", "attr_call"):
                continue

            # Skip if already awaited
            parent = call_node.parent
            if parent and parent.type == "await":
                continue

            # Check if inside an async function
            enclosing_async = self._find_enclosing_async(
                call_node, async_func_nodes,
            )
            if enclosing_async is None:
                continue

            func_name = self._get_text(
                call_node.child_by_field_name("function") or call_node, source,
            ).strip()

            # Check common async patterns
            is_likely_async = False
            for pattern in await_names:
                if pattern in func_name:
                    is_likely_async = True
                    break

            if is_likely_async:
                line, col = self._get_line_col(call_node)
                result.patterns.append(
                    AsyncPatternMatch(
                        pattern_type=AsyncPatternType.MISSING_AWAIT,
                        severity=PatternSeverity.ERROR,
                        file_path=file_path,
                        line=line,
                        column=col,
                        message=f"Possible missing await on async call: {func_name}",
                        function_name=enclosing_async[1],
                        language="python",
                        suggestion=f"Add 'await' before '{func_name}'",
                    ),
                )

    def _find_enclosing_async(
        self,
        node: tree_sitter.Node,
        async_funcs: list[tuple[tree_sitter.Node, str]],
    ) -> tuple[tree_sitter.Node, str] | None:
        """Find the enclosing async function for a node."""
        current = node.parent
        while current:
            for func_node, func_name in async_funcs:
                if current.id == func_node.id:
                    return (func_node, func_name)
            current = current.parent
        return None

    # --- JavaScript/TypeScript analysis ---

    def _analyze_javascript(
        self,
        tree: Tree,
        source: bytes,
        file_path: str,
        language: Any,
        result: AsyncPatternResult,
    ) -> None:
        """Analyze JavaScript/TypeScript async patterns."""
        root = tree.root_node

        # Find async functions
        async_funcs = TreeSitterQueryCompat.execute_query(
            language, _JS_ASYNC_FUNC_QUERY, root,
        )
        async_arrows = TreeSitterQueryCompat.execute_query(
            language, _JS_ASYNC_ARROW_QUERY, root,
        )

        async_func_nodes: list[tuple[tree_sitter.Node, str]] = []
        for node, capture_name in async_funcs:
            if capture_name == "async_function":
                name_node = node.child_by_field_name("name")
                func_name = self._get_text(name_node, source) if name_node else "<anonymous>"
                async_func_nodes.append((node, func_name))

        for node, capture_name in async_arrows:
            if capture_name == "async_arrow":
                async_func_nodes.append((node, "<arrow>"))

        result.total_async_functions = len(async_func_nodes)

        # Find await expressions
        await_exprs = TreeSitterQueryCompat.execute_query(
            language, _JS_AWAIT_QUERY, root,
        )
        result.total_await_expressions = len(await_exprs)

        # Check: async functions without await
        for func_node, func_name in async_func_nodes:
            body_node = func_node.child_by_field_name("body")
            if body_node is None:
                continue

            has_await = self._node_contains_type(body_node, "await_expression")
            if not has_await:
                line, col = self._get_line_col(func_node)
                result.patterns.append(
                    AsyncPatternMatch(
                        pattern_type=AsyncPatternType.ASYNC_WITHOUT_AWAIT,
                        severity=PatternSeverity.WARNING,
                        file_path=file_path,
                        line=line,
                        column=col,
                        message=f"Async function '{func_name}' has no await expressions",
                        function_name=func_name,
                        language="javascript",
                        suggestion="Add await expressions or remove async keyword",
                    ),
                )

        # Check: unhandled promises (new Promise without .catch)
        new_promises = TreeSitterQueryCompat.execute_query(
            language, _JS_NEW_PROMISE_QUERY, root,
        )
        self._check_js_unhandled_promises(
            new_promises, source, file_path, result,
        )

        # Check: promise chain mixing (.then mixed with async/await)
        promise_chains = TreeSitterQueryCompat.execute_query(
            language, _JS_PROMISE_CHAIN_QUERY, root,
        )
        if promise_chains and result.total_async_functions > 0:
            for node, _ in promise_chains[:3]:
                line, col = self._get_line_col(node)
                result.patterns.append(
                    AsyncPatternMatch(
                        pattern_type=AsyncPatternType.PROMISE_CHAIN_MIX,
                        severity=PatternSeverity.INFO,
                        file_path=file_path,
                        line=line,
                        column=col,
                        message="Mixing promise chains (.then) with async/await style",
                        function_name="<scope>",
                        language="javascript",
                        suggestion="Use consistent style: prefer async/await over .then chains",
                    ),
                )

    def _check_js_unhandled_promises(
        self,
        promises: list[tuple[tree_sitter.Node, str]],
        source: bytes,
        file_path: str,
        result: AsyncPatternResult,
    ) -> None:
        """Check for unhandled promise rejections."""
        for node, capture_name in promises:
            if capture_name != "new_promise":
                continue

            ctor_node = node.child_by_field_name("constructor")
            if ctor_node is None:
                continue

            ctor_text = self._get_text(ctor_node, source)
            if ctor_text != "Promise":
                continue

            # Check if parent has .catch
            parent = node.parent
            has_catch = False
            if parent:
                parent_text = self._get_text(parent, source)
                if ".catch" in parent_text:
                    has_catch = True

            if not has_catch:
                line, col = self._get_line_col(node)
                result.patterns.append(
                    AsyncPatternMatch(
                        pattern_type=AsyncPatternType.UNHANDLED_PROMISE,
                        severity=PatternSeverity.WARNING,
                        file_path=file_path,
                        line=line,
                        column=col,
                        message="new Promise without .catch() handler",
                        function_name="<scope>",
                        language="javascript",
                        suggestion="Add .catch() handler or use try/catch with await",
                    ),
                )

    # --- Java analysis ---

    def _analyze_java(
        self,
        tree: Tree,
        source: bytes,
        file_path: str,
        language: Any,
        result: AsyncPatternResult,
    ) -> None:
        """Analyze Java async patterns."""
        root = tree.root_node

        # Find @Async annotated methods
        query_str = """
        (method_declaration
            (modifiers
                (marker_annotation
                    (identifier) @annotation_name))
            name: (identifier) @method_name) @async_method
        """
        async_methods = TreeSitterQueryCompat.execute_query(
            language, query_str, root,
        )

        for node, capture_name in async_methods:
            if capture_name == "async_method":
                name_node = node.child_by_field_name("name")
                func_name = self._get_text(name_node, source) if name_node else "<method>"
                result.total_async_functions += 1

                body_node = node.child_by_field_name("body")
                if body_node is None:
                    continue

                body_text = self._get_text(body_node, source)

                # Check: @Async method returning void (fire-and-forget)
                type_node = node.child_by_field_name("type")
                if type_node:
                    return_type = self._get_text(type_node, source).strip()
                    if return_type == "void":
                        line, col = self._get_line_col(node)
                        result.patterns.append(
                            AsyncPatternMatch(
                                pattern_type=AsyncPatternType.FIRE_AND_FORGET,
                                severity=PatternSeverity.INFO,
                                file_path=file_path,
                                line=line,
                                column=col,
                                message=f"@Async method '{func_name}' returns void — fire-and-forget",
                                function_name=func_name,
                                language="java",
                                suggestion="Return CompletableFuture<Void> for better error handling",
                            ),
                        )

                # Check: blocking operations in @Async methods
                blocking_patterns = [
                    "Thread.sleep", "Object.wait", ".get()",
                    "CountDownLatch.await",
                ]
                for pattern in blocking_patterns:
                    if pattern in body_text:
                        line, col = self._get_line_col(node)
                        result.patterns.append(
                            AsyncPatternMatch(
                                pattern_type=AsyncPatternType.BLOCKING_IN_ASYNC,
                                severity=PatternSeverity.WARNING,
                                file_path=file_path,
                                line=line,
                                column=col,
                                message=f"@Async method '{func_name}' contains blocking call: {pattern}",
                                function_name=func_name,
                                language="java",
                                suggestion="Avoid blocking in async methods; use CompletableFuture chaining",
                            ),
                        )
                        break

    # --- Go analysis ---

    def _analyze_go(
        self,
        tree: Tree,
        source: bytes,
        file_path: str,
        language: Any,
        result: AsyncPatternResult,
    ) -> None:
        """Analyze Go concurrency patterns."""
        root = tree.root_node

        # Find goroutines
        goroutines = TreeSitterQueryCompat.execute_query(
            language, _GO_GOROUTINE_QUERY, root,
        )
        result.total_goroutines = len(goroutines)

        for node, capture_name in goroutines:
            if capture_name != "goroutine":
                continue

            # Check: bare goroutine (fire-and-forget)
            # Goroutines without recover() or WaitGroup are potential leaks
            line, col = self._get_line_col(node)

            # Simple heuristic: if goroutine call is just a function call
            # without context management, flag it
            result.patterns.append(
                AsyncPatternMatch(
                    pattern_type=AsyncPatternType.FIRE_AND_FORGET,
                    severity=PatternSeverity.INFO,
                    file_path=file_path,
                    line=line,
                    column=col,
                    message="Fire-and-forget goroutine — no WaitGroup or context visible",
                    function_name="<goroutine>",
                    language="go",
                    suggestion="Use sync.WaitGroup or context.Context to manage goroutine lifecycle",
                ),
            )

        # Find channel operations without select
        channels = TreeSitterQueryCompat.execute_query(
            language, _GO_CHANNEL_QUERY, root,
        )
        receives = TreeSitterQueryCompat.execute_query(
            language, _GO_RECEIVE_QUERY, root,
        )
        selects = TreeSitterQueryCompat.execute_query(
            language, _GO_SELECT_QUERY, root,
        )

        # If there are channel operations but no select, flag it
        if (channels or receives) and not selects:
            for node, _ in channels[:2]:
                line, col = self._get_line_col(node)
                result.patterns.append(
                    AsyncPatternMatch(
                        pattern_type=AsyncPatternType.UNCHECKED_CHANNEL,
                        severity=PatternSeverity.INFO,
                        file_path=file_path,
                        line=line,
                        column=col,
                        message="Channel send without select — potential deadlock",
                        function_name="<channel>",
                        language="go",
                        suggestion="Use select statement for non-blocking channel operations",
                    ),
                )

    # --- Utilities ---

    def _node_contains_type(self, node: tree_sitter.Node, type_name: str) -> bool:
        """Check if a node tree contains a node of the given type."""
        if node.type == type_name:
            return True
        for child in node.children:
            if self._node_contains_type(child, type_name):
                return True
        return False
