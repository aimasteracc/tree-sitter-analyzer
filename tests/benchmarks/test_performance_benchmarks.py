"""性能基准测试。

使用pytest-benchmark进行性能基准测试。
"""

from pathlib import Path
from typing import Any

import pytest

# 检查pytest-benchmark是否可用
pytest.importorskip("pytest_benchmark", reason="pytest-benchmark not installed")

# Import after pytest.importorskip to avoid issues when package is not available
from tree_sitter_analyzer.core.analysis_engine import (
    UnifiedAnalysisEngine,  # noqa: E402
)
from tree_sitter_analyzer.core.query import QueryExecutor  # noqa: E402
from tree_sitter_analyzer.formatters.formatter_selector import (  # noqa: E402
    FormatterSelector,
)
from tree_sitter_analyzer.language_detector import (  # noqa: E402
    detect_language_from_file as detect_language,
)


class TestPythonAnalysisBenchmarks:
    """Python分析性能基准测试。"""

    @pytest.fixture
    def python_file(self, tmp_path) -> Path:
        """创建测试用的Python文件。

        Args:
            tmp_path: 临时路径

        Returns:
            Python文件路径
        """
        file_path = tmp_path / "test.py"
        file_path.write_text("""
def function1():
    pass

def function2():
    pass

class Class1:
    def method1(self):
        pass

    def method2(self):
        pass

class Class2:
    def method3(self):
        pass
""")
        return file_path

    @pytest.mark.benchmark(group="python_analysis")
    def test_analyze_python_file(self, benchmark, python_file: Path) -> None:
        """基准测试：分析Python文件。

        Args:
            benchmark: pytest-benchmark fixture
            python_file: Python文件路径
        """
        engine = UnifiedAnalysisEngine()

        def analyze():
            return engine.analyze_file(file_path=python_file, language="python")

        benchmark(analyze)

    @pytest.mark.benchmark(group="python_analysis")
    def test_analyze_python_file_with_details(
        self, benchmark, python_file: Path
    ) -> None:
        """基准测试：分析Python文件（包含详细信息）。

        Args:
            benchmark: pytest-benchmark fixture
            python_file: Python文件路径
        """
        engine = UnifiedAnalysisEngine()

        def analyze():
            return engine.analyze_file(
                file_path=python_file, language="python", include_details=True
            )

        benchmark(analyze)

    @pytest.mark.benchmark(group="python_analysis")
    def test_query_python_classes(self, benchmark, python_file: Path) -> None:
        """基准测试：查询Python类。

        Args:
            benchmark: pytest-benchmark fixture
            python_file: Python文件路径
        """
        query_executor = QueryExecutor()
        source_code = python_file.read_text()

        def query():
            return query_executor.execute_query(
                source_code=source_code, language="python", query_name="classes"
            )

        benchmark(query)


class TestJavaAnalysisBenchmarks:
    """Java分析性能基准测试。"""

    @pytest.fixture
    def java_file(self, tmp_path) -> Path:
        """创建测试用的Java文件。

        Args:
            tmp_path: 临时路径

        Returns:
            Java文件路径
        """
        file_path = tmp_path / "Test.java"
        file_path.write_text("""
public class Test {
    public void method1() {
        System.out.println("Method 1");
    }

    public void method2() {
        System.out.println("Method 2");
    }

    public static class InnerClass {
        public void innerMethod() {
            System.out.println("Inner method");
        }
    }
}
""")
        return file_path

    @pytest.mark.benchmark(group="java_analysis")
    def test_analyze_java_file(self, benchmark, java_file: Path) -> None:
        """基准测试：分析Java文件。

        Args:
            benchmark: pytest-benchmark fixture
            java_file: Java文件路径
        """
        engine = UnifiedAnalysisEngine()

        def analyze():
            return engine.analyze_file(file_path=java_file, language="java")

        benchmark(analyze)

    @pytest.mark.benchmark(group="java_analysis")
    def test_query_java_classes(self, benchmark, java_file: Path) -> None:
        """基准测试：查询Java类。

        Args:
            benchmark: pytest-benchmark fixture
            java_file: Java文件路径
        """
        query_executor = QueryExecutor()
        source_code = java_file.read_text()

        def query():
            return query_executor.execute_query(
                source_code=source_code, language="java", query_name="classes"
            )

        benchmark(query)


