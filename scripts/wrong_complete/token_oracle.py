"""Java / TypeScript / JavaScript 的 token 扫描判定器（``git grep -w`` 的结构化版本）。

只看纯文本：去掉注释与字符串后，找出每个 ``name(`` / ``.name(`` /
``["name"](`` 调用 token，再按接收者做保守判定：

* ``this.`` / ``super.`` / 隐式 ``this``（Java 类体内的裸调用）→ 外层类；
* ``Cls.name(`` 且 ``Cls`` 是项目类 → 该类；
* 带声明类型的标识符（Java ``Type x``、TS ``x: Type``）与强制转型 ``((Type) x)`` → 该类型；
* TS / JS 的导入绑定（具名、改名、默认、命名空间，含一层以上的再导出）→ 目标文件；
* 其余接收者无法证明 → ``possible``。

类型命中目标类（或目标类的祖先且未被覆盖）→ ``target``；目标类是声明类型的子类 →
``possible``（虚分派，#1743）；无关的项目类型自己声明了同名方法、或项目外类型 →
``other``。定义行本身、注释与字符串里的出现不是调用点（已文档化的排除）。
"""

from __future__ import annotations

import re

from scripts.wrong_complete.sites import OTHER, POSSIBLE, TARGET, Site, Target
from scripts.wrong_complete.token_text import (
    ClassSpan,
    class_spans,
    code_view,
    enclosing_class,
    line_of,
)
from scripts.wrong_complete.ts_imports import ImportTable

#: 不约束成员的类型（TS ``any`` / ``unknown``、Java 原始类型参数等）：接收者等于未知。
_OPAQUE_TYPES = frozenset({"any", "unknown", "object", "T", "K", "V", "E"})
JAVA_SUFFIXES = (".java",)
JS_SUFFIXES = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
_IDENT = r"[A-Za-z_$][\w$]*"
_RESERVED = frozenset(
    {
        "if",
        "for",
        "while",
        "switch",
        "catch",
        "return",
        "function",
        "new",
        "typeof",
        "await",
        "throw",
        "else",
        "case",
        "yield",
    }
)


def family(path: str) -> tuple[str, ...] | None:
    """文件所属语言族的后缀元组；非 C 系返回 ``None``。"""
    if path.endswith(JAVA_SUFFIXES):
        return JAVA_SUFFIXES
    if path.endswith(JS_SUFFIXES) and not path.endswith(".d.ts"):
        return JS_SUFFIXES
    return None


class TokenCorpus:
    """一个语言族的全部文件的预处理结果（真实仓库扫描时跨目标复用）。"""

    def __init__(self, sources: dict[str, str], suffixes: tuple[str, ...]) -> None:
        self.java = suffixes == JAVA_SUFFIXES
        self.sources = {p: t for p, t in sources.items() if family(p) == suffixes}
        self.codes = {p: code_view(t) for p, t in self.sources.items()}
        self.spans = {p: class_spans(c) for p, c in self.codes.items()}
        self.classes: dict[str, list[tuple[str, ClassSpan]]] = {}
        for path, spans in self.spans.items():
            for span in spans:
                self.classes.setdefault(span.name, []).append((path, span))
        self.imports = ImportTable(self.codes, self.sources)


