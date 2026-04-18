"""Unit tests for SOLID Principles Analyzer."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.solid_principles import (
    SEVERITY_HIGH,
    SRP_VIOLATION,
    SOLIDPrinciplesAnalyzer,
)


@pytest.fixture
def analyzer() -> SOLIDPrinciplesAnalyzer:
    return SOLIDPrinciplesAnalyzer()


def _write_tmp(content: str, suffix: str = ".py") -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


# ── Python SRP Tests ──


class TestPythonSRP:
    def test_clean_class_no_violations(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        code = """
class UserService:
    def __init__(self, db):
        self.db = db

    def get_user(self, user_id):
        return self.db.find(user_id)

    def create_user(self, name, email):
        return self.db.insert({"name": name, "email": email})

    def update_user(self, user_id, data):
        return self.db.update(user_id, data)
"""
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            srp_violations = [v for v in result.violations if v.principle == "SRP"]
            assert len(srp_violations) == 0
        finally:
            path.unlink()

    def test_too_many_methods_triggers_srp(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        methods = "\n".join(f"    def method_{i}(self): pass" for i in range(12))
        code = f"class GodClass:\n{methods}\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            srp_violations = [v for v in result.violations if v.principle == "SRP"]
            assert len(srp_violations) >= 1
            assert any(v.violation_type == SRP_VIOLATION for v in srp_violations)
            assert "GodClass" in srp_violations[0].element_name
        finally:
            path.unlink()

    def test_very_long_class_triggers_srp(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        body = "\n".join(["    x = 1"] * 350)
        code = f"class LongClass:\n{body}\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            srp_violations = [v for v in result.violations if v.principle == "SRP"]
            assert len(srp_violations) >= 1
        finally:
            path.unlink()

    def test_srp_score_decreases_with_violations(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        methods = "\n".join(f"    def method_{i}(self): pass" for i in range(15))
        code = f"class GodClass:\n{methods}\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            srp_score = next(
                s.score for s in result.principle_scores if s.principle == "SRP"
            )
            assert srp_score < 100.0
        finally:
            path.unlink()


# ── Python OCP Tests ──


class TestPythonOCP:
    def test_isinstance_triggers_ocp(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        code = """
class ShapeRenderer:
    def render(self, shape):
        if isinstance(shape, Circle):
            self.draw_circle(shape)
        elif isinstance(shape, Square):
            self.draw_square(shape)
"""
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            ocp_violations = [v for v in result.violations if v.principle == "OCP"]
            assert len(ocp_violations) >= 1
            assert ocp_violations[0].severity == SEVERITY_HIGH
        finally:
            path.unlink()

    def test_type_check_triggers_ocp(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        code = """
class Handler:
    def process(self, data):
        if type(data) == dict:
            return self.handle_dict(data)
"""
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            ocp_violations = [v for v in result.violations if v.principle == "OCP"]
            assert len(ocp_violations) >= 1
        finally:
            path.unlink()

    def test_no_type_check_no_ocp_violation(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        code = """
class ShapeRenderer:
    def render(self, shape):
        shape.draw()
"""
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            ocp_violations = [v for v in result.violations if v.principle == "OCP"]
            assert len(ocp_violations) == 0
        finally:
            path.unlink()


# ── Python LSP Tests ──


class TestPythonLSP:
    def test_not_implemented_error_triggers_lsp(
        self, analyzer: SOLIDPrinciplesAnalyzer,
    ) -> None:
        code = """
class Bird:
    def fly(self):
        raise NotImplementedError

class Penguin(Bird):
    def fly(self):
        raise NotImplementedError("Penguins can't fly")
"""
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            lsp_violations = [v for v in result.violations if v.principle == "LSP"]
            assert len(lsp_violations) >= 1
            assert lsp_violations[0].severity == SEVERITY_HIGH
        finally:
            path.unlink()

    def test_proper_override_no_lsp_violation(
        self, analyzer: SOLIDPrinciplesAnalyzer,
    ) -> None:
        code = """
class Animal:
    def speak(self):
        return "..."

class Dog(Animal):
    def speak(self):
        return "Woof!"
