#!/usr/bin/env python3
"""
Format Regression Tests - 测试各种语言的格式稳定性
"""

import json
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.core.analysis_engine import UnifiedAnalysisEngine


class TestFormatRegressionPython:
    """Python格式稳定性测试"""

    @pytest.mark.regression
    def test_python_format_stability(self, tmp_path):
        """测试Python格式稳定性"""
        # 创建测试Python文件
        test_file = tmp_path / "test_format.py"
        test_file.write_text(
            """
class TestClass:
    def test_method(self):
        return "test"

def test_function():
    return "function"
"""
        )

        # 执行分析
        engine = UnifiedAnalysisEngine()
        import asyncio

        result = asyncio.run(
            engine.analyze_file(
                file_path=str(test_file),
                language="python",
                format_type="json",
            )
        )

        # 验证结果结构
        assert result is not None
        assert hasattr(result, "elements")
        assert result.elements is not None

        # 验证Golden Master一致性
        golden_master = self._get_golden_master("python", test_file.name)
        if golden_master:
            self._compare_with_golden_master(result, golden_master)

    def _get_golden_master(self, language: str, filename: str) -> dict[str, Any] | None:
        """获取Golden Master数据"""
        golden_file = (
            Path(__file__).parent / "golden_masters" / language / f"{filename}.json"
        )
        if golden_file.exists():
            with open(golden_file, encoding="utf-8") as f:
                return json.load(f)
        return None

    def _compare_with_golden_master(
        self, result: dict[str, Any], golden: dict[str, Any]
    ) -> None:
        """与Golden Master比较"""
        # 比较基本结构
        assert result.get("elements") == golden.get("elements")
        assert result.get("language") == golden.get("language")

    @pytest.mark.regression
    def test_python_format_detailed_analysis(self, tmp_path):
        """测试Python详细分析格式"""
        test_file = tmp_path / "test_detailed.py"
        test_file.write_text(
            """
import os
from typing import List, Optional

def complex_function(param: Optional[str] = None) -> List[str]:
    if param:
        return [param]
    return []
"""
        )

        engine = UnifiedAnalysisEngine()
        import asyncio

        result = asyncio.run(
            engine.analyze_file(
                file_path=str(test_file),
                language="python",
                format_type="json",
                include_details=True,
            )
        )

        assert result is not None
        assert hasattr(result, "elements")
        assert result.elements is not None


class TestFormatRegressionJava:
    """Java格式稳定性测试"""

    @pytest.mark.regression
    def test_java_format_stability(self, tmp_path):
        """测试Java格式稳定性"""
        test_file = tmp_path / "TestFormat.java"
        test_file.write_text(
            """
public class TestFormat {
    private String name;

    public TestFormat(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
"""
        )

        engine = UnifiedAnalysisEngine()
        import asyncio

        result = asyncio.run(
            engine.analyze_file(
                file_path=str(test_file),
                language="java",
                format_type="json",
            )
        )

        assert result is not None
        assert hasattr(result, "elements")
        assert result.elements is not None

    @pytest.mark.regression
    def test_java_format_with_imports(self, tmp_path):
        """测试带导入的Java格式"""
        test_file = tmp_path / "TestImports.java"
        test_file.write_text(
            """
import java.util.List;

public class TestImports {
    private List<String> items = new ArrayList<>();

    public void addItem(String item) {
        items.add(item);
    }
}
"""
        )

        engine = UnifiedAnalysisEngine()
        import asyncio

        result = asyncio.run(
            engine.analyze_file(
                file_path=str(test_file),
                language="java",
                format_type="json",
            )
        )

        assert result is not None
        assert hasattr(result, "elements")
        assert result.elements is not None