class TestJavaScriptAnalysisBenchmarks:
    """JavaScript分析性能基准测试。"""

    @pytest.fixture
    def javascript_file(self, tmp_path) -> Path:
        """创建测试用的JavaScript文件。

        Args:
            tmp_path: 临时路径

        Returns:
            JavaScript文件路径
        """
        file_path = tmp_path / "test.js"
        file_path.write_text("""
function function1() {
    console.log("Function 1");
}

function function2() {
    console.log("Function 2");
}

class Class1 {
    method1() {
        console.log("Method 1");
    }

    method2() {
        console.log("Method 2");
    }
}

class Class2 {
    method3() {
        console.log("Method 3");
    }
}
""")
        return file_path

    @pytest.mark.benchmark(group="javascript_analysis")
    def test_analyze_javascript_file(self, benchmark, javascript_file: Path) -> None:
        """基准测试：分析JavaScript文件。

        Args:
            benchmark: pytest-benchmark fixture
            javascript_file: JavaScript文件路径
        """
        engine = UnifiedAnalysisEngine()

        def analyze():
            return engine.analyze_file(file_path=javascript_file, language="javascript")

        benchmark(analyze)

    @pytest.mark.benchmark(group="javascript_analysis")
    def test_query_javascript_functions(self, benchmark, javascript_file: Path) -> None:
        """基准测试：查询JavaScript函数。

        Args:
            benchmark: pytest-benchmark fixture
            javascript_file: JavaScript文件路径
        """
        query_executor = QueryExecutor()
        source_code = javascript_file.read_text()

        def query():
            return query_executor.execute_query(
                source_code=source_code, language="javascript", query_name="functions"
            )

        benchmark(query)


class TestQueryPerformanceBenchmarks:
    """查询性能基准测试。"""

    @pytest.fixture
    def sample_elements(self) -> list[dict[str, Any]]:
        """创建示例元素列表。

        Returns:
            元素列表
        """
        from tree_sitter_analyzer.models import CodeElement

        return [
            CodeElement(
                name=f"element_{i}",
                element_type="class",
                start_line=1 + i * 10,
                end_line=10 + i * 10,
                language="python",
            )
            for i in range(10)
        ]

    @pytest.mark.benchmark(group="query_performance")
    def test_execute_single_query(
        self, benchmark, sample_elements: list[dict[str, Any]]
    ) -> None:
        """基准测试：执行单个查询。

        Args:
            benchmark: pytest-benchmark fixture
            sample_elements: 示例元素列表
        """
        query_executor = QueryExecutor()
        source_code = "def test(): pass"

        def query():
            return query_executor.execute_query(
                source_code=source_code, language="python", query_name="functions"
            )

        benchmark(query)

    @pytest.mark.benchmark(group="query_performance")
    def test_execute_multiple_queries(
        self, benchmark, sample_elements: list[dict[str, Any]]
    ) -> None:
        """基准测试：执行多个查询。

        Args:
            benchmark: pytest-benchmark fixture
            sample_elements: 示例元素列表
        """
        query_executor = QueryExecutor()
        source_code = "def test(): pass"
        query_names = ["classes", "functions", "methods", "variables"]

        def query():
            return query_executor.execute_multiple_queries(
                source_code=source_code, language="python", query_names=query_names
            )

        benchmark(query)

    @pytest.mark.benchmark(group="query_performance")
    def test_get_available_queries(
        self, benchmark, sample_elements: list[dict[str, Any]]
    ) -> None:
        """基准测试：获取可用查询列表。

        Args:
            benchmark: pytest-benchmark fixture
            sample_elements: 示例元素列表
        """
        query_executor = QueryExecutor()

        def get_queries():
            return query_executor.get_available_queries()

        benchmark(get_queries)


class TestCachePerformanceBenchmarks:
    """缓存性能基准测试。"""

    @pytest.mark.benchmark(group="cache_performance")
    def test_language_detection_cache(self, benchmark) -> None:
        """基准测试：语言检测缓存。

        Args:
            benchmark: pytest-benchmark fixture
        """
        file_path = Path("test.py")

        def detect():
            return detect_language(file_path)

        # 第一次调用（缓存未命中）
        benchmark(detect)

    @pytest.mark.benchmark(group="cache_performance")
    def test_language_detection_cached(self, benchmark) -> None:
        """基准测试：语言检测缓存命中。

        Args:
            benchmark: pytest-benchmark fixture
        """
        file_path = Path("test.py")

        # 预热缓存
        detect_language(file_path)
        detect_language(file_path)

        def detect():
            return detect_language(file_path)

        # 缓存命中
        benchmark(detect)

    @pytest.mark.benchmark(group="cache_performance")
    def test_formatter_selection_cache(self, benchmark) -> None:
        """基准测试：格式化器选择缓存。

        Args:
            benchmark: pytest-benchmark fixture
        """
        selector = FormatterSelector()

        def get_formatter():
            return selector.get_formatter("json")

        # 第一次调用（缓存未命中）
        benchmark(get_formatter)

    @pytest.mark.benchmark(group="cache_performance")
    def test_formatter_selection_cached(self, benchmark) -> None:
        """基准测试：格式化器选择缓存命中。

        Args:
            benchmark: pytest-benchmark fixture
        """
        selector = FormatterSelector()

        # 预热缓存
        selector.get_formatter("json")
        selector.get_formatter("json")

        def get_formatter():
            return selector.get_formatter("json")

        # 缓存命中
        benchmark(get_formatter)


