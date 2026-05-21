"""Regression tests for multibyte byte-slice handling across language plugins.

Tree-sitter exposes ``node.start_byte`` / ``node.end_byte`` as UTF-8 byte
offsets, while Python ``str`` slicing is by codepoint. When source code
contains multibyte characters (CJK ideographs, em-dashes, accented vowels,
emoji, ...) upstream of a target node, slicing the ``str`` form directly
mis-aligns the extracted text — names get truncated, signatures shift, raw
text bleeds into siblings.

This module pins the fix at the public extractor seam for every language
plugin that the bug-class report flagged (python, ruby, csharp, php). Each
test builds a tiny source file with a multibyte string in a docstring /
comment / attribute *upstream* of a class or function definition and asserts
that the extracted ``name`` (and where relevant ``raw_text``) is still
correct.

The assertions accept each plugin's natural qualified-name form (e.g. Ruby
``Wrapper#method``, PHP ``Wrapper::method``, PHP namespaced ``App\\Class``).
What we are pinning is *byte-vs-codepoint alignment*, not the qualified-name
convention.
"""

from __future__ import annotations

import pytest
import tree_sitter

from tree_sitter_analyzer.languages.csharp_plugin import CSharpPlugin
from tree_sitter_analyzer.languages.php_plugin import PHPPlugin
from tree_sitter_analyzer.languages.python_plugin import PythonPlugin
from tree_sitter_analyzer.languages.ruby_plugin import RubyPlugin

# A small zoo of multibyte chars. Each is 2-4 UTF-8 bytes so any direct
# ``str``-slicing of byte offsets will shift by at least 1 codepoint and
# corrupt downstream identifier extraction.
MULTIBYTE_SAMPLES = ["—", "中文", "café", "🚀", "Ωμέγα"]


def _build_parser(language: tree_sitter.Language) -> tree_sitter.Parser:
    """Construct a parser working with old + new tree_sitter binding APIs."""
    try:
        return tree_sitter.Parser(language)
    except TypeError:
        # Older binding: empty ctor + set_language / language attribute.
        parser = tree_sitter.Parser()
        if hasattr(parser, "set_language"):
            parser.set_language(language)
        else:
            parser.language = language
        return parser


def _parse(source: str, plugin: object) -> tree_sitter.Tree:
    """Parse ``source`` using ``plugin``'s tree-sitter language."""
    language = plugin.get_tree_sitter_language()  # type: ignore[attr-defined]
    assert language is not None, f"{type(plugin).__name__} missing language"
    parser = _build_parser(language)
    return parser.parse(source.encode("utf-8"))


def _has_simple_name(names: list[str], expected: str) -> bool:
    """Return True if any extracted name contains ``expected`` as a whole
    identifier component.

    Plugins emit ``ClassName``, ``Namespace\\ClassName``, ``Class#method``,
    ``Class::method`` etc. We split on the conventional separators and check
    the simple identifier survives intact — i.e. the byte/codepoint offsets
    did not shift and chop a leading character off the identifier.
    """
    for raw in names:
        parts: list[str] = [raw]
        for sep in ("::", "#", ".", "\\", "/"):
            new_parts: list[str] = []
            for piece in parts:
                new_parts.extend(piece.split(sep))
            parts = new_parts
        if expected in parts:
            return True
    return False


# -----------------------------------------------------------------------------
# Python
# -----------------------------------------------------------------------------


@pytest.mark.parametrize("mb", MULTIBYTE_SAMPLES)
def test_python_class_name_after_multibyte_docstring(mb: str) -> None:
    """Python class extraction stays aligned past a multibyte docstring."""
    source = f'''"""Module {mb} docstring."""


class TargetClass:
    """Class {mb} docstring."""

    def method_one(self) -> int:
        return 1
'''
    plugin = PythonPlugin()
    extractor = plugin.create_extractor()
    tree = _parse(source, plugin)

    classes = extractor.extract_classes(tree, source)
    class_names = [c.name for c in classes]
    assert _has_simple_name(class_names, "TargetClass"), (
        f"name shifted for multibyte={mb!r}: got {class_names}"
    )

    target = next(c for c in classes if "TargetClass" in c.name)
    # raw_text must start with ``class TargetClass`` — if byte offsets leak
    # through a str-slice the first chars become garbage.
    assert target.raw_text.startswith("class TargetClass"), (
        f"raw_text mis-aligned for multibyte={mb!r}: {target.raw_text[:40]!r}"
    )


@pytest.mark.parametrize("mb", MULTIBYTE_SAMPLES)
def test_python_function_signature_after_multibyte(mb: str) -> None:
    """Function name + parameter extraction stays aligned past multibyte."""
    source = f'''"""Module {mb}."""


def target_function(x: int, y: str) -> bool:
    """Function {mb}."""
    return True
'''
    plugin = PythonPlugin()
    extractor = plugin.create_extractor()
    tree = _parse(source, plugin)

    funcs = extractor.extract_functions(tree, source)
    names = [f.name for f in funcs]
    assert _has_simple_name(names, "target_function"), (
        f"function name shifted for multibyte={mb!r}: {names}"
    )

    target = next(f for f in funcs if "target_function" in f.name)
    # Parameter names must survive even though plugin may emit ``x`` or
    # ``x: int``. We split on `:` so either form is OK.
    param_names = [p.split(":")[0].strip() for p in target.parameters]
    assert param_names == ["x", "y"], (
        f"parameters mis-extracted for multibyte={mb!r}: {target.parameters}"
    )
    assert target.return_type == "bool", (
        f"return type mis-extracted for multibyte={mb!r}: {target.return_type}"
    )


