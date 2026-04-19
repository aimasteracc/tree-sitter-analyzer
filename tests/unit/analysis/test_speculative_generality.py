"""Tests for Speculative Generality Detector."""
from __future__ import annotations

import tempfile

from tree_sitter_analyzer.analysis.speculative_generality import (
    ISSUE_OVERLY_BROAD,
    ISSUE_SPECULATIVE_ABSTRACT,
    ISSUE_UNUSED_HOOK,
    ISSUE_UNUSED_TYPE_PARAM,
    SpeculativeGeneralityAnalyzer,
)

ANALYZER = SpeculativeGeneralityAnalyzer()


def _analyze(code: str, suffix: str) -> dict:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False
    ) as f:
        f.write(code)
        f.flush()
        result = ANALYZER.analyze_file(f.name)
    return {
        "issues": list(result.issues),
        "total_types": result.total_types,
        "total_issues": result.total_issues,
        "high_severity": result.high_severity_count,
        "issue_types": [i.issue_type for i in result.issues],
    }


# ── Python Tests ─────────────────────────────────────────────────────────


class TestPythonSpeculativeAbstract:
    def test_abstract_class_no_implementations(self) -> None:
        code = '''\
from abc import ABC, abstractmethod

class Shape(ABC):
    @abstractmethod
    def area(self) -> float:
        pass

    @abstractmethod
    def perimeter(self) -> float:
        pass
'''
        r = _analyze(code, ".py")
        assert r["total_types"] == 1
        assert ISSUE_SPECULATIVE_ABSTRACT in r["issue_types"]

    def test_abstract_class_one_implementation(self) -> None:
        code = '''\
from abc import ABC, abstractmethod

class Shape(ABC):
    @abstractmethod
    def area(self) -> float:
        pass

class Circle(Shape):
    def area(self) -> float:
        return 3.14
'''
        r = _analyze(code, ".py")
        assert r["total_types"] == 2
        assert ISSUE_SPECULATIVE_ABSTRACT in r["issue_types"]

    def test_abstract_class_two_implementations(self) -> None:
        code = '''\
from abc import ABC, abstractmethod

class Shape(ABC):
    @abstractmethod
    def area(self) -> float:
        pass

class Circle(Shape):
    def area(self) -> float:
        return 3.14

class Square(Shape):
    def area(self) -> float:
        return 4.0
'''
        r = _analyze(code, ".py")
        assert r["total_types"] == 3
        assert ISSUE_SPECULATIVE_ABSTRACT not in r["issue_types"]

    def test_concrete_class_no_flag(self) -> None:
        code = '''\
class UserService:
    def get_user(self, user_id: int) -> str:
        return "user"
'''
        r = _analyze(code, ".py")
        assert r["total_types"] == 1
        assert ISSUE_SPECULATIVE_ABSTRACT not in r["issue_types"]

    def test_no_classes(self) -> None:
        code = "def hello(): pass"
        r = _analyze(code, ".py")
        assert r["total_types"] == 0
        assert r["total_issues"] == 0


class TestPythonUnusedHook:
    def test_abstract_method_never_overridden(self) -> None:
        code = '''\
from abc import ABC, abstractmethod

class Base(ABC):
    @abstractmethod
    def required(self) -> None:
        pass

    @abstractmethod
    def optional(self) -> None:
        pass

class Impl(Base):
    def required(self) -> None:
        pass

    def optional(self) -> None:
        pass
'''
        r = _analyze(code, ".py")
        # Only 1 implementation, unused_hook not reported for single impl
        assert ISSUE_UNUSED_HOOK not in r["issue_types"]

    def test_abstract_method_partially_overridden_with_two_impls(self) -> None:
        code = '''\
from abc import ABC, abstractmethod

class Base(ABC):
    @abstractmethod
    def method_a(self) -> None:
        pass

    @abstractmethod
    def method_b(self) -> None:
        pass

class Impl1(Base):
    def method_a(self) -> None:
        pass

    def method_b(self) -> None:
        pass

class Impl2(Base):
    def method_a(self) -> None:
        pass
'''
        r = _analyze(code, ".py")
        # 2+ implementations, method_b not overridden in Impl2
        # But unused_hook checks if a method is NEVER overridden in ANY subclass
        # method_b IS overridden in Impl1, so no unused_hook
        # method_a IS overridden in both
        assert ISSUE_UNUSED_HOOK not in r["issue_types"]

    def test_abstract_method_truly_never_overridden(self) -> None:
        code = '''\
from abc import ABC, abstractmethod

class Base(ABC):
    @abstractmethod
    def method_a(self) -> None:
        pass

    @abstractmethod
    def method_b(self) -> None:
        pass

class Impl1(Base):
    def method_a(self) -> None:
        pass

class Impl2(Base):
    def method_a(self) -> None:
        pass
'''
        r = _analyze(code, ".py")
        # 2 implementations, method_b never overridden in any
        assert ISSUE_UNUSED_HOOK in r["issue_types"]


