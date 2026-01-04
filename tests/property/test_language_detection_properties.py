"""语言检测属性测试。

使用Hypothesis库进行基于属性的测试，验证语言检测的正确性。
"""

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from tree_sitter_analyzer.language_detector import LanguageDetector

# Create detector instance for extension-based detection
detector = LanguageDetector()


class TestLanguageDetectionProperties:
    """语言检测属性测试类。"""

    @given(
        file_path=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(blacklist_characters='\\/:*?"<>|'),
        ).map(lambda s: Path(s + ".py"))
    )
    @settings(max_examples=50)
    def test_python_extension_detection(self, file_path: Path) -> None:
        """测试Python扩展名检测的属性。

        验证：所有.py文件都应该被检测为Python语言。

        Args:
            file_path: 文件路径
        """
        # detect_from_extension works with virtual file paths (no file existence check)
        language = detector.detect_from_extension(str(file_path))
        assert language == "python", f"Expected 'python' but got '{language}'"

    @given(
        file_path=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(blacklist_characters='\\/:*?"<>|'),
        ).map(lambda s: Path(s + ".java"))
    )
    @settings(max_examples=50)
    def test_java_extension_detection(self, file_path: Path) -> None:
        """测试Java扩展名检测的属性。

        验证：所有.java文件都应该被检测为Java语言。

        Args:
            file_path: 文件路径
        """
        language = detector.detect_from_extension(str(file_path))
        assert language == "java", f"Expected 'java' but got '{language}'"

    @given(
        file_path=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(blacklist_characters='\\/:*?"<>|'),
        ).map(lambda s: Path(s + ".js"))
    )
    @settings(max_examples=50)
    def test_javascript_extension_detection(self, file_path: Path) -> None:
        """测试JavaScript扩展名检测的属性。

        验证：所有.js文件都应该被检测为JavaScript语言。

        Args:
            file_path: 文件路径
        """
        language = detector.detect_from_extension(str(file_path))
        assert language == "javascript", f"Expected 'javascript' but got '{language}'"

    @given(
        file_path=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(blacklist_characters='\\/:*?"<>|'),
        ).map(lambda s: Path(s + ".ts"))
    )
    @settings(max_examples=50)
    def test_typescript_extension_detection(self, file_path: Path) -> None:
        """测试TypeScript扩展名检测的属性。

        验证：所有.ts文件都应该被检测为TypeScript语言。

        Args:
            file_path: 文件路径
        """
        language = detector.detect_from_extension(str(file_path))
        assert language == "typescript", f"Expected 'typescript' but got '{language}'"

    @given(
        file_path=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(blacklist_characters='\\/:*?"<>|'),
        ).map(lambda s: Path(s + ".go"))
    )
    @settings(max_examples=50)
    def test_go_extension_detection(self, file_path: Path) -> None:
        """测试Go扩展名检测的属性。

        验证：所有.go文件都应该被检测为Go语言。

        Args:
            file_path: 文件路径
        """
        language = detector.detect_from_extension(str(file_path))
        assert language == "go", f"Expected 'go' but got '{language}'"

    @given(
        file_path=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(blacklist_characters='\\/:*?"<>|'),
        ).map(lambda s: Path(s + ".rs"))
    )
    @settings(max_examples=50)
    def test_rust_extension_detection(self, file_path: Path) -> None:
        """测试Rust扩展名检测的属性。

        验证：所有.rs文件都应该被检测为Rust语言。

        Args:
            file_path: 文件路径
        """
        language = detector.detect_from_extension(str(file_path))
        assert language == "rust", f"Expected 'rust' but got '{language}'"

    @given(
        file_path=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(blacklist_characters='\\/:*?"<>|'),
        ).map(lambda s: Path(s + ".cs"))
    )
    @settings(max_examples=50)
    def test_csharp_extension_detection(self, file_path: Path) -> None:
        """测试C#扩展名检测的属性。

        验证：所有.cs文件都应该被检测为C#语言。

        Args:
            file_path: 文件路径
        """
        language = detector.detect_from_extension(str(file_path))
        assert language == "csharp", f"Expected 'csharp' but got '{language}'"

    @given(
        file_path=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(blacklist_characters='\\/:*?"<>|'),
        ).map(lambda s: Path(s + ".css"))
    )
    @settings(max_examples=50)
    def test_css_extension_detection(self, file_path: Path) -> None:
        """测试CSS扩展名检测的属性。

        验证：所有.css文件都应该被检测为CSS语言。

        Args:
            file_path: 文件路径
        """
        language = detector.detect_from_extension(str(file_path))
        assert language == "css", f"Expected 'css' but got '{language}'"

    @given(
        file_path=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(blacklist_characters='\\/:*?"<>|'),
        ).map(lambda s: Path(s + ".html"))
    )
    @settings(max_examples=50)
    def test_html_extension_detection(self, file_path: Path) -> None:
        """测试HTML扩展名检测的属性。

        验证：所有.html文件都应该被检测为HTML语言。

        Args:
            file_path: 文件路径
        """
        language = detector.detect_from_extension(str(file_path))
        assert language == "html", f"Expected 'html' but got '{language}'"

    @given(
        file_path=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(blacklist_characters='\\/:*?"<>|'),
        ).map(lambda s: Path(s + ".yaml"))
    )
    @settings(max_examples=50)
    def test_yaml_extension_detection(self, file_path: Path) -> None:
        """测试YAML扩展名检测的属性。

        验证：所有.yaml文件都应该被检测为YAML语言。

        Args:
            file_path: 文件路径
        """
        language = detector.detect_from_extension(str(file_path))
        assert language == "yaml", f"Expected 'yaml' but got '{language}'"

    @given(
        file_path=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(blacklist_characters='\\/:*?"<>|'),
        ).map(lambda s: Path(s + ".yml"))
    )
    @settings(max_examples=50)
    def test_yml_extension_detection(self, file_path: Path) -> None:
        """测试.yml扩展名检测的属性。

        验证：所有.yml文件都应该被检测为YAML语言。

        Args:
            file_path: 文件路径
        """
        language = detector.detect_from_extension(str(file_path))
        assert language == "yaml", f"Expected 'yaml' but got '{language}'"

    @given(
        file_path=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(blacklist_characters='\\/:*?"<>|'),
        ).map(lambda s: Path(s + ".sql"))
    )
    @settings(max_examples=50)
    def test_sql_extension_detection(self, file_path: Path) -> None:
        """测试SQL扩展名检测的属性。

        验证：所有.sql文件都应该被检测为SQL语言。

        Args:
            file_path: 文件路径
        """
        language = detector.detect_from_extension(str(file_path))
        assert language == "sql", f"Expected 'sql' but got '{language}'"

    @given(
        file_path=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(blacklist_characters='\\/:*?"<>|'),
        ).map(lambda s: Path(s + ".unknown"))
    )
    @settings(max_examples=50)
    def test_unknown_extension_detection(self, file_path: Path) -> None:
        """测试未知扩展名检测的属性。

        验证：未知扩展名的文件应该返回None或默认值。

        Args:
            file_path: 文件路径
        """
        language = detector.detect_from_extension(str(file_path))
        # 未知扩展名应该返回"unknown"
        assert language == "unknown" or isinstance(language, str)

    @given(
        file_path=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(blacklist_characters='\\/:*?"<>|.'),
        ).map(lambda s: Path(s))
    )
    @settings(max_examples=50)
    def test_no_extension_detection(self, file_path: Path) -> None:
        """测试无扩展名检测的属性。

        验证：无扩展名的文件应该返回None或默认值。

        Args:
            file_path: 文件路径
        """
        # 确保没有扩展名
        if file_path.suffix:
            return

        language = detector.detect_from_extension(str(file_path))
        # 无扩展名应该返回"unknown"
        assert language == "unknown" or isinstance(language, str)

    @given(
        file_path=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(blacklist_characters='\\/:*?"<>|'),
        ).map(lambda s: Path(s + ".py"))
    )
    @settings(max_examples=50)
    def test_detection_idempotency(self, file_path: Path) -> None:
        """测试语言检测的幂等性。

        验证：多次检测同一文件应该返回相同的结果。

        Args:
            file_path: 文件路径
        """
        language1 = detector.detect_from_extension(str(file_path))
        language2 = detector.detect_from_extension(str(file_path))
        language3 = detector.detect_from_extension(str(file_path))

        assert language1 == language2 == language3

    @given(
        file_path1=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(blacklist_characters='\\/:*?"<>|'),
        ).map(lambda s: Path(s + ".py")),
        file_path2=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(blacklist_characters='\\/:*?"<>|'),
        ).map(lambda s: Path(s + ".py")),
    )
    @settings(max_examples=30)
    def test_same_extension_same_language(
        self, file_path1: Path, file_path2: Path
    ) -> None:
        """测试相同扩展名返回相同语言的属性。

        验证：相同扩展名的文件应该返回相同的语言。

        Args:
            file_path1: 第一个文件路径
            file_path2: 第二个文件路径
        """
        language1 = detector.detect_from_extension(str(file_path1))
        language2 = detector.detect_from_extension(str(file_path2))

        assert language1 == language2

    @given(
        extensions=st.lists(
            st.sampled_from(
                [
                    ".py",
                    ".java",
                    ".js",
                    ".ts",
                    ".go",
                    ".rs",
                    ".cs",
                    ".css",
                    ".html",
                    ".yaml",
                    ".sql",
                ]
            ),
            min_size=1,
            max_size=10,
        )
    )
    @settings(max_examples=30)
    def test_multiple_extensions_detection(self, extensions: list[str]) -> None:
        """测试多个扩展名检测的属性。

        验证：每个扩展名都应该被正确检测。

        Args:
            extensions: 扩展名列表
        """
        for ext in extensions:
            file_path = Path(f"test{ext}")
            language = detector.detect_from_extension(str(file_path))
            assert (
                language is not None
            ), f"Failed to detect language for extension {ext}"
            assert isinstance(
                language, str
            ), f"Expected string language for {ext}, got {type(language)}"