class TestFormattingPerformanceBenchmarks:
    """格式化性能基准测试。"""

    @pytest.fixture
    def sample_elements(self) -> list[dict[str, Any]]:
        """创建示例元素列表。

        Returns:
            元素列表
        """
        from tree_sitter_analyzer.models import CodeElement

        return [
            CodeElement(
                name=f"element_{i}",
                element_type="class",
                start_line=1 + i * 10,
                end_line=10 + i * 10,
                language="python",
            )
            for i in range(100)
        ]

    @pytest.mark.benchmark(group="formatting_performance")
    def test_format_json(
        self, benchmark, sample_elements: list[dict[str, Any]]
    ) -> None:
        """基准测试：JSON格式化。

        Args:
            benchmark: pytest-benchmark fixture
            sample_elements: 示例元素列表
        """
        from tree_sitter_analyzer.formatters.formatter_registry import (
            JsonFormatter as JSONFormatter,
        )

        formatter = JSONFormatter()

        def format():
            return formatter.format(sample_elements)

        benchmark(format)

    @pytest.mark.benchmark(group="formatting_performance")
    def test_format_markdown(
        self, benchmark, sample_elements: list[dict[str, Any]]
    ) -> None:
        """基准测试：Markdown格式化。

        Args:
            benchmark: pytest-benchmark fixture
            sample_elements: 示例元素列表
        """
        from tree_sitter_analyzer.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()

        def format():
            return formatter.format(sample_elements)

        benchmark(format)

    @pytest.mark.benchmark(group="formatting_performance")
    def test_format_toon(
        self, benchmark, sample_elements: list[dict[str, Any]]
    ) -> None:
        """基准测试：Toon格式化。

        Args:
            benchmark: pytest-benchmark fixture
            sample_elements: 示例元素列表
        """
        from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()

        def format():
            return formatter.format(sample_elements)

        benchmark(format)

    @pytest.mark.benchmark(group="formatting_performance")
    def test_format_csv(self, benchmark, sample_elements: list[dict[str, Any]]) -> None:
        """基准测试：CSV格式化。

        Args:
            benchmark: pytest-benchmark fixture
            sample_elements: 示例元素列表
        """
        from tree_sitter_analyzer.formatters.formatter_registry import (
            CsvFormatter as CSVFormatter,
        )

        formatter = CSVFormatter()

        def format():
            return formatter.format(sample_elements)

        benchmark(format)


class TestLargeFileBenchmarks:
    """大文件处理性能基准测试。"""

    @pytest.fixture
    def large_python_file(self, tmp_path) -> Path:
        """创建大型Python文件。

        Args:
            tmp_path: 临时路径

        Returns:
            Python文件路径
        """
        file_path = tmp_path / "large.py"
        content = ""

        # 创建1000个函数
        for i in range(1000):
            content += f"""
def function_{i}():
    \"\"\"Function {i}.\"\"\"
    pass
"""

        file_path.write_text(content)
        return file_path

    @pytest.mark.benchmark(group="large_file")
    def test_analyze_large_python_file(
        self, benchmark, large_python_file: Path
    ) -> None:
        """基准测试：分析大型Python文件。

        Args:
            benchmark: pytest-benchmark fixture
            large_python_file: 大型Python文件路径
        """
        engine = UnifiedAnalysisEngine()

        def analyze():
            return engine.analyze_file(file_path=large_python_file, language="python")

        benchmark(analyze)

    @pytest.mark.benchmark(group="large_file")
    def test_query_large_python_file(self, benchmark, large_python_file: Path) -> None:
        """基准测试：查询大型Python文件。

        Args:
            benchmark: pytest-benchmark fixture
            large_python_file: 大型Python文件路径
        """
        query_executor = QueryExecutor()
        source_code = large_python_file.read_text()

        def query():
            return query_executor.execute_query(
                source_code=source_code, language="python", query_name="functions"
            )

        benchmark(query)
