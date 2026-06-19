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


# ---------------------------------------------------------------------------
# Swift
# ---------------------------------------------------------------------------

SWIFT_SIMPLE = """\
func greet(name: String) -> String {
    return name
}
"""
# No branches → complexity = 1

SWIFT_BRANCHY = """\
func binarySearch(_ arr: [Int], _ target: Int) -> Int {
    var low = 0
    var high = arr.count - 1
    while low <= high {
        let mid = (low + high) / 2
        if arr[mid] == target {
            return mid
        } else if arr[mid] < target {
            low = mid + 1
        } else {
            high = mid - 1
        }
    }
    return -1
}
"""
# Decisions: while_statement(1) + if_statement(1) + else-if=nested if_statement(1) = 3
# → complexity = 1 + 3 = 4

SWIFT_RICH = """\
func process(x: Int) -> Int {
    if x > 0 {
        print(x)
    }
    guard x < 100 else { return -1 }
    switch x {
    case 1: print("one")
    default: print("other")
    }
    for i in 1...10 {
        print(i)
    }
    while x > 0 {
        print(x)
    }
    repeat {
        print(x)
    } while x < 10
    do {
        try riskyOp()
    } catch {
        print("error")
    }
    let r = x > 0 ? 1 : -1
    let t = x > 0 && x < 10
    let u = x < 0 || x > 100
    return r
}
"""
# Decisions:
#   if_statement           : 1
#   guard_statement        : 1
#   switch_statement       : 1
#   for_statement          : 1
#   while_statement        : 1
#   repeat_while_statement : 1
#   catch_block            : 1
#   ternary_expression     : 1
#   conjunction_expression : 1   (x > 0 && x < 10)
#   disjunction_expression : 1   (x < 0 || x > 100)
# Total = 10 → complexity = 1 + 10 = 11


def _swift_lang():
    import tree_sitter_swift

    return tree_sitter.Language(tree_sitter_swift.language())


def _swift_functions(source: str):
    lang = _swift_lang()
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(source.encode())
    from tree_sitter_analyzer.languages._swift_plugin_extractor import (
        SwiftElementExtractor,
    )

    extractor = SwiftElementExtractor()
    return extractor.extract_functions(tree, source)


class TestSwiftCyclomaticComplexity:
    def test_simple_no_branches(self):
        funcs = _swift_functions(SWIFT_SIMPLE)
        assert len(funcs) == 1
        assert funcs[0].name == "greet"
        assert funcs[0].complexity_score == 1

    def test_binary_search(self):
        """while + if + else-if (nested if_statement) = 3 decisions → complexity 4."""
        funcs = _swift_functions(SWIFT_BRANCHY)
        assert len(funcs) == 1
        assert funcs[0].name == "binarySearch"
        assert funcs[0].complexity_score == 4

    def test_rich_branching(self):
        """10 decision points → complexity 11."""
        funcs = _swift_functions(SWIFT_RICH)
        assert len(funcs) == 1
        assert funcs[0].name == "process"
        assert funcs[0].complexity_score == 11


# ---------------------------------------------------------------------------
# Scala
# ---------------------------------------------------------------------------

SCALA_SIMPLE = """\
def greet(name: String): String = {
  s"Hello, $name!"
}
"""
# No branches → complexity = 1

SCALA_BRANCHY = """\
def binarySearch(arr: Array[Int], target: Int): Int = {
  var low = 0
  var high = arr.length - 1
  while (low <= high) {
    val mid = (low + high) / 2
    if (arr(mid) == target) {
      mid
    } else if (arr(mid) < target) {
      low = mid + 1
      -1
    } else {
      high = mid - 1
      -1
    }
  }
  -1
}
"""
# Decisions: while_expression(1) + if_expression(1) + else-if (another if_expression)(1) = 3
# → complexity = 1 + 3 = 4