class TestFormatRegressionJavaScript:
    """JavaScript格式稳定性测试"""

    @pytest.mark.regression
    def test_javascript_format_stability(self, tmp_path):
        """测试JavaScript格式稳定性"""
        test_file = tmp_path / "test_format.js"
        test_file.write_text(
            """
class TestClass {
    constructor(name) {
        this.name = name;
    }

    getName() {
        return this.name;
    }
}

function testFunction() {
    return "test";
}
"""
        )

        engine = UnifiedAnalysisEngine()
        import asyncio

        result = asyncio.run(
            engine.analyze_file(
                file_path=str(test_file),
                language="javascript",
                format_type="json",
            )
        )

        assert result is not None
        assert hasattr(result, "elements")
        assert result.elements is not None

    @pytest.mark.regression
    def test_javascript_es6_format(self, tmp_path):
        """测试ES6格式"""
        test_file = tmp_path / "test_es6.js"
        test_file.write_text(
            """
const testArrow = () => {
    return "arrow function";
};

class TestClass {
    static method() {
        return "static";
    }
}
"""
        )

        engine = UnifiedAnalysisEngine()
        import asyncio

        result = asyncio.run(
            engine.analyze_file(
                file_path=str(test_file),
                language="javascript",
                format_type="json",
            )
        )

        assert result is not None
        assert hasattr(result, "elements")
        assert result.elements is not None


class TestFormatRegressionTypeScript:
    """TypeScript格式稳定性测试"""

    @pytest.mark.regression
    def test_typescript_format_stability(self, tmp_path):
        """测试TypeScript格式稳定性"""
        test_file = tmp_path / "test_format.ts"
        test_file.write_text(
            """
interface TestInterface {
    name: string;
    getValue(): number;
}

class TestClass implements TestInterface {
    constructor(public name: string) {
        // Implementation
    }

    getValue(): number {
        return 42;
    }
}
"""
        )

        engine = UnifiedAnalysisEngine()
        import asyncio

        result = asyncio.run(
            engine.analyze_file(
                file_path=str(test_file),
                language="typescript",
                format_type="json",
            )
        )

        assert result is not None
        assert hasattr(result, "elements")
        assert result.elements is not None


class TestFormatRegressionCSharp:
    """C#格式稳定性测试"""

    @pytest.mark.regression
    def test_csharp_format_stability(self, tmp_path):
        """测试C#格式稳定性"""
        test_file = tmp_path / "TestFormat.cs"
        test_file.write_text(
            """
using System;

public class TestFormat
{
    private string _name;

    public TestFormat(string name)
    {
        this._name = name;
    }

    public string GetName()
    {
        return _name;
    }
}
"""
        )

        engine = UnifiedAnalysisEngine()
        import asyncio

        result = asyncio.run(
            engine.analyze_file(
                file_path=str(test_file),
                language="csharp",
                format_type="json",
            )
        )

        assert result is not None
        assert hasattr(result, "elements")
        assert result.elements is not None


class TestFormatRegressionGo:
    """Go格式稳定性测试"""

    @pytest.mark.regression
    def test_go_format_stability(self, tmp_path):
        """测试Go格式稳定性"""
        test_file = tmp_path / "test_format.go"
        test_file.write_text(
            """
package main

import "fmt"

type TestStruct struct {
    Name string
}

func (t *TestStruct) GetName() string {
    return t.Name
}

func main() {
    fmt.Println("Hello, World!")
}
"""
        )

        engine = UnifiedAnalysisEngine()
        import asyncio

        result = asyncio.run(
            engine.analyze_file(
                file_path=str(test_file),
                language="go",
                format_type="json",
            )
        )

        assert result is not None
        assert hasattr(result, "elements")
        assert result.elements is not None


class TestFormatRegressionRust:
    """Rust格式稳定性测试"""

    @pytest.mark.regression
    def test_rust_format_stability(self, tmp_path):
        """测试Rust格式稳定性"""
        test_file = tmp_path / "test_format.rs"
        test_file.write_text(
            """
struct TestStruct {
    name: String,
}

impl TestStruct {
    fn new(name: String) -> Self {
        Self { name }
    }

    fn get_name(&self) -> &str {
        &self.name
    }
}

fn main() {
    let test = TestStruct::new(String::from("test"));
    println!("{}", test.get_name());
}
"""
        )

        engine = UnifiedAnalysisEngine()
        import asyncio

        result = asyncio.run(
            engine.analyze_file(
                file_path=str(test_file),
                language="rust",
                format_type="json",
            )
        )

        assert result is not None
        assert hasattr(result, "elements")
        assert result.elements is not None


