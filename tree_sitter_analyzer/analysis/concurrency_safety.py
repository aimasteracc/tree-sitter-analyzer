"""
Concurrency Safety Analyzer.

Detects concurrency bugs in source code: shared mutable state
accessed without synchronization, unsafe concurrent access patterns,
missing synchronization primitives, and check-then-act race conditions.

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

if TYPE_CHECKING:
    pass

logger = setup_logger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go",
}

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_SHARED_MUTABLE = "shared_mutable_state"
ISSUE_UNSAFE_CONCURRENT = "unsafe_concurrent_access"
ISSUE_MISSING_SYNC = "missing_sync_primitive"
ISSUE_CHECK_THEN_ACT = "check_then_act"

def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""

@dataclass(frozen=True)
class ConcurrencyIssue:
    """A single concurrency safety issue found in code."""

    line: int
    issue_type: str
    severity: str
    variable: str
    description: str
    suggestion: str

@dataclass(frozen=True)
class ConcurrencyResult:
    """Aggregated concurrency safety analysis result for a file."""

    issues: tuple[ConcurrencyIssue, ...]
    total_issues: int
    high_severity: int
    medium_severity: int
    low_severity: int
    file_path: str
    language: str

    def to_dict(self) -> dict[str, object]:
        return {
            "file_path": self.file_path,
            "language": self.language,
            "total_issues": self.total_issues,
            "high_severity": self.high_severity,
            "medium_severity": self.medium_severity,
            "low_severity": self.low_severity,
            "issues": [
                {
                    "line": i.line,
                    "issue_type": i.issue_type,
                    "severity": i.severity,
                    "variable": i.variable,
                    "description": i.description,
                    "suggestion": i.suggestion,
                }
                for i in self.issues
            ],
        }

def _empty_result(file_path: str, language: str) -> ConcurrencyResult:
    return ConcurrencyResult(
        issues=(),
        total_issues=0,
        high_severity=0,
        medium_severity=0,
        low_severity=0,
        file_path=file_path,
        language=language,
    )

def _severity_counts(issues: tuple[ConcurrencyIssue, ...]) -> tuple[int, int, int]:
    high = sum(1 for i in issues if i.severity == SEVERITY_HIGH)
    medium = sum(1 for i in issues if i.severity == SEVERITY_MEDIUM)
    low = sum(1 for i in issues if i.severity == SEVERITY_LOW)
    return high, medium, low

class ConcurrencySafetyAnalyzer(BaseAnalyzer):
    """Analyzes source code for concurrency safety issues."""

    def analyze_file(self, file_path: Path | str) -> ConcurrencyResult:
        path = Path(file_path)
        if not path.exists():
            return _empty_result(str(path), "unknown")

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return _empty_result(str(path), "unknown")

        language_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".tsx": "typescript", ".jsx": "javascript", ".java": "java",
            ".go": "go",
        }
        language = language_map.get(ext, "unknown")

        source = path.read_text(encoding="utf-8", errors="replace")
        language_obj, parser = self._get_parser(ext)
        if language_obj is None or parser is None:
            return _empty_result(str(path), language)

        tree = parser.parse(source.encode("utf-8"))
        issues: list[ConcurrencyIssue] = []

        if ext == ".py":
            issues.extend(self._analyze_python(tree.root_node, source))
        elif ext in (".js", ".ts", ".tsx", ".jsx"):
            issues.extend(self._analyze_javascript(tree.root_node, source))
        elif ext == ".java":
            issues.extend(self._analyze_java(tree.root_node, source))
        elif ext == ".go":
            issues.extend(self._analyze_go(tree.root_node, source))

        issue_tuple = tuple(issues)
        high, medium, low = _severity_counts(issue_tuple)
        return ConcurrencyResult(
            issues=issue_tuple,
            total_issues=len(issues),
            high_severity=high,
            medium_severity=medium,
            low_severity=low,
            file_path=str(path),
            language=language,
        )

    # ── Python ──────────────────────────────────────────────

    def _analyze_python(
        self, root: tree_sitter.Node, source: str
    ) -> list[ConcurrencyIssue]:
        issues: list[ConcurrencyIssue] = []
        issues.extend(self._python_shared_mutable(root, source))
        issues.extend(self._python_missing_sync(root, source))
        issues.extend(self._python_check_then_act(root, source))
        issues.extend(self._python_unsafe_concurrent(root, source))
        return issues

    def _python_shared_mutable(
        self, root: tree_sitter.Node, source: str
    ) -> list[ConcurrencyIssue]:
        issues: list[ConcurrencyIssue] = []

        concurrency_keywords = {
            "threading", "multiprocessing", "Thread", "Process",
            "Lock", "RLock", "Semaphore", "Event", "Condition",
            "ThreadPoolExecutor", "ProcessPoolExecutor", "asyncio",
        }

        for node in self._walk(root):
            if node.type != "class_definition":
                continue
            body_node = node.child_by_field_name("body")
            if body_node is None:
                continue

            body_text = _txt(body_node)
            has_concurrency = any(kw in body_text for kw in concurrency_keywords)
            if not has_concurrency:
                continue

            class_attrs = self._collect_python_class_attrs(body_node)
            sync_names = self._collect_python_sync_names(body_text)

            for child in self._walk(body_node):
                if child.type != "assignment":
                    continue
                left = child.child_by_field_name("left")
                if left is None:
                    continue
                var_name = _txt(left)
                if var_name in class_attrs:
                    continue
                if var_name.startswith("self."):
                    attr_name = var_name[5:]
                    if attr_name in class_attrs and attr_name not in sync_names:
                        issues.append(ConcurrencyIssue(
                            line=child.start_point[0] + 1,
                            issue_type=ISSUE_SHARED_MUTABLE,
                            severity=SEVERITY_HIGH,
                            variable=var_name,
                            description=(
                                f"Shared class attribute '{attr_name}' "
                                f"modified in concurrent context without "
                                f"synchronization"
                            ),
                            suggestion=(
                                f"Protect '{attr_name}' with threading.Lock "
                                f"or use queue.Queue for thread-safe access"
                            ),
                        ))
        return issues

    def _python_missing_sync(
        self, root: tree_sitter.Node, source: str
    ) -> list[ConcurrencyIssue]:
        issues: list[ConcurrencyIssue] = []
        lines = source.split("\n")
        thread_launch_pattern = re.compile(
            r"(Thread|Process)\s*\(\s*target\s*="
        )
        lock_pattern = re.compile(
            r"(Lock|RLock|Semaphore|Condition)\s*\(\s*\)"
        )

        for i, line in enumerate(lines):
            if thread_launch_pattern.search(line):
                context = "\n".join(lines[max(0, i - 10):i + 1])
                if not lock_pattern.search(context):
                    issues.append(ConcurrencyIssue(
                        line=i + 1,
                        issue_type=ISSUE_MISSING_SYNC,
                        severity=SEVERITY_MEDIUM,
                        variable="",
                        description=(
                            "Thread/Process launched without synchronization "
                            "primitive in surrounding context"
                        ),
                        suggestion=(
                            "Create a threading.Lock() before thread launch "
                            "and use it to guard shared state"
                        ),
                    ))
        return issues

    def _python_check_then_act(
        self, root: tree_sitter.Node, source: str
    ) -> list[ConcurrencyIssue]:
        issues: list[ConcurrencyIssue] = []
        lines = source.split("\n")
        check_pattern = re.compile(r"if\s+(\w+(?:\.\w+)*)\s*(?:==|!=|is|is not)")
        modify_pattern = re.compile(
            r"(?:self\.\w+|\w+)\s*[\+\-\*\/]?=(?!=)"
        )

        for i in range(len(lines) - 1):
            check_match = check_pattern.search(lines[i])
            if not check_match:
                continue
            var = check_match.group(1).strip()
            next_lines = lines[i + 1:min(i + 4, len(lines))]
            for _idx, next_line in enumerate(next_lines):
                if modify_pattern.search(next_line) and var in next_line:
                    issues.append(ConcurrencyIssue(
                        line=i + 1,
                        issue_type=ISSUE_CHECK_THEN_ACT,
                        severity=SEVERITY_MEDIUM,
                        variable=var,
                        description=(
                            f"Check-then-act on '{var}': condition check "
                            f"followed by modification without atomicity"
                        ),
                        suggestion=(
                            "Use threading.Lock to make the check-and-modify "
                            "atomic, or use queue.Queue"
                        ),
                    ))
                    break
        return issues

    def _python_unsafe_concurrent(
        self, root: tree_sitter.Node, source: str
    ) -> list[ConcurrencyIssue]:
        issues: list[ConcurrencyIssue] = []
        lines = source.split("\n")
        mutable_types = {"list(", "dict(", "set(", "[]", "{}"}
        concurrent_keywords = {"Thread(", "Process(", "threading.", "multiprocessing."}

        for i, line in enumerate(lines):
            has_mutable = any(m in line for m in mutable_types)
            if not has_mutable:
                continue
            context = "\n".join(lines[max(0, i - 5):min(len(lines), i + 15)])
            has_concurrent = any(k in context for k in concurrent_keywords)
            has_lock = "Lock" in context or "lock" in context
            if has_concurrent and not has_lock:
                issues.append(ConcurrencyIssue(
                    line=i + 1,
                    issue_type=ISSUE_UNSAFE_CONCURRENT,
                    severity=SEVERITY_HIGH,
                    variable="",
                    description=(
                        "Mutable data structure created near thread/process "
                        "launch without lock protection"
                    ),
                    suggestion=(
                        "Wrap mutable data in threading.Lock or use "
                        "queue.Queue for thread-safe communication"
                    ),
                ))
        return issues

    def _collect_python_class_attrs(self, class_body: tree_sitter.Node) -> set[str]:
        attrs: set[str] = set()
        for node in self._walk(class_body):
            if node.type == "assignment":
                left = node.child_by_field_name("left")
                if left is None:
                    continue
                txt = _txt(left)
                if txt.startswith("self."):
                    attr_name = txt[5:]
                    if "." not in attr_name:
                        attrs.add(attr_name)
        return attrs

    def _collect_python_sync_names(self, body_text: str) -> set[str]:
        sync_names: set[str] = set()
        pattern = re.compile(r"self\.(\w+)\s*=\s*(?:threading\.)?(?:Lock|RLock)")
        for m in pattern.finditer(body_text):
            sync_names.add(m.group(1))
        lock_assign = re.compile(r"(\w+)\s*=\s*(?:threading\.)?(?:Lock|RLock)\s*\(\s*\)")
        for m in lock_assign.finditer(body_text):
            sync_names.add(m.group(1))
        return sync_names

    # ── JavaScript/TypeScript ──────────────────────────────

    def _analyze_javascript(
        self, root: tree_sitter.Node, source: str
    ) -> list[ConcurrencyIssue]:
        issues: list[ConcurrencyIssue] = []
        issues.extend(self._js_shared_mutable(root, source))
        issues.extend(self._js_missing_sync(root, source))
        issues.extend(self._js_check_then_act(root, source))
        return issues

    def _js_shared_mutable(
        self, root: tree_sitter.Node, source: str
    ) -> list[ConcurrencyIssue]:
        issues: list[ConcurrencyIssue] = []
        lines = source.split("\n")
        mutable_decl = re.compile(
            r"(?:let|var)\s+(\w+)\s*=\s*(?:new\s+(?:Map|Set|Array|Object)|\[|\{)"
        )
        async_pattern = re.compile(r"(?:async\s+function|await\s+|\.then\(|setInterval|setTimeout)")

        for i, line in enumerate(lines):
            decl_match = mutable_decl.search(line)
            if not decl_match:
                continue
            var_name = decl_match.group(1)
            context = lines[i:min(len(lines), i + 20)]
            context_text = "\n".join(context)
            if not async_pattern.search(context_text):
                continue
            modify_re = re.compile(
                rf"\b{re.escape(var_name)}\b\s*[\+\-\*]?="
            )
            for j, ctx_line in enumerate(context):
                if j == 0:
                    continue
                if modify_re.search(ctx_line):
                    issues.append(ConcurrencyIssue(
                        line=i + j + 1,
                        issue_type=ISSUE_SHARED_MUTABLE,
                        severity=SEVERITY_HIGH,
                        variable=var_name,
                        description=(
                            f"Shared mutable variable '{var_name}' "
                            f"modified in async context"
                        ),
                        suggestion=(
                            "Use immutable patterns or ensure single-writer "
                            "discipline for async state"
                        ),
                    ))
                    break
        return issues

    def _js_missing_sync(
        self, root: tree_sitter.Node, source: str
    ) -> list[ConcurrencyIssue]:
        issues: list[ConcurrencyIssue] = []
        lines = source.split("\n")
        promise_all = re.compile(r"Promise\.all\s*\(")

        for i, line in enumerate(lines):
            if not promise_all.search(line):
                continue
            context = "\n".join(lines[i:min(len(lines), i + 10)])
            if "catch" not in context and ".catch" not in context:
                issues.append(ConcurrencyIssue(
                    line=i + 1,
                    issue_type=ISSUE_MISSING_SYNC,
                    severity=SEVERITY_MEDIUM,
                    variable="Promise.all",
                    description=(
                        "Promise.all without error handling: one rejection "
                        "kills the entire batch"
                    ),
                    suggestion=(
                        "Use Promise.allSettled() or add .catch() to handle "
                        "partial failures"
                    ),
                ))
        return issues

    def _js_check_then_act(
        self, root: tree_sitter.Node, source: str
    ) -> list[ConcurrencyIssue]:
        issues: list[ConcurrencyIssue] = []
        lines = source.split("\n")
        check_pattern = re.compile(
            r"if\s*\(\s*(\w+(?:\.\w+)*)\s*(?:===|!==|==|!=)"
        )
        modify_pattern = re.compile(r"(\w+(?:\.\w+)*)\s*[\+\-\*]?=(?!=)")

        for i in range(len(lines) - 1):
            check_match = check_pattern.search(lines[i])
            if not check_match:
                continue
            var = check_match.group(1).strip()
            if "await" not in "\n".join(lines[i:min(len(lines), i + 5)]):
                continue
            next_lines = lines[i + 1:min(i + 4, len(lines))]
            for next_line in next_lines:
                mod_match = modify_pattern.search(next_line)
                if mod_match and var in next_line:
                    issues.append(ConcurrencyIssue(
                        line=i + 1,
                        issue_type=ISSUE_CHECK_THEN_ACT,
                        severity=SEVERITY_MEDIUM,
                        variable=var,
                        description=(
                            f"TOCTOU: '{var}' checked then modified across "
                            f"await boundary"
                        ),
                        suggestion=(
                            "Use atomic operations or lock the check-and-modify "
                            "in a single async block"
                        ),
                    ))
                    break
        return issues

    # ── Java ────────────────────────────────────────────────

    def _analyze_java(
        self, root: tree_sitter.Node, source: str
    ) -> list[ConcurrencyIssue]:
        issues: list[ConcurrencyIssue] = []
        issues.extend(self._java_shared_mutable(root, source))
        issues.extend(self._java_missing_sync(root, source))
        issues.extend(self._java_check_then_act(root, source))
        return issues

    def _java_shared_mutable(
        self, root: tree_sitter.Node, source: str
    ) -> list[ConcurrencyIssue]:
        issues: list[ConcurrencyIssue] = []
        lines = source.split("\n")
        field_pattern = re.compile(
            r"private\s+(?:static\s+)?(?:final\s+)?"
            r"(?:List|Map|Set|HashMap|ArrayList|LinkedList|HashSet)"
            r"<[^>]*>\s+(\w+)\s*[;=]"
        )
        runnable_pattern = re.compile(
            r"(?:Runnable|Callable|Thread|CompletableFuture|ExecutorService|"
            r"@Async|synchronized)"
        )

        class_ranges: list[tuple[int, int]] = []
        for i, line in enumerate(lines):
            if re.search(r"\bclass\s+\w+", line):
                start = i
                brace_count = 0
                for j in range(i, len(lines)):
                    brace_count += lines[j].count("{") - lines[j].count("}")
                    if brace_count <= 0 and j > i:
                        class_ranges.append((start, j))
                        break

        for class_start, class_end in class_ranges:
            class_text = "\n".join(lines[class_start:class_end + 1])
            if not runnable_pattern.search(class_text):
                continue

            for i in range(class_start, class_end + 1):
                field_match = field_pattern.search(lines[i])
                if field_match is None:
                    continue
                var_name = field_match.group(1)
                if "Collections.synchronized" in lines[i]:
                    continue
                if "ConcurrentHashMap" in lines[i]:
                    continue
                if "volatile" in lines[i]:
                    continue

                issues.append(ConcurrencyIssue(
                    line=i + 1,
                    issue_type=ISSUE_SHARED_MUTABLE,
                    severity=SEVERITY_HIGH,
                    variable=var_name,
                    description=(
                        f"Non-thread-safe collection '{var_name}' in class "
                        f"with concurrent access patterns"
                    ),
                    suggestion=(
                        "Use ConcurrentHashMap, Collections.synchronizedList(), "
                        "or CopyOnWriteArrayList"
                    ),
                ))
        return issues

    def _java_missing_sync(
        self, root: tree_sitter.Node, source: str
    ) -> list[ConcurrencyIssue]:
        issues: list[ConcurrencyIssue] = []
        lines = source.split("\n")
        double_check = re.compile(
            r"if\s*\(\s*(\w+)\s*==\s*null\s*\)"
        )

        for i in range(len(lines) - 3):
            check_match = double_check.search(lines[i])
            if check_match is None:
                continue
            var = check_match.group(1)
            next_block = "\n".join(lines[i + 1:min(len(lines), i + 5)])
            if "synchronized" in next_block:
                inner = "\n".join(lines[i + 2:min(len(lines), i + 6)])
                if f"{var} ==" in inner or f"{var} ==" in inner:
                    field_line = None
                    for j in range(max(0, i - 20), i):
                        if var in lines[j] and "volatile" not in lines[j]:
                            field_line = j + 1
                    if field_line is not None:
                        issues.append(ConcurrencyIssue(
                            line=field_line,
                            issue_type=ISSUE_MISSING_SYNC,
                            severity=SEVERITY_MEDIUM,
                            variable=var,
                            description=(
                                f"Double-checked locking on '{var}' without "
                                f"volatile: broken in Java"
                            ),
                            suggestion=(
                                f"Declare '{var}' as volatile to ensure "
                                f"correct double-checked locking"
                            ),
                        ))
        return issues

    def _java_check_then_act(
        self, root: tree_sitter.Node, source: str
    ) -> list[ConcurrencyIssue]:
        issues: list[ConcurrencyIssue] = []
        lines = source.split("\n")
        check_pattern = re.compile(
            r"if\s*\(\s*(!?\s*\w+(?:\.\w+\(\))?)\s*\)"
        )
        concurrent_methods = {"run(", "call(", "submit(", "execute("}

        for i in range(len(lines) - 1):
            check_match = check_pattern.search(lines[i])
            if check_match is None:
                continue
            var = check_match.group(1).strip().lstrip("!")
            context = "\n".join(lines[max(0, i - 5):i + 5])
            in_concurrent = any(m in context for m in concurrent_methods)
            if not in_concurrent:
                continue
            next_lines = lines[i + 1:min(i + 4, len(lines))]
            for next_line in next_lines:
                if var in next_line and (
                    "=" in next_line or ".add(" in next_line
                    or ".put(" in next_line or ".remove(" in next_line
                ):
                    issues.append(ConcurrencyIssue(
                        line=i + 1,
                        issue_type=ISSUE_CHECK_THEN_ACT,
                        severity=SEVERITY_MEDIUM,
                        variable=var,
                        description=(
                            f"Check-then-act on '{var}' in concurrent method "
                            f"without synchronization"
                        ),
                        suggestion=(
                            "Wrap check-and-modify in synchronized block "
                            "or use AtomicBoolean/AtomicReference"
                        ),
                    ))
                    break
        return issues

    # ── Go ──────────────────────────────────────────────────

    def _analyze_go(
        self, root: tree_sitter.Node, source: str
    ) -> list[ConcurrencyIssue]:
        issues: list[ConcurrencyIssue] = []
        issues.extend(self._go_shared_mutable(root, source))
        issues.extend(self._go_missing_sync(root, source))
        issues.extend(self._go_check_then_act(root, source))
        return issues

    def _go_shared_mutable(
        self, root: tree_sitter.Node, source: str
    ) -> list[ConcurrencyIssue]:
        issues: list[ConcurrencyIssue] = []
        lines = source.split("\n")
        goroutine_pattern = re.compile(r"go\s+(?:func|\w+\()")
        var_assign = re.compile(r"(\w+)\s*:?=(?!=)")
        map_literal = re.compile(r"map\[")

        goroutine_lines: set[int] = set()
        for i, line in enumerate(lines):
            if goroutine_pattern.search(line):
                goroutine_lines.add(i)

        for gline in goroutine_lines:
            context_start = max(0, gline - 15)
            context_end = min(len(lines), gline + 20)
            context = lines[context_start:context_end]
            has_mutex = any(
                "mutex" in line.lower() or "Mutex" in line
                for line in context
            )
            has_channel = any(
                "<-" in line or "chan " in line for line in context
            )

            if has_mutex or has_channel:
                continue

            for j, ctx_line in enumerate(context):
                if map_literal.search(ctx_line) and "sync." not in ctx_line:
                    actual_line = context_start + j + 1
                    issues.append(ConcurrencyIssue(
                        line=actual_line,
                        issue_type=ISSUE_UNSAFE_CONCURRENT,
                        severity=SEVERITY_HIGH,
                        variable="",
                        description=(
                            "Map used near goroutine without mutex or "
                            "channel protection"
                        ),
                        suggestion=(
                            "Use sync.RWMutex to protect map access, or "
                            "communicate via channels instead"
                        ),
                    ))
                    break

            for j, ctx_line in enumerate(context):
                assign_match = var_assign.search(ctx_line)
                if assign_match is None:
                    continue
                var_name = assign_match.group(1)
                if var_name.startswith("_") or var_name in (
                    "err", "ok", "true", "false", "nil",
                ):
                    continue
                if gline != context_start + j:
                    issues.append(ConcurrencyIssue(
                        line=context_start + j + 1,
                        issue_type=ISSUE_SHARED_MUTABLE,
                        severity=SEVERITY_HIGH,
                        variable=var_name,
                        description=(
                            f"Variable '{var_name}' accessed near goroutine "
                            f"without synchronization"
                        ),
                        suggestion=(
                            "Protect with sync.Mutex, sync.RWMutex, or "
                            "use channels for communication"
                        ),
                    ))
                    break
        return issues

    def _go_missing_sync(
        self, root: tree_sitter.Node, source: str
    ) -> list[ConcurrencyIssue]:
        issues: list[ConcurrencyIssue] = []
        lines = source.split("\n")
        wg_add = re.compile(r"(\w+)\.Add\s*\(\s*1\s*\)")
        goroutine_launch = re.compile(r"go\s+func")
        goroutine_close = re.compile(r"\}\)\(\)")

        goroutine_starts: list[int] = []
        goroutine_ends: list[int] = []
        brace_depth = 0
        in_goroutine = False
        for i, line in enumerate(lines):
            if goroutine_launch.search(line):
                in_goroutine = True
                brace_depth = 0
                goroutine_starts.append(i)
            if in_goroutine:
                brace_depth += line.count("{") - line.count("}")
                if brace_depth <= 0 or goroutine_close.search(line):
                    goroutine_ends.append(i)
                    in_goroutine = False

        for i, line in enumerate(lines):
            add_match = wg_add.search(line)
            if add_match is None:
                continue
            wg_name = add_match.group(1)
            for gstart, _gend in zip(
                goroutine_starts,
                goroutine_ends + [len(lines)] * max(0, len(goroutine_starts) - len(goroutine_ends)),
                strict=False,
            ):
                if gstart < i:
                    issues.append(ConcurrencyIssue(
                        line=i + 1,
                        issue_type=ISSUE_MISSING_SYNC,
                        severity=SEVERITY_MEDIUM,
                        variable=wg_name,
                        description=(
                            f"WaitGroup '{wg_name}.Add(1)' inside "
                            f"goroutine: should be called before 'go func'"
                        ),
                        suggestion=(
                            f"Move '{wg_name}.Add(1)' before the "
                            f"'go func' launch to prevent race"
                        ),
                    ))
                    break
        return issues

    def _go_check_then_act(
        self, root: tree_sitter.Node, source: str
    ) -> list[ConcurrencyIssue]:
        issues: list[ConcurrencyIssue] = []
        lines = source.split("\n")
        check_pattern = re.compile(r"if\s+(\w+(?:\[\w+\])?)\s*(?:==|!=)")
        goroutine = re.compile(r"go\s+(?:func|\w+\()")

        for i in range(len(lines) - 1):
            check_match = check_pattern.search(lines[i])
            if check_match is None:
                continue
            var = check_match.group(1).strip()
            context = "\n".join(lines[max(0, i - 5):i + 5])
            if not goroutine.search(context):
                continue
            next_lines = lines[i + 1:min(i + 3, len(lines))]
            for next_line in next_lines:
                if var in next_line and (
                    "=" in next_line or "append(" in next_line
                    or "delete(" in next_line
                ):
                    issues.append(ConcurrencyIssue(
                        line=i + 1,
                        issue_type=ISSUE_CHECK_THEN_ACT,
                        severity=SEVERITY_MEDIUM,
                        variable=var,
                        description=(
                            f"Check-then-act on '{var}' near goroutine "
                            f"without mutex protection"
                        ),
                        suggestion=(
                            "Use sync.Mutex or atomic operations for "
                            "check-and-modify patterns"
                        ),
                    ))
                    break
        return issues

    # ── Helpers ─────────────────────────────────────────────

    @staticmethod
    def _walk(node: tree_sitter.Node) -> list[tree_sitter.Node]:
        result: list[tree_sitter.Node] = []
        stack: list[tree_sitter.Node] = [node]
        while stack:
            current = stack.pop()
            result.append(current)
            for child in current.children:
                stack.append(child)
        return result