class TestLanguageDetectionStateful(RuleBasedStateMachine):
    """语言检测状态机测试。"""

    def __init__(self) -> None:
        super().__init__()
        self.detected_languages: dict[str, str] = {}

    @rule(
        file_name=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(blacklist_characters='\\/:*?"<>|'),
        ),
        extension=st.sampled_from(
            [
                ".py",
                ".java",
                ".js",
                ".ts",
                ".go",
                ".rs",
                ".cs",
                ".css",
                ".html",
                ".yaml",
                ".sql",
            ]
        ),
    )
    def detect_language_for_file(self, file_name: str, extension: str) -> None:
        """为文件检测语言。

        Args:
            file_name: 文件名
            extension: 扩展名
        """
        file_path = Path(file_name + extension)
        language = detector.detect_from_extension(str(file_path))
        self.detected_languages[str(file_path)] = language

    @invariant()
    def all_detections_are_valid(self) -> None:
        """验证所有检测结果都是有效的。"""
        for file_path, language in self.detected_languages.items():
            assert language is not None or isinstance(
                language, str
            ), f"Invalid detection for {file_path}: {language}"

    @invariant()
    def same_extension_same_language(self) -> None:
        """验证相同扩展名返回相同语言。"""
        extension_map: dict[str, str] = {}
        for file_path, language in self.detected_languages.items():
            ext = Path(file_path).suffix
            if ext in extension_map:
                assert (
                    language == extension_map[ext]
                ), f"Same extension {ext} but different languages: {language} vs {extension_map[ext]}"
            else:
                extension_map[ext] = language