SCALA_RICH = """\
def process(x: Int): String = {
  val r = if (x > 0) "pos" else "neg"
  x match {
    case 1 => "one"
    case 2 => "two"
    case _ => "other"
  }
  for (i <- 1 to 10) {
    println(i)
  }
  while (x > 0) { println(x) }
  val ok = x > 0 && x < 10
  val ok2 = x < 0 || x > 100
  try {
    val d = 1 / x
  } catch {
    case e: Exception => println(e)
  }
  r
}
"""
# Decisions:
#   if_expression (inline if)   : 1
#   match_expression            : 1
#   case_clause x3 (in match)   : 3
#   for_expression              : 1
#   while_expression            : 1
#   catch_clause                : 1
#   case_clause (in catch)      : 1
#   &&  (operator_identifier)   : 1
#   ||  (operator_identifier)   : 1
# Total = 11 → complexity = 1 + 11 = 12


def _scala_lang():
    import tree_sitter_scala

    return tree_sitter.Language(tree_sitter_scala.language())


def _scala_functions(source: str):
    lang = _scala_lang()
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(source.encode())
    from tree_sitter_analyzer.languages.scala_plugin import ScalaElementExtractor

    extractor = ScalaElementExtractor()
    return extractor.extract_functions(tree, source)


class TestScalaCyclomaticComplexity:
    def test_simple_no_branches(self):
        funcs = _scala_functions(SCALA_SIMPLE)
        assert len(funcs) == 1
        assert funcs[0].name == "greet"
        assert funcs[0].complexity_score == 1

    def test_binary_search(self):
        """while_expression + if_expression x2 = 3 decisions → complexity 4."""
        funcs = _scala_functions(SCALA_BRANCHY)
        assert len(funcs) == 1
        assert funcs[0].name == "binarySearch"
        assert funcs[0].complexity_score == 4

    def test_rich_branching(self):
        """11 decision points → complexity 12."""
        funcs = _scala_functions(SCALA_RICH)
        assert len(funcs) == 1
        assert funcs[0].name == "process"
        assert funcs[0].complexity_score == 12


# ---------------------------------------------------------------------------
# Bash
# ---------------------------------------------------------------------------

BASH_SIMPLE = """\
greet() {
    echo "Hello, world!"
}
"""
# No branches → complexity = 1

BASH_BRANCHY = """\
binary_search() {
    local low=0
    local high=10
    while [ $low -le $high ]; do
        local mid=$(( (low + high) / 2 ))
        if [ "$mid" -eq 5 ]; then
            echo $mid
            return
        elif [ "$mid" -lt 5 ]; then
            low=$((mid + 1))
        else
            high=$((mid - 1))
        fi
    done
    echo -1
}
"""
# Decisions: while_statement(1) + if_statement(1) + elif_clause(1) = 3 → complexity 4

BASH_RICH = """\
process() {
    local x="$1"
    if [ "$x" -gt 0 ]; then
        echo "positive"
    elif [ "$x" -eq 0 ]; then
        echo "zero"
    fi
    while [ "$x" -gt 0 ]; do
        x=$((x - 1))
    done
    until [ "$x" -ge 10 ]; do
        x=$((x + 1))
    done
    for i in 1 2 3; do
        echo "$i"
    done
    for ((j=0; j<3; j++)); do
        echo "$j"
    done
    case "$x" in
        1) echo "one";;
        2) echo "two";;
        *) echo "other";;
    esac
    [ "$x" -gt 0 ] && echo "and" || echo "or"
}
"""
# Decisions:
#   if_statement          : 1
#   elif_clause           : 1
#   while_statement (while): 1
#   while_statement (until): 1
#   for_statement         : 1
#   c_style_for_statement : 1
#   case_item x3          : 3
#   &&                    : 1
#   ||                    : 1
# Total = 11 → complexity = 1 + 11 = 12


def _bash_lang():
    import tree_sitter_bash

    return tree_sitter.Language(tree_sitter_bash.language())


def _bash_functions(source: str):
    lang = _bash_lang()
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(source.encode())
    from tree_sitter_analyzer.languages.bash_plugin import BashElementExtractor

    extractor = BashElementExtractor()
    return extractor.extract_functions(tree, source)


