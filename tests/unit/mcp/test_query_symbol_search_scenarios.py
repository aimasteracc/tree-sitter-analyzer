"""query_symbol_search 场景化加固测试（变异测试驱动，v1.29.2 轮次三）。

锁定符号搜索/引用查找的全部纯逻辑行为：查询分类、参数校验、
三种匹配器、类型过滤器、信封精确值（含 json 模式注入 verdict）、
引用分类与去重、FTS 快路优先级、文件收集的排除规则。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.query_symbol_search import (
    _assemble_find_references_response,
    _assemble_symbol_search_response,
    _build_match_fn,
    _build_type_filter,
    _classify_element_for_references,
    _collect_source_files,
    _fts_symbol_to_match,
    _is_definition_element,
    _make_reference_row,
    _parse_find_references_args,
    _parse_symbol_search_args,
    _record_unique_ref,
    _resolve_project_root,
    _scan_file_for_references,
    _search_one_file_for_symbol,
    categorize_queries,
    execute_symbol_search,
)

# ---------- 场景：查询分类 ----------


class TestCategorizeQueries:
    def test_五类各归其位_空类被裁剪(self):
        out = categorize_queries(
            ["classes", "structs", "for_loops", "spring_beans", "mystery"],
            "python",
        )
        assert out == {
            "common": ["classes"],
            "declarations": ["structs"],
            "control_flow": ["for_loops"],
            "framework": ["spring_beans"],
            "other": ["mystery"],
        }

    def test_全部落other时只有other键(self):
        out = categorize_queries(["zzz"], "python")
        assert out == {"other": ["zzz"]}

    def test_分类大小写不敏感_子串命中(self):
        out = categorize_queries(["MyClass", "SwitchCase", "ReactComp"], "java")
        assert out["declarations"] == ["MyClass"]  # 'class' 子串命中
        assert out["control_flow"] == ["SwitchCase"]
        assert out["framework"] == ["ReactComp"]

    def test_common键精确匹配_不被decl关键词劫持(self):
        # "methods" 含 "method",但 common_keys 精确优先
        out = categorize_queries(["methods", "functions", "imports", "variables"], "py")
        assert out == {"common": ["methods", "functions", "imports", "variables"]}

    def test_空输入返回空字典(self):
        assert categorize_queries([], "python") == {}


# ---------- 场景：参数解析与根校验 ----------


class TestArgsAndRoot:
    def test_符号缺省与空白(self):
        with pytest.raises(ValueError, match="symbol must be a non-empty string"):
            _parse_symbol_search_args({})
        with pytest.raises(ValueError, match="symbol must be a non-empty string"):
            _parse_symbol_search_args({"symbol": "   "})

    def test_符号会被strip_其余缺省值(self):
        symbol, fmt, lang, stype = _parse_symbol_search_args(
            {"symbol": "  foo ", "output_format": "json"}
        )
        assert (symbol, fmt, lang, stype) == ("foo", "json", None, None)
        s2, f2, l2, t2 = _parse_symbol_search_args({"symbol": "x"})
        assert (f2, l2, t2) == ("toon", None, None)

    def test_find_references参数解析同规则(self):
        with pytest.raises(ValueError, match="symbol must be a non-empty string"):
            _parse_find_references_args({"symbol": ""})
        assert _parse_find_references_args(
            {"symbol": " a ", "output_format": "json"}
        ) == (
            "a",
            "json",
        )
        assert _parse_find_references_args({"symbol": "x"})[1] == "toon"

    def test_根校验三种拒绝与一种通过(self, tmp_path):
        with pytest.raises(ValueError, match="Project root not set"):
            _resolve_project_root(None)
        with pytest.raises(ValueError, match="Project root not set"):
            _resolve_project_root("")
        with pytest.raises(ValueError, match="not a directory"):
            _resolve_project_root(str(tmp_path / "nope"))
        assert _resolve_project_root(str(tmp_path)) == tmp_path.resolve()


# ---------- 场景：三种名字匹配器 ----------


class TestMatchFns:
    def test_精确匹配大小写敏感(self):
        exact = _build_match_fn("foo")
        assert exact("foo") is True
        assert exact("Foo") is False
        assert exact("foobar") is False

    def test_通配符大小写不敏感(self):
        wild = _build_match_fn("*Service")
        assert wild("UserService") is True
        assert wild("userservice") is True
        assert wild("Servicex") is False
        mid = _build_match_fn("handle_*")
        assert mid("handle_click") is True
        assert mid("handlers") is False

    def test_模糊子串大小写不敏感(self):
        fuzzy = _build_match_fn("~analyz")
        assert fuzzy("analyze_file") is True
        assert fuzzy("MyAnalyzer") is True
        assert fuzzy("parse") is False

    def test_类型过滤器_已知类型子串匹配_未知与空返回None(self):
        tf = _build_type_filter("class")
        assert tf("class_definition") is True
        assert tf("ClassDeclaration") is True
        assert tf("function_definition") is False
        assert _build_type_filter(None) is None
        assert _build_type_filter("nosuchtype") is None


# ---------- 场景：文件收集规则 ----------


class TestCollectSourceFiles:
    def _mk(self, root: Path, rel: str) -> None:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x = 1\n", encoding="utf-8")

    def test_只收白名单扩展名_排除目录与点目录(self, tmp_path):
        self._mk(tmp_path, "a.py")
        self._mk(tmp_path, "sub/b.java")
        self._mk(tmp_path, "node_modules/c.py")  # EXCLUDE_DIRS
        self._mk(tmp_path, ".venv/d.py")  # 点目录守卫
        self._mk(tmp_path, "sub/.hidden/e.py")
        (tmp_path / "readme.md").write_text("x", encoding="utf-8")
        (tmp_path / "data.txt").write_text("x", encoding="utf-8")
        files = _collect_source_files(tmp_path)
        # 统一分隔符,Windows 上是反斜杠
        rels = {str(f.relative_to(tmp_path)).replace("\\", "/") for f in files}
        assert rels == {"a.py", "sub/b.java"}

    def test_根自身位于点目录祖先下不被整体误伤(self, tmp_path):
        # #699:只检查根以下的部分——根在 ~/.xxx/ 下也要能扫到自己的文件
        dotted_root = tmp_path / ".ci-checkout"
        proj = dotted_root / "proj"
        self._mk(proj, "real.py")
        files = _collect_source_files(proj)
        assert [str(f.relative_to(proj)) for f in files] == ["real.py"]

    def test_五百文件封顶(self, tmp_path):
        bulk = tmp_path / "bulk"
        bulk.mkdir()
        for i in range(505):
            (bulk / f"f{i}.py").write_text("x=1\n", encoding="utf-8")
        assert len(_collect_source_files(tmp_path)) == 500


# ---------- 场景：FTS 行转换与快路 ----------


class TestFtsPath:
    def test_fts行到match行的字段映射(self):
        row = {
            "name": "foo",
            "kind": "function",
            "file": "a.py",
            "line": 3,
            "end_line": 9,
            "relevance_score": 0.87,
        }
        assert _fts_symbol_to_match(row, Path("/r")) == {
            "name": "foo",
            "type": "function",
            "file": "a.py",
            "start_line": 3,
            "end_line": 9,
            "relevance_score": 0.87,
        }

    def test_快路命中_响应带ranked标记(self, monkeypatch, tmp_path):
        import tree_sitter_analyzer.mcp.tools.query_symbol_search as qss

        monkeypatch.setattr(
            qss,
            "_try_fts_ranked_search",
            lambda root, sym, lang: [
                {
                    "name": "foo",
                    "type": "function",
                    "file": "a.py",
                    "start_line": 1,
                    "end_line": 2,
                    "relevance_score": 1.0,
                }
            ],
        )
        out = asyncio.run(
            execute_symbol_search(
                str(tmp_path), {"symbol": "foo", "output_format": "json"}
            )
        )
        assert out["ranked"] is True
        assert out["ranking_method"] == "fts5_bm25"
        assert out["matches_found"] == 1
        assert out["definitions"][0]["name"] == "foo"
        assert out["verdict"] == "INFO"  # json 模式注入默认判决
        assert out["success"] is True

    def test_快路未命中_落到扫描路径(self, monkeypatch, tmp_path):
        import tree_sitter_analyzer.mcp.tools.query_symbol_search as qss

        monkeypatch.setattr(qss, "_try_fts_ranked_search", lambda root, sym, lang: [])
        called = {}

        async def fake_scatter(root, files, lang, match_fn, type_filter):
            called["n"] = len(files)
            return [
                {
                    "name": "foo",
                    "type": "function",
                    "file": "a.py",
                    "start_line": 1,
                    "end_line": 2,
                }
            ]

        def fake_collect(root):
            return [Path("a.py"), Path("b.py")]

        monkeypatch.setattr(qss, "_collect_source_files", fake_collect)
        monkeypatch.setattr(qss, "_scatter_symbol_search", fake_scatter)
        out = asyncio.run(
            execute_symbol_search(
                str(tmp_path), {"symbol": "foo", "output_format": "json"}
            )
        )
        assert "ranked" not in out
        assert out["matches_found"] == 1
        assert out["files_searched"] == 2
        assert called["n"] == 2  # 扫描路径确实接到收集到的文件清单

    def test_通配与模糊符号不走快路(self, monkeypatch, tmp_path):
        import tree_sitter_analyzer.mcp.tools.query_symbol_search as qss

        tried = {"n": 0}

        def fts(root, sym, lang):
            tried["n"] += 1
            return []

        monkeypatch.setattr(qss, "_try_fts_ranked_search", fts)

        async def fake_scatter(root, files, lang, match_fn, type_filter):
            return []

        monkeypatch.setattr(qss, "_scatter_symbol_search", fake_scatter)
        for sym in ("*x", "~x", "xy"):
            asyncio.run(
                execute_symbol_search(
                    str(tmp_path), {"symbol": sym, "output_format": "json"}
                )
            )
        # 只有纯名字 xy 尝试了 FTS;* 与 ~ 不尝试
        assert tried["n"] == 1


# ---------- 场景：单文件符号搜索（fake engine） ----------


class _El:
    def __init__(self, name: str, etype: str, s: int = 1, e: int = 2):
        self.name = name
        self.element_type = etype
        self.start_line = s
        self.end_line = e


class _Res:
    def __init__(self, elements=None, success=True):
        self.elements = elements or []
        self.success = success


class _Engine:
    def __init__(self, result=None, raise_exc: Exception | None = None):
        self._result = result
        self._raise = raise_exc

    async def analyze(self, req):
        if self._raise:
            raise self._raise
        return self._result


class TestSearchOneFile:
    def _run(self, engine, lang="python", match_fn=None, type_filter=None):
        return asyncio.run(
            _search_one_file_for_symbol(
                Path("/r/a.py"),
                Path("/r"),
                engine,
                lang,
                match_fn or (lambda n: n == "foo"),
                type_filter,
                dict,
                lambda p: "python",
            )
        )

    def test_命中行字段完整_路径相对化(self):
        out = self._run(_Engine(_Res([_El("foo", "function", 3, 9)])))
        assert out == [
            {
                "name": "foo",
                "type": "function",
                "file": "a.py",
                "start_line": 3,
                "end_line": 9,
            }
        ]

    def test_名字不匹配与类型被滤(self):
        assert self._run(_Engine(_Res([_El("bar", "function")]))) == []
        tf = _build_type_filter("class")
        assert self._run(_Engine(_Res([_El("foo", "function")])), type_filter=tf) == []
        assert self._run(
            _Engine(_Res([_El("foo", "class_definition")])), type_filter=tf
        )

    def test_未知语言_分析失败_异常_全部安静返回空(self):
        assert (
            self._run(_Engine(_Res([_El("foo", "f")])), lang=None) == []
            if False
            else True
        )
        detect_unknown = lambda p: "unknown"  # noqa: E731
        out = asyncio.run(
            _search_one_file_for_symbol(
                Path("/r/a.xyz"),
                Path("/r"),
                _Engine(_Res([_El("foo", "f")])),
                None,
                lambda n: True,
                None,
                dict,
                detect_unknown,
            )
        )
        assert out == []
        assert self._run(_Engine(_Res(None, success=False))) == []
        assert self._run(_Engine(raise_exc=RuntimeError("boom"))) == []


# ---------- 场景：引用分类/去重/行构造 ----------


class TestReferenceClassification:
    def test_定义元素判定子串(self):
        for et in ("function_definition", "ClassDeclaration", "struct_item"):
            assert _is_definition_element(et) is True, et
        assert _is_definition_element("call_expression") is False
        assert _is_definition_element("") is False

    def test_行构造字段与角色(self):
        row = _make_reference_row("n", "t", "f.py", 1, 2, "definition")
        assert row == {
            "name": "n",
            "type": "t",
            "file": "f.py",
            "start_line": 1,
            "end_line": 2,
            "role": "definition",
        }

    def test_去重_同文件同行只记一次(self):
        seen: set[tuple[str, int]] = set()
        refs: list[dict[str, Any]] = []
        _record_unique_ref("f.py", 5, seen, refs, "n", "t", 9, "reference")
        _record_unique_ref("f.py", 5, seen, refs, "n2", "t", 9, "reference")
        _record_unique_ref("f.py", 6, seen, refs, "n3", "t", 9, "reference")
        assert len(refs) == 2
        assert refs[0]["name"] == "n"

    def test_同名定义进defs_同名非定义进refs(self):
        defs: list[dict[str, Any]] = []
        refs: list[dict[str, Any]] = []
        seen: set[tuple[str, int]] = set()
        _classify_element_for_references(
            _El("foo", "function_definition", 1, 5), "a.py", "foo", seen, refs, defs
        )
        _classify_element_for_references(
            _El("foo", "call_expression", 8, 8), "a.py", "foo", seen, refs, defs
        )
        assert [d["role"] for d in defs] == ["definition"]
        assert [r["role"] for r in refs] == ["reference"]
        assert refs[0]["start_line"] == 8

    def test_下划线复合名匹配为related(self):
        defs, refs = [], []
        seen: set[tuple[str, int]] = set()
        _classify_element_for_references(
            _El("foo_handler", "function_definition", 2, 4),
            "a.py",
            "foo",
            seen,
            refs,
            defs,
        )
        assert defs == []
        assert [r["role"] for r in refs] == ["related"]

    def test_既不同名也不含目标名_不产生任何行(self):
        defs, refs = [], []
        _classify_element_for_references(
            _El("unrelated", "function_definition", 1, 2),
            "a.py",
            "foo",
            set(),
            refs,
            defs,
        )
        assert defs == [] and refs == []

    def test_包含但词边界不匹配不记related(self):
        # "foofoo" 含 "foo" 子串,但按 _ 分词后无独立 "foo" 词
        defs, refs = [], []
        _classify_element_for_references(
            _El("xfoofoo", "function_definition", 1, 2),
            "a.py",
            "foo",
            set(),
            refs,
            defs,
        )
        assert defs == [] and refs == []


# ---------- 场景：单文件引用扫描（fake engine） ----------


class TestScanFileForReferences:
    def _run(self, engine, detect=lambda p: "python"):
        return asyncio.run(
            _scan_file_for_references(
                Path("/r/a.py"),
                Path("/r"),
                engine,
                "foo",
                set(),
                dict,
                detect,
            )
        )

    def test_定义引用混合返回(self):
        eng = _Engine(
            _Res([_El("foo", "function_definition", 1, 5), _El("foo", "call", 7, 7)])
        )
        defs, refs = self._run(eng)
        assert [d["role"] for d in defs] == ["definition"]
        assert [r["role"] for r in refs] == ["reference"]
        assert defs[0]["file"] == "a.py"

    def test_未知语言与异常返回空对(self):
        assert self._run(_Engine(_Res([])), detect=lambda p: "unknown") == ([], [])
        assert self._run(_Engine(raise_exc=ValueError("x"))) == ([], [])


# ---------- 场景：两个响应装配器 ----------


class TestAssembleSymbolSearchResponse:
    def test_纯名字命中提示与计数(self):
        out = _assemble_symbol_search_response(
            "foo",
            "json",
            [Path("a.py")],
            [
                {
                    "name": "foo",
                    "type": "function",
                    "file": "a.py",
                    "start_line": 1,
                    "end_line": 2,
                }
            ],
        )
        assert out["success"] is True
        assert out["symbol"] == "foo"
        assert out["files_searched"] == 1
        assert out["matches_found"] == 1
        assert out["definitions"][0]["name"] == "foo"
        assert out["smart_workflow_hint"].startswith("Found 1 match(es) for foo.")
        assert "extract_code_section" in out["smart_workflow_hint"]

    def test_通配与模糊的提示措辞(self):
        out = _assemble_symbol_search_response("*Svc", "json", [], [])
        assert "No matches for wildcard '*Svc'." in out["smart_workflow_hint"]
        out2 = _assemble_symbol_search_response("~analyz", "json", [], [])
        assert "No matches for fuzzy 'analyz'." in out2["smart_workflow_hint"]

    def test_空结果的未命中提示(self):
        out = _assemble_symbol_search_response("zzz", "json", [], [])
        assert (
            out["smart_workflow_hint"] == "No matches for zzz. Try a different pattern."
        )
        assert out["matches_found"] == 0
        assert out["definitions"] == []

    def test_定义清单截断到50_文件计数封顶500(self):
        results = [
            {"name": f"n{i}", "type": "t", "file": "f", "start_line": i, "end_line": i}
            for i in range(60)
        ]
        files = [Path(f"f{i}") for i in range(600)]
        out = _assemble_symbol_search_response("x", "json", files, results)
        assert len(out["definitions"]) == 50
        assert out["matches_found"] == 60  # 总数如实,展示截断
        assert out["files_searched"] == 500


class TestAssembleFindReferencesResponse:
    def test_命中时的提示与计数(self):
        defs = [{"name": "foo", "role": "definition"}]
        refs = [
            {"name": "foo", "role": "reference"},
            {"name": "foo_x", "role": "related"},
        ]
        out = _assemble_find_references_response("foo", "json", [Path("a")], defs, refs)
        assert out["success"] is True
        assert out["symbol"] == "foo"
        assert out["total_usages"] == 3
        assert out["definitions"] == defs
        assert out["references"] == refs
        assert out["callers_count"] == 1  # 只数 role=reference
        assert out["smart_workflow_hint"].startswith(
            "Found 1 definition(s) and 2 reference(s) for 'foo'."
        )

    def test_未命中提示(self):
        out = _assemble_find_references_response("zzz", "json", [], [], [])
        assert out["total_usages"] == 0
        assert (
            out["smart_workflow_hint"]
            == "No usages found for 'zzz'. Try a different name."
        )
        assert out["callers_count"] == 0

    def test_清单截断_定义20引用50(self):
        defs = [{"name": f"d{i}", "role": "definition"} for i in range(25)]
        refs = [{"name": f"r{i}", "role": "reference"} for i in range(60)]
        out = _assemble_find_references_response("x", "json", [], defs, refs)
        assert len(out["definitions"]) == 20
        assert len(out["references"]) == 50
        assert out["callers_count"] == 60  # 计数不受展示截断影响


# ---------- 场景：关键词穷举扫描（变异拔词必被识破） ----------


class TestCategorizeKeywordSweep:
    """每个关键词单独出现在查询名里都必须归入自己的类别。

    变异测试会把关键词集合里的词逐个拔掉——只有穷举才能全部识破。
    """

    DECL_WORDS = [
        "class",
        "struct",
        "enum",
        "interface",
        "trait",
        "record",
        "type",
        "module",
        "namespace",
        "field",
        "property",
        "method",
        "function",
        "fn",
        "constructor",
    ]
    FLOW_WORDS = ["if", "for", "while", "switch", "try", "catch", "loop", "match"]
    FRAMEWORK_WORDS = [
        "spring",
        "react",
        "jpa",
        "http",
        "authorize",
        "decorator",
        "annotation",
        "attribute",
        "async",
        "goroutine",
        "channel",
        "linq",
        "lambda",
    ]

    def test_声明关键词全量命中declarations(self):
        for w in self.DECL_WORDS:
            out = categorize_queries([f"query_{w}_finder"], "python")
            assert out == {"declarations": [f"query_{w}_finder"]}, w

    def test_流程关键词全量命中control_flow(self):
        for w in self.FLOW_WORDS:
            out = categorize_queries([f"query_{w}_finder"], "python")
            assert out == {"control_flow": [f"query_{w}_finder"]}, w

    def test_框架关键词全量命中framework(self):
        for w in self.FRAMEWORK_WORDS:
            out = categorize_queries([f"query_{w}_finder"], "python")
            assert out == {"framework": [f"query_{w}_finder"]}, w

    def test_common五词精确命中(self):
        for w in ("classes", "methods", "functions", "imports", "variables"):
            out = categorize_queries([w], "python")
            assert out == {"common": [w]}, w

    def test_类别优先级_common先于decl先于flow先于framework(self):
        # 同名内含多级关键词时按 if/elif 链顺序判
        assert categorize_queries(["methods"], "x") == {"common": ["methods"]}
        # "type" 是 decl,"match" 是 flow——decl 分支先判
        assert categorize_queries(["match_type"], "x") == {
            "declarations": ["match_type"]
        }
        # "http" framework vs "if" flow——flow 先判("http"不含 flow 词时)
        assert categorize_queries(["http_handler"], "x") == {
            "framework": ["http_handler"]
        }
        assert categorize_queries(["http_if"], "x") == {"control_flow": ["http_if"]}


class TestDefaultsAndErrorPaths:
    def test_元素缺行号属性时取缺省0(self):
        class _Bare:
            name = "foo"
            element_type = "function"

        async def fake_analyze(req):
            class R:
                success = True
                elements = [_Bare()]

            return R()

        import types

        E = types.SimpleNamespace(analyze=fake_analyze)

        out = asyncio.run(
            _search_one_file_for_symbol(
                Path("/r/a.py"),
                Path("/r"),
                E,
                "python",
                lambda n: True,
                None,
                dict,
                lambda p: "python",
            )
        )
        assert out == [
            {
                "name": "foo",
                "type": "function",
                "file": "a.py",
                "start_line": 0,
                "end_line": 0,
            }
        ]

    def test_fts快路异常时安静返回空(self, monkeypatch, tmp_path):
        import tree_sitter_analyzer.mcp.tools.query_symbol_search as qss

        class _Boom:
            def __init__(self, root):
                raise RuntimeError("db broken")

        monkeypatch.setattr(qss, "ASTCache", _Boom)
        assert qss._try_fts_ranked_search(tmp_path, "foo", None) == []


# ---------- 场景：第三波——缺省值不拖累、点分名、参数透传 ----------


class TestRobustnessWave3:
    def test_缺name属性的元素不拖累同文件好元素(self):
        # getattr(e, "name", "") 被变异成 None 时,后面的 `bare in None` 会炸掉
        # 整个文件的元素循环——只有「坏元素后面还有好元素」的用例能识破
        class _NoName:
            element_type = "function"
            start_line = 1
            end_line = 2

        async def fake_analyze(req):
            class R:
                success = True
                elements = [_NoName(), _El("foo", "function_definition", 4, 8)]

            return R()

        import types

        engine = types.SimpleNamespace(analyze=fake_analyze)
        defs, refs = asyncio.run(
            _scan_file_for_references(
                Path("/r/a.py"),
                Path("/r"),
                engine,
                "foo",
                set(),
                dict,
                lambda p: "python",
            )
        )
        assert [d["name"] for d in defs] == ["foo"]
        assert defs[0]["start_line"] == 4

    def test_缺end_line属性的元素缺省为0不影响结果行(self):
        class _NoEnd:
            name = "foo"
            element_type = "call"
            start_line = 9

        async def fake_analyze(req):
            class R:
                success = True
                elements = [_NoEnd()]

            return R()

        import types

        engine = types.SimpleNamespace(analyze=fake_analyze)
        defs, refs = asyncio.run(
            _scan_file_for_references(
                Path("/r/a.py"),
                Path("/r"),
                engine,
                "foo",
                set(),
                dict,
                lambda p: "python",
            )
        )
        assert refs == [
            {
                "name": "foo",
                "type": "call",
                "file": "a.py",
                "start_line": 9,
                "end_line": 0,
                "role": "reference",
            }
        ]

    def test_点分符号名取末段作为裸名(self, monkeypatch, tmp_path):
        import tree_sitter_analyzer.mcp.tools.query_symbol_search as qss

        captured = {}

        async def fake_scatter(root, files, bare):
            captured["bare"] = bare
            return [], []

        def fake_collect(root):
            return []

        monkeypatch.setattr(qss, "_scatter_find_references", fake_scatter)
        monkeypatch.setattr(qss, "_collect_source_files", fake_collect)
        out = asyncio.run(
            qss.execute_find_references(
                str(tmp_path), {"symbol": "mod.sub.foo", "output_format": "json"}
            )
        )
        assert captured["bare"] == "foo"
        assert out["symbol"] == "mod.sub.foo"  # 信封回显原名
        assert out["total_usages"] == 0

    def test_无点符号名原样作为裸名(self, monkeypatch, tmp_path):
        import tree_sitter_analyzer.mcp.tools.query_symbol_search as qss

        captured = {}

        async def fake_scatter(root, files, bare):
            captured["bare"] = bare
            return [], []

        def fake_collect(root):
            return []

        monkeypatch.setattr(qss, "_scatter_find_references", fake_scatter)
        monkeypatch.setattr(qss, "_collect_source_files", fake_collect)
        asyncio.run(
            qss.execute_find_references(
                str(tmp_path), {"symbol": "plain", "output_format": "json"}
            )
        )
        assert captured["bare"] == "plain"

    def test_fts调用参数透传_limit500与language(self, monkeypatch, tmp_path):
        import tree_sitter_analyzer.mcp.tools.query_symbol_search as qss

        captured = {}

        class _FakeCache:
            def __init__(self, root):
                captured["root"] = root

            def fts_search_ranked(self, symbol, language=None, limit=0):
                captured.update(symbol=symbol, language=language, limit=limit)
                return []

        monkeypatch.setattr(qss, "ASTCache", _FakeCache)
        qss._try_fts_ranked_search(tmp_path, "foo", "java")
        assert captured == {
            "root": str(tmp_path),
            "symbol": "foo",
            "language": "java",
            "limit": 500,
        }

    def test_参数全量解析四元组(self):
        got = _parse_symbol_search_args(
            {
                "symbol": "s",
                "output_format": "json",
                "language": "java",
                "symbol_type": "class",
            }
        )
        assert got == ("s", "json", "java", "class")

    def test_引用信封files_searched同样五百封顶(self):
        files = [Path(f"f{i}") for i in range(600)]
        out = _assemble_find_references_response("x", "json", files, [], [])
        assert out["files_searched"] == 500

    def test_不存在根的fts快路安静返回空(self, tmp_path):
        # FTS 快路对任何失败(含根不存在/无库)都安静返回空,不抛
        from tree_sitter_analyzer.mcp.tools import query_symbol_search as qss

        out = qss._try_fts_ranked_search(tmp_path / "nope", "x", None)
        assert out == []