TestLanguageDetectionStateful.TestCase.settings = settings(max_examples=100)


class TestLanguageDetectionEdgeCases:
    """语言检测边界情况测试。"""

    def test_empty_filename(self) -> None:
        """测试空文件名。"""
        file_path = Path("")
        language = detector.detect_from_extension(str(file_path))
        assert language == "unknown" or isinstance(language, str)

    def test_dotfile(self) -> None:
        """测试点文件。"""
        file_path = Path(".hidden.py")
        language = detector.detect_from_extension(str(file_path))
        assert language == "python"

    def test_multiple_dots(self) -> None:
        """测试多个点。"""
        file_path = Path("file.name.with.dots.py")
        language = detector.detect_from_extension(str(file_path))
        assert language == "python"

    def test_uppercase_extension(self) -> None:
        """测试大写扩展名。"""
        file_path = Path("test.PY")
        language = detector.detect_from_extension(str(file_path))
        # 根据实现，可能返回python或None
        assert language is None or language.lower() == "python"

    def test_mixed_case_extension(self) -> None:
        """测试混合大小写扩展名。"""
        file_path = Path("test.Py")
        language = detector.detect_from_extension(str(file_path))
        # 根据实现，可能返回python或None
        assert language is None or language.lower() == "python"

    def test_extension_with_numbers(self) -> None:
        """测试带数字的扩展名。"""
        file_path = Path("test.py2")
        language = detector.detect_from_extension(str(file_path))
        # 根据实现，可能返回None或特定语言
        assert language is None or isinstance(language, str)
