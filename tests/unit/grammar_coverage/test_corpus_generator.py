"""Unit tests for corpus_generator module.

测试黄金语料库生成器的核心功能：
- 代码生成
- 验证逻辑
- 文件保存
- 分类组织
"""

import tempfile

from tree_sitter_analyzer.grammar_coverage.corpus_generator import (
    generate_and_save_corpus,
    generate_corpus_by_category,
    generate_minimal_code_for_node_type,
    save_corpus_files,
    validate_generated_code,
)


class TestGenerateMinimalCode:
    """测试最小化代码生成"""

    def test_python_function_definition(self) -> None:
        """测试 Python function_definition 生成"""
        code = generate_minimal_code_for_node_type("python", "function_definition")
        assert code
        assert "def" in code
        assert "foo" in code
        assert "pass" in code

    def test_python_class_definition(self) -> None:
        """测试 Python class_definition 生成"""
        code = generate_minimal_code_for_node_type("python", "class_definition")
        assert code
        assert "class" in code
        assert "Foo" in code
        assert "pass" in code

    def test_python_if_statement(self) -> None:
        """测试 Python if_statement 生成"""
        code = generate_minimal_code_for_node_type("python", "if_statement")
        assert code
        assert "if" in code
        assert "True" in code or "true" in code.lower()

    def test_javascript_function_declaration(self) -> None:
        """测试 JavaScript function_declaration 生成"""
        code = generate_minimal_code_for_node_type("javascript", "function_declaration")
        assert code
        assert "function" in code
        assert "foo" in code

    def test_javascript_arrow_function(self) -> None:
        """测试 JavaScript arrow_function 生成"""
        code = generate_minimal_code_for_node_type("javascript", "arrow_function")
        assert code
        assert "=>" in code
        assert "const" in code or "let" in code or "var" in code

    def test_java_class_declaration(self) -> None:
        """测试 Java class_declaration 生成"""
        code = generate_minimal_code_for_node_type("java", "class_declaration")
        assert code
        assert "class" in code
        assert "Foo" in code

    def test_java_method_declaration(self) -> None:
        """测试 Java method_declaration 生成"""
        code = generate_minimal_code_for_node_type("java", "method_declaration")
        assert code
        assert "class" in code  # Java methods must be in a class
        assert "void" in code or "int" in code

    def test_unsupported_language(self) -> None:
        """测试不支持的语言返回空字符串"""
        code = generate_minimal_code_for_node_type("cobol", "function_definition")
        assert code == ""

    def test_unsupported_node_type(self) -> None:
        """测试不支持的节点类型返回空字符串"""
        code = generate_minimal_code_for_node_type("python", "nonexistent_type")
        assert code == ""


class TestValidateGeneratedCode:
    """测试代码验证功能"""

    def test_valid_python_code(self) -> None:
        """测试有效的 Python 代码"""
        code = "def foo():\n    pass\n"
        assert validate_generated_code("python", code) is True

    def test_valid_javascript_code(self) -> None:
        """测试有效的 JavaScript 代码"""
        code = "function foo() {}\n"
        assert validate_generated_code("javascript", code) is True

    def test_valid_java_code(self) -> None:
        """测试有效的 Java 代码"""
        code = "class Foo {}\n"
        assert validate_generated_code("java", code) is True

    def test_invalid_python_code(self) -> None:
        """测试无效的 Python 代码"""
        code = "def foo(\n"  # Missing closing parenthesis
        assert validate_generated_code("python", code) is False

    def test_invalid_javascript_code(self) -> None:
        """测试无效的 JavaScript 代码"""
        code = "function foo() {\n"  # Missing closing brace
        assert validate_generated_code("javascript", code) is False

    def test_unsupported_language_validation(self) -> None:
        """测试不支持的语言验证返回 False"""
        code = "def foo():\n    pass\n"
        assert validate_generated_code("cobol", code) is False


class TestGenerateCorpusByCategory:
    """测试按分类生成语料库"""

    def test_python_corpus_structure(self) -> None:
        """测试 Python 语料库结构"""
        corpus = generate_corpus_by_category("python")
        assert len(corpus) > 0
        # 检查是否有函数、类、语句等分类
        assert any("functions" in path for path in corpus.keys())
        assert any("classes" in path for path in corpus.keys())
        assert any("statements" in path for path in corpus.keys())

    def test_python_corpus_file_extensions(self) -> None:
        """测试 Python 语料库文件扩展名"""
        corpus = generate_corpus_by_category("python")
        for path in corpus.keys():
            assert path.endswith(".py")

    def test_python_corpus_content(self) -> None:
        """测试 Python 语料库内容包含节点类型注释"""
        corpus = generate_corpus_by_category("python")
        # 检查至少一个文件包含节点类型注释
        has_node_type_comment = any(
            "Node type:" in content for content in corpus.values()
        )
        assert has_node_type_comment

    def test_javascript_corpus_structure(self) -> None:
        """测试 JavaScript 语料库结构"""
        corpus = generate_corpus_by_category("javascript")
        assert len(corpus) > 0
        assert any("functions" in path for path in corpus.keys())
        assert any("classes" in path for path in corpus.keys())

    def test_javascript_corpus_file_extensions(self) -> None:
        """测试 JavaScript 语料库文件扩展名"""
        corpus = generate_corpus_by_category("javascript")
        for path in corpus.keys():
            assert path.endswith(".js")

    def test_java_corpus_structure(self) -> None:
        """测试 Java 语料库结构"""
        corpus = generate_corpus_by_category("java")
        assert len(corpus) > 0
        assert any("methods" in path or "classes" in path for path in corpus.keys())

    def test_java_corpus_file_extensions(self) -> None:
        """测试 Java 语料库文件扩展名"""
        corpus = generate_corpus_by_category("java")
        for path in corpus.keys():
            assert path.endswith(".java")

    def test_unsupported_language_corpus(self) -> None:
        """测试不支持的语言返回空字典"""
        corpus = generate_corpus_by_category("cobol")
        assert corpus == {}