class TestBashCyclomaticComplexity:
    def test_simple_no_branches(self):
        funcs = _bash_functions(BASH_SIMPLE)
        assert len(funcs) == 1
        assert funcs[0].name == "greet"
        assert funcs[0].complexity_score == 1

    def test_binary_search(self):
        """while_statement + if_statement + elif_clause = 3 decisions → complexity 4."""
        funcs = _bash_functions(BASH_BRANCHY)
        assert len(funcs) == 1
        assert funcs[0].name == "binary_search"
        assert funcs[0].complexity_score == 4

    def test_rich_branching(self):
        """11 decision points → complexity 12."""
        funcs = _bash_functions(BASH_RICH)
        assert len(funcs) == 1
        assert funcs[0].name == "process"
        assert funcs[0].complexity_score == 12


# ---------------------------------------------------------------------------
# Go
# ---------------------------------------------------------------------------

GO_SIMPLE = """\
package main

func greet(name string) string {
	return "Hello, " + name
}
"""
# No branches → complexity = 1

GO_BRANCHY = """\
package main

func binarySearch(arr []int, target int) int {
	low := 0
	high := len(arr) - 1
	for low <= high {
		mid := (low + high) / 2
		if arr[mid] == target {
			return mid
		} else if arr[mid] < target {
			low = mid + 1
		} else {
			high = mid - 1
		}
	}
	return -1
}
"""
# Decisions: for(1) + if(1) + else-if (nested if_statement)(1) = 3 → complexity = 4

GO_RICH = """\
package main

func process(x int) int {
	if x > 0 && x < 100 {
		return 1
	} else if x < 0 || x > 200 {
		return 2
	}
	for i := 0; i < 10; i++ {
	}
	switch x {
	case 1:
		return 3
	}
	return 0
}
"""
# Decisions:
#   if_statement                 : 1
#   &&                           : 1
#   else if (nested if_statement): 1
#   ||                           : 1
#   for_statement                : 1
#   expression_switch_statement  : 1
# Total = 6 → complexity = 1 + 6 = 7


def _go_functions(source: str):
    import tree_sitter_go

    lang = tree_sitter.Language(tree_sitter_go.language())
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(source.encode())
    from tree_sitter_analyzer.languages.go_plugin import GoElementExtractor

    extractor = GoElementExtractor()
    return extractor.extract_functions(tree, source)


class TestGoCyclomaticComplexity:
    def test_simple_no_branches(self):
        funcs = _go_functions(GO_SIMPLE)
        assert len(funcs) == 1
        assert funcs[0].name == "greet"
        assert funcs[0].complexity_score == 1

    def test_binary_search(self):
        """for + if + else-if (nested if_statement) = 3 decisions → complexity 4."""
        funcs = _go_functions(GO_BRANCHY)
        assert len(funcs) == 1
        assert funcs[0].name == "binarySearch"
        assert funcs[0].complexity_score == 4

    def test_rich_branching(self):
        """6 decision points → complexity 7."""
        funcs = _go_functions(GO_RICH)
        assert len(funcs) == 1
        assert funcs[0].name == "process"
        assert funcs[0].complexity_score == 7


# ---------------------------------------------------------------------------
# Rust
# ---------------------------------------------------------------------------

RUST_SIMPLE = """\
fn greet(name: &str) -> String {
    format!("Hello, {}!", name)
}
"""
# No branches → complexity = 1

RUST_BRANCHY = """\
fn binary_search(arr: &[i32], target: i32) -> i32 {
    let mut low = 0i32;
    let mut high = arr.len() as i32 - 1;
    while low <= high {
        let mid = (low + high) / 2;
        if arr[mid as usize] == target {
            return mid;
        } else if arr[mid as usize] < target {
            low = mid + 1;
        } else {
            high = mid - 1;
        }
    }
    -1
}
"""
# Decisions: while(1) + if(1) + else-if (nested if_expression)(1) = 3 → complexity = 4

RUST_RICH = """\
fn process(x: i32) -> i32 {
    if x > 0 && x < 100 {
        return 1;
    } else if x < 0 || x > 200 {
        return 2;
    }
    for _i in 0..10 {}
    match x {
        1 => return 3,
        _ => {}
    }
    0
}
"""
# Decisions:
#   if_expression                  : 1
#   &&                            : 1
#   else if (nested if_expression) : 1
#   ||                            : 1
#   for_expression                 : 1
#   match_expression               : 1
# Total = 6 → complexity = 1 + 6 = 7


