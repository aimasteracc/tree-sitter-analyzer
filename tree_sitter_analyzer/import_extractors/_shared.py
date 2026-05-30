"""Shared utilities used across all language-specific import extractors."""

from typing import Any


def _node_text(node: Any, source: str) -> str:
    """Safely extract text from a Tree-sitter node.

    Perf history (2026-05-23): the previous implementation called
    ``source.encode('utf-8')`` TWICE per invocation (once for the
    length-check, once for the slice). Each call materializes the
    full UTF-8 byte representation of the entire file. Across 217k
    calls during one ``DependencyGraph.build()`` that added ~7.5s of
    pure encode overhead — making the test suite ~2× slower.

    Tree-sitter exposes ``node.text`` as ``bytes`` directly (the
    parser already holds the UTF-8 buffer internally), so we use
    that and decode just the slice. O(1) lookup + O(slice_len)
    decode, no per-call full-file encode.

    The ``source`` argument is kept for API compatibility and as a
    fallback when the parser binding doesn't expose ``text`` (older
    tree-sitter versions).
    """
    try:
        text_attr = getattr(node, "text", None)
        if isinstance(text_attr, bytes):
            return text_attr.decode("utf-8", errors="replace")
        if isinstance(text_attr, str):
            return text_attr
        # Fallback path — encode once, not twice.
        start = node.start_byte
        end = node.end_byte
        if start is not None and end is not None and start < end:
            encoded = source.encode("utf-8", errors="replace")
            if end <= len(encoded):
                return encoded[start:end].decode("utf-8", errors="replace")
        return ""
    except Exception:
        return ""
