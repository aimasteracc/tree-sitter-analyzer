"""Tests for ReflectionUsageAnalyzer."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.reflection_usage import (
    ISSUE_DYNAMIC_ACCESS,
    ISSUE_DYNAMIC_EXEC,
    ReflectionFinding,
    ReflectionResult,
    ReflectionUsageAnalyzer,
)

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"


@pytest.fixture
def analyzer() -> ReflectionUsageAnalyzer:
    return ReflectionUsageAnalyzer()


def _write_tmp(content: str, suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="test_refl_")
    with open(fd, "w") as f:
        f.write(content)
    return path


class TestReflectionFinding:
    def test_frozen(self) -> None:
        f = ReflectionFinding(
            issue_type=ISSUE_DYNAMIC_EXEC,
            name="eval",
            line=1,
            severity=SEVERITY_HIGH,
            description="desc",
            suggestion="sug",
        )
        with pytest.raises(AttributeError):
            f.name = "other"  # type: ignore[misc]


class TestReflectionResult:
    def test_to_dict_structure(self) -> None:
        r = ReflectionResult(
            file_path="test.py",
            findings=[
                ReflectionFinding(
                    issue_type=ISSUE_DYNAMIC_EXEC,
                    name="eval",
                    line=1,
                    severity=SEVERITY_HIGH,
                    description="desc",
                    suggestion="sug",
                )
            ],
        )
        d = r.to_dict()
        assert d["file_path"] == "test.py"
        assert d["total_findings"] == 1
        assert d["high_severity"] == 1
        assert len(d["findings"]) == 1
        assert d["findings"][0]["issue_type"] == ISSUE_DYNAMIC_EXEC

    def test_high_severity_count(self) -> None:
        r = ReflectionResult(
            file_path="test.py",
            findings=[
                ReflectionFinding(ISSUE_DYNAMIC_EXEC, "eval", 1, SEVERITY_HIGH, "d", "s"),
                ReflectionFinding(ISSUE_DYNAMIC_ACCESS, "getattr", 2, SEVERITY_MEDIUM, "d", "s"),
                ReflectionFinding(ISSUE_DYNAMIC_EXEC, "exec", 3, SEVERITY_HIGH, "d", "s"),
            ],
        )
        assert r.to_dict()["high_severity"] == 2

    def test_empty_findings(self) -> None:
        r = ReflectionResult(file_path="test.py")
        d = r.to_dict()
        assert d["total_findings"] == 0
        assert d["high_severity"] == 0

    def test_nonexistent_file(self, analyzer: ReflectionUsageAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.findings == []

    def test_unsupported_extension(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp("eval('x')", ".rb")
        try:
            result = analyzer.analyze_file(path)
            assert result.findings == []
        finally:
            Path(path).unlink(missing_ok=True)


class TestPythonDynamicExec:
    def test_detects_eval(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp("result = eval('1 + 1')\n", ".py")
        try:
            result = analyzer.analyze_file(path)
            assert any(
                f.issue_type == ISSUE_DYNAMIC_EXEC and f.name == "eval"
                for f in result.findings
            )
        finally:
            Path(path).unlink(missing_ok=True)

    def test_detects_exec(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp("exec('print(1)')\n", ".py")
        try:
            result = analyzer.analyze_file(path)
            assert any(
                f.issue_type == ISSUE_DYNAMIC_EXEC and f.name == "exec"
                for f in result.findings
            )
        finally:
            Path(path).unlink(missing_ok=True)

    def test_detects_compile(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp("code = compile('1+1', '<string>', 'eval')\n", ".py")
        try:
            result = analyzer.analyze_file(path)
            assert any(
                f.issue_type == ISSUE_DYNAMIC_EXEC and f.name == "compile"
                for f in result.findings
            )
        finally:
            Path(path).unlink(missing_ok=True)

    def test_detects_import(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp("mod = __import__('os')\n", ".py")
        try:
            result = analyzer.analyze_file(path)
            assert any(
                f.issue_type == ISSUE_DYNAMIC_EXEC and f.name == "__import__"
                for f in result.findings
            )
        finally:
            Path(path).unlink(missing_ok=True)

    def test_eval_severity_is_high(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp("eval('x')\n", ".py")
        try:
            result = analyzer.analyze_file(path)
            ev = [f for f in result.findings if f.name == "eval"]
            assert len(ev) == 1
            assert ev[0].severity == SEVERITY_HIGH
        finally:
            Path(path).unlink(missing_ok=True)


class TestPythonDynamicAccess:
    def test_detects_getattr(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp("val = getattr(obj, 'attr')\n", ".py")
        try:
            result = analyzer.analyze_file(path)
            assert any(f.name == "getattr" for f in result.findings)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_detects_setattr(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp("setattr(obj, 'attr', 1)\n", ".py")
        try:
            result = analyzer.analyze_file(path)
            assert any(f.name == "setattr" for f in result.findings)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_detects_delattr(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp("delattr(obj, 'attr')\n", ".py")
        try:
            result = analyzer.analyze_file(path)
            assert any(f.name == "delattr" for f in result.findings)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_detects_hasattr(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp("hasattr(obj, 'attr')\n", ".py")
        try:
            result = analyzer.analyze_file(path)
            assert any(f.name == "hasattr" for f in result.findings)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_dynamic_access_severity_is_medium(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp("getattr(obj, 'x')\n", ".py")
        try:
            result = analyzer.analyze_file(path)
            ga = [f for f in result.findings if f.name == "getattr"]
            assert len(ga) == 1
            assert ga[0].severity == SEVERITY_MEDIUM
        finally:
            Path(path).unlink(missing_ok=True)


class TestPythonNoFalsePositives:
    def test_clean_file(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp("x = 1 + 2\nprint(x)\n", ".py")
        try:
            result = analyzer.analyze_file(path)
            assert len(result.findings) == 0
        finally:
            Path(path).unlink(missing_ok=True)

    def test_function_def_not_flagged(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp("def evaluate(x):\n    return x\n", ".py")
        try:
            result = analyzer.analyze_file(path)
            assert len(result.findings) == 0
        finally:
            Path(path).unlink(missing_ok=True)

    def test_string_literal_eval_not_flagged(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp("s = 'eval is bad'\n", ".py")
        try:
            result = analyzer.analyze_file(path)
            assert len(result.findings) == 0
        finally:
            Path(path).unlink(missing_ok=True)


class TestJSTSDynamicExec:
    def test_detects_eval(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp("eval('1 + 1');\n", ".js")
        try:
            result = analyzer.analyze_file(path)
            assert any(f.name == "eval" for f in result.findings)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_detects_new_function(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp("var fn = new Function('x', 'return x + 1');\n", ".js")
        try:
            result = analyzer.analyze_file(path)
            assert any(f.name == "new Function" for f in result.findings)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_eval_severity_high(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp("eval('x');\n", ".js")
        try:
            result = analyzer.analyze_file(path)
            ev = [f for f in result.findings if f.name == "eval"]
            assert len(ev) == 1
            assert ev[0].severity == SEVERITY_HIGH
        finally:
            Path(path).unlink(missing_ok=True)

    def test_typescript_eval(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp("eval('1');\n", ".ts")
        try:
            result = analyzer.analyze_file(path)
            assert any(f.name == "eval" for f in result.findings)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_clean_js(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp("function add(a, b) { return a + b; }\n", ".js")
        try:
            result = analyzer.analyze_file(path)
            assert len(result.findings) == 0
        finally:
            Path(path).unlink(missing_ok=True)


class TestJavaReflection:
    def test_detects_class_forName(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp(
            "public class T {\n"
            "    void m() {\n"
            "        Class<?> c = Class.forName(\"java.lang.String\");\n"
            "    }\n"
            "}\n",
            ".java",
        )
        try:
            result = analyzer.analyze_file(path)
            assert any(f.name == "Class.forName" for f in result.findings)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_detects_method_invoke(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp(
            "public class T {\n"
            "    void m() throws Exception {\n"
            "        Method m2 = T.class.getDeclaredMethod(\"f\");\n"
            "        m2.invoke(this);\n"
            "    }\n"
            "}\n",
            ".java",
        )
        try:
            result = analyzer.analyze_file(path)
            assert any("invoke" in f.name for f in result.findings)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_detects_setAccessible(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp(
            "public class T {\n"
            "    void m() throws Exception {\n"
            "        Field f = T.class.getDeclaredField(\"x\");\n"
            "        f.setAccessible(true);\n"
            "    }\n"
            "}\n",
            ".java",
        )
        try:
            result = analyzer.analyze_file(path)
            sa = [f for f in result.findings if "setAccessible" in f.name]
            assert len(sa) == 1
            assert sa[0].severity == SEVERITY_HIGH
        finally:
            Path(path).unlink(missing_ok=True)

    def test_clean_java(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp(
            "public class T {\n"
            "    public String getName() { return \"test\"; }\n"
            "}\n",
            ".java",
        )
        try:
            result = analyzer.analyze_file(path)
            assert len(result.findings) == 0
        finally:
            Path(path).unlink(missing_ok=True)


    def test_detects_getDeclaredMethod(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp(
            "public class T {\n"
            "    void m() throws Exception {\n"
            "        Method m2 = T.class.getDeclaredMethod(\"f\");\n"
            "    }\n"
            "}\n",
            ".java",
        )
        try:
            result = analyzer.analyze_file(path)
            assert any("getDeclaredMethod" in f.name for f in result.findings)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_detects_getDeclaredField(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp(
            "public class T {\n"
            "    void m() throws Exception {\n"
            "        Field f = T.class.getDeclaredField(\"x\");\n"
            "    }\n"
            "}\n",
            ".java",
        )
        try:
            result = analyzer.analyze_file(path)
            assert any("getDeclaredField" in f.name for f in result.findings)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_detects_newInstance(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp(
            "public class T {\n"
            "    void m() throws Exception {\n"
            "        Object o = cls.newInstance();\n"
            "    }\n"
            "}\n",
            ".java",
        )
        try:
            result = analyzer.analyze_file(path)
            assert any("newInstance" in f.name for f in result.findings)
        finally:
            Path(path).unlink(missing_ok=True)


class TestGoReflection:
    def test_detects_reflect_DeepEqual(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp(
            "package main\n\n"
            'import "reflect"\n\n'
            "func main() {\n"
            "    reflect.DeepEqual(1, 1)\n"
            "}\n",
            ".go",
        )
        try:
            result = analyzer.analyze_file(path)
            assert any("DeepEqual" in f.name for f in result.findings)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_detects_reflect_ValueOf(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp(
            "package main\n\n"
            'import "reflect"\n\n'
            "func main() {\n"
            "    reflect.ValueOf(42)\n"
            "}\n",
            ".go",
        )
        try:
            result = analyzer.analyze_file(path)
            assert any("ValueOf" in f.name for f in result.findings)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_detects_reflect_TypeOf(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp(
            "package main\n\n"
            'import "reflect"\n\n'
            "func main() {\n"
            "    reflect.TypeOf(42)\n"
            "}\n",
            ".go",
        )
        try:
            result = analyzer.analyze_file(path)
            assert any("TypeOf" in f.name for f in result.findings)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_clean_go(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp(
            "package main\n\n"
            "func main() {\n"
            "    println(\"hello\")\n"
            "}\n",
            ".go",
        )
        try:
            result = analyzer.analyze_file(path)
            assert len(result.findings) == 0
        finally:
            Path(path).unlink(missing_ok=True)


class TestMultipleFindings:
    def test_multiple_in_one_file(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp(
            "eval('x')\n"
            "exec('y')\n"
            "getattr(obj, 'z')\n",
            ".py",
        )
        try:
            result = analyzer.analyze_file(path)
            assert len(result.findings) == 3
            names = {f.name for f in result.findings}
            assert names == {"eval", "exec", "getattr"}
        finally:
            Path(path).unlink(missing_ok=True)

    def test_severity_counts(self, analyzer: ReflectionUsageAnalyzer) -> None:
        path = _write_tmp(
            "eval('x')\n"
            "getattr(obj, 'y')\n",
            ".py",
        )
        try:
            result = analyzer.analyze_file(path)
            d = result.to_dict()
            assert d["high_severity"] == 1
            assert d["total_findings"] == 2
        finally:
            Path(path).unlink(missing_ok=True)


class TestMCPToolIntegration:
    def test_tool_definition(self) -> None:
        from tree_sitter_analyzer.mcp.tools.reflection_usage_tool import (
            ReflectionUsageTool,
        )

        tool = ReflectionUsageTool()
        definition = tool.get_tool_definition()
        assert definition["name"] == "reflection_usage"
        assert "file_path" in definition["inputSchema"]["properties"]
        assert "format" in definition["inputSchema"]["properties"]

    @pytest.mark.asyncio
    async def test_tool_execute_json(self) -> None:
        from tree_sitter_analyzer.mcp.tools.reflection_usage_tool import (
            ReflectionUsageTool,
        )

        path = _write_tmp("eval('x')\n", ".py")
        try:
            tool = ReflectionUsageTool()
            result = await tool.execute({"file_path": path, "format": "json"})
            assert "total_findings" in result
            assert result["total_findings"] >= 1
        finally:
            Path(path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_tool_execute_toon(self) -> None:
        from tree_sitter_analyzer.mcp.tools.reflection_usage_tool import (
            ReflectionUsageTool,
        )

        path = _write_tmp("eval('x')\n", ".py")
        try:
            tool = ReflectionUsageTool()
            result = await tool.execute({"file_path": path, "format": "toon"})
            assert "content" in result
            assert "total_findings" in result
        finally:
            Path(path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_tool_execute_no_file(self) -> None:
        from tree_sitter_analyzer.mcp.tools.reflection_usage_tool import (
            ReflectionUsageTool,
        )

        tool = ReflectionUsageTool()
        result = await tool.execute({"file_path": "", "format": "json"})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_tool_execute_clean_file(self) -> None:
        from tree_sitter_analyzer.mcp.tools.reflection_usage_tool import (
            ReflectionUsageTool,
        )

        path = _write_tmp("x = 1\nprint(x)\n", ".py")
        try:
            tool = ReflectionUsageTool()
            result = await tool.execute({"file_path": path, "format": "json"})
            assert result["total_findings"] == 0
        finally:
            Path(path).unlink(missing_ok=True)
