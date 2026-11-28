"""RFC-0042: resident state for ``nav callers`` in a long-running MCP server.

Phase 1 (:mod:`.loader`) moves *when* today's work is done: right after the
MCP ``initialize`` answer, a background thread takes the certified snapshot
lease and builds the call graph with the same code a first query runs, so the
first query reuses both. Nothing here changes how an answer is computed, and
nothing here is freshness evidence (RFC-0030): resident results are found only
through the keys today's caches already use (the certified snapshot identity
and the graph input digest), and any other state takes today's path.
"""