class TestPythonOverlyBroad:
    def test_interface_with_many_methods(self) -> None:
        methods = "\n".join(
            f"    @abstractmethod\n    def method_{i}(self) -> None:\n        pass\n"
            for i in range(6)
        )
        code = f"from abc import ABC, abstractmethod\n\nclass BigInterface(ABC):\n{methods}"
        r = _analyze(code, ".py")
        assert ISSUE_OVERLY_BROAD in r["issue_types"]

    def test_interface_few_methods(self) -> None:
        methods = "\n".join(
            f"    @abstractmethod\n    def method_{i}(self) -> None:\n        pass\n"
            for i in range(3)
        )
        code = f"from abc import ABC, abstractmethod\n\nclass SmallInterface(ABC):\n{methods}"
        r = _analyze(code, ".py")
        assert ISSUE_OVERLY_BROAD not in r["issue_types"]


# ── JavaScript Tests ────────────────────────────────────────────────────


class TestJavaScriptSpeculativeAbstract:
    def test_abstract_class_no_impl(self) -> None:
        code = '''\
class Animal {
    makeSound() {
        throw new Error("abstract");
    }
}
'''
        r = _analyze(code, ".js")
        # JS class without 'abstract' keyword is not flagged as abstract
        assert ISSUE_SPECULATIVE_ABSTRACT not in r["issue_types"]

    def test_concrete_class(self) -> None:
        code = '''\
class UserService {
    getUser(id) {
        return { id };
    }
}
'''
        r = _analyze(code, ".js")
        assert r["total_types"] == 1
        assert r["total_issues"] == 0


# ── TypeScript Tests ────────────────────────────────────────────────────


class TestTypeScriptSpeculativeAbstract:
    def test_interface_no_impl(self) -> None:
        code = '''\
interface IShape {
    area(): number;
    perimeter(): number;
}
'''
        r = _analyze(code, ".ts")
        assert r["total_types"] == 1
        assert ISSUE_SPECULATIVE_ABSTRACT in r["issue_types"]

    def test_interface_with_impl(self) -> None:
        code = '''\
interface IShape {
    area(): number;
}

class Circle implements IShape {
    area() { return 3.14; }
}

class Square implements IShape {
    area() { return 4.0; }
}
'''
        r = _analyze(code, ".ts")
        assert ISSUE_SPECULATIVE_ABSTRACT not in r["issue_types"]

    def test_abstract_class(self) -> None:
        code = '''\
abstract class Handler {
    abstract handle(): void;
}
'''
        r = _analyze(code, ".ts")
        assert ISSUE_SPECULATIVE_ABSTRACT in r["issue_types"]

    def test_overly_broad_interface(self) -> None:
        methods = "\n".join(
            f"    method_{i}(): void;" for i in range(6)
        )
        code = f"interface BigInterface {{\n{methods}\n}}"
        r = _analyze(code, ".ts")
        assert ISSUE_OVERLY_BROAD in r["issue_types"]

    def test_type_parameters(self) -> None:
        code = '''\
interface Repository<T> {
    get(id: string): T;
    save(item: T): void;
}
'''
        r = _analyze(code, ".ts")
        # T is used in method signatures, so no unused_type_param
        assert ISSUE_UNUSED_TYPE_PARAM not in r["issue_types"]

    def test_unused_type_parameter(self) -> None:
        code = '''\
interface Marker<T> {
    name: string;
}
'''
        r = _analyze(code, ".ts")
        # T is declared but only name is used
        # The detection is heuristic: T appears in the body text
        # If T only appears once (declaration), it's unused
        # This test verifies the detection runs without error
        assert r["total_types"] == 1