def _rust_functions(source: str):
    import tree_sitter_rust

    lang = tree_sitter.Language(tree_sitter_rust.language())
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(source.encode())
    from tree_sitter_analyzer.languages.rust_plugin import RustPlugin

    extractor = RustPlugin().create_extractor()
    return extractor.extract_functions(tree, source)


class TestRustCyclomaticComplexity:
    def test_simple_no_branches(self):
        funcs = _rust_functions(RUST_SIMPLE)
        assert len(funcs) == 1
        assert funcs[0].name == "greet"
        assert funcs[0].complexity_score == 1

    def test_binary_search(self):
        """while + if + else-if (nested if_expression) = 3 decisions → complexity 4."""
        funcs = _rust_functions(RUST_BRANCHY)
        assert len(funcs) == 1
        assert funcs[0].name == "binary_search"
        assert funcs[0].complexity_score == 4

    def test_rich_branching(self):
        """6 decision points → complexity 7."""
        funcs = _rust_functions(RUST_RICH)
        assert len(funcs) == 1
        assert funcs[0].name == "process"
        assert funcs[0].complexity_score == 7


# ---------------------------------------------------------------------------
# Java
# ---------------------------------------------------------------------------
# The C-family plugins (Java/C/C++/C#) historically counted control-flow
# statements but NOT the "&&"/"||" short-circuit operators, while every other
# plugin (Python/JS/TS/Go/Rust/Ruby/Kotlin/PHP/Scala/Swift/Bash) does. These
# RED-first tests pin the post-fix value where each "&&"/"||" adds one decision
# point, restoring cross-language parity. The binary_search fixture has no
# boolean operators, so it is a control that stays at 4 (unchanged by the fix).

JAVA_SIMPLE = """\
class Sample {
    String greet(String name) {
        return "Hello, " + name;
    }
}
"""
# No branches → complexity = 1

JAVA_BRANCHY = """\
class Sample {
    int binarySearch(int[] arr, int target) {
        int low = 0;
        int high = arr.length - 1;
        while (low <= high) {
            int mid = (low + high) / 2;
            if (arr[mid] == target) {
                return mid;
            } else if (arr[mid] < target) {
                low = mid + 1;
            } else {
                high = mid - 1;
            }
        }
        return -1;
    }
}
"""
# Decisions: while(1) + if(1) + else-if (nested if_statement)(1) = 3
# No boolean operators → complexity = 1 + 3 = 4 (unchanged by the fix).

JAVA_RICH = """\
class Sample {
    int process(int x) {
        if (x > 0 && x < 100) {
            return 1;
        } else if (x < 0 || x > 200) {
            return 2;
        }
        for (int i = 0; i < 10; i++) {}
        while (x > 0) {
            x--;
        }
        try {
            int d = 1 / x;
        } catch (Exception e) {}
        return 0;
    }
}
"""
# Decisions counted by the Java walker:
#   if_statement          : 2   (if + else-if)
#   for_statement         : 1
#   while_statement       : 1
#   catch_clause          : 1
#   &&                    : 1   (NEW: short-circuit operator)
#   ||                    : 1   (NEW: short-circuit operator)
# Total = 7 → complexity = 1 + 7 = 8 (pre-fix this measured 6).


def _java_functions(source: str):
    import tree_sitter_java

    lang = tree_sitter.Language(tree_sitter_java.language())
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(source.encode())
    from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor

    return JavaElementExtractor().extract_functions(tree, source)


class TestJavaCyclomaticComplexity:
    def test_simple_no_branches(self):
        funcs = _java_functions(JAVA_SIMPLE)
        assert len(funcs) == 1
        assert funcs[0].name == "greet"
        assert funcs[0].complexity_score == 1

    def test_binary_search(self):
        """while + if + else-if = 3 decisions, no booleans → complexity 4."""
        funcs = _java_functions(JAVA_BRANCHY)
        assert len(funcs) == 1
        assert funcs[0].name == "binarySearch"
        assert funcs[0].complexity_score == 4

    def test_rich_branching(self):
        """7 decision points (incl. && and ||) → complexity 8."""
        funcs = _java_functions(JAVA_RICH)
        assert len(funcs) == 1
        assert funcs[0].name == "process"
        assert funcs[0].complexity_score == 8


# ---------------------------------------------------------------------------
# C
# ---------------------------------------------------------------------------