"""
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            lsp_violations = [v for v in result.violations if v.principle == "LSP"]
            assert len(lsp_violations) == 0
        finally:
            path.unlink()


# ── Python ISP Tests ──


class TestPythonISP:
    def test_fat_protocol_triggers_isp(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        methods = "\n".join(f"    def method_{i}(self): ..." for i in range(18))
        code = f"from typing import Protocol\n\n\nclass FatProtocol(Protocol):\n{methods}\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            isp_violations = [v for v in result.violations if v.principle == "ISP"]
            assert len(isp_violations) >= 1
            assert "FatProtocol" in isp_violations[0].element_name
        finally:
            path.unlink()

    def test_small_protocol_no_isp_violation(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        code = """
from typing import Protocol

class UserRepository(Protocol):
    def find(self, id: int): ...
    def save(self, entity): ...
    def delete(self, id: int): ...
"""
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            isp_violations = [v for v in result.violations if v.principle == "ISP"]
            assert len(isp_violations) == 0
        finally:
            path.unlink()

    def test_fat_abc_triggers_isp(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        methods = "\n".join(f"    def method_{i}(self): ..." for i in range(18))
        code = f"from abc import ABC\n\n\nclass FatABC(ABC):\n{methods}\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            isp_violations = [v for v in result.violations if v.principle == "ISP"]
            assert len(isp_violations) >= 1
        finally:
            path.unlink()


# ── Python DIP Tests ──


class TestPythonDIP:
    def test_import_concrete_impl_triggers_dip(
        self, analyzer: SOLIDPrinciplesAnalyzer,
    ) -> None:
        code = "from services.user_service_impl import UserServiceImpl\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            dip_violations = [v for v in result.violations if v.principle == "DIP"]
            assert len(dip_violations) >= 1
            assert "impl" in dip_violations[0].element_name.lower()
        finally:
            path.unlink()

    def test_import_abstract_no_dip_violation(
        self, analyzer: SOLIDPrinciplesAnalyzer,
    ) -> None:
        code = "from repositories.base import BaseRepository\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            dip_violations = [v for v in result.violations if v.principle == "DIP"]
            assert len(dip_violations) == 0
        finally:
            path.unlink()


# ── JavaScript Tests ──


class TestJavaScriptSOLID:
    def test_js_too_many_methods_srp(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        methods = "\n".join(f"  method{i}() {{}}" for i in range(12))
        code = f"class GodClass {{\n{methods}\n}}\n"
        path = _write_tmp(code, suffix=".js")
        try:
            result = analyzer.analyze_file(path)
            srp_violations = [v for v in result.violations if v.principle == "SRP"]
            assert len(srp_violations) >= 1
        finally:
            path.unlink()

    def test_js_instanceof_triggers_ocp(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        code = """
class Handler {
  process(obj) {
    if (obj instanceof Array) {
      return this.handleArray(obj);
    }
  }
}
"""
        path = _write_tmp(code, suffix=".js")
        try:
            result = analyzer.analyze_file(path)
            ocp_violations = [v for v in result.violations if v.principle == "OCP"]
            assert len(ocp_violations) >= 1
        finally:
            path.unlink()

    def test_js_typeof_triggers_ocp(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        code = """
class Processor {
  handle(value) {
    if (typeof value === 'string') {
      return this.processString(value);
    }
  }
}
"""
        path = _write_tmp(code, suffix=".js")
        try:
            result = analyzer.analyze_file(path)
            ocp_violations = [v for v in result.violations if v.principle == "OCP"]
            assert len(ocp_violations) >= 1
        finally:
            path.unlink()

    def test_js_import_concrete_dip(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        code = "import { UserServiceImpl } from './services/userServiceImpl';\n"
        path = _write_tmp(code, suffix=".js")
        try:
            result = analyzer.analyze_file(path)
            dip_violations = [v for v in result.violations if v.principle == "DIP"]
            assert len(dip_violations) >= 1
        finally:
            path.unlink()

    def test_js_clean_class_no_violations(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        code = """
