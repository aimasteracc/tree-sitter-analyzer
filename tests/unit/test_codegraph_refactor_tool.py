"""Tests for codegraph_refactor MCP tool — AST-aware symbol renaming."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_refactor_tool import CodeGraphRefactorTool


@pytest.fixture
def tool():
    return CodeGraphRefactorTool()


@pytest.fixture
def tool_with_root(tmp_path):
    t = CodeGraphRefactorTool(str(tmp_path))
    return t


class TestToolDefinition:
    def test_tool_name(self, tool):
        assert tool.get_tool_definition()["name"] == "codegraph_refactor"

    def test_schema_required_fields(self, tool):
        required = tool.get_tool_schema()["required"]
        assert "symbol" in required
        assert "new_name" in required

    def test_schema_mode_enum(self, tool):
        mode = tool.get_tool_schema()["properties"]["mode"]
        assert set(mode["enum"]) == {"preview", "apply"}
        assert mode["default"] == "preview"

    def test_schema_output_format_default_toon(self, tool):
        fmt = tool.get_tool_schema()["properties"]["output_format"]
        assert fmt["default"] == "toon"

    def test_no_annotations_destructive_false(self, tool):
        defn = tool.get_tool_definition()
        # refactor tool explicitly does NOT have readOnlyHint in the dict
        # because it CAN write (apply mode); omitting the hint is fine per spec.
        # The important thing is it doesn't claim readOnlyHint=True.
        assert defn.get("annotations", {}).get("readOnlyHint") is not True


class TestValidation:
    def test_valid_rename(self, tool):
        assert (
            tool.validate_arguments({"symbol": "old_name", "new_name": "new_name"})
            is True
        )

    def test_requires_symbol(self, tool):
        with pytest.raises(ValueError, match="symbol is required"):
            tool.validate_arguments({"symbol": "", "new_name": "new_name"})

    def test_requires_new_name(self, tool):
        with pytest.raises(ValueError, match="new_name is required"):
            tool.validate_arguments({"symbol": "old_name", "new_name": ""})

    def test_same_name_rejected(self, tool):
        with pytest.raises(ValueError, match="must differ"):
            tool.validate_arguments({"symbol": "foo", "new_name": "foo"})

    def test_invalid_chars_in_symbol(self, tool):
        with pytest.raises(ValueError, match="valid identifier"):
            tool.validate_arguments({"symbol": "bad-name", "new_name": "good_name"})

    def test_invalid_chars_in_new_name(self, tool):
        with pytest.raises(ValueError, match="valid identifier"):
            tool.validate_arguments({"symbol": "old_name", "new_name": "bad-name"})

    def test_dotted_symbol_allowed(self, tool):
        assert (
            tool.validate_arguments(
                {"symbol": "Module.method", "new_name": "new_method"}
            )
            is True
        )


@pytest.mark.asyncio
class TestExecutePreview:
    async def test_preview_no_project_root_returns_error(self, tool):
        result = await tool.execute(
            {"symbol": "foo", "new_name": "bar", "output_format": "json"}
        )
        assert result["success"] is False

    async def test_preview_on_empty_project(self, tool_with_root):
        result = await tool_with_root.execute(
            {
                "symbol": "nonexistent_fn",
                "new_name": "renamed_fn",
                "output_format": "json",
            }
        )
        assert result["success"] is True
        assert (
            result.get("dry_run") is True
            or result.get("preview") is True
            or "sites" in result
        )

    async def test_toon_format_default(self, tool_with_root):
        result = await tool_with_root.execute(
            {"symbol": "nonexistent_fn", "new_name": "renamed_fn"}
        )
        assert result["format"] == "toon"
        assert "toon_content" in result


@pytest.mark.asyncio
async def test_unknown_mode_never_writes(tool_with_root, tmp_path):
    # 2026-09-08：拼错预览模式不能写入文件。
    source = tmp_path / "sample.py"
    original = b'def foo(x="foo"): return x\n\nfoo()\n'
    source.write_bytes(original)
    with pytest.raises(ValueError, match="mode"):
        await tool_with_root.execute(
            {"symbol": "foo", "new_name": "bar", "mode": "preveiw"}
        )
    assert source.read_bytes() == original


@pytest.mark.asyncio
async def test_real_rename_preserves_literals_and_reports_calls(
    tool_with_root, tmp_path
):
    # 2026-09-08：声明默认值不能误改，调用不能被零行占位符遗漏。
    source = tmp_path / "sample.py"
    source.write_bytes(b'def foo(x="foo"): return x\r\n\r\nfoo() # foo\r\n')
    result = await tool_with_root.execute(
        {"symbol": "foo", "new_name": "bar", "mode": "apply", "output_format": "json"}
    )
    assert result["success"] is True
    assert source.read_bytes() == b'def bar(x="foo"): return x\r\n\r\nbar() # foo\r\n'
    assert [(s["line"], s["column"]) for s in result["sites"]] == [(1, 4), (3, 0)]
    second = await tool_with_root.execute(
        {"symbol": "bar", "new_name": "baz", "mode": "apply", "output_format": "json"}
    )
    assert second["sites_renamed"] == 2
    assert source.read_bytes() == b'def baz(x="foo"): return x\r\n\r\nbaz() # foo\r\n'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra", ["\ndef other(foo): return foo()\n", "\nbar = 1\n", "\nobj.foo()\n"]
)
async def test_ambiguous_rename_fails_without_writes(tool_with_root, tmp_path, extra):
    source = tmp_path / "sample.py"
    original = ("def foo(): pass\nfoo()\n" + extra).encode()
    source.write_bytes(original)
    result = await tool_with_root.execute(
        {"symbol": "foo", "new_name": "bar", "mode": "apply", "output_format": "json"}
    )
    assert result["success"] is False
    assert result["files_changed"] == 0
    assert source.read_bytes() == original


@pytest.mark.asyncio
async def test_import_alias_binding_is_preserved(tool_with_root, tmp_path):
    (tmp_path / "a.py").write_bytes(b"def foo(): pass\n")
    source = tmp_path / "b.py"
    source.write_bytes(b"from a import foo as local\nlocal()\n")
    result = await tool_with_root.execute(
        {"symbol": "foo", "new_name": "bar", "mode": "apply", "output_format": "json"}
    )
    assert result["success"] is True
    assert source.read_bytes() == b"from a import bar as local\nlocal()\n"
    assert (tmp_path / "a.py").read_bytes() == b"def bar(): pass\n"


@pytest.mark.asyncio
async def test_direct_import_call_rename(tool_with_root, tmp_path):
    (tmp_path / "a.py").write_bytes(b"class foo: pass\n")
    source = tmp_path / "b.py"
    source.write_bytes(b"from a import foo\nfoo()\n")
    result = await tool_with_root.execute(
        {"symbol": "foo", "new_name": "bar", "mode": "apply", "output_format": "json"}
    )
    assert result["success"] is True
    assert result["sites_renamed"] == 3
    assert source.read_bytes() == b"from a import bar\nbar()\n"
    assert (tmp_path / "a.py").read_bytes() == b"class bar: pass\n"
    assert tool_with_root._cache.lookup(str(source)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "original",
    [
        b'# coding: latin-1\r\ndef foo(x="\xe9"): return x\r\nfoo()\r\n',
        b"\xef\xbb\xbfdef foo(): pass\nfoo()\n",
    ],
)
async def test_source_encoding_is_preserved(tool_with_root, tmp_path, original):
    source = tmp_path / "sample.py"
    source.write_bytes(original)
    result = await tool_with_root.execute(
        {"symbol": "foo", "new_name": "bar", "mode": "apply", "output_format": "json"}
    )
    assert result["success"] is True
    assert source.read_bytes() == original.replace(b"foo", b"bar")


@pytest.mark.asyncio
async def test_second_file_failure_rolls_back_all_bytes(
    tool_with_root, tmp_path, monkeypatch
):
    from pathlib import Path

    originals = {"a.py": b"def foo(): pass\r\n", "b.py": b"from a import foo\nfoo()\n"}
    for name, content in originals.items():
        (tmp_path / name).write_bytes(content)
    write = Path.write_bytes

    def fail_second(path, data):
        if path.name == "b.py" and b"bar" in data:
            write(path, b"partial")
            raise OSError("disk full")
        return write(path, data)

    monkeypatch.setattr(Path, "write_bytes", fail_second)
    result = await tool_with_root.execute(
        {"symbol": "foo", "new_name": "bar", "mode": "apply", "output_format": "json"}
    )
    assert result["success"] is False
    assert (result["files_changed"], result["sites_renamed"]) == (0, 0)
    assert {name: (tmp_path / name).read_bytes() for name in originals} == originals


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra",
    [
        '\n__all__ = ["foo"]\n',
        '\ndef other(x: "foo"): pass\n',
        "\nfrom a import *\n",
        '\nexec("foo()")\n',
        "\nfrom .a import foo\n",
    ],
)
async def test_unsupported_binding_forms_fail_closed(tool_with_root, tmp_path, extra):
    source = tmp_path / "a.py"
    original = ("def foo(): pass\n" + extra).encode()
    source.write_bytes(original)
    result = await tool_with_root.execute(
        {"symbol": "foo", "new_name": "bar", "mode": "apply", "output_format": "json"}
    )
    assert result["success"] is False
    assert source.read_bytes() == original


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["preview", "apply"])
@pytest.mark.parametrize("new_name", ["__debug__", "\uff42\uff41\uff52"])
async def test_reserved_or_non_normalized_names_fail_closed(
    tool_with_root, tmp_path, mode, new_name
):
    source = tmp_path / "sample.py"
    original = b"def foo(): pass\nfoo()\n"
    source.write_bytes(original)
    result = await tool_with_root.execute(
        {"symbol": "foo", "new_name": new_name, "mode": mode, "output_format": "json"}
    )
    assert result["success"] is False
    assert source.read_bytes() == original


@pytest.mark.asyncio
async def test_class_private_name_mangling_is_rejected(tool_with_root, tmp_path):
    source = tmp_path / "sample.py"
    original = b"def foo(): pass\nclass C:\n    def run(self): return foo()\n"
    source.write_bytes(original)
    result = await tool_with_root.execute(
        {
            "symbol": "foo",
            "new_name": "__renamed",
            "mode": "apply",
            "output_format": "json",
        }
    )
    assert result["success"] is False
    assert source.read_bytes() == original


@pytest.mark.asyncio
async def test_preview_reports_exact_sites_without_writing(tool_with_root, tmp_path):
    source = tmp_path / "sample.py"
    original = b"def foo(): pass\nfoo()\n"
    source.write_bytes(original)
    result = await tool_with_root.execute(
        {"symbol": "foo", "new_name": "bar", "mode": "preview", "output_format": "json"}
    )
    assert result["success"] is True
    assert result["files_affected"] == ["sample.py"]
    assert [(site["line"], site["column"]) for site in result["sites"]] == [
        (1, 4),
        (2, 0),
    ]
    assert result["files_changed"] == 0
    assert source.read_bytes() == original


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["preview", "apply"])
@pytest.mark.parametrize(
    "body",
    [
        "    def __init__(self): self.__x = 1\n",
        "    def __method(self): pass\n",
        "    __value = 1\n",
        "    def method(self, __argument): return __argument\n",
    ],
)
async def test_class_with_private_identifiers_cannot_be_renamed(
    tool_with_root, tmp_path, mode, body
):
    # 2026-09-08：类名变化会改变私有标识符的名称改写规则。
    source = tmp_path / "sample.py"
    original = ("class Foo:\n" + body + "obj = Foo()\n").encode()
    source.write_bytes(original)
    result = await tool_with_root.execute(
        {"symbol": "Foo", "new_name": "Bar", "mode": mode, "output_format": "json"}
    )
    assert result["success"] is False
    assert result["errors"] == ["Classes with private name mangling are unsupported"]
    assert result["files_changed"] == 0
    assert source.read_bytes() == original


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["preview", "apply"])
async def test_class_with_slots_cannot_be_renamed(tool_with_root, tmp_path, mode):
    # 2026-09-08：字符串形式的私有槽也依赖类名改写。
    source = tmp_path / "sample.py"
    original = b'class Foo: __slots__ = ("__x",)\nobj = Foo()\nobj._Foo__x = 1\n'
    source.write_bytes(original)
    result = await tool_with_root.execute(
        {"symbol": "Foo", "new_name": "Bar", "mode": mode, "output_format": "json"}
    )
    assert result["success"] is False
    assert result["errors"] == ["Classes with __slots__ are unsupported"]
    assert result["files_changed"] == 0
    assert source.read_bytes() == original