C_SIMPLE = """\
int greet(int n) {
    return n;
}
"""
# No branches → complexity = 1

C_BRANCHY = """\
int binary_search(int* arr, int n, int target) {
    int low = 0;
    int high = n - 1;
    while (low <= high) {
        int mid = (low + high) / 2;
        if (arr[mid] == target) {
            return mid;
        } else if (arr[mid] < target) {
            low = mid + 1;
        } else {
            high = mid - 1;
        }
    }
    return -1;
}
"""
# Decisions: while(1) + if(1) + else-if (nested if_statement)(1) = 3
# No boolean operators → complexity = 1 + 3 = 4 (unchanged by the fix).

C_RICH = """\
int process(int x) {
    if (x > 0 && x < 100) {
        return 1;
    } else if (x < 0 || x > 200) {
        return 2;
    }
    for (int i = 0; i < 10; i++) {}
    while (x > 0) {
        x--;
    }
    switch (x) {
        case 1: return 3;
    }
    int r = x > 0 ? 1 : -1;
    return r;
}
"""
# Decisions counted by the C walker:
#   if_statement          : 2   (if + else-if)
#   for_statement         : 1
#   while_statement       : 1
#   switch_statement      : 1
#   case_statement        : 1
#   conditional_expression: 1   (ternary)
#   &&                    : 1   (NEW: short-circuit operator)
#   ||                    : 1   (NEW: short-circuit operator)
# Total = 9 → complexity = 1 + 9 = 10 (pre-fix this measured 8).


def _c_functions(source: str):
    import tree_sitter_c

    lang = tree_sitter.Language(tree_sitter_c.language())
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(source.encode())
    from tree_sitter_analyzer.languages.c_plugin import CElementExtractor

    return CElementExtractor().extract_functions(tree, source)


class TestCCyclomaticComplexity:
    def test_simple_no_branches(self):
        funcs = _c_functions(C_SIMPLE)
        assert len(funcs) == 1
        assert funcs[0].name == "greet"
        assert funcs[0].complexity_score == 1

    def test_binary_search(self):
        """while + if + else-if = 3 decisions, no booleans → complexity 4."""
        funcs = _c_functions(C_BRANCHY)
        assert len(funcs) == 1
        assert funcs[0].name == "binary_search"
        assert funcs[0].complexity_score == 4

    def test_rich_branching(self):
        """9 decision points (incl. && and ||) → complexity 10."""
        funcs = _c_functions(C_RICH)
        assert len(funcs) == 1
        assert funcs[0].name == "process"
        assert funcs[0].complexity_score == 10


# ---------------------------------------------------------------------------
# C++
# ---------------------------------------------------------------------------


def _cpp_functions(source: str):
    import tree_sitter_cpp

    lang = tree_sitter.Language(tree_sitter_cpp.language())
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(source.encode())
    from tree_sitter_analyzer.languages.cpp_plugin import CppElementExtractor

    return CppElementExtractor().extract_functions(tree, source)


class TestCppCyclomaticComplexity:
    # Reuses the C fixtures: the grammars share the same decision-node types
    # for these constructs, and the C++ walker now counts && / || as well.
    def test_simple_no_branches(self):
        funcs = _cpp_functions(C_SIMPLE)
        assert len(funcs) == 1
        assert funcs[0].name == "greet"
        assert funcs[0].complexity_score == 1

    def test_binary_search(self):
        """while + if + else-if = 3 decisions, no booleans → complexity 4."""
        funcs = _cpp_functions(C_BRANCHY)
        assert len(funcs) == 1
        assert funcs[0].name == "binary_search"
        assert funcs[0].complexity_score == 4

    def test_rich_branching(self):
        """9 decision points (incl. && and ||) → complexity 10."""
        funcs = _cpp_functions(C_RICH)
        assert len(funcs) == 1
        assert funcs[0].name == "process"
        assert funcs[0].complexity_score == 10


# ---------------------------------------------------------------------------
# C#
# ---------------------------------------------------------------------------

CSHARP_SIMPLE = """\
class Sample {
    int Greet(int n) {
        return n;
    }
}
"""
# No branches → complexity = 1

