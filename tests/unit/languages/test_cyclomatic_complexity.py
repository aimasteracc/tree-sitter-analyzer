"""Tests for cyclomatic complexity in Ruby, Kotlin, and PHP plugins.

RED-first: these tests are written before the fix.
Each fixture has an exactly-known decision-point count.
Per CLAUDE.md locked rule: assertions MUST pin the EXACT expected integer,
never a loose bound (>= N, > 0, etc.).
"""

import tree_sitter

# ---------------------------------------------------------------------------
# Ruby
# ---------------------------------------------------------------------------

RUBY_BRANCHY = """\
def binary_search(arr, target)
  low = 0
  high = arr.length - 1
  while low <= high
    mid = (low + high) / 2
    if arr[mid] == target
      return mid
    elsif arr[mid] < target
      low = mid + 1
    else
      high = mid - 1
    end
  end
  -1
end
"""
# Decisions: while(1) + if(1) + elsif(1) = 3 → complexity = 1 + 3 = 4

RUBY_SIMPLE = """\
def greet(name)
  "Hello, #{name}!"
end
"""
# No branches → complexity = 1

RUBY_RICH = """\
def process(x, arr)
  result = x > 0 ? 1 : -1
  unless x.nil?
    puts x
  end
  until x >= 10
    x += 1
  end
  for i in arr
    puts i
  end
  begin
    result2 = 1/1
  rescue ZeroDivisionError
    puts 'err'
  end
  ok = x > 0 && x < 100
  ok2 = x < 0 || x > 200
  result
end
"""
# Decisions:
#   conditional (ternary)  : 1
#   unless                 : 1
#   until                  : 1
#   for                    : 1
#   rescue                 : 1
#   &&  (operator child)   : 1
#   ||  (operator child)   : 1
# Total decisions = 7 → complexity = 1 + 7 = 8


def _ruby_lang():
    import tree_sitter_ruby

    return tree_sitter.Language(tree_sitter_ruby.language())


def _ruby_functions(source: str):
    lang = _ruby_lang()
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(source.encode())
    from tree_sitter_analyzer.languages.ruby_plugin import RubyElementExtractor

    extractor = RubyElementExtractor()
    return extractor.extract_functions(tree, source)


class TestRubyCyclomaticComplexity:
    def test_simple_no_branches(self):
        funcs = _ruby_functions(RUBY_SIMPLE)
        assert len(funcs) == 1
        assert funcs[0].name == "greet"
        assert funcs[0].complexity_score == 1

    def test_binary_search(self):
        """while + if + elsif = 3 decisions → complexity 4."""
        funcs = _ruby_functions(RUBY_BRANCHY)
        assert len(funcs) == 1
        assert funcs[0].name == "binary_search"
        assert funcs[0].complexity_score == 4

    def test_rich_branching(self):
        """ternary+unless+until+for+rescue+&&+|| = 7 decisions → complexity 8."""
        funcs = _ruby_functions(RUBY_RICH)
        assert len(funcs) == 1
        assert funcs[0].name == "process"
        assert funcs[0].complexity_score == 8


# ---------------------------------------------------------------------------
# Kotlin
# ---------------------------------------------------------------------------

KOTLIN_SIMPLE = """\
fun greet(name: String): String {
    return "Hello, $name!"
}
"""
# No branches → complexity = 1

KOTLIN_BRANCHY = """\
fun binarySearch(arr: List<Int>, target: Int): Int {
    var low = 0
    var high = arr.size - 1
    while (low <= high) {
        val mid = (low + high) / 2
        if (arr[mid] == target) {
            return mid
        } else if (arr[mid] < target) {
            low = mid + 1
        } else {
            high = mid - 1
        }
    }
    return -1
}
"""
# Decisions: while_statement(1) + if_expression(1) + else-if=another if_expression(1) = 3
# → complexity = 1 + 3 = 4

KOTLIN_RICH = """\
fun process(x: Int): String {
    val r = if (x > 0) "pos" else "neg"
    val s = when (x) {
        1 -> "one"
        2 -> "two"
        else -> "other"
    }
    for (i in 1..10) {
        println(i)
    }
    var y = x
    while (y > 0) { println(y) }
    do { println(y) } while (y < 10)
    try {
        val d = 1 / x
    } catch (e: Exception) {
        println(e)
    }
    val t = x > 0 && x < 10
    val u = x < 0 || x > 100
    return r
}
"""
# Decisions:
#   if_expression (inline if)  : 1
#   when_expression            : 1
#   for_statement              : 1
#   while_statement            : 1
#   do_while_statement         : 1
#   catch_block                : 1
#   &&  (operator)             : 1
#   ||  (operator)             : 1
# Total = 8 → complexity = 1 + 8 = 9