class UserService {
  constructor(db) { this.db = db; }
  getUser(id) { return this.db.find(id); }
}
"""
        path = _write_tmp(code, suffix=".js")
        try:
            result = analyzer.analyze_file(path)
            assert result.overall_score == 100.0
        finally:
            path.unlink()


# ── TypeScript Tests ──


class TestTypeScriptSOLID:
    def test_ts_too_many_methods_srp(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        methods = "\n".join(f"  method{i}(): void {{}}" for i in range(12))
        code = f"class GodClass {{\n{methods}\n}}\n"
        path = _write_tmp(code, suffix=".ts")
        try:
            result = analyzer.analyze_file(path)
            srp_violations = [v for v in result.violations if v.principle == "SRP"]
            assert len(srp_violations) >= 1
        finally:
            path.unlink()

    def test_ts_instanceof_triggers_ocp(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        code = """
class Handler {
  process(obj: unknown): string {
    if (obj instanceof Array) {
      return "array";
    }
    return "unknown";
  }
}
"""
        path = _write_tmp(code, suffix=".ts")
        try:
            result = analyzer.analyze_file(path)
            ocp_violations = [v for v in result.violations if v.principle == "OCP"]
            assert len(ocp_violations) >= 1
        finally:
            path.unlink()

    def test_ts_clean_class_no_violations(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        code = """
class UserService {
  private db: any;
  constructor(db: any) { this.db = db; }
  getUser(id: number): any { return this.db.find(id); }
}
"""
        path = _write_tmp(code, suffix=".ts")
        try:
            result = analyzer.analyze_file(path)
            assert result.overall_score == 100.0
        finally:
            path.unlink()


# ── Java Tests ──


class TestJavaSOLID:
    def test_java_too_many_methods_srp(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        methods = "\n".join(
            f"    public void method{i}() {{}}" for i in range(14)
        )
        code = f"""
public class GodClass {{
{methods}
}}
"""
        path = _write_tmp(code, suffix=".java")
        try:
            result = analyzer.analyze_file(path)
            srp_violations = [v for v in result.violations if v.principle == "SRP"]
            assert len(srp_violations) >= 1
            assert "GodClass" in srp_violations[0].element_name
        finally:
            path.unlink()

    def test_java_instanceof_triggers_ocp(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        code = """
public class Handler {
    public String process(Object obj) {
        if (obj instanceof String) {
            return ((String) obj).toUpperCase();
        }
        return obj.toString();
    }
}
"""
        path = _write_tmp(code, suffix=".java")
        try:
            result = analyzer.analyze_file(path)
            ocp_violations = [v for v in result.violations if v.principle == "OCP"]
            assert len(ocp_violations) >= 1
        finally:
            path.unlink()

    def test_java_fat_interface_isp(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        methods = "\n".join(
            f"    void method{i}();" for i in range(18)
        )
        code = f"""
public interface FatInterface {{
{methods}
}}
"""
        path = _write_tmp(code, suffix=".java")
        try:
            result = analyzer.analyze_file(path)
            isp_violations = [v for v in result.violations if v.principle == "ISP"]
            assert len(isp_violations) >= 1
            assert "FatInterface" in isp_violations[0].element_name
        finally:
            path.unlink()

    def test_java_small_interface_no_isp(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        code = """
public interface Repository {
    Object find(int id);
    void save(Object entity);
    void delete(int id);
}
"""
        path = _write_tmp(code, suffix=".java")
        try:
            result = analyzer.analyze_file(path)
            isp_violations = [v for v in result.violations if v.principle == "ISP"]
            assert len(isp_violations) == 0
        finally:
            path.unlink()

    def test_java_import_concrete_dip(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        code = "import com.example.services.UserServiceImpl;\n"
        path = _write_tmp(code, suffix=".java")
        try:
            result = analyzer.analyze_file(path)
            dip_violations = [v for v in result.violations if v.principle == "DIP"]
            assert len(dip_violations) >= 1
        finally:
            path.unlink()

    def test_java_clean_class_no_violations(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        code = """
public class UserService {
    private Repository repo;

    public UserService(Repository repo) {
        this.repo = repo;
    }