class TokenOracle:
    """对一个项目、一个目标给出 token 扫描判定结果。"""

    def __init__(self, corpus: TokenCorpus, target: Target) -> None:
        self.target = target
        self.java = corpus.java
        self.sources = corpus.sources
        self.codes = corpus.codes
        self.spans = corpus.spans
        self.classes = corpus.classes
        self.imports = corpus.imports
        self.def_lines = self._definition_lines()

    # ------------------------------------------------------------ 定义与继承
    def _definition_lines(self) -> set[tuple[str, int]]:
        """所有与目标同名的定义所在行（不是调用点）。"""
        name = re.escape(self.target.name.strip("\"'"))
        method_def = re.compile(
            r"(?m)^[ \t]*(?![ \t])(?!(?:return|throw|new|else|await|yield|case|export\s+default)\b)"
            r"(?:@[\w.]+(?:\([^)]*\))?\s+)*(?P<prefix>(?:[\w$<>\[\],.?&| ]+\s+)?)"
            rf"(?P<name>[\"']{name}[\"']|(?<![\w$.]){name})\s*(?:<[^>()]*>)?\s*\([^;{{}}]*?\)\s*"
            r"(?P<ret>:\s*[^={;]+)?(?:throws\s+[\w.$,\s]+)?\s*(?P<end>[{;])"
        )
        func_def = re.compile(
            rf"\bfunction\s*\*?\s*{name}\s*[<(]"
            rf"|\b(?:const|let|var)\s+{name}\s*(?::[^=]+)?=\s*(?:async\s+)?(?:function\b|\(|{_IDENT}\s*=>)"
        )
        found: set[tuple[str, int]] = set()
        for path, text in self.sources.items():
            code = self.codes[path]
            for match in method_def.finditer(text):
                in_code = code[match.end() - 1] == text[match.end() - 1]
                declared = (
                    match.group("end") == "{"
                    or match.group("prefix").strip()
                    or match.group("ret")
                )
                if in_code and declared:
                    found.add((path, line_of(text, match.start("name"))))
            for match in func_def.finditer(code):
                found.add((path, line_of(code, match.start())))
        return found

    def _declares(self, cls: str) -> bool:
        name = self.target.name.strip("\"'")
        pattern = re.compile(
            rf"(?:[\"']{re.escape(name)}[\"']|(?<![\w$.]){re.escape(name)})\s*(?:<[^>()]*>)?\s*\("
        )
        for path, span in self.classes.get(cls, []):
            body = self.sources[path][span.start : span.end]
            for match in pattern.finditer(body):
                if (
                    path,
                    line_of(self.sources[path], span.start + match.start()),
                ) in self.def_lines:
                    return True
        return False

    def _ancestors(self, cls: str) -> list[str]:
        """``cls`` 及其项目内祖先（广度优先、去重）。"""
        order = [cls]
        for current in order:
            for _path, span in self.classes.get(current, []):
                for sup in span.supers:
                    if sup not in order:
                        order.append(sup)
            if len(order) > 64:
                break
        return order

    def _external_ancestor(self, cls: str) -> bool:
        return any(name not in self.classes for name in self._ancestors(cls)[1:])

    # ------------------------------------------------------------ 判定
    def classify_type(self, cls: str, dispatch: bool, reason: str) -> tuple[str, str]:
        """接收者类型为 ``cls`` 时的判定；``dispatch`` 表示可能是子类实例。"""
        owner = self.target.owner
        if cls in _OPAQUE_TYPES:
            return POSSIBLE, "opaque_type"
        if cls not in self.classes:
            return OTHER, "external_type"
        for klass in self._ancestors(cls):
            if klass in self.classes and self._declares(klass):
                if klass == owner:
                    return TARGET, reason
                break
        if (
            dispatch
            and owner is not None
            and cls in self._ancestors(owner)
            and cls != owner
        ):
            return POSSIBLE, "override_dispatch"
        if self._external_ancestor(cls):
            return POSSIBLE, "unknown_base"
        return OTHER, f"{reason}_other"

    def run(self) -> list[Site]:
        """扫描全部同族文件。"""
        name = self.target.name.strip("\"'")
        call = re.compile(rf"(?<![\w$]){re.escape(name)}\s*(?:<[^<>()]*>)?\s*\(")
        element = re.compile(rf"\[\s*([\"'`]){re.escape(name)}\1\s*\]\s*\(")
        sites: dict[tuple[str, int], Site] = {}
        for path, text in self.sources.items():
            code = self.codes[path]
            hits = [(m.start(), False) for m in call.finditer(code)]
            hits += [
                (m.start(), True)
                for m in element.finditer(text)
                if code[m.start()] == "["
            ]
            for start, element_access in hits:
                line = line_of(text, start)
                if (path, line) in self.def_lines or _is_construction(code, start):
                    continue
                verdict, reason = self._classify(path, code, start, element_access)
                sites[(path, line)] = Site(path, line, "call", verdict, reason, "")
            for alias_site in self.imports.alias_calls(path, self.target, self.java):
                sites.setdefault(alias_site.key(), alias_site)
        return sorted(sites.values(), key=lambda s: (s.file, s.line))

    def _classify(
        self, path: str, code: str, at: int, element_access: bool
    ) -> tuple[str, str]:
        before = code[:at].rstrip()
        if element_access:
            receiver = before
        elif before.endswith((".", "?.")):
            receiver = (before[:-2] if before.endswith("?.") else before[:-1]).rstrip()
        else:
            return self._classify_bare(path, code, at)
        span = enclosing_class(self.spans[path], at)
        if re.search(r"(?<![\w$])this\s*$", receiver):
            return self._classify_this(span, "this")
        if re.search(r"(?<![\w$])super\s*$", receiver):
            if span is None or not span.supers:
                return POSSIBLE, "super_unknown"
            return self.classify_type(span.supers[0], False, "super")
        cast = re.search(
            rf"\(\s*\(\s*({_IDENT})(?:<[^()]*>)?\s*\)\s*{_IDENT}\s*\)\s*$", receiver
        )
        if cast:
            return self.classify_type(cast.group(1), True, "cast")
        ident = re.search(rf"(?<![\w$.])({_IDENT})\s*$", receiver)
        if ident is None:
            return POSSIBLE, "unresolved_receiver"
        head = ident.group(1)
        namespace = self.imports.namespace_target(path, head, self.target)
        if namespace is not None:
            return namespace
        if head in self.classes and head[:1].isupper():
            return self.classify_type(head, False, "class_object")
        declared = _declared_type(code, head, at, self.java)
        if declared is not None:
            return self.classify_type(declared, True, "declared")
        return POSSIBLE, "unresolved_receiver"

    def _classify_this(self, span: ClassSpan | None, reason: str) -> tuple[str, str]:
        if span is None:
            return POSSIBLE, "this_outside_class"
        return self.classify_type(span.name, True, reason)

    def _classify_bare(self, path: str, code: str, at: int) -> tuple[str, str]:
        if self.java:
            return self._classify_this(
                enclosing_class(self.spans[path], at), "implicit_this"
            )
        bound = self.imports.bare_target(path, self.target.name, self.target)
        if bound is not None:
            return bound
        if self.target.owner is None and path == self.target.file:
            return TARGET, "same_file_function"
        if self.target.owner is None:
            return POSSIBLE, "unbound_function_call"
        return OTHER, "bare_call_cannot_reach_method"


