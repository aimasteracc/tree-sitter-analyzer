"""Multi-language tests for magic value detection."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.magic_values import MagicValueDetector


class TestJavaScript:
    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.detector = MagicValueDetector("javascript")

    def test_js_magic_number(self) -> None:
        code = b"const x = 42; const y = 100;"
        with tempfile.NamedTemporaryFile(suffix=".js", delete=False) as f:
            f.write(code)
            p = Path(f.name)
        result = self.detector.detect(p)
        nums = [r for r in result.references if r.category == "magic_number"]
        values = {r.value for r in nums}
        assert "42" in values
        assert "100" in values

    def test_js_url(self) -> None:
        code = b'const url = "https://api.example.com/v1";'
        with tempfile.NamedTemporaryFile(suffix=".js", delete=False) as f:
            f.write(code)
            p = Path(f.name)
        result = self.detector.detect(p)
        urls = [r for r in result.references if r.category == "hardcoded_url"]
        assert len(urls) >= 1

    def test_js_string(self) -> None:
        code = b'const msg = "hello world from test";'
        with tempfile.NamedTemporaryFile(suffix=".js", delete=False) as f:
            f.write(code)
            p = Path(f.name)
        result = self.detector.detect(p)
        strs = [r for r in result.references if r.category == "magic_string"]
        assert len(strs) >= 1
        assert "hello world from test" in strs[0].value

    def test_js_safe_numbers(self) -> None:
        code = b"const a = 0; const b = 1; const c = -1;"
        with tempfile.NamedTemporaryFile(suffix=".js", delete=False) as f:
            f.write(code)
            p = Path(f.name)
        result = self.detector.detect(p)
        nums = [r for r in result.references if r.category == "magic_number"]
        assert len(nums) == 0


class TestJava:
    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.detector = MagicValueDetector("java")

    def test_java_magic_number(self) -> None:
        code = b"int x = 42; int y = 100;"
        with tempfile.NamedTemporaryFile(suffix=".java", delete=False) as f:
            f.write(code)
            p = Path(f.name)
        result = self.detector.detect(p)
        nums = [r for r in result.references if r.category == "magic_number"]
        values = {r.value for r in nums}
        assert "42" in values
        assert "100" in values

    def test_java_string(self) -> None:
        code = b'String msg = "hello world from java";'
        with tempfile.NamedTemporaryFile(suffix=".java", delete=False) as f:
            f.write(code)
            p = Path(f.name)
        result = self.detector.detect(p)
        strs = [r for r in result.references if r.category == "magic_string"]
        assert len(strs) >= 1


class TestGo:
    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.detector = MagicValueDetector("go")

    def test_go_magic_number(self) -> None:
        code = b'package main\n\nfunc main() {\n\tx := 42\n\ty := 100\n}'
        with tempfile.NamedTemporaryFile(suffix=".go", delete=False) as f:
            f.write(code)
            p = Path(f.name)
        result = self.detector.detect(p)
        nums = [r for r in result.references if r.category == "magic_number"]
        values = {r.value for r in nums}
        assert "42" in values
        assert "100" in values

    def test_go_string(self) -> None:
        code = b'package main\n\nfunc main() {\n\ts := "hello world from go"\n}'
        with tempfile.NamedTemporaryFile(suffix=".go", delete=False) as f:
            f.write(code)
            p = Path(f.name)
        result = self.detector.detect(p)
        strs = [r for r in result.references if r.category == "magic_string"]
        assert len(strs) >= 1

    def test_go_safe_numbers(self) -> None:
        code = b'package main\n\nfunc main() {\n\ta := 0\n\tb := 1\n}'
        with tempfile.NamedTemporaryFile(suffix=".go", delete=False) as f:
            f.write(code)
            p = Path(f.name)
        result = self.detector.detect(p)
        nums = [r for r in result.references if r.category == "magic_number"]
        assert len(nums) == 0


class TestTypeScript:
    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.detector = MagicValueDetector("typescript")

    def test_ts_magic_number(self) -> None:
        code = b"const x: number = 42;"
        with tempfile.NamedTemporaryFile(suffix=".ts", delete=False) as f:
            f.write(code)
            p = Path(f.name)
        result = self.detector.detect(p)
        nums = [r for r in result.references if r.category == "magic_number"]
        assert len(nums) >= 1
        assert nums[0].value == "42"

    def test_ts_url(self) -> None:
        code = b'const endpoint: string = "https://api.example.com/graphql";'
        with tempfile.NamedTemporaryFile(suffix=".ts", delete=False) as f:
            f.write(code)
            p = Path(f.name)
        result = self.detector.detect(p)
        urls = [r for r in result.references if r.category == "hardcoded_url"]
        assert len(urls) >= 1
