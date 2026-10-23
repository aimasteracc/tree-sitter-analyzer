"""Ignore-rule matching shared by the filesystem discovery paths.

Discovery that honors ``.gitignore`` must draw the rules from one place: the
index paths and ``source_lines`` previously disagreed about which directories
are part of a project. A rule file applies to the directory that declares it
and to every directory below, and a later rule with an opinion overrides an
earlier one, which is what makes ``!`` negation work.
"""

from __future__ import annotations

import os
import re
import threading
from typing import cast

import pathspec

# Rule files honored per directory, in increasing precedence.
IGNORE_RULE_FILES = (".gitignore", ".ignore", ".rgignore")

# Collected rules: each entry pairs the directory that declared a rule file
# (relative to the walk root, "" for the root) with its compiled spec.
IgnoreRules = list[tuple[str, pathspec.GitIgnoreSpec]]


def load_ignore_rules(
    project_root: str,
    rel_dir: str,
    inherited: IgnoreRules,
) -> IgnoreRules:
    """Return ``inherited`` plus the ignore specs declared in ``rel_dir``.

    ``rel_dir`` is relative to ``project_root``; the empty string is the root.
    A symlinked or unreadable rule file is skipped rather than fatal, so
    discovery never fails because of an ignore file.
    """
    rules = list(inherited)
    base = os.path.join(project_root, rel_dir) if rel_dir else project_root
    for name in IGNORE_RULE_FILES:
        path = os.path.join(base, name)
        try:
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            spec = _compiled_spec(path)
        except OSError:
            continue
        rules.append((rel_dir, spec))
    return rules


#: #1737：规则文件内容 -> 编译后的规则。一次刷新要扫描源码树数次，每次都重新编译
#: 同一批规则文件；按内容（而非 stat）复用，任何改写都会换键重编。
_SPEC_CACHE: dict[tuple[str, str], pathspec.GitIgnoreSpec] = {}
_SPEC_LOCK = threading.Lock()
_SPEC_CACHE_LIMIT = 4096


def _compiled_spec(path: str) -> pathspec.GitIgnoreSpec:
    with open(path, encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    key = (path, text)
    with _SPEC_LOCK:
        cached = _SPEC_CACHE.get(key)
    if cached is not None:
        return cached
    spec = pathspec.GitIgnoreSpec.from_lines(text.splitlines())
    with _SPEC_LOCK:
        if len(_SPEC_CACHE) >= _SPEC_CACHE_LIMIT:
            _SPEC_CACHE.clear()
        _SPEC_CACHE[key] = spec
    return spec


_UNSET = object()
_NAMED_GROUP = re.compile(r"\(\?P<[A-Za-z_][A-Za-z0-9_]*>")


def _any_pattern(spec: pathspec.GitIgnoreSpec) -> re.Pattern[str] | None:
    """规则中任一模式的合并正则：不命中即可断定该规则对路径没有意见。

    命中时仍由 ``check_file`` 按 gitignore 的“最后一条有意见的规则生效”判定，
    合并正则只用来跳过绝大多数与任何模式都不相干的路径（#1737）。命名分组改为
    非捕获分组以便合并；无法合并时返回 ``None``（总是走 ``check_file``）。
    """
    cached = getattr(spec, "_tsa_any_pattern", _UNSET)
    if cached is not _UNSET:
        return cast("re.Pattern[str] | None", cached)
    parts = []
    combined: re.Pattern[str] | None
    try:
        for pattern in spec.patterns:
            regex = getattr(pattern, "regex", None)
            if getattr(pattern, "include", None) is None or regex is None:
                continue
            source = regex.pattern
            if not isinstance(source, str) or regex.flags & ~re.UNICODE:
                raise ValueError("unsupported pattern")
            parts.append("(?:" + _NAMED_GROUP.sub("(?:", source) + ")")
        combined = re.compile("|".join(parts)) if parts else re.compile(r"(?!)")
    except (re.error, ValueError, AttributeError):
        combined = None
    try:
        spec._tsa_any_pattern = combined  # type: ignore[attr-defined]
    except AttributeError:
        pass
    return combined


def is_gitignored(
    rel_path: str,
    rules: IgnoreRules,
    *,
    directory: bool,
) -> bool:
    """Whether ``rules`` exclude ``rel_path``; later specs override earlier ones.

    ``rel_path`` is relative to the same root the rules were collected from.
    ``directory`` appends the trailing slash gitignore patterns use to anchor a
    rule to directories.
    """
    ignored = False
    posix = rel_path.replace(os.sep, "/")
    for base, spec in rules:
        if base:
            prefix = base + "/"
            if not posix.startswith(prefix):
                continue
            target = posix[len(prefix) :]
        else:
            target = posix
        if not target:
            continue
        candidate = target + ("/" if directory else "")
        quick = _any_pattern(spec)
        if quick is not None and quick.search(candidate) is None:
            continue  # 没有任何模式命中：本规则对该路径没有意见
        result = spec.check_file(candidate)
        if result.include is not None:
            ignored = bool(result.include)
    return ignored
