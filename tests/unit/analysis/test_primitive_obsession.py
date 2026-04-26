"""Tests for Primitive Obsession Detector."""
from __future__ import annotations

import os
import tempfile

from tree_sitter_analyzer.analysis.primitive_obsession import (
    ISSUE_ANEMIC_VALUE_OBJECT,
    ISSUE_PRIMITIVE_HEAVY_PARAMS,
    ISSUE_PRIMITIVE_SOUP,
    ISSUE_TYPE_HINT_CODE_SMELL,
    PrimitiveObsessionAnalyzer,
    PrimitiveObsessionResult,
)


def _write_tmp(content: str, suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


# ── Python Tests ──


class TestPythonPrimitiveHeavyParams:
    def test_detects_all_primitive_params(self) -> None:
        code = """\
def process_user(name: str, email: str, age: int, role: str):
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_primitive_params=4)
            result = analyzer.analyze_file(path)
            assert isinstance(result, PrimitiveObsessionResult)
            assert result.functions_analyzed == 1
            assert result.total_issues >= 1
            issue = result.issues[0]
            assert issue.issue_type == ISSUE_PRIMITIVE_HEAVY_PARAMS
            assert "process_user" in issue.message
            assert "4" in issue.message
        finally:
            os.unlink(path)

    def test_no_issue_few_params(self) -> None:
        code = """\
def greet(name: str, greeting: str):
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_primitive_params=4)
            result = analyzer.analyze_file(path)
            param_issues = [
                i for i in result.issues
                if i.issue_type == ISSUE_PRIMITIVE_HEAVY_PARAMS
            ]
            assert len(param_issues) == 0
        finally:
            os.unlink(path)

    def test_no_issue_mixed_types(self) -> None:
        code = """\
def process(name: str, email: str, user: User, db: Database):
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_primitive_params=4)
            result = analyzer.analyze_file(path)
            param_issues = [
                i for i in result.issues
                if i.issue_type == ISSUE_PRIMITIVE_HEAVY_PARAMS
            ]
            assert len(param_issues) == 0
        finally:
            os.unlink(path)

    def test_detects_untyped_params_by_name(self) -> None:
        code = """\
def create(name, email, age, role):
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_primitive_params=4)
            result = analyzer.analyze_file(path)
            assert result.total_issues >= 1
        finally:
            os.unlink(path)

    def test_self_param_excluded(self) -> None:
        code = """\
class User:
    def update(self, name: str, email: str, age: int, role: str):
        pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_primitive_params=4)
            result = analyzer.analyze_file(path)
            param_issues = [
                i for i in result.issues
                if i.issue_type == ISSUE_PRIMITIVE_HEAVY_PARAMS
            ]
            assert len(param_issues) == 1
        finally:
            os.unlink(path)


class TestPythonPrimitiveSoup:
    def test_detects_many_primitive_locals(self) -> None:
        code = """\
def process_order():
    name = "Alice"
    email = "alice@example.com"
    phone = "555-1234"
    address = "123 Main St"
    city = "Springfield"
    state = "IL"
    zip_code = "62704"
    country = "US"
    total = 100.0
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_primitive_locals=8)
            result = analyzer.analyze_file(path)
            soup_issues = [
                i for i in result.issues
                if i.issue_type == ISSUE_PRIMITIVE_SOUP
            ]
            assert len(soup_issues) >= 1
            assert "process_order" in soup_issues[0].message
        finally:
            os.unlink(path)

    def test_no_issue_few_locals(self) -> None:
        code = """\
def simple():
    name = "Alice"
    age = 30
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_primitive_locals=8)
            result = analyzer.analyze_file(path)
            soup_issues = [
                i for i in result.issues
                if i.issue_type == ISSUE_PRIMITIVE_SOUP
            ]
            assert len(soup_issues) == 0
        finally:
            os.unlink(path)


class TestPythonAnemicValueObject:
    def test_detects_anemic_class(self) -> None:
        code = """\
class Address:
    street = ""
    city = ""
    state = ""
    zip_code = ""
    country = ""
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_anemic_fields=3)
            result = analyzer.analyze_file(path)
            anemic_issues = [
                i for i in result.issues
                if i.issue_type == ISSUE_ANEMIC_VALUE_OBJECT
            ]
            assert len(anemic_issues) >= 1
            assert "Address" in anemic_issues[0].message
        finally:
            os.unlink(path)

    def test_no_issue_class_with_methods(self) -> None:
        code = """\
class User:
    name = ""
    email = ""
    age = 0

    def validate(self):
        return len(self.name) > 0

    def to_dict(self):
        return {"name": self.name}
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_anemic_fields=3)
            result = analyzer.analyze_file(path)
            anemic_issues = [
                i for i in result.issues
                if i.issue_type == ISSUE_ANEMIC_VALUE_OBJECT
            ]
            assert len(anemic_issues) == 0
        finally:
            os.unlink(path)

    def test_no_issue_few_fields(self) -> None:
        code = """\