def _kotlin_lang():
    import tree_sitter_kotlin

    return tree_sitter.Language(tree_sitter_kotlin.language())


def _kotlin_functions(source: str):
    lang = _kotlin_lang()
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(source.encode())
    from tree_sitter_analyzer.languages.kotlin_plugin import KotlinElementExtractor

    extractor = KotlinElementExtractor()
    return extractor.extract_functions(tree, source)


class TestKotlinCyclomaticComplexity:
    def test_simple_no_branches(self):
        funcs = _kotlin_functions(KOTLIN_SIMPLE)
        assert len(funcs) == 1
        assert funcs[0].name == "greet"
        assert funcs[0].complexity_score == 1

    def test_binary_search(self):
        """while + if + else-if (as if_expression) = 3 decisions → complexity 4."""
        funcs = _kotlin_functions(KOTLIN_BRANCHY)
        assert len(funcs) == 1
        assert funcs[0].name == "binarySearch"
        assert funcs[0].complexity_score == 4

    def test_rich_branching(self):
        """8 decision points → complexity 9."""
        funcs = _kotlin_functions(KOTLIN_RICH)
        assert len(funcs) == 1
        assert funcs[0].name == "process"
        assert funcs[0].complexity_score == 9


# ---------------------------------------------------------------------------
# PHP
# ---------------------------------------------------------------------------

PHP_SIMPLE = """\
<?php
function greet(string $name): string {
    return "Hello, $name!";
}
?>
"""
# No branches → complexity = 1

PHP_BRANCHY = """\
<?php
function binarySearch(array $arr, int $target): int {
    $low = 0;
    $high = count($arr) - 1;
    while ($low <= $high) {
        $mid = intdiv($low + $high, 2);
        if ($arr[$mid] == $target) {
            return $mid;
        } elseif ($arr[$mid] < $target) {
            $low = $mid + 1;
        } else {
            $high = $mid - 1;
        }
    }
    return -1;
}
?>
"""
# Decisions: while_statement(1) + if_statement(1) + else_if_clause(1) = 3 → complexity 4

PHP_RICH = """\
<?php
function process($x) {
    if ($x > 0) {
        echo 'pos';
    } elseif ($x == 0) {
        echo 'zero';
    } else {
        echo 'neg';
    }
    switch ($x) {
        case 1: echo 'one'; break;
        case 2: echo 'two'; break;
    }
    for ($i = 0; $i < 10; $i++) { echo $i; }
    foreach ([1,2,3] as $v) { echo $v; }
    while ($x > 0) { $x--; }
    do { $x++; } while ($x < 10);
    try {
        $d = 1;
    } catch (Exception $e) {
        echo $e;
    }
    $r = $x > 0 ? 1 : -1;
    $t = $x > 0 && $x < 10;
    $u = $x < 0 || $x > 100;
    $m = $x ?? 0;
}
?>
"""
# Decisions:
#   if_statement          : 1
#   else_if_clause        : 1
#   switch_statement      : 1
#   for_statement         : 1
#   foreach_statement     : 1
#   while_statement       : 1
#   do_statement          : 1
#   catch_clause          : 1
#   conditional_expression: 1
#   &&                    : 1
#   ||                    : 1
#   ??  (null-coalesce)   : 1
# Total = 12 → complexity = 1 + 12 = 13


def _php_lang():
    import tree_sitter_php

    return tree_sitter.Language(tree_sitter_php.language_php())


def _php_functions(source: str):
    lang = _php_lang()
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(source.encode())
    from tree_sitter_analyzer.languages.php_plugin import PHPElementExtractor

    extractor = PHPElementExtractor()
    return extractor.extract_functions(tree, source)


class TestPHPCyclomaticComplexity:
    def test_simple_no_branches(self):
        funcs = _php_functions(PHP_SIMPLE)
        assert len(funcs) == 1
        assert funcs[0].name == "greet"
        assert funcs[0].complexity_score == 1

    def test_binary_search(self):
        """while + if + elseif = 3 decisions → complexity 4."""
        funcs = _php_functions(PHP_BRANCHY)
        assert len(funcs) == 1
        assert funcs[0].name == "binarySearch"
        assert funcs[0].complexity_score == 4

    def test_rich_branching(self):
        """12 decision points → complexity 13."""
        funcs = _php_functions(PHP_RICH)
        assert len(funcs) == 1
        assert funcs[0].name == "process"
        assert funcs[0].complexity_score == 13