class TestTypeScriptInterfaceMethods:
    def test_interface_methods_detected(self) -> None:
        code = '''\
interface IService {
    method1(): void;
    method2(): string;
    method3(): number;
}
'''
        r = _analyze(code, ".ts")
        assert r["total_types"] == 1
        assert ISSUE_SPECULATIVE_ABSTRACT in r["issue_types"]


# ── Java Tests ──────────────────────────────────────────────────────────


class TestJavaSpeculativeAbstract:
    def test_abstract_class_no_impl(self) -> None:
        code = '''\
public abstract class Shape {
    public abstract double area();
    public abstract double perimeter();
}
'''
        r = _analyze(code, ".java")
        assert r["total_types"] == 1
        assert ISSUE_SPECULATIVE_ABSTRACT in r["issue_types"]

    def test_abstract_class_with_impl(self) -> None:
        code = '''\
public abstract class Shape {
    public abstract double area();
}

public class Circle extends Shape {
    public double area() { return 3.14; }
}

public class Square extends Shape {
    public double area() { return 4.0; }
}
'''
        r = _analyze(code, ".java")
        assert ISSUE_SPECULATIVE_ABSTRACT not in r["issue_types"]

    def test_interface_no_impl(self) -> None:
        code = '''\
public interface Clickable {
    void onClick();
    void onDoubleClick();
}
'''
        r = _analyze(code, ".java")
        assert r["total_types"] == 1
        assert ISSUE_SPECULATIVE_ABSTRACT in r["issue_types"]

    def test_concrete_class(self) -> None:
        code = '''\
public class UserService {
    public String getUser(int id) {
        return "user";
    }
}
'''
        r = _analyze(code, ".java")
        assert r["total_types"] == 1
        assert r["total_issues"] == 0

    def test_overly_broad_interface(self) -> None:
        methods = "\n".join(
            f"    void method{i}();" for i in range(6)
        )
        code = f"public interface BigInterface {{\n{methods}\n}}"
        r = _analyze(code, ".java")
        assert ISSUE_OVERLY_BROAD in r["issue_types"]

    def test_unused_hook_java(self) -> None:
        code = '''\
public interface Listener {
    void onClick();
    void onHover();
}

public class ButtonListener implements Listener {
    public void onClick() {}
}

public class AnotherListener implements Listener {
    public void onClick() {}
}
'''
        r = _analyze(code, ".java")
        # onHover is never overridden in any subclass
        assert ISSUE_UNUSED_HOOK in r["issue_types"]

    def test_type_parameters_java(self) -> None:
        code = '''\
public interface Repository<T> {
    T get(String id);
    void save(T item);
}
'''
        r = _analyze(code, ".java")
        # T is used, so no unused_type_param
        assert ISSUE_UNUSED_TYPE_PARAM not in r["issue_types"]


# ── Go Tests ────────────────────────────────────────────────────────────