class Point:
    x = 0
    y = 0
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_anemic_fields=3)
            result = analyzer.analyze_file(path)
            anemic_issues = [
                i for i in result.issues
                if i.issue_type == ISSUE_ANEMIC_VALUE_OBJECT
            ]
            assert len(anemic_issues) == 0
        finally:
            os.unlink(path)


class TestPythonTypeHintCodeSmell:
    def test_detects_string_type_comparison(self) -> None:
        code = """\
def handle(event):
    if event.type == "click":
        pass
    elif event.type == "keydown":
        pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = PrimitiveObsessionAnalyzer()
            result = analyzer.analyze_file(path)
            smell_issues = [
                i for i in result.issues
                if i.issue_type == ISSUE_TYPE_HINT_CODE_SMELL
            ]
            assert len(smell_issues) >= 1
        finally:
            os.unlink(path)

    def test_no_issue_non_type_comparison(self) -> None:
        code = """\
def check(user):
    if user.active == True:
        pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = PrimitiveObsessionAnalyzer()
            result = analyzer.analyze_file(path)
            smell_issues = [
                i for i in result.issues
                if i.issue_type == ISSUE_TYPE_HINT_CODE_SMELL
            ]
            assert len(smell_issues) == 0
        finally:
            os.unlink(path)


# ── JavaScript/TypeScript Tests ──


class TestJavaScriptPrimitiveHeavyParams:
    def test_detects_primitive_params_js(self) -> None:
        code = """\
function create(name, email, age, role) {
    return { name, email, age, role };
}
"""
        path = _write_tmp(code, ".js")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_primitive_params=4)
            result = analyzer.analyze_file(path)
            assert result.functions_analyzed == 1
            assert result.total_issues >= 1
        finally:
            os.unlink(path)

    def test_detects_arrow_function_js(self) -> None:
        code = """\
const process = (name, email, age, role) => {
    return { name, email, age, role };
};
"""
        path = _write_tmp(code, ".js")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_primitive_params=4)
            result = analyzer.analyze_file(path)
            assert result.total_issues >= 1
        finally:
            os.unlink(path)


class TestTypeScriptPrimitiveHeavyParams:
    def test_detects_typed_params(self) -> None:
        code = """\
function create(name: string, email: string, age: number, role: string): void {
    console.log(name, email, age, role);
}
"""
        path = _write_tmp(code, ".ts")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_primitive_params=4)
            result = analyzer.analyze_file(path)
            assert result.total_issues >= 1
        finally:
            os.unlink(path)


class TestJSTypeHintCodeSmell:
    def test_detects_dot_type_comparison(self) -> None:
        code = """\
function handle(event) {
    if (event.type === "click") {
        console.log("clicked");
    }
}
"""
        path = _write_tmp(code, ".js")
        try:
            analyzer = PrimitiveObsessionAnalyzer()
            result = analyzer.analyze_file(path)
            smell_issues = [
                i for i in result.issues
                if i.issue_type == ISSUE_TYPE_HINT_CODE_SMELL
            ]
            assert len(smell_issues) >= 1
        finally:
            os.unlink(path)


# ── Java Tests ──


class TestJavaPrimitiveHeavyParams:
    def test_detects_primitive_params_java(self) -> None:
        code = """\
public class UserService {
    public void createUser(String name, String email, int age, String role) {
        System.out.println(name);
    }
}
"""
        path = _write_tmp(code, ".java")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_primitive_params=4)
            result = analyzer.analyze_file(path)
            assert result.functions_analyzed >= 1
            assert result.total_issues >= 1
        finally:
            os.unlink(path)

    def test_no_issue_mixed_types_java(self) -> None:
        code = """\
public class Service {
    public void process(String name, int age, User user, Database db) {
        return;
    }
}
"""
        path = _write_tmp(code, ".java")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_primitive_params=4)
            result = analyzer.analyze_file(path)
            param_issues = [
                i for i in result.issues
                if i.issue_type == ISSUE_PRIMITIVE_HEAVY_PARAMS
            ]
            assert len(param_issues) == 0
        finally:
            os.unlink(path)


class TestJavaAnemicValueObject:
    def test_detects_anemic_java_class(self) -> None:
        code = """\
public class Address {
    String street;
    String city;
    String state;
    String zipCode;
    String country;
}
"""
        path = _write_tmp(code, ".java")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_anemic_fields=3)
            result = analyzer.analyze_file(path)
            anemic_issues = [
                i for i in result.issues
                if i.issue_type == ISSUE_ANEMIC_VALUE_OBJECT
            ]
            assert len(anemic_issues) >= 1
        finally:
            os.unlink(path)

    def test_no_issue_java_class_with_methods(self) -> None:
        code = """\
public class User {
    String name;
    String email;

    public boolean validate() {
        return name != null && !name.isEmpty();
    }
}
"""
        path = _write_tmp(code, ".java")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_anemic_fields=3)
            result = analyzer.analyze_file(path)
            anemic_issues = [
                i for i in result.issues
                if i.issue_type == ISSUE_ANEMIC_VALUE_OBJECT
            ]
            assert len(anemic_issues) == 0
        finally:
            os.unlink(path)


