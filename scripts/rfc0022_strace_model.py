#!/usr/bin/env python3
"""Shared immutable records for the RFC-0022 strace authority."""

from __future__ import annotations

from dataclasses import dataclass


class AuthorityError(RuntimeError):
    """The native authority could not prove a complete classification."""


@dataclass(frozen=True)
class TraceCall:
    timestamp: str
    pid: int
    line: int
    syscall: str
    arguments: tuple[str, ...]
    result: str


@dataclass(frozen=True)
class Violation:
    timestamp: str
    pid: int
    line: int
    syscall: str
    operation: str
    target: str
    result: str
    flags: str | None = None