CSHARP_BRANCHY = """\
class Sample {
    int BinarySearch(int[] arr, int target) {
        int low = 0;
        int high = arr.Length - 1;
        while (low <= high) {
            int mid = (low + high) / 2;
            if (arr[mid] == target) {
                return mid;
            } else if (arr[mid] < target) {
                low = mid + 1;
            } else {
                high = mid - 1;
            }
        }
        return -1;
    }
}
"""
# Decisions: while(1) + if(1) + else-if (nested if_statement)(1) = 3
# No boolean operators → complexity = 1 + 3 = 4 (unchanged by the fix).

CSHARP_RICH = """\
class Sample {
    int Process(int x) {
        if (x > 0 && x < 100) {
            return 1;
        } else if (x < 0 || x > 200) {
            return 2;
        }
        for (int i = 0; i < 10; i++) {}
        foreach (var y in new[] {1, 2}) {}
        while (x > 0) {
            x--;
        }
        switch (x) {
            case 1: return 3;
        }
        try {
            int d = 1 / x;
        } catch (Exception e) {}
        int r = x > 0 ? 1 : -1;
        return r;
    }
}
"""
# Decisions counted by the C# walker:
#   if_statement          : 2   (if + else-if)
#   for_statement         : 1
#   foreach_statement     : 1
#   while_statement       : 1
#   switch_statement      : 1
#   catch_clause          : 1
#   conditional_expression: 1   (ternary)
#   &&                    : 1   (NEW: short-circuit operator)
#   ||                    : 1   (NEW: short-circuit operator)
# Total = 10 → complexity = 1 + 10 = 11 (pre-fix this measured 9).


def _csharp_functions(source: str):
    import tree_sitter_c_sharp

    lang = tree_sitter.Language(tree_sitter_c_sharp.language())
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(source.encode())
    from tree_sitter_analyzer.languages.csharp_plugin import CSharpElementExtractor

    return CSharpElementExtractor().extract_functions(tree, source)


class TestCSharpCyclomaticComplexity:
    def test_simple_no_branches(self):
        funcs = _csharp_functions(CSHARP_SIMPLE)
        assert len(funcs) == 1
        assert funcs[0].name == "Greet"
        assert funcs[0].complexity_score == 1

    def test_binary_search(self):
        """while + if + else-if = 3 decisions, no booleans → complexity 4."""
        funcs = _csharp_functions(CSHARP_BRANCHY)
        assert len(funcs) == 1
        assert funcs[0].name == "BinarySearch"
        assert funcs[0].complexity_score == 4

    def test_rich_branching(self):
        """10 decision points (incl. && and ||) → complexity 11."""
        funcs = _csharp_functions(CSHARP_RICH)
        assert len(funcs) == 1
        assert funcs[0].name == "Process"
        assert funcs[0].complexity_score == 11


# ---------------------------------------------------------------------------
# Non-executable boolean contexts (Codex P2/P3 on PR #1085)
# ---------------------------------------------------------------------------
# A "&&"/"||" only adds a decision point when it drives executable control
# flow. Boolean tokens in a C++ noexcept/requires specifier, a preprocessor
# "#if A && B" condition, a default argument, or an attribute/annotation are
# compile-time / signature metadata, NOT runtime branches, and must leave an
# otherwise branch-free function at complexity 1.


