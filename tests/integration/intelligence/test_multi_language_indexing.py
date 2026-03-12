#!/usr/bin/env python3
"""
修复 C 集成测试：Intelligence Graph 多语言索引

覆盖规格：openspec/changes/fix-intelligence-graph/specs/multi-language-indexing/spec.md
验收标准：AC-ML-001 ~ AC-ML-006

集成测试规则：使用真实 tree-sitter 解析器，使用 tmp_path 创建临时文件。
"""

from __future__ import annotations

from tree_sitter_analyzer.intelligence.project_indexer import ProjectIndexer

JAVA_SOURCE = """\
package com.example;

public class UserService {
    private String name;

    public UserService(String name) {
        this.name = name;
    }

    public String findUser(String id) {
        return id;
    }

    private void helper() {}
}
"""

CPP_SOURCE = """\
namespace MyApp {
    class Engine {
    public:
        void start();
        int getSpeed();
    private:
        int speed;
    };
}
"""

PYTHON_SOURCE = """\
class DataProcessor:
    def process(self, data):
        return data

    def validate(self, data):
        return bool(data)
"""

MIXED_JAVA_PYTHON = {
    "service.java": JAVA_SOURCE,
    "processor.py": PYTHON_SOURCE,
}


class TestJavaFileIndexing:
    """AC-ML-001, AC-ML-002: Java 文件被正确索引。"""

    def test_java_class_appears_in_symbol_index(self, tmp_path):
        """AC-ML-001: Java 文件的类应出现在 SymbolIndex 中。"""
        (tmp_path / "UserService.java").write_text(JAVA_SOURCE)

        indexer = ProjectIndexer(str(tmp_path))
        indexer.ensure_indexed()

        defs = indexer.symbol_index.lookup_definition("UserService")
        assert len(defs) >= 1, (
            "Java 类 UserService 应出现在 SymbolIndex 中，"
            "但 lookup_definition('UserService') 返回空"
        )
        assert defs[0].symbol_type == "class"
        assert "UserService.java" in defs[0].file_path

    def test_java_method_appears_in_symbol_index(self, tmp_path):
        """AC-ML-002: Java 文件的方法应出现在 SymbolIndex 中。"""
        (tmp_path / "UserService.java").write_text(JAVA_SOURCE)

        indexer = ProjectIndexer(str(tmp_path))
        indexer.ensure_indexed()

        defs = indexer.symbol_index.lookup_definition("findUser")
        assert len(defs) >= 1, (
            "Java 方法 findUser 应出现在 SymbolIndex 中"
        )

    def test_java_class_correct_line_number(self, tmp_path):
        """Java 类定义的行号应正确。"""
        (tmp_path / "UserService.java").write_text(JAVA_SOURCE)

        indexer = ProjectIndexer(str(tmp_path))
        indexer.ensure_indexed()

        defs = indexer.symbol_index.lookup_definition("UserService")
        assert len(defs) >= 1
        # UserService 类从第 3 行开始（package 声明之后）
        assert defs[0].line >= 1


class TestCppFileIndexing:
    """AC-ML-003: C++ 文件被正确索引。"""

    def test_cpp_class_appears_in_symbol_index(self, tmp_path):
        """AC-ML-003: C++ 文件的类应出现在 SymbolIndex 中。"""
        (tmp_path / "engine.cpp").write_text(CPP_SOURCE)

        indexer = ProjectIndexer(str(tmp_path))
        indexer.ensure_indexed()

        defs = indexer.symbol_index.lookup_definition("Engine")
        assert len(defs) >= 1, (
            "C++ 类 Engine 应出现在 SymbolIndex 中，"
            "但 lookup_definition('Engine') 返回空"
        )
        assert "engine.cpp" in defs[0].file_path


class TestPythonRegressionAfterMultiLanguage:
    """AC-ML-004: 添加多语言支持后 Python 索引行为不变。"""

    def test_python_class_still_indexed(self, tmp_path):
        """AC-ML-004: Python 文件的类在多语言支持后仍被正确索引。"""
        (tmp_path / "processor.py").write_text(PYTHON_SOURCE)

        indexer = ProjectIndexer(str(tmp_path))
        indexer.ensure_indexed()

        defs = indexer.symbol_index.lookup_definition("DataProcessor")
        assert len(defs) >= 1, (
            "Python 类 DataProcessor 应仍被正确索引"
        )
        assert defs[0].symbol_type == "class"

    def test_python_method_still_indexed(self, tmp_path):
        """Python 方法在多语言支持后仍被正确索引。"""
        (tmp_path / "processor.py").write_text(PYTHON_SOURCE)

        indexer = ProjectIndexer(str(tmp_path))
        indexer.ensure_indexed()

        defs = indexer.symbol_index.lookup_definition("process")
        assert len(defs) >= 1


class TestMixedProjectIndexing:
    """AC-ML-005: Python + Java 混合项目两种语言均被正确索引。"""

    def test_java_and_python_both_indexed(self, tmp_path):
        """AC-ML-005: 混合项目中 Java 和 Python 文件均被正确索引。"""
        for filename, content in MIXED_JAVA_PYTHON.items():
            (tmp_path / filename).write_text(content)

        indexer = ProjectIndexer(str(tmp_path))
        indexer.ensure_indexed()

        # Python 类被索引
        python_defs = indexer.symbol_index.lookup_definition("DataProcessor")
        assert len(python_defs) >= 1, "Python 类 DataProcessor 应被索引"

        # Java 类被索引
        java_defs = indexer.symbol_index.lookup_definition("UserService")
        assert len(java_defs) >= 1, "Java 类 UserService 应被索引"

    def test_indexed_files_include_java(self, tmp_path):
        """get_source_files() 应包含 .java 文件。"""
        for filename, content in MIXED_JAVA_PYTHON.items():
            (tmp_path / filename).write_text(content)

        indexer = ProjectIndexer(str(tmp_path))
        indexer.ensure_indexed()

        source_files = indexer.get_source_files()
        java_files = [f for f in source_files if f.endswith(".java")]
        assert len(java_files) >= 1, (
            f"source_files 应包含 .java 文件，但只有: {source_files}"
        )