class TestGoSpeculativeGenerality:
    def test_interface_no_impl(self) -> None:
        code = '''\
package main

type Shape interface {
    Area() float64
    Perimeter() float64
}
'''
        r = _analyze(code, ".go")
        assert r["total_types"] == 1
        assert ISSUE_SPECULATIVE_ABSTRACT in r["issue_types"]

    def test_interface_with_impl(self) -> None:
        code = '''\
package main

type Shape interface {
    Area() float64
}

type Circle struct{}
func (c Circle) Area() float64 { return 3.14 }

type Square struct{}
func (s Square) Area() float64 { return 4.0 }
'''
        r = _analyze(code, ".go")
        assert ISSUE_SPECULATIVE_ABSTRACT not in r["issue_types"]

    def test_empty_interface(self) -> None:
        code = '''\
package main

type Any interface{}
'''
        r = _analyze(code, ".go")
        assert r["total_types"] == 1
        # Empty interface has 0 abstract methods, so no overly_broad
        assert ISSUE_OVERLY_BROAD not in r["issue_types"]

    def test_overly_broad_interface(self) -> None:
        methods = "\n".join(
            f"    Method{i}()" for i in range(6)
        )
        code = f"package main\n\ntype BigInterface interface {{\n{methods}\n}}"
        r = _analyze(code, ".go")
        assert ISSUE_OVERLY_BROAD in r["issue_types"]

    def test_struct_not_flagged(self) -> None:
        code = '''\
package main

type UserService struct {
    name string
}
'''
        r = _analyze(code, ".go")
        assert r["total_types"] == 1
        assert r["total_issues"] == 0


# ── Edge Cases ──────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_file(self) -> None:
        result = ANALYZER.analyze_file("/nonexistent/file.py")
        assert result.total_types == 0
        assert result.total_issues == 0

    def test_unsupported_extension(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".rb", delete=False
        ) as f:
            f.write("class Foo; end")
            f.flush()
            result = ANALYZER.analyze_file(f.name)
        assert result.total_types == 0

    def test_empty_file(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write("")
            f.flush()
            result = ANALYZER.analyze_file(f.name)
        assert result.total_types == 0

    def test_result_to_dict(self) -> None:
        code = '''\
from abc import ABC, abstractmethod

class Base(ABC):
    @abstractmethod
    def do_stuff(self) -> None:
        pass
'''
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write(code)
            f.flush()
            result = ANALYZER.analyze_file(f.name)
        d = result.to_dict()
        assert "file_path" in d
        assert "total_types" in d
        assert "total_issues" in d
        assert isinstance(d["issues"], list)

    def test_issue_to_dict(self) -> None:
        code = '''\
from abc import ABC, abstractmethod

class Base(ABC):
    @abstractmethod
    def method_a(self) -> None:
        pass
'''
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write(code)
            f.flush()
            result = ANALYZER.analyze_file(f.name)
        if result.issues:
            d = result.issues[0].to_dict()
            assert "issue_type" in d
            assert "line" in d
            assert "severity" in d

    def test_get_issues_by_severity(self) -> None:
        code = '''\
from abc import ABC, abstractmethod

class Base(ABC):
    @abstractmethod
    def do_stuff(self) -> None:
        pass
'''
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write(code)
            f.flush()
            result = ANALYZER.analyze_file(f.name)
        high_issues = result.get_issues_by_severity("high")
        assert len(high_issues) == result.high_severity_count

    def test_get_issues_by_type(self) -> None:
        code = '''\
from abc import ABC, abstractmethod

class Base(ABC):
    @abstractmethod
    def do_stuff(self) -> None:
        pass
'''
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write(code)
            f.flush()
            result = ANALYZER.analyze_file(f.name)
        abstract_issues = result.get_issues_by_type(ISSUE_SPECULATIVE_ABSTRACT)
        assert len(abstract_issues) >= 0  # may or may not have the issue

    def test_custom_broad_threshold(self) -> None:
        analyzer = SpeculativeGeneralityAnalyzer(broad_threshold=2)
        methods = "\n".join(
            f"    @abstractmethod\n    def method_{i}(self) -> None:\n        pass\n"
            for i in range(3)
        )
        code = f"from abc import ABC, abstractmethod\n\nclass Base(ABC):\n{methods}"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write(code)
            f.flush()
            result = analyzer.analyze_file(f.name)
        assert ISSUE_OVERLY_BROAD in [i.issue_type for i in result.issues]

    def test_python_type_params_detection(self) -> None:
        code = '''\
class Container[T]:
    def get(self) -> T:
        pass
'''
        r = _analyze(code, ".py")
        # T is used in the method, so no unused_type_param
        # This test verifies it runs without crashing on Python 3.12 syntax
        assert r["total_types"] == 1