    public Object getUser(int id) {
        return repo.find(id);
    }
}
"""
        path = _write_tmp(code, suffix=".java")
        try:
            result = analyzer.analyze_file(path)
            assert result.overall_score == 100.0
        finally:
            path.unlink()


# ── Go Tests ──


class TestGoSOLID:
    def test_go_fat_interface_isp(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        methods = "\n".join(f"\tMethod{i}()" for i in range(12))
        code = f"""package main

type FatInterface interface {{
{methods}
}}
"""
        path = _write_tmp(code, suffix=".go")
        try:
            result = analyzer.analyze_file(path)
            isp_violations = [v for v in result.violations if v.principle == "ISP"]
            assert len(isp_violations) >= 1
            assert "FatInterface" in isp_violations[0].element_name
        finally:
            path.unlink()

    def test_go_small_interface_no_isp(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        code = """package main

type Reader interface {
    Read(p []byte) (n int, err error)
}
"""
        path = _write_tmp(code, suffix=".go")
        try:
            result = analyzer.analyze_file(path)
            isp_violations = [v for v in result.violations if v.principle == "ISP"]
            assert len(isp_violations) == 0
        finally:
            path.unlink()

    def test_go_type_switch_triggers_ocp(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        code = """package main

func process(v interface{}) {
    switch t := v.(type) {
    case string:
        println(t)
    case int:
        println(t)
    }
}
"""
        path = _write_tmp(code, suffix=".go")
        try:
            result = analyzer.analyze_file(path)
            ocp_violations = [v for v in result.violations if v.principle == "OCP"]
            assert len(ocp_violations) >= 1
        finally:
            path.unlink()

    def test_go_many_methods_srp(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        methods = "\n".join(
            f"func (s *Service) Method{i}() {{}}" for i in range(12)
        )
        code = f"package main\n\n{methods}\n"
        path = _write_tmp(code, suffix=".go")
        try:
            result = analyzer.analyze_file(path)
            srp_violations = [v for v in result.violations if v.principle == "SRP"]
            assert len(srp_violations) >= 1
        finally:
            path.unlink()


# ── General Tests ──


class TestGeneral:
    def test_unsupported_extension_returns_100(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        path = _write_tmp("hello", suffix=".txt")
        try:
            result = analyzer.analyze_file(path)
            assert result.overall_score == 100.0
            assert result.language == "unknown"
        finally:
            path.unlink()

    def test_empty_file_returns_100(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        path = _write_tmp("", suffix=".py")
        try:
            result = analyzer.analyze_file(path)
            assert result.overall_score == 100.0
        finally:
            path.unlink()

    def test_result_has_all_principles(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        path = _write_tmp("x = 1", suffix=".py")
        try:
            result = analyzer.analyze_file(path)
            principles = {s.principle for s in result.principle_scores}
            assert principles == {"SRP", "OCP", "LSP", "ISP", "DIP"}
        finally:
            path.unlink()

    def test_to_dict_format(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        code = """
class Big:
    pass
"""
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            d = result.to_dict()
            assert "file_path" in d
            assert "language" in d
            assert "overall_score" in d
            assert "violations" in d
            assert "principle_scores" in d
            assert "violation_count" in d
        finally:
            path.unlink()

    def test_nonexistent_file_returns_100(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.overall_score == 100.0

    def test_violation_has_suggestion(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        code = """
class Handler:
    def process(self, obj):
        if isinstance(obj, str):
            return obj.upper()
"""
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            for v in result.violations:
                assert len(v.suggestion) > 0
        finally:
            path.unlink()

    def test_multiple_violations_stack(self, analyzer: SOLIDPrinciplesAnalyzer) -> None:
        methods = "\n".join(f"    def method_{i}(self): pass" for i in range(12))
        code = f"""
class GodClass:
{methods}
    def check_type(self, obj):
        if isinstance(obj, str):
            return obj
"""
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            principles = {v.principle for v in result.violations}
            assert "SRP" in principles
            assert "OCP" in principles
            assert result.overall_score < 100.0
        finally:
            path.unlink()