class TestFormatRegressionToon:
    """Toon格式稳定性测试"""

    @pytest.mark.regression
    def test_toon_format_stability(self, tmp_path):
        """测试Toon格式稳定性"""
        test_file = tmp_path / "test_format.py"
        test_file.write_text(
            """
class TestClass:
    def test_method(self):
        return "test"
"""
        )

        engine = UnifiedAnalysisEngine()
        import asyncio

        result = asyncio.run(
            engine.analyze_file(
                file_path=str(test_file),
                language="python",
                format_type="toon",
            )
        )

        assert result is not None
        assert hasattr(result, "elements")
        assert result.elements is not None

    @pytest.mark.regression
    def test_toon_format_with_details(self, tmp_path):
        """测试Toon格式带详细信息"""
        test_file = tmp_path / "test_detailed.py"
        test_file.write_text(
            """
def complex_function(param):
    return param
"""
        )

        engine = UnifiedAnalysisEngine()
        import asyncio

        result = asyncio.run(
            engine.analyze_file(
                file_path=str(test_file),
                language="python",
                format_type="toon",
                include_details=True,
            )
        )

        assert result is not None
        assert hasattr(result, "elements")
        assert result.elements is not None


class TestFormatRegressionMarkdown:
    """Markdown格式稳定性测试"""

    @pytest.mark.regression
    def test_markdown_format_stability(self, tmp_path):
        """测试Markdown格式稳定性"""
        test_file = tmp_path / "test_format.md"
        test_file.write_text(
            """
# Test Document

## Section 1

This is a test paragraph.

### Subsection

- Item 1
- Item 2
"""
        )

        engine = UnifiedAnalysisEngine()
        import asyncio

        result = asyncio.run(
            engine.analyze_file(
                file_path=str(test_file),
                language="markdown",
                format_type="json",
            )
        )

        assert result is not None
        assert hasattr(result, "elements")
        assert result.elements is not None


# CSV is not a supported language for code analysis, removing this test class
# class TestFormatRegressionCSV:
#     """CSV格式稳定性测试"""
#
#     @pytest.mark.regression
#     def test_csv_format_stability(self, tmp_path):
#         """测试CSV格式稳定性"""
#         # CSV is not a programming language and is not supported
#         pass


class TestGoldenMasterUpdate:
    """Golden Master自动更新机制测试"""

    @pytest.mark.regression
    def test_update_golden_master_python(self, tmp_path, monkeypatch):
        """测试Python Golden Master更新"""
        import sys

        # 模拟--update-golden-master参数
        monkeypatch.setattr(sys, "argv", ["pytest", "--update-golden-master"])

        test_file = tmp_path / "test_update.py"
        test_file.write_text("def test(): return 'updated'")

        # 创建golden_masters目录
        golden_dir = tmp_path / "golden_masters" / "python"
        golden_dir.mkdir(parents=True)

        # 如果存在Golden Master，应该更新
        golden_file = golden_dir / "test_update.py.json"
        if golden_file.exists():
            # 模拟更新逻辑
            pass

    @pytest.mark.regression
    def test_create_new_golden_master(self, tmp_path):
        """测试创建新的Golden Master"""
        test_file = tmp_path / "test_new.py"
        test_file.write_text("def new_test(): return 'new'")

        engine = UnifiedAnalysisEngine()
        import asyncio

        result = asyncio.run(
            engine.analyze_file(
                file_path=str(test_file),
                language="python",
                format_type="json",
            )
        )

        # 创建Golden Master
        golden_dir = tmp_path / "golden_masters" / "python"
        golden_dir.mkdir(parents=True)
        golden_file = golden_dir / "test_new.py.json"

        with open(golden_file, "w", encoding="utf-8") as f:
            # Convert AnalysisResult to dict before JSON serialization
            json.dump(
                result.to_dict() if hasattr(result, "to_dict") else result, f, indent=2
            )

        assert golden_file.exists()

    @pytest.mark.regression
    def test_golden_master_consistency(self, tmp_path):
        """测试Golden Master一致性"""
        test_file = tmp_path / "test_consistency.py"
        test_file.write_text("class Test: pass")

        engine = UnifiedAnalysisEngine()
        import asyncio

        result1 = asyncio.run(
            engine.analyze_file(
                file_path=str(test_file),
                language="python",
                format_type="json",
            )
        )

        result2 = asyncio.run(
            engine.analyze_file(
                file_path=str(test_file),
                language="python",
                format_type="json",
            )
        )

        # 两次分析结果应该一致
        assert result1 == result2