class TestJavaTypeHintCodeSmell:
    def test_detects_string_type_equals(self) -> None:
        code = """\
public class Handler {
    public void handle(Event event) {
        if (type.equals("click")) {
            System.out.println("clicked");
        }
    }
}
"""
        path = _write_tmp(code, ".java")
        try:
            analyzer = PrimitiveObsessionAnalyzer()
            result = analyzer.analyze_file(path)
            smell_issues = [
                i for i in result.issues
                if i.issue_type == ISSUE_TYPE_HINT_CODE_SMELL
            ]
            assert len(smell_issues) >= 1
        finally:
            os.unlink(path)


# ── Go Tests ──


class TestGoPrimitiveHeavyParams:
    def test_detects_primitive_params_go(self) -> None:
        code = """\
package main

func CreateUser(name string, email string, age int, role string) {
    println(name)
}
"""
        path = _write_tmp(code, ".go")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_primitive_params=4)
            result = analyzer.analyze_file(path)
            assert result.functions_analyzed >= 1
            assert result.total_issues >= 1
        finally:
            os.unlink(path)

    def test_no_issue_few_params_go(self) -> None:
        code = """\
package main

func greet(name string) {
    println(name)
}
"""
        path = _write_tmp(code, ".go")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_primitive_params=4)
            result = analyzer.analyze_file(path)
            param_issues = [
                i for i in result.issues
                if i.issue_type == ISSUE_PRIMITIVE_HEAVY_PARAMS
            ]
            assert len(param_issues) == 0
        finally:
            os.unlink(path)


class TestGoAnemicValueObject:
    def test_detects_anemic_go_struct(self) -> None:
        code = """\
package main

type Address struct {
    Street  string
    City    string
    State   string
    ZipCode string
    Country string
}
"""
        path = _write_tmp(code, ".go")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_anemic_fields=3)
            result = analyzer.analyze_file(path)
            anemic_issues = [
                i for i in result.issues
                if i.issue_type == ISSUE_ANEMIC_VALUE_OBJECT
            ]
            assert len(anemic_issues) >= 1
        finally:
            os.unlink(path)

    def test_no_issue_go_struct_with_methods(self) -> None:
        code = """\
package main

type User struct {
    Name  string
    Email string
}

func (u User) Validate() bool {
    return u.Name != ""
}
"""
        path = _write_tmp(code, ".go")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_anemic_fields=3)
            result = analyzer.analyze_file(path)
            anemic_issues = [
                i for i in result.issues
                if i.issue_type == ISSUE_ANEMIC_VALUE_OBJECT
            ]
            assert len(anemic_issues) == 0
        finally:
            os.unlink(path)


class TestGoTypeHintCodeSmell:
    def test_detects_field_type_comparison(self) -> None:
        code = """\
package main

func handle(e Event) {
    if e.Type == "click" {
        println("clicked")
    }
}
"""
        path = _write_tmp(code, ".go")
        try:
            analyzer = PrimitiveObsessionAnalyzer()
            result = analyzer.analyze_file(path)
            smell_issues = [
                i for i in result.issues
                if i.issue_type == ISSUE_TYPE_HINT_CODE_SMELL
            ]
            assert len(smell_issues) >= 1
        finally:
            os.unlink(path)


# ── General Tests ──


class TestGeneral:
    def test_result_to_dict(self) -> None:
        code = """\
def process(name: str, email: str, age: int, role: str):
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_primitive_params=4)
            result = analyzer.analyze_file(path)
            d = result.to_dict()
            assert "file_path" in d
            assert "issues" in d
            assert "total_issues" in d
            assert "functions_analyzed" in d
            assert isinstance(d["issues"], list)
        finally:
            os.unlink(path)

    def test_issue_to_dict(self) -> None:
        code = """\
def process(name: str, email: str, age: int, role: str):
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_primitive_params=4)
            result = analyzer.analyze_file(path)
            assert result.total_issues >= 1
            d = result.issues[0].to_dict()
            assert "issue_type" in d
            assert "line" in d
            assert "severity" in d
            assert "suggestion" in d
        finally:
            os.unlink(path)

    def test_get_issues_by_severity(self) -> None:
        code = """\
def process(name: str, email: str, age: int, role: str):
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_primitive_params=4)
            result = analyzer.analyze_file(path)
            medium = result.get_issues_by_severity("medium")
            assert len(medium) >= 1
            high = result.get_issues_by_severity("high")
            assert isinstance(high, list)
        finally:
            os.unlink(path)

    def test_custom_thresholds(self) -> None:
        code = """\
def create(name: str, email: str):
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = PrimitiveObsessionAnalyzer(min_primitive_params=2)
            result = analyzer.analyze_file(path)
            param_issues = [
                i for i in result.issues
                if i.issue_type == ISSUE_PRIMITIVE_HEAVY_PARAMS
            ]
            assert len(param_issues) >= 1
        finally:
            os.unlink(path)
