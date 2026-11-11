"""PR-2: Java annotations that provably register nothing.

The decorator gate (#1596 / #1623) treated every Java annotation as "may register",
so about a quarter of gson's methods (``@Override``, ``@SuppressWarnings``) could
never answer ``complete``. A few ``java.lang`` annotations are compile-time only:
they hand the method to nobody.

* ``@SuppressWarnings``, ``@Deprecated``, ``@SafeVarargs``, ``@FunctionalInterface``
  are exempt.
* ``@Override`` is exempt only when :func:`callers_java_overrides.override_proof`
  proves the overridden method is declared in the project and no call edge may
  dispatch to the target through a supertype. Otherwise the gate reports
  ``OVERRIDE_DISPATCH`` (not ``DECORATOR_MAY_REGISTER``: nothing is registered, the
  method is reached through its supertype).

A simple name is the ``java.lang`` annotation only when nothing can shadow it:
neither a project type of that name (same package, nested or imported) nor a
single-type import of it. Without the index nothing is exempt. Every other
annotation (``@Subscribe``, ``@Bean``, ``@Test``, ...) still blocks.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from .callers_java_overrides import OVERRIDE_REASON, override_proof

#: ``java.lang`` annotations with no runtime effect on who calls the method.
PASSIVE_ANNOTATIONS = frozenset(
    {"SuppressWarnings", "Deprecated", "SafeVarargs", "FunctionalInterface"}
)
OVERRIDE = "Override"
_JAVA_LANG = "java.lang."
_NAME = re.compile(r"^@\s*([\w.\s]+?)\s*(?:\(|$)")


@dataclass(frozen=True)
class JavaFinding:
    """An annotation that keeps the gate shut, with its reason and hint detail."""

    text: str
    override: bool
    detail: str = ""


def annotation_name(text: str) -> str | None:
    """``@java.lang.Override`` -> ``java.lang.Override``; None when not an annotation."""
    found = _NAME.match(text)
    return None if found is None else re.sub(r"\s+", "", found.group(1))


def java_findings(
    cache: Any,
    project_root: str,
    rel_path: str,
    text: str,
    line: int,
    bare: str | None,
    annotations: list[str],
) -> list[JavaFinding]:
    """Annotations on one Java declaration that keep the gate shut (source order)."""
    found: list[JavaFinding] = []
    for raw in annotations:
        simple = _java_lang_name(cache, text, annotation_name(raw))
        if simple in PASSIVE_ANNOTATIONS:
            continue
        if simple == OVERRIDE and bare:
            proof = override_proof(cache, project_root, rel_path, text, line, bare)
            if not proof.proved:
                found.append(JavaFinding(raw, True, proof.detail))
            continue
        found.append(JavaFinding(raw, False))
    return found


def _java_lang_name(cache: Any, text: str, name: str | None) -> str | None:
    """The ``java.lang`` simple name the annotation provably denotes, else None."""
    if name is None or cache is None:
        return None
    if name.startswith(_JAVA_LANG):
        simple = name[len(_JAVA_LANG) :]
        return simple if "." not in simple else None
    if "." in name or name not in PASSIVE_ANNOTATIONS | {OVERRIDE}:
        return None
    if re.search(
        r"^\s*import\s+(?:static\s+)?[\w.]+\." + re.escape(name) + r"\s*;", text, re.M
    ):
        return None
    try:
        shadowing = (
            cache.get_conn()
            .execute(
                "SELECT 1 FROM ast_symbol_rows WHERE name = ? AND kind = 'class' "
                "AND language = 'java' LIMIT 1",
                (name,),
            )
            .fetchone()
        )
    except (sqlite3.Error, AttributeError):
        return None
    return None if shadowing else name


__all__ = [
    "OVERRIDE",
    "OVERRIDE_REASON",
    "PASSIVE_ANNOTATIONS",
    "JavaFinding",
    "annotation_name",
    "java_findings",
]