class TestLogicalOperatorNonExecutableContexts:
    def test_cpp_noexcept_boolean_not_counted(self):
        funcs = _cpp_functions("int f() noexcept(true && false) { return 1; }")
        assert funcs[0].name == "f"
        assert funcs[0].complexity_score == 1

    def test_cpp_requires_boolean_not_counted(self):
        src = (
            "template<class T> int g() "
            "requires (sizeof(T) > 0 && sizeof(T) < 99) { return 2; }"
        )
        funcs = _cpp_functions(src)
        assert funcs[0].name == "g"
        assert funcs[0].complexity_score == 1

    def test_cpp_default_argument_boolean_not_counted(self):
        funcs = _cpp_functions("int h(bool flag = true && false) { return 1; }")
        assert funcs[0].name == "h"
        assert funcs[0].complexity_score == 1

    def test_cpp_preproc_if_boolean_not_counted(self):
        src = (
            "int f(int x) {\n#if defined(A) && defined(B)\n x++;\n#endif\n return x;\n}"
        )
        funcs = _cpp_functions(src)
        assert funcs[0].name == "f"
        assert funcs[0].complexity_score == 1

    def test_c_preproc_if_boolean_not_counted(self):
        src = (
            "int f(int x) {\n#if defined(A) && defined(B)\n x++;\n#endif\n return x;\n}"
        )
        funcs = _c_functions(src)
        assert funcs[0].name == "f"
        assert funcs[0].complexity_score == 1

    def test_csharp_default_argument_boolean_not_counted(self):
        funcs = _csharp_functions("class P { void M(bool flag = true && false) {} }")
        assert funcs[0].name == "M"
        assert funcs[0].complexity_score == 1

    def test_csharp_attribute_boolean_not_counted(self):
        funcs = _csharp_functions("class P { [Attr(true && false)] void M() {} }")
        assert funcs[0].name == "M"
        assert funcs[0].complexity_score == 1

    def test_csharp_preproc_if_boolean_not_counted(self):
        src = "class P {\n void M(int x) {\n#if DEBUG && TRACE\n x++;\n#endif\n }\n}"
        funcs = _csharp_functions(src)
        assert funcs[0].name == "M"
        assert funcs[0].complexity_score == 1

    def test_body_boolean_still_counts_as_control(self):
        """A genuine body "&&" must still add a decision point (regression guard)."""
        funcs = _cpp_functions(
            "int f(int x) { if (x > 0 && x < 9) { return 1; } return 0; }"
        )
        assert funcs[0].name == "f"
        assert funcs[0].complexity_score == 3


# ---------------------------------------------------------------------------
# Java decision-node coverage (tree-sitter-java node-name parity)
# ---------------------------------------------------------------------------
# tree-sitter-java emits "switch_expression" (NOT "switch_statement"),
# "ternary_expression" (NOT "conditional_expression"), and has a separate
# "do_statement". The historical _JAVA_DECISION_NODES used the wrong names, so
# Java silently ignored every switch, every ternary, and every do-while loop.
# Each construct is pinned in isolation (per CLAUDE.md: a mixed fixture would
# let one missed construct hide behind another's count).

JAVA_SWITCH_ONLY = """\
class S {
    int pick(int x) {
        switch (x) {
            case 1: return 10;
            case 2: return 20;
            case 3: return 30;
            default: return 0;
        }
    }
}
"""
# switch counts once (construct-once convention) → complexity = 1 + 1 = 2.

JAVA_TERNARY_ONLY = """\
class S {
    int sign(int x) {
        return x > 0 ? 1 : -1;
    }
}
"""
# one ternary → complexity = 1 + 1 = 2.

JAVA_DO_WHILE_ONLY = """\
class S {
    int drain(int x) {
        do {
            x--;
        } while (x > 0);
        return x;
    }
}
"""
# one do-while → complexity = 1 + 1 = 2.

JAVA_ALL_THREE = """\
class S {
    int run(int x) {
        do { x--; } while (x > 0);
        switch (x) { case 1: return 1; case 2: return 2; }
        return x > 0 ? 1 : -1;
    }
}
"""
# do-while(1) + switch(1) + ternary(1) = 3 → complexity = 1 + 3 = 4.


class TestJavaDecisionNodeCoverage:
    def test_switch_counts_once(self):
        funcs = _java_functions(JAVA_SWITCH_ONLY)
        assert len(funcs) == 1
        assert funcs[0].name == "pick"
        assert funcs[0].complexity_score == 2

    def test_ternary_counts(self):
        funcs = _java_functions(JAVA_TERNARY_ONLY)
        assert len(funcs) == 1
        assert funcs[0].name == "sign"
        assert funcs[0].complexity_score == 2

    def test_do_while_counts(self):
        funcs = _java_functions(JAVA_DO_WHILE_ONLY)
        assert len(funcs) == 1
        assert funcs[0].name == "drain"
        assert funcs[0].complexity_score == 2

    def test_all_three_combined(self):
        funcs = _java_functions(JAVA_ALL_THREE)
        assert len(funcs) == 1
        assert funcs[0].name == "run"
        assert funcs[0].complexity_score == 4
