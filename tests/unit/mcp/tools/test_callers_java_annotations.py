"""PR-2: declaration headers below annotations, and Java annotations that register nothing.

r15 dogfood: gson ``JsonWriter.beforeValue`` was blocked only by its own name line
(806, below ``@SuppressWarnings`` on 805, the line the index records), and every
``@Override`` / ``@SuppressWarnings`` counted as "may register" (~24% of gson).
An ``@Override`` of a method declared outside the project (``ClassValue``), or one
that a supertype call may dispatch to, must stay non-complete.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.callers_decorators import DECORATED_REASON
from tree_sitter_analyzer.mcp.tools.callers_java_overrides import OVERRIDE_REASON
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_WRITER = (
    "package p;\n"
    "\n"
    "class Writer {\n"
    "  void write() {\n"
    "    beforeValue();\n"
    "    beforeName();\n"
    "  }\n"
    "\n"
    '  @SuppressWarnings("fallthrough")\n'
    "  private void beforeValue() {\n"
    "    flush();\n"
    "  }\n"
    "\n"
    "  @Deprecated\n"
    "  private void beforeName() { submit(this::beforeName); }\n"
    "\n"
    '  @SuppressWarnings("unused")\n'
    "  private void retry() {\n"
    "    submit(this::retry);\n"
    "  }\n"
    "\n"
    "  @SafeVarargs\n"
    "  @FunctionalInterface\n"
    "  private final void idle() {}\n"
    "\n"
    "  @Subscribe\n"
    "  void onEvent() {}\n"
    "\n"
    "  @Bean\n"
    "  Object service() { return null; }\n"
    "\n"
    "  void flush() {}\n"
    "  void submit(Runnable r) {}\n"
    "}\n"
)
_BASE = (
    "package p;\n"
    "\n"
    "abstract class Base<T> {\n"
    "  abstract void hook(T value);\n"
    "  abstract void handle(T value);\n"
    "  void run() { flushAll(); }\n"
    "  void flushAll() {}\n"
    "}\n"
)
_IMPL = (
    "package p;\n"
    "\n"
    "import java.util.List;\n"
    "\n"
    "class Impl extends Base<String> {\n"
    "  @Override\n"
    "  void hook(String value) {}\n"
    "\n"
    "  @Override\n"
    "  void handle(String value) {}\n"
    "\n"
    "  @Override\n"
    '  public String toString() { return "impl"; }\n'
    "}\n"
)
_RUNNER = (
    "package p;\n"
    "\n"
    "class Runner {\n"
    "  void go(Base<String> base) {\n"
    '    base.handle("x");\n'
    "  }\n"
    "}\n"
)
_EXTERNAL = (
    "package p;\n"
    "\n"
    "import com.example.lib.Plugin;\n"
    "\n"
    "class Adapter extends ClassValue<String> {\n"
    "  @Override\n"
    "  protected String computeValue(Class<?> type) { return type.getName(); }\n"
    "}\n"
    "\n"
    "class Extension extends Plugin {\n"
    "  @Override\n"
    "  void start() {}\n"
    "}\n"
)
#: A project type named like a ``java.lang`` annotation shadows it.
_SHADOW = (
    "package q;\n"
    "\n"
    "@interface Deprecated {}\n"
    "\n"
    "class Legacy {\n"
    "  void call() { old(); }\n"
    "  @Deprecated\n"
    "  void old() {}\n"
    "}\n"
)


async def _index(tmp_path, files: dict[str, str]) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert indexed["published"] is True
    return str(tmp_path)


@pytest.fixture
async def java_root(tmp_path):
    return await _index(
        tmp_path,
        {
            "p/Writer.java": _WRITER,
            "p/Base.java": _BASE,
            "p/Impl.java": _IMPL,
            "p/Runner.java": _RUNNER,
            "p/Adapter.java": _EXTERNAL,
        },
    )


async def _callers(root: str, name: str, file_path: str) -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "file_path": file_path, "include_bodies": False}
    )


@pytest.mark.asyncio
async def test_name_line_below_an_annotation_is_not_a_reference(java_root) -> None:
    # gson JsonWriter.beforeValue: the index records line 9 (the annotation); the
    # name on line 10 is the declaration itself, and @SuppressWarnings registers
    # nothing.
    result = await _callers(java_root, "Writer.beforeValue", "p/Writer.java")

    assert (result["caller_count"], result["completeness"]) == (1, "complete")
    assert result["non_call_references"] == 0


@pytest.mark.asyncio
async def test_a_reference_on_the_name_line_still_counts(java_root) -> None:
    # `submit(this::beforeName)` on the name line mentions the name a second time.
    result = await _callers(java_root, "Writer.beforeName", "p/Writer.java")

    assert result["completeness"] != "complete"
    assert result["completeness_reason"] == "NON_CALL_REFERENCES"
    assert result["non_call_reference_sites"] == [{"file": "p/Writer.java", "line": 15}]


@pytest.mark.asyncio
async def test_a_recursive_body_reference_still_counts(java_root) -> None:
    # The header ends at the name: `this::retry` in the body is a reference.
    result = await _callers(java_root, "Writer.retry", "p/Writer.java")

    assert result["completeness"] == "unknown"
    assert result["non_call_reference_sites"] == [{"file": "p/Writer.java", "line": 19}]


@pytest.mark.asyncio
async def test_passive_java_lang_annotations_keep_complete(java_root) -> None:
    result = await _callers(java_root, "Writer.idle", "p/Writer.java")

    assert (result["caller_count"], result["completeness"]) == (0, "complete")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "annotation"), [("onEvent", "@Subscribe"), ("service", "@Bean")]
)
async def test_registering_java_annotations_still_block(
    java_root, name: str, annotation: str
) -> None:
    result = await _callers(java_root, f"Writer.{name}", "p/Writer.java")

    assert (result["completeness"], result["completeness_reason"]) == (
        "unknown",
        DECORATED_REASON,
    )
    assert annotation in result["next_step"]


@pytest.mark.asyncio
async def test_in_project_override_without_dispatch_is_complete(java_root) -> None:
    # Base.hook is declared in the project and nothing calls `hook` anywhere.
    result = await _callers(java_root, "Impl.hook", "p/Impl.java")

    assert (result["caller_count"], result["completeness"]) == (0, "complete")


@pytest.mark.asyncio
async def test_override_reached_through_the_supertype_stays_blocked(java_root) -> None:
    # `base.handle("x")` binds to Base.handle and may dispatch to Impl.handle; the
    # generic `extends Base<String>` leaves no extends edge, so @Override is what
    # keeps this from a wrong complete.
    result = await _callers(java_root, "Impl.handle", "p/Impl.java")

    assert result["completeness"] != "complete"
    assert result["completeness_reasons"][0] in {OVERRIDE_REASON, "NAME_ONLY_INBOUND"}
    if result["completeness_reason"] == OVERRIDE_REASON:
        assert "p/Runner.java:5" in result["next_step"]


@pytest.mark.asyncio
async def test_object_method_override_stays_blocked(java_root) -> None:
    result = await _callers(java_root, "Impl.toString", "p/Impl.java")

    assert (result["completeness"], result["completeness_reason"]) == (
        "unknown",
        OVERRIDE_REASON,
    )
    assert "java.lang.Object.toString" in result["next_step"]


@pytest.mark.asyncio
async def test_override_of_an_external_method_stays_blocked(java_root) -> None:
    # gson Adapter.computeValue overrides java.lang.ClassValue.computeValue: the JDK
    # calls it.
    result = await _callers(java_root, "Adapter.computeValue", "p/Adapter.java")

    assert (result["caller_count"], result["completeness"]) == (0, "unknown")
    assert result["completeness_reason"] == OVERRIDE_REASON
    assert "`ClassValue` is outside the project" in result["next_step"]


@pytest.mark.asyncio
async def test_override_of_an_unresolved_supertype_stays_blocked(java_root) -> None:
    result = await _callers(java_root, "Extension.start", "p/Adapter.java")

    assert (result["completeness"], result["completeness_reason"]) == (
        "unknown",
        OVERRIDE_REASON,
    )
    assert "`Plugin` is outside the project" in result["next_step"]


@pytest.mark.asyncio
async def test_project_type_shadowing_a_java_lang_annotation_blocks(tmp_path) -> None:
    root = await _index(tmp_path, {"q/Legacy.java": _SHADOW})

    result = await _callers(root, "Legacy.old", "q/Legacy.java")

    assert (result["completeness"], result["completeness_reason"]) == (
        "incomplete",
        DECORATED_REASON,
    )


@pytest.mark.asyncio
async def test_python_decorator_named_like_a_java_annotation_still_blocks(
    tmp_path,
) -> None:
    # The Java rule is Java-only: a Python `@Override` is a project decorator.
    root = await _index(
        tmp_path,
        {
            "mod.py": (
                "def Override(fn):\n    return fn\n\n\n"
                "@Override\n"
                "def target():\n    return 1\n\n\n"
                "def other():\n    return len([])\n"
            )
        },
    )

    result = await _callers(root, "target", "mod.py")

    assert result["completeness"] != "complete"
    assert result["completeness_reason"] == DECORATED_REASON