def _is_construction(code: str, start: int) -> bool:
    return bool(re.search(r"\bnew\s+$", code[:start]))


def _declared_type(code: str, ident: str, before: int, java: bool) -> str | None:
    """``ident`` 的声明类型名（Java ``T x`` / TS ``x: T``）。

    取 ``before`` 之前最近的一次声明；没有时取之后的第一次（Java 字段可声明在方法之后）。
    """
    if java:
        pattern = rf"(?<![\w$.])({_IDENT})(?:<[^;(){{}}]*>)?(?:\[\])*\s+{re.escape(ident)}\s*[;=,)]"
    else:
        pattern = rf"(?<![\w$.]){re.escape(ident)}\s*\??:\s*({_IDENT})(?:<[^;(){{}}]*>)?\s*[;=,)]"
    matches = [m for m in re.finditer(pattern, code) if m.group(1) not in _RESERVED]
    earlier = [m for m in matches if m.start() < before]
    chosen = earlier[-1] if earlier else (matches[0] if matches else None)
    return chosen.group(1) if chosen else None


def token_sites(sources: dict[str, str], target: Target) -> list[Site]:
    """便捷入口：源码字典 + 目标 → 判定结果。"""
    corpus = TokenCorpus(sources, family(target.file) or JAVA_SUFFIXES)
    return TokenOracle(corpus, target).run()
