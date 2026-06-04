"""Tests for the canonical test-file detection util (utils.test_detection)."""

from __future__ import annotations

from tree_sitter_analyzer.utils.test_detection import (
    is_test_file,
    query_wants_tests,
    rank_tier,
)


def test_is_test_file_detects_cross_language_conventions() -> None:
    # Go / Python / Rust / C++ / Ruby suffixes
    assert is_test_file("response_writer_test.go")
    assert is_test_file("pkg/router_test.go")
    assert is_test_file("thing_test.py")
    assert is_test_file("test_thing.py")
    assert is_test_file("mod_test.rs")
    assert is_test_file("widget_test.cc")
    assert is_test_file("model_spec.rb")
    # JS / TS
    assert is_test_file("src/app/foo.test.tsx")
    assert is_test_file("foo.spec.ts")
    assert is_test_file("comp.test.jsx")
    # Directory conventions
    assert is_test_file("tests/test_thing.py")
    assert is_test_file("src/test/java/FooTest.java")
    assert is_test_file("__tests__/comp.jsx")
    assert is_test_file("project/testdata/sample.go")
    assert is_test_file("pkg/fixtures/data.go")
    # Repo-root fixture/test trees (prefix, no leading slash) — Codex P2 #294.
    assert is_test_file("fixtures/data.go")
    assert is_test_file("testdata/sample.go")
    assert is_test_file("spec/thing_spec.rb")


def test_is_test_file_no_false_positives() -> None:
    assert not is_test_file("response_writer.go")
    assert not is_test_file("src/TestRunner.java")  # production class
    assert not is_test_file("latest.java")  # 'test' substring trap
    assert not is_test_file("contest.py")
    assert not is_test_file("greatest_hits.rb")
    assert not is_test_file("")
    assert not is_test_file(None)


def test_query_wants_tests() -> None:
    assert query_wants_tests("response writer tests")
    assert query_wants_tests("how is routing tested")
    assert query_wants_tests("the spec for the parser")
    assert query_wants_tests("router benchmark")
    assert query_wants_tests("fixtures for the model")
    assert not query_wants_tests("how does route matching work")
    assert not query_wants_tests("latest contest results")
    assert not query_wants_tests("")


def test_rank_tier_behaviour() -> None:
    # Non-test → 0, test → 1.
    assert rank_tier("router.go") == 0
    assert rank_tier("router_test.go") == 1
    # wants_tests forces tier 0 so tests are not demoted.
    assert rank_tier("router_test.go", wants_tests=True) == 0
    assert rank_tier("router.go", wants_tests=True) == 0
