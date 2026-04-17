"""
Tests for test generation engine.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.test_gen import (
    FuncInfo,
    ParamInfo,
    TestCase,
    TestGenerationEngine,
    TestGenerationError,
)


@pytest.fixture
def temp_repo() -> tempfile.TemporaryDirectory[str]:
    """Create a temporary repository for testing."""
    return tempfile.TemporaryDirectory()


@pytest.fixture
def engine(temp_repo: tempfile.TemporaryDirectory[str]) -> TestGenerationEngine:
    """Create a test generation engine for testing."""
    return TestGenerationEngine(temp_repo.name)


@pytest.fixture
def sample_python_file(temp_repo: tempfile.TemporaryDirectory[str]) -> str:
    """Create a sample Python file for testing."""
    file_path = f"{temp_repo.name}/sample.py"
    with open(file_path, "w") as f:
        f.write("""
def simple_function(x: int, y: int) -> int:
    return x + y

def complex_function(value: str) -> bool:
    if not value:
        return False
    if len(value) < 3:
        return True
    for char in value:
        if char.isdigit():
            return True
    return False

def raises_exception(username: str, password: str) -> bool:
    if not username or not password:
        raise ValueError("Username and password required")
    return True

async def async_function(x: int) -> int:
    return x * 2
""")
    return file_path


class TestParamInfo:
    """Tests for ParamInfo dataclass."""

    def test_create_param_info(self) -> None:
        """ParamInfo should create with correct attributes."""
        param = ParamInfo(name="x", type_hint="int", has_default=False)
        assert param.name == "x"
        assert param.type_hint == "int"
        assert param.has_default is False

    def test_create_param_info_no_type(self) -> None:
        """ParamInfo should handle missing type hint."""
        param = ParamInfo(name="y", type_hint=None, has_default=True)
        assert param.name == "y"
        assert param.type_hint is None
        assert param.has_default is True


class TestFuncInfo:
    """Tests for FuncInfo dataclass."""

    def test_create_func_info(self) -> None:
        """FuncInfo should create with correct attributes."""
        params = [
            ParamInfo(name="x", type_hint="int", has_default=False),
            ParamInfo(name="y", type_hint="int", has_default=False),
        ]
        func = FuncInfo(
            name="add",
            parameters=params,
            return_type="int",
            complexity=1,
            has_exceptions=False,
            has_branches=False,
            decorators=[],
            source_location="test.py:10",
        )
        assert func.name == "add"
        assert len(func.parameters) == 2
        assert func.complexity == 1
        assert func.has_exceptions is False
        assert func.has_branches is False


class TestTestCase:
    """Tests for TestCase dataclass."""

    def test_create_test_case(self) -> None:
        """TestCase should create with correct attributes."""
        test = TestCase(
            test_name="test_add_success",
            setup="",
            call="result = add(1, 2)",
            assertions=["assert result == 3"],
            comment="Test add function",
        )
        assert test.test_name == "test_add_success"
        assert test.call == "result = add(1, 2)"
        assert len(test.assertions) == 1


class TestTestGenerationEngine:
    """Tests for TestGenerationEngine."""

    def test_init(self, temp_repo: tempfile.TemporaryDirectory[str]) -> None:
        """TestGenerationEngine should initialize with repo path."""
        engine = TestGenerationEngine(temp_repo.name)
        assert engine.repo_path == Path(temp_repo.name).resolve()

    def test_extract_functions_simple(
        self, engine: TestGenerationEngine, sample_python_file: str
    ) -> None:
        """Should extract simple function information."""
        functions = engine.extract_functions(sample_python_file)

        # Should find 3 functions (async function skipped)
        assert len(functions) == 3

        # First function should be simple_function
        simple_func = next((f for f in functions if f.name == "simple_function"), None)
        assert simple_func is not None
        assert simple_func.name == "simple_function"
        assert len(simple_func.parameters) == 2
        assert simple_func.return_type == "int"
        assert simple_func.complexity == 1

    def test_extract_functions_complex(
        self, engine: TestGenerationEngine, sample_python_file: str
    ) -> None:
        """Should extract complex function information."""
        functions = engine.extract_functions(sample_python_file)

        complex_func = next((f for f in functions if f.name == "complex_function"), None)
        assert complex_func is not None
        assert complex_func.name == "complex_function"
        assert complex_func.has_branches is True
        assert complex_func.complexity > 1

    def test_extract_functions_with_exceptions(
        self, engine: TestGenerationEngine, sample_python_file: str
    ) -> None:
        """Should detect functions that raise exceptions."""
        functions = engine.extract_functions(sample_python_file)

        raises_func = next((f for f in functions if f.name == "raises_exception"), None)
        assert raises_func is not None
        assert raises_func.has_exceptions is True

    def test_extract_functions_skips_async(
        self, engine: TestGenerationEngine, sample_python_file: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should skip async functions with warning."""
        functions = engine.extract_functions(sample_python_file)

        # async_function should not be in the list
        async_func = next((f for f in functions if f.name == "async_function"), None)
        assert async_func is None

        # Should print warning to stderr
        captured = capsys.readouterr()
        assert "Skipping async function" in captured.err

    def test_extract_functions_invalid_file(self, engine: TestGenerationEngine, temp_repo: tempfile.TemporaryDirectory[str]) -> None:
        """Should raise TestGenerationError for invalid file."""
        with pytest.raises(TestGenerationError, match="Failed to parse"):
            engine.extract_functions("nonexistent.py")

    def test_generate_happy_path(self, engine: TestGenerationEngine) -> None:
        """Should generate happy path test case."""
        func_info = FuncInfo(
            name="add",
            parameters=[
                ParamInfo(name="x", type_hint="int", has_default=False),
                ParamInfo(name="y", type_hint="int", has_default=False),
            ],
            return_type="int",
            complexity=1,
            has_exceptions=False,
            has_branches=False,
            decorators=[],
            source_location="test.py:10",
        )

        test_cases = engine.generate_test_cases(func_info)

        # Should have at least happy path test
        happy_path = next((t for t in test_cases if "success" in t.test_name), None)
        assert happy_path is not None
        assert "test_add_success" == happy_path.test_name
        assert happy_path.call == "result = add(1, 1)"

    def test_generate_edge_cases(self, engine: TestGenerationEngine) -> None:
        """Should generate edge case tests based on complexity."""
        func_info = FuncInfo(
            name="process",
            parameters=[
                ParamInfo(name="value", type_hint="str", has_default=False),
            ],
            return_type="bool",
            complexity=5,  # Should generate up to 5 edge cases
            has_exceptions=False,
            has_branches=True,
            decorators=[],
            source_location="test.py:20",
        )

        test_cases = engine.generate_test_cases(func_info)

        # Should have 1 happy path + 5 edge cases = 6 tests
        edge_cases = [t for t in test_cases if "success" not in t.test_name]
        assert len(edge_cases) == 5

    def test_generate_exception_test(self, engine: TestGenerationEngine) -> None:
        """Should generate exception test for functions that raise."""
        func_info = FuncInfo(
            name="validate",
            parameters=[
                ParamInfo(name="username", type_hint="str", has_default=False),
                ParamInfo(name="password", type_hint="str", has_default=False),
            ],
            return_type="bool",
            complexity=3,
            has_exceptions=True,
            has_branches=True,
            decorators=[],
            source_location="test.py:30",
        )

        test_cases = engine.generate_test_cases(func_info)

        # Should have exception test
        exception_test = next((t for t in test_cases if "exception" in t.test_name), None)
        assert exception_test is not None
        assert "with pytest.raises" in exception_test.call

    def test_calculate_complexity(self, engine: TestGenerationEngine) -> None:
        """Should calculate cyclomatic complexity correctly."""
        func_item = {
            "if_count": 2,
            "elif_count": 1,
            "for_count": 1,
            "while_count": 0,
            "try_count": 0,
            "except_count": 0,
            "with_count": 1,
        }

        complexity = engine._calculate_complexity(func_item)

        # Base (1) + if (2) + elif (1) + for (1) + with (1) = 6
        assert complexity == 6

    def test_has_branches_true(self, engine: TestGenerationEngine) -> None:
        """Should detect branches in function."""
        func_item = {"if_count": 1, "elif_count": 0, "try_count": 0}

        assert engine._has_branches(func_item) is True

    def test_has_branches_false(self, engine: TestGenerationEngine) -> None:
        """Should return False for functions without branches."""
        func_item = {"if_count": 0, "elif_count": 0, "try_count": 0}

        assert engine._has_branches(func_item) is False

    def test_has_exceptions_true(self, engine: TestGenerationEngine) -> None:
        """Should detect exception raising."""
        func_item = {"raises_count": 1}

        assert engine._has_exceptions(func_item) is True

    def test_has_exceptions_false(self, engine: TestGenerationEngine) -> None:
        """Should return False for functions without exceptions."""
        func_item = {"raises_count": 0}

        assert engine._has_exceptions(func_item) is False

    def test_generate_function_call_with_defaults(self, engine: TestGenerationEngine) -> None:
        """Should generate function call with default values."""
        func_info = FuncInfo(
            name="add",
            parameters=[
                ParamInfo(name="x", type_hint="int", has_default=False),
                ParamInfo(name="y", type_hint="int", has_default=False),
            ],
            return_type="int",
            complexity=1,
            has_exceptions=False,
            has_branches=False,
            decorators=[],
            source_location="test.py:10",
        )

        call = engine._generate_function_call(func_info, use_defaults=True)
        assert call == "result = add(1, 1)"

    def test_generate_function_call_with_none(self, engine: TestGenerationEngine) -> None:
        """Should generate function call with None values."""
        func_info = FuncInfo(
            name="process",
            parameters=[
                ParamInfo(name="value", type_hint="str", has_default=False),
            ],
            return_type="bool",
            complexity=1,
            has_exceptions=False,
            has_branches=False,
            decorators=[],
            source_location="test.py:10",
        )

        call = engine._generate_function_call(func_info, use_defaults=False)
        assert call == "result = process(None)"

    def test_get_module_path(self, engine: TestGenerationEngine, temp_repo: tempfile.TemporaryDirectory[str]) -> None:
        """Should generate correct module path."""
        # Create a file in src/auth/auth.py
        auth_dir = Path(temp_repo.name) / "src" / "auth"
        auth_dir.mkdir(parents=True)
        auth_file = auth_dir / "auth.py"
        auth_file.touch()

        module_path = engine.get_module_path(str(auth_file))
        assert module_path == "src.auth.auth"

    def test_get_module_path_simple(self, engine: TestGenerationEngine, temp_repo: tempfile.TemporaryDirectory[str]) -> None:
        """Should handle simple file structure."""
        simple_file = Path(temp_repo.name) / "main.py"
        simple_file.touch()

        module_path = engine.get_module_path(str(simple_file))
        assert module_path == "main"

    def test_get_module_path_init_file(self, engine: TestGenerationEngine, temp_repo: tempfile.TemporaryDirectory[str]) -> None:
        """Should handle __init__.py files correctly."""
        init_file = Path(temp_repo.name) / "utils" / "__init__.py"
        init_file.parent.mkdir(parents=True)
        init_file.touch()

        module_path = engine.get_module_path(str(init_file))
        assert module_path == "utils"


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_file(self, engine: TestGenerationEngine, temp_repo: tempfile.TemporaryDirectory[str]) -> None:
        """Should handle empty Python file."""
        empty_file = f"{temp_repo.name}/empty.py"
        with open(empty_file, "w") as f:
            f.write("")

        functions = engine.extract_functions(empty_file)
        assert len(functions) == 0

    def test_function_with_no_params(self, engine: TestGenerationEngine, temp_repo: tempfile.TemporaryDirectory[str]) -> None:
        """Should handle functions with no parameters."""
        file_path = f"{temp_repo.name}/no_params.py"
        with open(file_path, "w") as f:
            f.write("def no_params() -> bool:\n    return True\n")

        functions = engine.extract_functions(file_path)
        assert len(functions) == 1
        assert len(functions[0].parameters) == 0

    def test_function_with_decorator(self, engine: TestGenerationEngine, temp_repo: tempfile.TemporaryDirectory[str]) -> None:
        """Should extract decorator information."""
        file_path = f"{temp_repo.name}/decorated.py"
        with open(file_path, "w") as f:
            f.write("@staticmethod\ndef decorated_func() -> int:\n    return 42\n")

        functions = engine.extract_functions(file_path)
        assert len(functions) == 1
        assert "staticmethod" in functions[0].decorators