# -----------------------------------------------------------------------------
# Ruby
# -----------------------------------------------------------------------------


@pytest.mark.parametrize("mb", MULTIBYTE_SAMPLES)
def test_ruby_class_name_after_multibyte_comment(mb: str) -> None:
    """Ruby class extraction stays aligned past a multibyte comment."""
    source = f"""# Header comment {mb}

class TargetRuby
  def hello
    "hi"
  end
end
"""
    plugin = RubyPlugin()
    extractor = plugin.create_extractor()
    tree = _parse(source, plugin)

    classes = extractor.extract_classes(tree, source)
    class_names = [c.name for c in classes]
    assert _has_simple_name(class_names, "TargetRuby"), (
        f"ruby class name shifted for multibyte={mb!r}: {class_names}"
    )


@pytest.mark.parametrize("mb", MULTIBYTE_SAMPLES)
def test_ruby_function_name_after_multibyte_comment(mb: str) -> None:
    """Ruby method extraction stays aligned past a multibyte comment."""
    source = f"""# Header {mb}

class Wrapper
  def target_method(x)
    x
  end
end
"""
    plugin = RubyPlugin()
    extractor = plugin.create_extractor()
    tree = _parse(source, plugin)

    funcs = extractor.extract_functions(tree, source)
    names = [f.name for f in funcs]
    assert _has_simple_name(names, "target_method"), (
        f"ruby method shifted for multibyte={mb!r}: {names}"
    )


# -----------------------------------------------------------------------------
# C#
# -----------------------------------------------------------------------------


@pytest.mark.parametrize("mb", MULTIBYTE_SAMPLES)
def test_csharp_class_name_after_multibyte_comment(mb: str) -> None:
    """C# class extraction stays aligned past a multibyte XML doc comment."""
    source = f"""// File comment {mb}
using System;

namespace App
{{
    /// <summary>Doc {mb}.</summary>
    public class TargetCSharp
    {{
        public int DoWork() => 42;
    }}
}}
"""
    plugin = CSharpPlugin()
    extractor = plugin.create_extractor()
    tree = _parse(source, plugin)

    classes = extractor.extract_classes(tree, source)
    class_names = [c.name for c in classes]
    assert _has_simple_name(class_names, "TargetCSharp"), (
        f"csharp class name shifted for multibyte={mb!r}: {class_names}"
    )


@pytest.mark.parametrize("mb", MULTIBYTE_SAMPLES)
def test_csharp_method_name_after_multibyte_comment(mb: str) -> None:
    """C# method extraction stays aligned past a multibyte comment."""
    source = f"""// Header {mb}
using System;

namespace App
{{
    public class Wrapper
    {{
        /// <summary>{mb}</summary>
        public int TargetMethod(int x) => x;
    }}
}}
"""
    plugin = CSharpPlugin()
    extractor = plugin.create_extractor()
    tree = _parse(source, plugin)

    funcs = extractor.extract_functions(tree, source)
    names = [f.name for f in funcs]
    assert _has_simple_name(names, "TargetMethod"), (
        f"csharp method shifted for multibyte={mb!r}: {names}"
    )


# -----------------------------------------------------------------------------
# PHP
# -----------------------------------------------------------------------------


@pytest.mark.parametrize("mb", MULTIBYTE_SAMPLES)
def test_php_class_name_after_multibyte_comment(mb: str) -> None:
    """PHP class extraction stays aligned past a multibyte PHPDoc comment."""
    source = f"""<?php
// Header comment {mb}
namespace App;

/** Class doc {mb}. */
class TargetPhp
{{
    public function hello(): string
    {{
        return "hi";
    }}
}}
"""
    plugin = PHPPlugin()
    extractor = plugin.create_extractor()
    tree = _parse(source, plugin)

    classes = extractor.extract_classes(tree, source)
    class_names = [c.name for c in classes]
    assert _has_simple_name(class_names, "TargetPhp"), (
        f"php class name shifted for multibyte={mb!r}: {class_names}"
    )


@pytest.mark.parametrize("mb", MULTIBYTE_SAMPLES)
def test_php_function_name_after_multibyte_comment(mb: str) -> None:
    """PHP method extraction stays aligned past a multibyte comment."""
    source = f"""<?php
// Header {mb}
namespace App;

class Wrapper
{{
    /** Method {mb}. */
    public function targetMethod(int $x): int
    {{
        return $x;
    }}
}}
"""
    plugin = PHPPlugin()
    extractor = plugin.create_extractor()
    tree = _parse(source, plugin)

    funcs = extractor.extract_functions(tree, source)
    names = [f.name for f in funcs]
    assert _has_simple_name(names, "targetMethod"), (
        f"php method shifted for multibyte={mb!r}: {names}"
    )