class TestSaveCorpusFiles:
    """测试语料库文件保存"""

    def test_save_python_corpus(self) -> None:
        """测试保存 Python 语料库"""
        corpus = {"functions/test.py": "def foo():\n    pass\n"}
        with tempfile.TemporaryDirectory() as tmpdir:
            saved_paths = save_corpus_files("python", corpus, tmpdir)
            assert len(saved_paths) == 1
            assert saved_paths[0].exists()
            assert saved_paths[0].read_text(encoding="utf-8") == corpus["functions/test.py"]

    def test_save_multiple_files(self) -> None:
        """测试保存多个文件"""
        corpus = {
            "functions/test1.py": "def foo():\n    pass\n",
            "classes/test2.py": "class Foo:\n    pass\n",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            saved_paths = save_corpus_files("python", corpus, tmpdir)
            assert len(saved_paths) == 2
            assert all(path.exists() for path in saved_paths)

    def test_create_nested_directories(self) -> None:
        """测试创建嵌套目录"""
        corpus = {"deep/nested/path/test.py": "def foo():\n    pass\n"}
        with tempfile.TemporaryDirectory() as tmpdir:
            saved_paths = save_corpus_files("python", corpus, tmpdir)
            assert len(saved_paths) == 1
            assert saved_paths[0].exists()
            assert "deep" in str(saved_paths[0])
            assert "nested" in str(saved_paths[0])

    def test_utf8_encoding(self) -> None:
        """测试 UTF-8 编码支持"""
        corpus = {"test.py": "# 中文注释\ndef foo():\n    pass\n"}
        with tempfile.TemporaryDirectory() as tmpdir:
            saved_paths = save_corpus_files("python", corpus, tmpdir)
            assert len(saved_paths) == 1
            content = saved_paths[0].read_text(encoding="utf-8")
            assert "中文注释" in content


class TestGenerateAndSaveCorpus:
    """测试完整的生成和保存流程"""

    def test_python_end_to_end(self) -> None:
        """测试 Python 端到端流程"""
        with tempfile.TemporaryDirectory() as tmpdir:
            paths, success, failed = generate_and_save_corpus(
                "python", tmpdir, validate=True
            )
            assert len(paths) > 0
            assert success > 0
            assert all(path.exists() for path in paths)

    def test_javascript_end_to_end(self) -> None:
        """测试 JavaScript 端到端流程"""
        with tempfile.TemporaryDirectory() as tmpdir:
            paths, success, failed = generate_and_save_corpus(
                "javascript", tmpdir, validate=True
            )
            assert len(paths) > 0
            assert success > 0
            assert all(path.exists() for path in paths)

    def test_java_end_to_end(self) -> None:
        """测试 Java 端到端流程"""
        with tempfile.TemporaryDirectory() as tmpdir:
            paths, success, failed = generate_and_save_corpus(
                "java", tmpdir, validate=True
            )
            assert len(paths) > 0
            assert success > 0
            assert all(path.exists() for path in paths)

    def test_without_validation(self) -> None:
        """测试跳过验证的情况"""
        with tempfile.TemporaryDirectory() as tmpdir:
            paths, success, failed = generate_and_save_corpus(
                "python", tmpdir, validate=False
            )
            assert len(paths) > 0
            assert success == 0  # No validation performed
            assert failed == 0

    def test_unsupported_language_end_to_end(self) -> None:
        """测试不支持的语言端到端流程"""
        with tempfile.TemporaryDirectory() as tmpdir:
            paths, success, failed = generate_and_save_corpus(
                "cobol", tmpdir, validate=True
            )
            assert len(paths) == 0
            assert success == 0
            assert failed == 0


class TestCorpusValidation:
    """测试生成的语料库可被 tree-sitter 成功解析"""

    def test_all_python_templates_valid(self) -> None:
        """测试所有 Python 模板都是有效的"""
        corpus = generate_corpus_by_category("python")
        for relative_path, code in corpus.items():
            # 移除注释行后验证
            code_lines = [
                line for line in code.split("\n") if not line.strip().startswith("#")
            ]
            clean_code = "\n".join(code_lines)
            if clean_code.strip():  # 只验证非空代码
                assert validate_generated_code(
                    "python", clean_code
                ), f"Invalid code in {relative_path}"

    def test_all_javascript_templates_valid(self) -> None:
        """测试所有 JavaScript 模板都是有效的"""
        corpus = generate_corpus_by_category("javascript")
        for relative_path, code in corpus.items():
            code_lines = [
                line for line in code.split("\n") if not line.strip().startswith("//")
            ]
            clean_code = "\n".join(code_lines)
            if clean_code.strip():
                assert validate_generated_code(
                    "javascript", clean_code
                ), f"Invalid code in {relative_path}"

    def test_all_java_templates_valid(self) -> None:
        """测试所有 Java 模板都是有效的"""
        corpus = generate_corpus_by_category("java")
        for relative_path, code in corpus.items():
            code_lines = [
                line for line in code.split("\n") if not line.strip().startswith("//")
            ]
            clean_code = "\n".join(code_lines)
            if clean_code.strip():
                assert validate_generated_code(
                    "java", clean_code
                ), f"Invalid code in {relative_path}"
